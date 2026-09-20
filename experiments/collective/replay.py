#!/usr/bin/env python3
"""Reproduce the saved method in fresh CAOS jobs, without another model call."""
import argparse
import importlib.util
import json
import secrets
import shutil
import subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
EVENT="e4346569b4c81557006a494f66bdf14acd113380"
CHILD="subagent-85fcfa5365a8985789f7310786cc705ef41ad536689b20b8d0556564be227aa0"


def capture_objects(server, result, directory):
    import hashlib
    import urllib.request
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    seen=set()
    def get(oid,recurse=False):
        if oid in seen:return
        with urllib.request.urlopen(server.rstrip("/")+"/object/"+oid,timeout=30) as response:
            raw=response.read(16*1024*1024+1)
        assert hashlib.sha1(raw).hexdigest()==oid
        header,body=raw.split(b"\0",1);kind,size=header.decode().split()
        assert len(body)==int(size)
        (directory/oid).write_bytes(raw);seen.add(oid)
        if recurse and kind=="tree":
            while body:
                _,body=body.split(b"\0",1);child,body=body[:20].hex(),body[20:];get(child,True)
    for job in result["jobs"].values():
        with urllib.request.urlopen(server.rstrip("/")+"/status/"+job["request"]+"?all=1",timeout=30) as response:
            job["trace"]=json.load(response)
        get(job["request"])
        body=(directory/job["request"]).read_bytes().split(b"\0",1)[1]
        while body:
            header,body=body.split(b"\0",1);child,body=body[:20].hex(),body[20:]
            if header.split(b" ",1)[1]!=b"base":get(child,True)
        get(job["result"].split()[-1],True)
    result["objects"]=sorted(seen)
    result["object_scope"]="Request trees, task inputs, replay worker and outputs. The std/bash image closure is excluded; replay.py resolves std/bash from your CAOS checkout."

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--harness",type=Path,required=True)
    p.add_argument("--cli",type=Path,required=True)
    p.add_argument("--server",required=True)
    p.add_argument("--workdir",type=Path,required=True)
    p.add_argument("--data",type=Path,default=REPO/"docs/trajectories/data")
    a=p.parse_args()
    spec=importlib.util.spec_from_file_location("verify",REPO/"trajectories/verify.py")
    v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v);v.DATA=a.data
    d=json.loads((a.data/"metr-collective.json").read_text())
    conversations=v.verify_export(d)
    child=conversations[CHILD]
    event=next(e for e in child["events"] if e["oid"]==EVENT)
    root=a.workdir.resolve();root.mkdir(parents=True,exist_ok=False)
    harness=root/"harness"
    subprocess.run(["git","clone","--quiet","--no-hardlinks",str(a.harness.resolve()),str(harness)],check=True)
    def git(*args):
        return subprocess.check_output(["git","-C",str(harness),*args],text=True).strip()
    git("switch","-c","codex/collective-replay-"+secrets.token_hex(5))
    git("remote","add","caos",a.server)
    source=harness/"replay/source";source.mkdir(parents=True)
    prefix="code/dirty/"
    for name,row in d["snapshots"][event["tree"]]["files"].items():
        if not name.startswith(prefix): continue
        relative=Path(name[len(prefix):])
        if relative.is_absolute() or ".." in relative.parts or row["mode"] not in ("100644","100755"):
            raise ValueError("Unexpected source path or mode: "+name)
        kind,body=v.raw(row["oid"])
        assert kind=="blob"
        dest=source/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(body)
        dest.chmod(0o755 if row["mode"]=="100755" else 0o644)
    shutil.copyfile(HERE/"replay-worker.sh",harness/"replay/worker.sh")
    shutil.copyfile(HERE/"fixture/session.env",harness/"replay/original.env")
    git("add","replay")
    common=[str(a.cli.resolve()),"--base:@=std/bash","--worker1:@=replay/worker.sh","--source:@=replay/source","--original-session:@=replay/original.env"]
    result={"conversation":CHILD,"event":EVENT,"runtime":git("rev-parse","HEAD"),"description":"Same captured source in fresh std/bash jobs; clean changes only session.env. This is not a replay of the original bash-tool ArgTree.","jobs":{}}
    for mode,expected in (("captured","SCORE=1"),("clean","SCORE=0")):
        args=common[1:]+["--mode="+mode,"--salt=collective-replay-"+secrets.token_hex(12)]
        with (root/(mode+"-prepare.log")).open("w") as log:
            request=subprocess.check_output([common[0],"prepare-request",*args],cwd=harness,text=True,stderr=log).strip()
        output=root/(mode+"-result")
        with (root/(mode+"-run.log")).open("w") as log:
            run=subprocess.run([common[0],"run",str(output),*args],cwd=harness,text=True,stdout=subprocess.PIPE,stderr=log,check=True)
        score=(output/"score.txt").read_text().strip()
        assert score==expected,(mode,score)
        result["jobs"][mode]={"request":request,"result":run.stdout.strip(),"score":score,"run":(output/"run.txt").read_text(),"command":(output/"receipt/command").read_text().strip(),"exit":int((output/"receipt/exit").read_text()),"integrity_before":(output/"receipt/integrity.before").read_text().strip(),"integrity_after":(output/"receipt/integrity.after").read_text().strip()}
        (root/"replay.json").write_text(json.dumps(result,indent=2)+"\n")
        print(mode,score,request,flush=True)
    capture_objects(a.server,result,root/"objects")
    (root/"replay.json").write_text(json.dumps(result,indent=2)+"\n")
    print(root/"replay.json")

if __name__=="__main__":main()
