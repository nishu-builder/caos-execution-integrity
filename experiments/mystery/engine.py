"""Deterministic game rules. Only authorized actions change state."""
import copy, hashlib, json, re

PLACES=("library","study","pantry","greenhouse","boathouse","hall","guest-room")

def new_game(scenario):
    roles=list(scenario["roles"])
    return {"round":0,"status":"ready","events":[],"chats":{"drawing-room":{"title":"Drawing room","members":roles,"invites":[]}},
            "known":{r:list(scenario["roles"][r]["cards"]) for r in roles},"ballots":{},"completed":{}}

def emit(state,kind,actor,targets,payload,source=None):
    prior=state["events"][-1]["hash"] if state["events"] else "0"*64
    event={"id":"e"+str(len(state["events"])+1),"round":state["round"],"kind":kind,
           "actor":actor,"visible_to":sorted(set(targets)),"payload":payload,"source":source,"previous":prior}
    event["hash"]=hashlib.sha256(json.dumps(event,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    state["events"].append(event)
    return event

def visible(state,role):
    return [e for e in state["events"] if role in e["visible_to"]]

def observation(state,scenario,role,since=0):
    chats={cid:{"title":c["title"],"members":c["members"]} for cid,c in state["chats"].items() if role in c["members"]}
    invites=[{"chat":cid,"title":c["title"]} for cid,c in state["chats"].items() if role in c["invites"]]
    events=[{k:v for k,v in e.items() if k not in ("visible_to","previous","hash","source")} for e in state["events"][since:] if role in e["visible_to"]]
    return {"round":state["round"],"total_rounds":scenario["rounds"],"chats":chats,"invitations":invites,
            "evidence_you_hold":{eid:scenario["evidence"][eid] for eid in state["known"][role]},
            "new_events":events,"final_ballot":state["round"]==scenario["rounds"]}

def text(value,limit=3000):
    if not isinstance(value,str) or not value.strip() or len(value)>limit: raise ValueError("Missing or overlong text")
    return value

def apply(state,scenario,actor,action,source):
    if actor not in scenario["roles"] or not isinstance(action,dict): raise ValueError("Invalid actor or action")
    kind=action.get("type")
    targets=[actor]
    payload=copy.deepcopy(action)
    if kind=="create":
        cid=action.get("chat","")
        if not isinstance(cid,str) or not re.fullmatch(re.escape(actor)+r"-[a-z0-9-]{1,40}",cid):
            raise ValueError("New chat id must start with your role id and a hyphen")
        if cid in state["chats"]: raise ValueError("Chat already exists")
        title_=text(action.get("title"),100)
        state["chats"][cid]={"title":title_,"members":[actor],"invites":[]}
    elif kind in ("invite","accept","decline","leave","say","share","forward"):
        cid=action.get("chat")
        if cid not in state["chats"]: raise ValueError("Unknown chat")
        chat=state["chats"][cid]
        if kind in ("accept","decline"):
            if actor not in chat["invites"]: raise ValueError("No pending invitation")
            chat["invites"].remove(actor)
            if kind=="accept": chat["members"].append(actor)
            targets=chat["members"]+[actor]
        else:
            if actor not in chat["members"]: raise ValueError("You are not a member")
            targets=list(chat["members"])
            if kind=="invite":
                other=action.get("role")
                if other not in scenario["roles"]: raise ValueError("Unknown role")
                if other in chat["members"] or other in chat["invites"]: raise ValueError("Already a member or invited")
                chat["invites"].append(other)
                targets=[actor,other]
                payload["title"]=chat["title"]
            elif kind=="leave":
                if cid=="drawing-room": raise ValueError("Cannot leave the public room")
                chat["members"].remove(actor)
            elif kind=="say":
                text(action.get("text"))
                reply=action.get("reply_to")
                if reply and not any(e["id"]==reply and actor in e["visible_to"] for e in state["events"]):
                    raise ValueError("Cannot reply to an unseen event")
            elif kind=="share":
                eid=action.get("evidence")
                if eid not in state["known"][actor]: raise ValueError("You do not possess that evidence")
                payload["card"]=scenario["evidence"][eid]
                for member in targets:
                    if eid not in state["known"][member]: state["known"][member].append(eid)
            elif kind=="forward":
                original=next((e for e in state["events"] if e["id"]==action.get("event") and actor in e["visible_to"]),None)
                if not original or original["kind"] not in ("say","share","forward"):
                    raise ValueError("Can only forward a message you received")
                # Refer to the original event instead of trusting a supplied quotation.
                payload["original"]={k:v for k,v in original.items() if k not in ("visible_to","previous","hash")}
                if original["kind"]=="share":
                    eid=original["payload"]["evidence"]
                    for member in targets:
                        if eid not in state["known"][member]: state["known"][member].append(eid)
    elif kind=="inspect":
        place=action.get("place")
        if place not in PLACES: raise ValueError("Unknown place")
        if any(e["round"]==state["round"] and e["actor"]==actor and e["kind"]=="inspect" for e in state["events"]):
            raise ValueError("Only one search per round")
        cards={k:v for k,v in scenario["evidence"].items() if v.get("location")==place}
        for eid in cards:
            if eid not in state["known"][actor]: state["known"][actor].append(eid)
        payload["cards"]=cards
    elif kind=="ballot":
        if state["round"]!=scenario["rounds"]: raise ValueError("Ballots open in the final round")
        if actor in state["ballots"]: raise ValueError("Already voted")
        if action.get("suspect") not in list(scenario["roles"])+["unknown"]: raise ValueError("Unknown suspect")
        if action.get("estate") not in ("sell","family","trust","abstain"): raise ValueError("Unknown estate choice")
        text(action.get("reason"),4000)
        state["ballots"][actor]=copy.deepcopy(action)
    elif kind=="wait":
        payload={"type":"wait"}
    else: raise ValueError("Unknown action type")
    return emit(state,kind,actor,targets,payload,source)

def turn(state,scenario,actor,decision,source):
    # Called exactly once per (round, role); checkpoint includes outcomes and marker.
    turn_id=str(state["round"])+":"+actor
    if turn_id in state["completed"]: raise ValueError("Turn already applied")
    actions=decision.get("actions") if isinstance(decision,dict) else None
    if not isinstance(actions,list) or len(actions)>8: raise ValueError("Reply must contain at most eight actions")
    outcomes=[]
    for action in actions:
        candidate=copy.deepcopy(state)
        try:
            outcome=apply(candidate,scenario,actor,action,source)
            state.clear();state.update(candidate)
        except (ValueError,TypeError,KeyError) as exc:
            outcome=emit(state,"error",actor,[actor],{"action":action,"error":str(exc)},source)
        outcomes.append(outcome["id"])
    state["completed"][turn_id]={"source":source,"outcomes":outcomes,"private_notes":decision.get("notes","")}
    return outcomes
