#!/usr/bin/env python3
"""Publish a completed-turn snapshot, including original CAOS objects."""
import argparse, json, sqlite3, subprocess, sys, time
from pathlib import Path
from run import export, save, git, SITE

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--config",type=Path,required=True)
    a=p.parse_args();cfg=json.loads(a.config.read_text());root=Path(cfg["workdir"])
    state=json.loads((root/"state.json").read_text())
    if not state["completed"]:raise SystemExit("No completed game turns yet")
    dest=SITE/"docs/mystery";dest.mkdir(exist_ok=True)
    data=dest/"data";data.mkdir(exist_ok=True)
    forbidden=[Path(path).read_bytes().strip() for path in cfg["forbid_files"]]
    scenario=json.loads((root/"scenario.json").read_text())
    latest={};turns=[]
    for key,value in state["completed"].items():
        round_,role=key.split(":")
        result=json.loads((root/"turns"/("%02d-%s"%(int(round_),role))/"result.json").read_text())
        if result["head"]!=value["source"]["head"]:raise ValueError("Source head mismatch")
        turns.append({"round":int(round_),"role":role,**result,"seen_through":value["seen_through"]})
        latest[role]=result
    unapplied=[];interrupted=[]
    terminal=state["status"] in ("complete","stopped","budget-stopped","failed")
    if terminal:
        for path in sorted((root/"turns").glob("*/result.json")):
            round_text,role=path.parent.name.split("-",1)
            if str(int(round_text))+":"+role in state["completed"]:continue
            result=json.loads(path.read_text())
            unapplied.append({"round":int(round_text),"role":role,**result})
            latest[role]=result
        # Include rejected/unfinished turns in each native conversation's history too.
        for role,row in latest.items():
            ref="refs/caos/v3/conversations/"+row["conversation"].encode().hex()+"/head"
            head=git(cfg["harness"],"ls-remote","caos",ref).split()[0]
            if head!=row["head"]:
                interrupted.append({"role":role,"conversation":row["conversation"],"head":head})
                latest[role]={**row,"head":head}
    examples=[];reply_events={}
    for role,row in latest.items():
        title=scenario["roles"][role]["name"]
        objects=export.Objects(cfg["server"],data/"objects",forbidden)
        obj=export.Exporter(objects).export(row["head"],"bellweather-"+role,title,
            "Private character conversation in the Bellweather House mystery.",cfg["runtime"])
        for conversation in obj["conversations"]:
            last_reply=None
            for event in conversation["events"]:
                if any(m.get("role")=="assistant" for m in event["messages"]):last_reply=event["oid"]
                if last_reply:reply_events[event["oid"]]=last_reply
        save(data/("bellweather-"+role+".json"),obj)
        examples.append({"id":"bellweather-"+role,"title":title,"head":row["head"]})
    save(data/"index.json",{"examples":examples})
    budget=sqlite3.connect(root/"budget.sqlite")
    cost=budget.execute("SELECT COALESCE(SUM(charged),0),COUNT(*) FROM calls").fetchone()
    snapshot={"title":scenario["title"],"run_id":cfg["run_id"],"updated":time.time(),
              "runtime":cfg["runtime"],"model":"claude-opus-4-8","status":state["status"],
              "round":state["round"],"total_rounds":scenario["rounds"],"charged_usd":cost[0],
              "provider_calls":cost[1],"stop_reason":state.get("stop_reason"),"stopped_at":state.get("stopped_at"),"unapplied_turns":unapplied,"interrupted_turns":interrupted,"deadline":cfg["deadline"],"cast":{k:{"name":v["name"],"public":v["public"]} for k,v in scenario["roles"].items()},
              "heads":{k:{"conversation":v["conversation"],"head":v["head"]} for k,v in latest.items()},
              "reply_events":reply_events,"events":state["events"],"chats":state["chats"],"ballots":state["ballots"],"turns":turns}
    raw=json.dumps(snapshot,ensure_ascii=True,indent=2).encode()
    if any(secret and secret in raw for secret in forbidden):raise ValueError("Secret in snapshot")
    (dest/"state.json").write_bytes(raw+b"\n")
    # A separate, explicitly marked spoiler file makes the fixed solution inspectable.
    save(dest/"scenario-spoilers.json",scenario)
    subprocess.run([sys.executable,str(Path(__file__).parent/"verify.py"),"--snapshot",str(dest)],check=True)
    subprocess.run([sys.executable,str(SITE/"trajectories/publish_objects.py"),"--data",str(data),"--output",str(dest/"git")],check=True)
    current={e["head"] for e in examples}
    for pack in (dest/"git/packs").iterdir():
        if pack.suffix in (".pack",".idx") and pack.stem not in current:
            pack.unlink()
    print("Published snapshot:",dest,flush=True)

if __name__=="__main__":main()
