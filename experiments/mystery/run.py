#!/usr/bin/env python3
"""Persistent peer CAOS conversations, joined by a deterministic game controller."""
import argparse, concurrent.futures, hashlib, importlib.util, json, os, re
import subprocess, sys, time, traceback
from pathlib import Path
from engine import new_game, observation, turn

HERE=Path(__file__).resolve().parent
SITE=HERE.parents[1]
spec=importlib.util.spec_from_file_location("trajectory_export",SITE/"trajectories/export.py")
export=importlib.util.module_from_spec(spec);spec.loader.exec_module(export)

def save(path,value):
    temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value,indent=2)+"\n")
    os.replace(temporary,path)

def git(repo,*args):
    return subprocess.check_output(["git","-C",str(repo),*args],text=True).strip()

def finish_text(objects,head):
    tree=objects.commit(head)["tree"]
    step=objects.at(tree,".caos/step.json")
    # The last assistant text is read from Git, never scraped from terminal output.
    transcript=export.Exporter(objects).transcript(tree)
    messages=[m for m in transcript if m.get("role")=="assistant"]
    if not messages: raise ValueError("No recorded assistant reply")
    last=messages[-1]
    if any(b.get("type")=="tool_use" for b in last["blocks"]): raise ValueError("Unexpected tool call")
    text="".join(b.get("text","") for b in last["blocks"] if b.get("type")=="text").strip()
    if text.startswith("```"):
        text=re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$","",text)
    return json.loads(text)

def model_turn(config,root,round_,role,prompt):
    name=config["run_id"]+"-"+role
    base=root/"turns"/("%02d-%s"%(round_,role));base.mkdir(parents=True,exist_ok=True)
    result_file=base/"result.json"
    if result_file.exists(): return json.loads(result_file.read_text())
    if (base/"started.json").exists():
        raise RuntimeError("Unfinished model turn requires inspection before resuming: "+str(base))
    (base/"prompt.txt").write_text(prompt)
    save(base/"started.json",{"time":time.time(),"conversation":name})
    args=[config["cli"],"chat",name,"--llm-step:@=std/llm-step","--llm-call:@=std/llm-call",
          "--username","mystery-controller","--model","claude-opus-4-8",
          "--base-url",config["gateway"],"--system-file",str(HERE/"SYSTEM.txt"),"-m",prompt]
    with (base/"cli.log").open("w") as log:
        subprocess.run(args,cwd=config["harness"],check=True,stdout=log,stderr=subprocess.STDOUT,timeout=1500)
    ref="refs/caos/v3/conversations/"+name.encode().hex()+"/head"
    head=git(config["harness"],"ls-remote","caos",ref).split()[0]
    objects=export.Objects(config["server"],root/"objects",
                           [Path(p).read_bytes().strip() for p in config["forbid_files"]])
    decision=finish_text(objects,head)
    result={"conversation":name,"head":head,"decision":decision,"time":time.time()}
    save(result_file,result)
    print(json.dumps({"round":round_,"role":role,"head":head,"actions":len(decision.get("actions",[]))}),flush=True)
    return result

def archive(config,root,state):
    # Observer archive is not mounted into any player conversation.
    repo=root/"archive";repo.mkdir(exist_ok=True)
    if not (repo/".git").exists():
        git(repo,"init","-b","main")
        git(repo,"config","user.name","CAOS mystery")
        git(repo,"config","user.email","experiments@example.invalid")
    save(repo/"game.json",state)
    save(repo/"scenario.json",json.loads((root/"scenario.json").read_text()))
    git(repo,"add","game.json","scenario.json")
    if subprocess.run(["git","-C",str(repo),"diff","--cached","--quiet"]).returncode:
        git(repo,"commit","-m","Record mystery round "+str(state["round"]))
    save(root/"archive-head.json",{"head":git(repo,"rev-parse","HEAD")})

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--config",type=Path,required=True)
    p.add_argument("--pilot",action="store_true")
    args=p.parse_args()
    config=json.loads(args.config.read_text());root=Path(config["workdir"])
    root.mkdir(parents=True,exist_ok=True)
    # Prevent two controllers from driving the same conversations.
    import fcntl
    lock=(root/"controller.lock").open("w")
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    scenario_path=root/"scenario.json"
    if not scenario_path.exists(): scenario_path.write_bytes((HERE/"scenario.json").read_bytes())
    scenario=json.loads(scenario_path.read_text())
    state_path=root/"state.json"
    state=json.loads(state_path.read_text()) if state_path.exists() else new_game(scenario)
    try:
        if state["status"]=="complete": return
        for round_ in range(1,scenario["rounds"]+1):
            roles=list(scenario["roles"])
            if all(str(round_)+":"+r in state["completed"] for r in roles): continue
            if time.time()>=config["deadline"] or (root/"STOP").exists():
                state["status"]="stopped";save(state_path,state);return
            state["round"]=round_;state["status"]="running";state.pop("failure",None);save(state_path,state)
            batch_path=root/("round-%02d-inputs.json"%round_)
            if batch_path.exists(): inputs=json.loads(batch_path.read_text())
            else:
                inputs={}
                for role,packet in scenario["roles"].items():
                    previous=[v for k,v in state["completed"].items() if k.endswith(":"+role)]
                    since=previous[-1].get("seen_through",0) if previous else 0
                    obs=observation(state,scenario,role,since)
                    lead=""
                    if round_==1:
                        lead=json.dumps({"world":scenario["public"],"cast":{k:{"name":v["name"],"description":v["public"]} for k,v in scenario["roles"].items()},
                                         "your_role":role,"your_private_packet":packet},ensure_ascii=False)+"\n\n"
                    if round_==scenario["rounds"]-1: lead+="Next round is the final ballot. Make any last disclosures or questions now.\n"
                    if round_==scenario["rounds"]: lead+="Final round. Include your private ballot. Other characters will not see new messages before voting.\n"
                    inputs[role]={"prompt":lead+json.dumps(obs,ensure_ascii=False),"seen_through":len(state["events"])}
                save(batch_path,inputs)
            pending=[r for r in roles if str(round_)+":"+r not in state["completed"]]
            results={}
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures={pool.submit(model_turn,config,root,round_,r,inputs[r]["prompt"]):r for r in pending}
                for future in concurrent.futures.as_completed(futures): results[futures[future]]=future.result()
            # Fixed rotating application order; all model decisions used the same round boundary.
            order=roles[(round_-1)%len(roles):]+roles[:(round_-1)%len(roles)]
            for role in order:
                if role not in results: continue
                result=results[role]
                source={"conversation":result["conversation"],"head":result["head"]}
                turn(state,scenario,role,result["decision"],source)
                state["completed"][str(round_)+":"+role]["seen_through"]=inputs[role]["seen_through"]
                save(state_path,state)
            archive(config,root,state)
            print(json.dumps({"round_complete":round_,"events":len(state["events"]),"chats":len(state["chats"])}),flush=True)
            if args.pilot:
                state["status"]="pilot-complete";save(state_path,state);return
            if round_<scenario["rounds"]:
                until=min(time.time()+config.get("round_pause_seconds",300),config["deadline"])
                while time.time()<until and not (root/"STOP").exists(): time.sleep(min(10,until-time.time()))
        state["status"]="complete";save(state_path,state);archive(config,root,state)
    except Exception as exc:
        state["status"]="failed";state["failure"]=str(exc);save(state_path,state)
        traceback.print_exc()
        raise

if __name__=="__main__":main()
