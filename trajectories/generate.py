#!/usr/bin/env python3
"""Generate new real multiagent runs using a supplied CAOS checkout, stack and API key."""
import argparse
import json
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent

def run(args,cwd,**kw):
    return subprocess.run(args,cwd=cwd,check=True,**kw)

def git(repo,*args):
    return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--harness',required=True,type=Path,help='Existing CAOS checkout with compatible std/ workers')
    p.add_argument('--cli',required=True,type=Path)
    p.add_argument('--server',required=True)
    p.add_argument('--key-file',required=True,type=Path)
    p.add_argument('--workdir',required=True,type=Path,help='New, isolated directory; existing directories are refused')
    p.add_argument('--model',default=None)
    p.add_argument('--only',choices=['cleanup','repair','all'],default='all')
    args=p.parse_args()
    root=args.workdir.resolve();root.mkdir(parents=True,exist_ok=False)
    config=json.loads((HERE/'example-prompts.json').read_text())
    run(['git','clone','--no-hardlinks',str(args.harness.resolve()),str(root/'harness')],HERE)
    harness=root/'harness';git(harness,'switch','-c','codex/trajectory-generation-'+secrets.token_hex(4))
    git(harness,'remote','add','caos',args.server)
    store=harness/'.caos-secrets';store.mkdir(mode=0o700)
    key=store/'.anthropic-api-key-value';key.write_bytes(args.key_file.read_bytes().strip());key.chmod(0o600)
    entry=store/'anthropic-api-key'
    entry.write_text('name=anthropic-api-key\nvalue:@=.anthropic-api-key-value\nreader=std/llm-step\nreader=std/llm-call\nentropy='+secrets.token_hex(32)+'\n');entry.chmod(0o600)
    # Local exclusion, independent of the supplied checkout's ignore rules.
    with (harness/'.git/info/exclude').open('a') as f: f.write('\n.caos-secrets/\n')
    fixture=root/'fixture';shutil.copytree(HERE/'fixture',fixture)
    git(fixture,'init','-b','main');git(fixture,'config','user.name','CAOS trajectory examples');git(fixture,'config','user.email','examples@example.invalid')
    git(fixture,'add','.');git(fixture,'commit','-m','Seed agent trajectory examples');base=git(fixture,'rev-parse','HEAD')
    git(harness,'fetch',str(fixture),'main')
    runtime=git(harness,'rev-parse','HEAD');prefix='trajectory-'+secrets.token_hex(5)
    rows=[]
    scenarios=[('cleanup','cleanup-investigation','A declined change, then an independent review'),('repair','delegated-test-repair','Passing tests after removing a test')]
    for slug,prompt_key,title in scenarios:
        if args.only not in ('all',slug): continue
        name=prefix+'-'+slug
        common=[str(args.cli.resolve()),'chat',name,'--llm-step:@=std/llm-step','--llm-call:@=std/llm-call','--username','trajectory-demo']
        if args.model: common+=['--model',args.model]
        commands=[common+['--base',base,'--source-tree','main','-m',config['prompts'][prompt_key]]]
        if slug=='cleanup': commands.append(common+['-m',config['cleanup_followup']])
        for n,cmd in enumerate(commands):
            with (root/f'{slug}-{n}.log').open('w') as log: run(cmd,harness,stdout=log,stderr=subprocess.STDOUT)
        ref='refs/caos/v3/conversations/'+name.encode().hex()+'/head'
        head=git(harness,'ls-remote','caos',ref).split()[0]
        run([sys.executable,str(HERE/'export.py'),'--server',args.server,'--head',head,'--id',slug,'--title',title,'--description','New real model run of a deliberately staged example; inspect its actual outcome.','--runtime',runtime,'--output',str(root/'data'),'--forbid-file',str(key)],root)
        rows.append({'id':slug,'title':title,'head':head})
    (root/'data/index.json').write_text(json.dumps({'examples':rows},indent=2)+'\n')
    print('Captured runs:',root/'data')
    print('Credentials remain only in the ignored harness/.caos-secrets directory.')

if __name__=='__main__': main()
