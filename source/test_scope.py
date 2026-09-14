import tempfile
from pathlib import Path
import unittest
from scope import git, graft
from verify_suite import args_without_salt


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        git(self.repo, "init")
        self.policy = self.blob("review=required\n")
        self.guide = self.blob("Guide\n")
        self.docs = self.tree("100644 blob " + self.guide + "\tguide.txt\n")
        self.parent = self.tree("100644 blob " + self.policy + "\tpolicy.txt\n040000 tree " + self.docs + "\tdocs\n")

    def tearDown(self):
        self.temp.cleanup()

    def blob(self, text):
        return git(self.repo, "hash-object", "-w", "--stdin", input=text)

    def tree(self, text):
        return git(self.repo, "mktree", input=text)

    def test_child_cannot_replace_sibling_policy(self):
        attack = self.tree("100644 blob " + self.blob("review=disabled\n") + "\tpolicy.txt\n")
        result = graft(self.repo, self.parent, self.parent, attack)
        self.assertEqual(git(self.repo,"rev-parse",result+":policy.txt"),self.policy)
        self.assertEqual(git(self.repo,"rev-parse",result+":docs"),attack)

    def test_legitimate_update_is_applied(self):
        docs = self.tree("100644 blob " + self.blob("New guide\n") + "\tguide.txt\n")
        result = graft(self.repo,self.parent,self.parent,docs)
        self.assertEqual(git(self.repo,"show",result+":docs/guide.txt"),"New guide")

    def test_child_cannot_select_destination(self):
        for path in (".", "", "..", "../policy.txt", "docs/../policy.txt", "/docs", "policy.txt"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                graft(self.repo,self.parent,self.parent,self.docs,path)

    def test_stale_parent_is_rejected(self):
        with self.assertRaises(ValueError):
            graft(self.repo,self.docs,self.parent,self.docs)

    def test_symlink_escape_is_rejected(self):
        proposal = self.tree("120000 blob " + self.blob("../policy.txt") + "\tguide.txt\n")
        with self.assertRaises(ValueError):
            graft(self.repo,self.parent,self.parent,proposal)

    def test_nested_symlink_is_rejected(self):
        link = self.tree("120000 blob " + self.blob("../../policy.txt") + "\tlink\n")
        proposal = self.tree("040000 tree " + link + "\tnested\n")
        with self.assertRaises(ValueError):
            graft(self.repo,self.parent,self.parent,proposal)

    def test_blob_proposal_is_rejected(self):
        with self.assertRaises(ValueError):
            graft(self.repo,self.parent,self.parent,self.policy)

    def test_only_salt_is_ignored_in_replay_comparison(self):
        def request(salt, content):
            return self.tree("100644 blob " + self.blob(salt) + "\tsalt\n100644 blob " + content + "\tinput\n")
        first=request("a",self.policy)
        self.assertEqual(args_without_salt(self.repo,first),args_without_salt(self.repo,request("b",self.policy)))
        self.assertNotEqual(args_without_salt(self.repo,first),args_without_salt(self.repo,request("a",self.guide)))


if __name__ == "__main__":
    unittest.main()
