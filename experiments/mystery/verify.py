#!/usr/bin/env python3
"""Check every game action against its original model reply and replay the rules."""
import argparse, json
from pathlib import Path
from engine import new_game, turn
from run import export, finish_text, SITE

def verify(folder):
    snapshot=json.loads((folder/"state.json").read_text())
    scenario=json.loads((folder/"scenario-spoilers.json").read_text())
    state=new_game(scenario)
    objects=export.Objects("http://invalid.invalid",folder/"data/objects")
    ancestry={}
    for role,row in snapshot["heads"].items():
        allowed=set();head=row["head"]
        while head:
            allowed.add(head)
            commit=objects.commit(head)
            head=None if commit["kind"]=="conversation.root" else commit["parents"][0]
        ancestry[role]=allowed
    for row in snapshot["turns"]:
        state["round"]=row["round"]
        if row["head"] not in ancestry[row["role"]]:raise ValueError("Turn outside published conversation ancestry")
        recorded=finish_text(objects,row["head"])
        if recorded!=row["decision"]:raise ValueError("Published decision differs from CAOS reply")
        turn(state,scenario,row["role"],recorded,{"conversation":row["conversation"],"head":row["head"]})
    if state["events"]!=snapshot["events"]:raise ValueError("Game events do not replay from recorded decisions")
    if state["chats"]!=snapshot["chats"] or state["ballots"]!=snapshot["ballots"]:
        raise ValueError("Published state differs from replay")
    print("Verified",len(snapshot["turns"]),"model turns,",len(state["events"]),"events and",len(state["chats"]),"chats")

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--snapshot",type=Path,default=SITE/"docs/mystery")
    verify(p.parse_args().snapshot)
