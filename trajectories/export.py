#!/usr/bin/env python3
"""Export selected CAOS conversations into a static, inspectable evidence browser."""
import argparse
import difflib
import hashlib
import json
import re
import urllib.request
from pathlib import Path

OID = re.compile(r'^[0-9a-f]{40}$')

class Objects:
    def __init__(self, server, destination, forbidden=()):
        self.server = server.rstrip('/')
        self.destination = Path(destination)
        self.destination.mkdir(parents=True, exist_ok=True)
        self.forbidden = forbidden
        self.cache = {}

    def fetch_raw(self, oid):
        with urllib.request.urlopen(self.server + '/object/' + oid, timeout=45) as response:
            return response.read(32 * 1024 * 1024 + 1)

    def get(self, oid):
        if not OID.fullmatch(oid):
            raise ValueError('Invalid Git object identity: ' + str(oid))
        if oid in self.cache:
            return self.cache[oid]
        target = self.destination / oid
        if target.exists():
            raw = target.read_bytes()
        else:
            raw = self.fetch_raw(oid)
        if len(raw) > 32 * 1024 * 1024:
            raise ValueError('Object exceeds export size bound: ' + oid)
        if hashlib.sha1(raw).hexdigest() != oid:
            raise ValueError('Git object hash mismatch: ' + oid)
        header, data = raw.split(b'\0', 1)
        kind, size = header.decode('ascii').split(' ')
        if len(data) != int(size):
            raise ValueError('Object length mismatch: ' + oid)
        if any(secret and secret in raw for secret in self.forbidden):
            raise ValueError('Credential found in captured object; export refused: ' + oid)
        target.write_bytes(raw)
        self.cache[oid] = kind, data
        return kind, data

    def tree(self, oid):
        kind, data = self.get(oid)
        if kind != 'tree':
            raise ValueError('Expected tree: ' + oid)
        entries = []
        while data:
            header, data = data.split(b'\0', 1)
            mode, name = header.split(b' ', 1)
            entries.append({'mode': mode.decode(), 'name': name.decode('utf8', 'surrogateescape'), 'oid': data[:20].hex()})
            data = data[20:]
        return entries

    def commit(self, oid):
        kind, data = self.get(oid)
        if kind != 'commit':
            raise ValueError('Expected commit: ' + oid)
        headers, message = data.split(b'\n\n', 1)
        fields = {}
        for line in headers.decode().splitlines():
            key, _, value = line.partition(' ')
            fields.setdefault(key, []).append(value)
        text = message.decode()
        event_kind, sep, body = text.partition('\n\n')
        events = json.loads(body)['events'] if sep and body.strip().startswith('{') and '"events"' in body else []
        return {'oid': oid, 'tree': fields['tree'][0], 'parents': fields.get('parent', []), 'kind': event_kind.strip(), 'events': events, 'message': text}

    def at(self, tree, path):
        for part in path.split('/'):
            entry = next((e for e in self.tree(tree) if e['name'] == part), None)
            if entry is None:
                return None
            tree = entry['oid']
        return tree

class Exporter:
    def __init__(self, objects):
        self.o = objects
        self.blobs = {}
        self.snapshots = {}
        self.requests = {}
        self.conversations = {}
        self.source_commits = {}

    def blob(self, oid):
        if oid not in self.blobs:
            kind, data = self.o.get(oid)
            if kind != 'blob':
                raise ValueError('Expected blob: ' + oid)
            try:
                text = data.decode('utf8')
                binary = '\0' in text
            except UnicodeDecodeError:
                binary, text = True, None
            self.blobs[oid] = {'size': len(data), 'binary': binary, 'text': text if not binary else None}
        return self.blobs[oid]

    def snapshot(self, tree):
        if tree in self.snapshots:
            return self.snapshots[tree]
        files, sources = {}, {}
        def walk(oid, prefix='', depth=0):
            if depth > 32:
                raise ValueError('Excessive tree nesting')
            for entry in self.o.tree(oid):
                path = prefix + entry['name']
                if not prefix and entry['name'] == '.caos':
                    continue
                mode, child = entry['mode'], entry['oid']
                if mode == '40000':
                    walk(child, path + '/', depth + 1)
                elif mode == '160000':
                    c = self.o.commit(child)
                    sources[path] = child
                    self.source_commits[child] = {k: c[k] for k in ('oid','tree','parents','message')}
                    walk(c['tree'], path + '/', depth + 1)
                else:
                    self.blob(child)
                    files[path] = {'oid': child, 'mode': mode}
        walk(tree)
        self.snapshots[tree] = {'files': files, 'sources': sources}
        return self.snapshots[tree]

    def transcript(self, tree):
        root = self.o.at(tree, '.caos/transcript')
        if not root:
            return []
        entries = []
        def walk(oid):
            for e in self.o.tree(oid):
                if e['mode'] == '40000':
                    continue
                else:
                    value = json.loads(self.blob(e['oid'])['text'])
                    entries.append((e['name'], value))
        walk(root)
        return [value for _, value in sorted(entries)]

    def payload(self, tree, path, payloads):
        if isinstance(path, dict):
            path = path.get('path')
        if not path:
            return None
        data = payloads.get(path)
        if data is None:
            oid = self.o.at(tree, path)
            if oid:
                data = self.o.get(oid)[1]
        if data is None:
            return {'missing': path}
        try:
            return json.loads(data)
        except (ValueError, UnicodeDecodeError):
            return data.decode('utf8', 'replace')

    def request(self, oid):
        if oid in self.requests:
            return
        rows = []
        for entry in self.o.tree(oid):
            row = dict(entry)
            if entry['mode'] not in ('40000', '160000'):
                row.update(self.blob(entry['oid']))
            elif entry['name'] in ('in', 'head'):
                kind, _ = self.o.get(entry['oid'])
                tree = self.o.commit(entry['oid'])['tree'] if kind == 'commit' else entry['oid']
                row['snapshot'] = tree
                self.snapshot(tree)
            rows.append(row)
        self.requests[oid] = {'oid': oid, 'entries': rows, 'image_contents_included': False}

    def diff(self, before, after):
        a = self.snapshots[before]['files'] if before else {}
        b = self.snapshots[after]['files']
        result = []
        for path in sorted(a.keys() | b.keys()):
            if a.get(path) == b.get(path):
                continue
            old, new = a.get(path), b.get(path)
            oldblob = self.blobs[old['oid']] if old else {'text': ''}
            newblob = self.blobs[new['oid']] if new else {'text': ''}
            patch = None
            if oldblob.get('text') is not None and newblob.get('text') is not None:
                patch = ''.join(difflib.unified_diff(oldblob['text'].splitlines(True), newblob['text'].splitlines(True), fromfile='before/'+path, tofile='after/'+path))
            result.append({'path': path, 'before': old, 'after': new, 'patch': patch})
        return result

    def conversation(self, head):
        identity_oid = self.o.at(self.o.commit(head)['tree'], '.caos/identity.json')
        if not identity_oid:
            raise ValueError('This is not a CAOS conversation commit. Use the conversation head, not a source-code commit.')
        chain = []
        current = head
        while True:
            commit = self.o.commit(current)
            chain.append(commit)
            if commit['kind'] == 'conversation.root':
                break
            if len(commit['parents']) != 1:
                raise ValueError('Malformed conversation parent count at ' + current)
            current = commit['parents'][0]
        chain.reverse()
        root_tree = chain[-1]['tree']
        identity = json.loads(self.o.get(identity_oid)[1])
        cid = identity['id']
        if cid in self.conversations:
            return cid
        title = self.o.get(self.o.at(root_tree, '.caos/title'))[1].decode().strip()
        result = {'id': cid, 'title': title, 'head': head, 'identity': identity, 'events': [], 'children': []}
        self.conversations[cid] = result
        payloads, previous_tree, known_messages = {}, None, set()
        children = {}
        for ordinal, commit in enumerate(chain):
            tree = commit['tree']
            self.snapshot(tree)
            for event in commit['events']:
                if event['event'] == 'payload':
                    payloads[event['value']['path']] = bytes(event['value']['bytes'])
            messages = []
            for message in self.transcript(tree):
                mid = message['message_id']
                if mid in known_messages:
                    continue
                known_messages.add(mid)
                enriched = dict(message)
                enriched['blocks'] = []
                for block in message['blocks']:
                    block = dict(block)
                    if block.get('type') == 'tool_use' or 'arguments' in block:
                        block['resolved_arguments'] = self.payload(tree, block.get('arguments'), payloads)
                    enriched['blocks'].append(block)
                messages.append(enriched)
            records = []
            for event in commit['events']:
                kind, value = event['event'], event['value']
                if kind == 'payload':
                    continue
                record = {'type': kind, **value}
                if kind == 'tool':
                    outcome = value.get('result') or {}
                    record['observation'] = self.payload(tree, outcome.get('observation') or outcome.get('error'), payloads)
                    if value.get('task'):
                        self.request(value['task'])
                if kind == 'child':
                    children[value['id']] = value
                if kind == 'request':
                    self.request(value['id'])
                records.append(record)
            result['events'].append({'oid': commit['oid'], 'parent': commit['parents'][0] if commit['parents'] else None, 'kind': commit['kind'], 'ordinal': ordinal, 'tree': tree, 'before_tree': previous_tree, 'messages': messages, 'records': records, 'changes': self.diff(previous_tree, tree)})
            previous_tree = tree
        result['children'] = list(children.values())
        for child in children.values():
            self.conversation(child.get('terminal_head') or child['initial_head'])
        return cid

    def export(self, head, slug, title, description, runtime):
        root = self.conversation(head)
        return {'schema': 1, 'id': slug, 'title': title, 'description': description, 'root': root, 'runtime': runtime, 'conversations': list(self.conversations.values()), 'snapshots': self.snapshots, 'blobs': self.blobs, 'requests': self.requests, 'source_commits': self.source_commits, 'evidence': {'objects': sorted(self.o.cache), 'hash_algorithm': 'sha1', 'scope': 'Captured conversation records, workspace files and request arguments. Worker image closures are not included; this is an inspection package, not a standalone runtime.'}}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', required=True)
    parser.add_argument('--head', required=True)
    parser.add_argument('--id', required=True)
    parser.add_argument('--title', required=True)
    parser.add_argument('--description', required=True)
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--forbid-file', action='append', default=[])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    forbidden = [Path(p).read_bytes().strip() for p in args.forbid_file]
    o = Objects(args.server, args.output/'objects', forbidden)
    data = Exporter(o).export(args.head, args.id, args.title, args.description, args.runtime)
    out = args.output/(args.id+'.json')
    out.write_text(json.dumps(data, ensure_ascii=True, separators=(',',':'))+'\n')
    print(json.dumps({'file':str(out),'conversations':len(data['conversations']),'events':sum(len(c['events']) for c in data['conversations']),'objects':len(o.cache)}))

if __name__ == '__main__':
    main()
