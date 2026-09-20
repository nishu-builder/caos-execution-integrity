#!/usr/bin/env python3
"""Budgeted, text-only Anthropic gateway for this one fictional game."""
import argparse, hashlib, hmac, json, sqlite3, threading, time
import urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

class Budget:
    def __init__(self, path, cap, deadline, max_calls=300):
        self.path, self.cap, self.deadline, self.max_calls = str(path), cap, deadline, max_calls
        with self.db() as c:
            c.execute("CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY, hash TEXT, started REAL, status TEXT, reserved REAL, charged REAL, usage TEXT)")
    def db(self):
        return sqlite3.connect(self.path, timeout=30)
    def reserve(self, digest, amount):
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            spent, count = c.execute("SELECT COALESCE(SUM(charged),0), COUNT(*) FROM calls").fetchone()
            if time.time() >= self.deadline or count >= self.max_calls or spent + amount > self.cap:
                raise ValueError("Run budget, call limit or deadline reached")
            cur = c.execute("INSERT INTO calls(hash,started,status,reserved,charged) VALUES(?,?,?,?,?)", (digest,time.time(),"pending",amount,amount))
            return cur.lastrowid
    def settle(self, call, usage):
        required = ("input_tokens", "output_tokens")
        if not all(isinstance(usage.get(k),int) and usage[k] >= 0 for k in required):
            raise ValueError("Missing trustworthy usage; keep full reservation")
        # Charge all cache writes at the more expensive one-hour rate.
        charged = (usage["input_tokens"]*5 + usage["output_tokens"]*25
                   + usage.get("cache_creation_input_tokens",0)*10
                   + usage.get("cache_read_input_tokens",0)*0.5)/1_000_000
        with self.db() as c:
            reserved = c.execute("SELECT reserved FROM calls WHERE id=?",(call,)).fetchone()[0]
            c.execute("UPDATE calls SET status=?,charged=?,usage=? WHERE id=?",
                      ("complete" if charged <= reserved else "over-reservation",charged,json.dumps(usage),call))
        if charged > reserved:
            raise ValueError("Usage exceeded conservative reservation")
    def uncertain(self, call):
        with self.db() as c:
            c.execute("UPDATE calls SET status='uncertain' WHERE id=? AND status='pending'",(call,))
    def status(self):
        with self.db() as c:
            rows = c.execute("SELECT status,COUNT(*),SUM(charged) FROM calls GROUP BY status").fetchall()
        return {"cap_usd":self.cap,"deadline":self.deadline,"charged_usd":sum(r[2] for r in rows),
                "calls":sum(r[1] for r in rows),"by_status":rows}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--config",type=Path,required=True)
    a=p.parse_args()
    cfg=json.loads(a.config.read_text())
    token=Path(cfg["token_file"]).read_text().strip()
    key=Path(cfg["key_file"]).read_text().strip()
    budget=Budget(cfg["ledger"],cfg["cap_usd"],cfg["deadline"])
    stop=Path(cfg["stop_file"])
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def reply(self,status,value):
            raw=json.dumps(value).encode()
            self.send_response(status);self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(raw)));self.end_headers()
            self.wfile.write(raw)
        def authorized(self):
            return hmac.compare_digest(self.headers.get("x-api-key",""),token)
        def do_GET(self):
            if not self.authorized(): return self.reply(403,{"error":"Forbidden"})
            return self.reply(200,budget.status())
        def do_POST(self):
            if not self.authorized(): return self.reply(403,{"error":"Forbidden"})
            if self.path != "/v1/messages": return self.reply(404,{"error":"Unsupported endpoint"})
            if stop.exists(): return self.reply(400,{"error":"Run stopped"})
            call=None
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not 0 < length <= 2_000_000: raise ValueError("Invalid body size")
                raw=self.rfile.read(length)
                body=json.loads(raw)
                if body.get("model") != "claude-opus-4-8" or body.get("stream",False):
                    raise ValueError("Unexpected model or streaming request")
                if body.get("speed") == "fast": raise ValueError("Fast mode disabled")
                if any(t.get("type","custom") != "custom" for t in body.get("tools",[])):
                    raise ValueError("Server tools disabled")
                maximum=body.get("max_tokens")
                if type(maximum) is not int or not 0 < maximum <= 64000: raise ValueError("Invalid output bound")
                # Text-only inputs. No images, audio or paid server-side features.
                for message in body.get("messages",[]):
                    for block in message.get("content",[]) if isinstance(message.get("content"),list) else []:
                        if block.get("type") not in ("text","thinking","redacted_thinking"):
                            raise ValueError("Non-text message block")
                # This adapter exposes a text-only game, not the coding tool registry.
                original=raw
                body.pop("tools",None)
                body.pop("tool_choice",None)
                raw=json.dumps(body,separators=(",",":")).encode()
                reserve=(len(raw)+16384)*10/1_000_000 + maximum*25/1_000_000
                call=budget.reserve(hashlib.sha256(raw).hexdigest(),reserve)
                capture=Path(cfg["ledger"]).parent/"provider"/str(call)
                capture.mkdir(parents=True,exist_ok=False)
                (capture/"caos-request.json").write_bytes(original)
                (capture/"provider-request.json").write_bytes(raw)
                request=urllib.request.Request("https://api.anthropic.com/v1/messages",data=raw,headers={
                    "x-api-key":key,"anthropic-version":"2023-06-01","content-type":"application/json"})
                with urllib.request.urlopen(request,timeout=600) as response:
                    result=json.loads(response.read(8_000_000))
                (capture/"provider-response.json").write_text(json.dumps(result))
                budget.settle(call,result.get("usage",{}))
                # The game's action list is the only permitted action surface.
                # Refuse a model tool call before CAOS could execute it.
                if result.get("stop_reason") != "end_turn" or any(
                    b.get("type") == "tool_use" for b in result.get("content",[])):
                    raise ValueError("Only completed text replies are permitted in this game")
                return self.reply(200,result)
            except Exception as exc:
                if call is not None: budget.uncertain(call)
                # Do not forward provider bodies or credentials into model-visible errors.
                if isinstance(exc,ValueError): reason=str(exc)
                else: reason="Upstream request failed; reservation retained for uncertain billing"
                print(json.dumps({"time":time.time(),"call":call,"error":reason}),flush=True)
                return self.reply(400,{"type":"error","error":{"type":"invalid_request_error","message":reason}})
    print(json.dumps({"listening":cfg["bind"],"port":cfg["port"],"budget":budget.status()}),flush=True)
    ThreadingHTTPServer((cfg["bind"],cfg["port"]),Handler).serve_forever()

if __name__=="__main__": main()
