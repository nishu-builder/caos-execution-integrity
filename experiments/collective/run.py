#!/usr/bin/env python3
"""Run the local METR-inspired studies as real CAOS conversations."""
import argparse
import json
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def call(args, cwd, **kwargs):
    return subprocess.run([str(a) for a in args], cwd=cwd, check=True, **kwargs)


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--harness', type=Path, required=True)
    p.add_argument('--cli', type=Path, required=True)
    p.add_argument('--server', required=True)
    p.add_argument('--key-file', type=Path, required=True)
    p.add_argument('--workdir', type=Path, required=True)
    p.add_argument('--model', default='claude-opus-4-8')
    p.add_argument('--only', choices=['collective', 'all'], default='collective')
    a = p.parse_args()
    root = a.workdir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    config = json.loads((HERE/'prompts.json').read_text())
    harness = root/'harness'
    call(['git', 'clone', '--quiet', '--no-hardlinks', a.harness.resolve(), harness], root)
    git(harness, 'switch', '-c', 'codex/metr-study-'+secrets.token_hex(5))
    git(harness, 'remote', 'add', 'caos', a.server)
    store = harness/'.caos-secrets'
    store.mkdir(mode=0o700)
    key = store/'.anthropic-api-key-value'
    key.write_bytes(a.key_file.read_bytes().strip())
    key.chmod(0o600)
    entry = store/'anthropic-api-key'
    entry.write_text('name=anthropic-api-key\nvalue:@=.anthropic-api-key-value\nreader=std/llm-step\nreader=std/llm-call\nentropy='+secrets.token_hex(32)+'\n')
    entry.chmod(0o600)
    with (harness/'.git/info/exclude').open('a') as f:
        f.write('\n.caos-secrets/\n')
    manifest = {'model': a.model, 'runtime': git(harness, 'rev-parse', 'HEAD'), 'cases': {}}
    prefix = 'metr-'+secrets.token_hex(5)
    for slug, case in config['cases'].items():
        if a.only not in ('all', slug):
            continue
        fixture = root/('fixture-'+slug)
        shutil.copytree(HERE/'fixture', fixture)
        git(fixture, 'init', '-b', 'main')
        git(fixture, 'config', 'user.name', 'CAOS experiment')
        git(fixture, 'config', 'user.email', 'experiments@example.invalid')
        git(fixture, 'add', '.')
        git(fixture, 'commit', '-m', 'Initial '+slug+' study')
        base = git(fixture, 'rev-parse', 'HEAD')
        git(harness, 'fetch', str(fixture), 'main')
        name = prefix+'-'+slug
        row = {'id': 'metr-'+slug, 'title': case['title'], 'conversation': name, 'base': base, 'stages': {}}
        manifest['cases'][slug] = row
        common = [a.cli.resolve(), 'chat', name, '--llm-step:@=std/llm-step', '--llm-call:@=std/llm-call', '--username', 'metr-study', '--model', a.model]
        for stage in ('setup', 'attack', 'review'):
            cmd = common + (['--base', base, '--source-tree', 'main'] if stage == 'setup' else []) + ['-m', case[stage]]
            print(slug, stage, 'starting', flush=True)
            with (root/(slug+'-'+stage+'.log')).open('w') as log:
                call(cmd, harness, stdout=log, stderr=subprocess.STDOUT)
            ref = 'refs/caos/v3/conversations/'+name.encode().hex()+'/head'
            head = git(harness, 'ls-remote', 'caos', ref).split()[0]
            row['stages'][stage] = head
            row['head'] = head
            (root/'run.json').write_text(json.dumps(manifest, indent=2)+'\n')
            call([sys.executable, REPO/'trajectories/export.py', '--server', a.server, '--head', head, '--id', row['id'], '--title', case['title'], '--description', 'Independent researchers share and replicate a method for two blocked tasks; inspect the actual execution history.', '--runtime', manifest['runtime'], '--output', root/'data', '--forbid-file', key], root)
            print(slug, stage, head, flush=True)
    (root/'data/index.json').write_text(json.dumps({'examples': [{'id': c['id'], 'title': c['title'], 'head': c['head']} for c in manifest['cases'].values()]}, indent=2)+'\n')
    print('Completed:', root/'run.json', flush=True)


if __name__ == '__main__':
    main()
