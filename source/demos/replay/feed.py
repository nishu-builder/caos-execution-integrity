"""Disposable external policy service; host-mounted policy can change between calls."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path

events = []


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/rule":
            value = Path("/data/policy").read_text()
            events.append({"sequence": len(events) + 1, "value": value.strip()})
            payload = value.encode()
        elif self.path == "/events":
            payload = json.dumps(events).encode()
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
