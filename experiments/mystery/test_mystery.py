import concurrent.futures, copy, json, tempfile, time, unittest
from pathlib import Path
from engine import new_game, apply, turn, observation
from gateway import Budget
S=json.loads((Path(__file__).parent/"scenario.json").read_text())

class GameTests(unittest.TestCase):
    def setUp(self):
        self.s=new_game(S);self.s["round"]=1
    def action(self,actor,**kw): return apply(self.s,S,actor,kw,{"head":"test"})
    def test_invite_does_not_deliver_history(self):
        self.action("nell",type="create",chat="nell-test",title="Talk")
        self.action("nell",type="say",chat="nell-test",text="Before invitation")
        self.action("nell",type="invite",chat="nell-test",role="iris")
        self.action("nell",type="say",chat="nell-test",text="While invited")
        before=observation(self.s,S,"iris")
        self.assertNotIn("Before invitation",json.dumps(before))
        self.assertNotIn("While invited",json.dumps(before))
        self.action("iris",type="accept",chat="nell-test")
        self.action("nell",type="say",chat="nell-test",text="After acceptance")
        after=json.dumps(observation(self.s,S,"iris"))
        self.assertIn("After acceptance",after);self.assertNotIn("Before invitation",after)
        self.assertNotIn("After acceptance",json.dumps(observation(self.s,S,"miles")))
    def test_private_search_and_validated_sharing(self):
        self.action("nell",type="inspect",place="study")
        self.assertNotIn("study-company",self.s["known"]["iris"])
        with self.assertRaises(ValueError):self.action("iris",type="share",chat="drawing-room",evidence="study-company")
        self.action("nell",type="share",chat="drawing-room",evidence="study-company")
        self.assertIn("study-company",self.s["known"]["iris"])
    def test_membership_and_forwarding(self):
        self.action("nell",type="create",chat="nell-test",title="Talk")
        private=self.action("nell",type="say",chat="nell-test",text="Private")
        with self.assertRaises(ValueError): self.action("iris",type="say",chat="nell-test",text="Intrusion")
        with self.assertRaises(ValueError): self.action("iris",type="forward",chat="drawing-room",event=private["id"])
        forwarded=self.action("nell",type="forward",chat="drawing-room",event=private["id"])
        self.assertEqual(forwarded["payload"]["original"]["actor"],"nell")
    def test_atomic_errors_and_no_duplicate_turn(self):
        turn(self.s,S,"nell",{"actions":[{"type":"create","chat":"nell-a","title":"A"},{"type":"invite","chat":"nell-a","role":"nobody"}]}, {})
        self.assertEqual(self.s["chats"]["nell-a"]["invites"],[])
        self.assertEqual(self.s["events"][-1]["kind"],"error")
        with self.assertRaises(ValueError):turn(self.s,S,"nell",{"actions":[]},{})
        self.assertNotIn("error",json.dumps(observation(self.s,S,"iris")))
    def test_search_limit_and_final_ballot_privacy(self):
        self.action("vale",type="inspect",place="library")
        with self.assertRaises(ValueError):self.action("vale",type="inspect",place="study")
        self.s["round"]=S["rounds"]
        self.action("vale",type="ballot",suspect="miles",estate="trust",reason="A private conclusion")
        self.assertNotIn("A private conclusion",json.dumps(observation(self.s,S,"iris")))
    def test_all_initial_cards_owned_only_by_their_role(self):
        for role,packet in S["roles"].items():
            for card in packet["cards"]:
                self.assertEqual(S["evidence"][card]["owner"],role)
                for other in S["roles"]:
                    if other!=role:self.assertNotIn(card,new_game(S)["known"][other])
        self.assertEqual(S["truth"]["killer"],"miles")

class BudgetTests(unittest.TestCase):
    def test_atomic_cap_and_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"budget.sqlite"
            b=Budget(path,1,time.time()+600)
            def reserve(_):
                try:return b.reserve("test",0.3)
                except ValueError:return None
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                ids=list(pool.map(reserve,range(12)))
            self.assertEqual(sum(x is not None for x in ids),3)
            b=Budget(path,1,time.time()+600)
            self.assertAlmostEqual(b.status()["charged_usd"],0.9)
            call=next(x for x in ids if x is not None)
            b.uncertain(call)
            self.assertAlmostEqual(b.status()["charged_usd"],0.9)
            b.settle(call,{"input_tokens":1000,"output_tokens":1000})
            self.assertAlmostEqual(b.status()["charged_usd"],0.63)
    def test_deadline(self):
        with tempfile.TemporaryDirectory() as temp:
            b=Budget(Path(temp)/"budget.sqlite",50,time.time()-1)
            with self.assertRaises(ValueError):b.reserve("test",1)

if __name__=="__main__":unittest.main()
