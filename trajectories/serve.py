#!/usr/bin/env python3
"""Serve the trajectory browser locally and read runs from CAOS or Git remotes."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, urlencode

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('trajectory_export', HERE / 'export.py')
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


class GitObjects(export.Objects):
    """Fetch into our own bare repository; never check out or execute fetched code."""
    def __init__(self, remote, destination):
        super().__init__('', destination)
        self.remote = remote
        self.repo = Path(destination).parent / 'git'
        self.git('init', '--bare', '--quiet', str(self.repo), repo=False)

    def git(self, *args, repo=True, check=True):
        env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_LFS_SKIP_SMUDGE='1')
        cmd = ['git', '-c', 'protocol.ext.allow=never', '-c', 'gc.auto=0']
        if repo:
            cmd += ['--git-dir', str(self.repo)]
        result = subprocess.run(cmd + list(args), capture_output=True, timeout=120, env=env)
        if check and result.returncode:
            # Keep credential-bearing remote URLs and transport diagnostics out of the page.
            raise ValueError('Git could not read the requested object. Check the remote, Git credentials, and whether it permits fetching this hash.')
        return result

    def fetch_raw(self, oid):
        probe = self.git('cat-file', '-t', oid, check=False)
        if probe.returncode:
            self.git('fetch', '--quiet', '--no-tags', '--no-write-fetch-head', '--', self.remote, oid)
            probe = self.git('cat-file', '-t', oid)
        kind = probe.stdout.strip().decode('ascii')
        size = int(self.git('cat-file', '-s', oid).stdout)
        if size > 32 * 1024 * 1024:
            raise ValueError('Object exceeds 32 MiB inspection limit: ' + oid)
        content = self.git('cat-file', kind, oid).stdout
        return f'{kind} {len(content)}\0'.encode() + content


class ViewerServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, port, cache):
        super().__init__(('127.0.0.1', port), Handler)
        self.cache = Path(cache)
        self.loads = threading.BoundedSemaphore(2)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE.parent / 'docs'), **kwargs)

    def log_message(self, fmt, *args):
        pass  # Do not put private remote URLs or conversation text in access logs.

    def valid_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

    def json_response(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if not self.valid_host():
            return self.json_response(403, {'error': 'Use the loopback viewer URL.'})
        path = urlsplit(self.path).path
        if path == '/api/viewer':
            return self.json_response(200, {'version': 1})
        if path.startswith('/captures/'):
            parts = path.split('/')
            if len(parts) != 5 or parts[3] != 'objects' or not export.OID.fullmatch(parts[4]) or len(parts[2]) != 32 or any(c not in '0123456789abcdef' for c in parts[2]):
                return self.send_error(404)
            target = self.server.cache / parts[2] / 'objects' / parts[4]
            if not target.is_file():
                return self.send_error(404)
            raw = target.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Disposition', f'attachment; filename="{parts[4]}.git-object"')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(raw)
            return
        return super().do_GET()

    def do_POST(self):
        # No CORS: other websites cannot drive this user's authenticated Git client.
        origin = self.headers.get('Origin')
        if not self.valid_host() or (origin and origin != 'http://' + self.headers['Host']):
            return self.json_response(403, {'error': 'Open this viewer locally to load a run.'})
        if self.path != '/api/load':
            return self.send_error(404)
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.json_response(415, {'error': 'Expected JSON.'})
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 16384:
                raise ValueError('Invalid request size.')
            request = json.loads(self.rfile.read(length))
            head, source, kind = request['head'], request['source'], request['kind']
            if not isinstance(head, str) or not export.OID.fullmatch(head):
                raise ValueError('Enter a full 40-character conversation commit hash.')
            if not isinstance(source, str) or not source or source.startswith('-') or '\0' in source:
                raise ValueError('Enter a server URL or Git remote.')
            if kind not in ('server', 'remote'):
                raise ValueError('Choose a CAOS server or Git remote.')
            if kind == 'server':
                url = urlsplit(source)
                if url.scheme not in ('http', 'https') or not url.netloc or url.username or url.password or url.query or url.fragment:
                    raise ValueError('Use an HTTP(S) server URL without credentials, query, or fragment.')
            if not self.server.loads.acquire(blocking=False):
                return self.json_response(429, {'error': 'Two runs are already loading. Try again shortly.'})
            try:
                token = secrets.token_hex(16)
                directory = self.server.cache / token
                objects = (export.Objects(source, directory / 'objects') if kind == 'server' else GitObjects(source, directory / 'objects'))
                data = export.Exporter(objects).export(head, 'live', 'Loaded conversation', '', 'not supplied')
                root = next(c for c in data['conversations'] if c['id'] == data['root'])
                data['title'] = root['title']
                data['description'] = 'Loaded from ' + source + ' at ' + head + '. Child conversations follow the heads recorded at this commit.'
                data['object_base'] = '/captures/' + token + '/objects/'
                return self.json_response(200, data)
            finally:
                self.server.loads.release()
        except (ValueError, KeyError, TypeError) as e:
            return self.json_response(400, {'error': str(e)})
        except Exception:
            return self.json_response(502, {'error': 'Could not read this conversation. Check connectivity, access, and that the remote holds its referenced objects. This viewer supports CAOS chat v3 records.'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--server', help='CAOS HTTP object server')
    group.add_argument('--remote', help='Git remote URL or local repository path')
    parser.add_argument('--head', help='Full conversation commit hash')
    parser.add_argument('--port', type=int, default=18184)
    args = parser.parse_args()
    if bool(args.head) != bool(args.server or args.remote):
        parser.error('Supply --head together with --server or --remote, or start without either.')
    if args.head and not export.OID.fullmatch(args.head):
        parser.error('--head must be a full 40-character commit hash')
    with tempfile.TemporaryDirectory(prefix='caos-viewer-') as cache:
        server = ViewerServer(args.port, cache)
        query = urlencode({('server' if args.server else 'remote'): args.server or args.remote, 'head': args.head, 'reader': 'local'}) if args.head else ''
        print(f'Open http://127.0.0.1:{server.server_port}/trajectories/' + ('?' + query if query else ''), flush=True)
        print('Read-only viewer. Captures are temporary and removed when it stops.', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == '__main__':
    main()
