"""Local fixtures for lost responses and an explicitly scoped object gateway."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import json
import socket


class Ledger:
    def __init__(self):
        self.effects = {"unsafe": [], "safe": []}
        self.saved = {}
        self.dropped = set()
        self.events = []

    def post(self, mode, key, body):
        if mode not in self.effects or not key:
            return 400, "invalid request", False
        if mode == "safe" and key in self.saved:
            if self.saved[key] != body:
                self.events.append(dict(mode=mode, key=key, status=409, applied=False, dropped=False))
                return 409, "key already bound to another payload", False
            self.events.append(dict(mode=mode, key=key, status=200, applied=False, dropped=False))
            return 200, "already applied", False
        self.effects[mode].append({"key": key, "body": body})
        if mode == "safe":
            self.saved[key] = body
        occurrence = (mode, key)
        drop = occurrence not in self.dropped
        self.dropped.add(occurrence)
        self.events.append(dict(mode=mode, key=key, status=201, applied=True, dropped=drop))
        return 201, "applied", drop


def serve(config):
    ledger = Ledger()
    reads = []

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, text):
            body = text.encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/events":
                self.reply(200, json.dumps({"effects": ledger.effects, "events": ledger.events, "reads": reads}))
                return
            oid = self.path.removeprefix("/blob/")
            if self.path.startswith("/blob/") and oid in config.get("allowed", {}):
                reads.append({"oid": oid, "status": 200})
                self.reply(200, config["allowed"][oid])
            else:
                reads.append({"oid": oid, "status": 403})
                self.reply(403, "denied\n")

        def do_POST(self):
            count = int(self.headers.get("Content-Length", "0"))
            if not 0 <= count <= 4096:
                self.reply(400, "request too large")
                return
            body = self.rfile.read(count).decode()
            status, answer, drop = ledger.post(self.path.strip("/"), self.headers.get("Idempotency-Key", ""), body)
            if drop:
                # The effect is already in the ledger. Deliberately lose the reply.
                self.close_connection = True
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
            else:
                self.reply(status, answer + "\n")

        def log_message(self, *args):
            pass

    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()


if __name__ == "__main__":
    serve(json.loads(Path("/data/config.json").read_text()))
