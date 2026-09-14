"""Apply a child's proposed tree only at the operator's fixed destination."""
import re
import subprocess


def git(repo, *args, input=None):
    result = subprocess.run(["git", "-C", str(repo), *args], input=input, text=True,
                            capture_output=True, check=True)
    return result.stdout.strip()


def checked_oid(value):
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{40}", value):
        raise ValueError("invalid object identity")
    return value


def graft(repo, current_parent, expected_parent, proposal, destination="docs"):
    for value in (current_parent, expected_parent, proposal):
        checked_oid(value)
    if current_parent != expected_parent:
        raise ValueError("parent changed since delegation")
    if destination != "docs":
        raise ValueError("destination is outside this delegation")
    if git(repo, "cat-file", "-t", proposal) != "tree":
        raise ValueError("proposal must be a tree")
    # This demo's publication contract accepts regular files only. Symlinks and
    # submodules could escape the intended boundary when consumers materialize it.
    listing = git(repo, "ls-tree", "-rz", proposal)
    for row in listing.split("\0"):
        if row:
            mode = row.split(" ", 1)[0]
            if mode not in ("100644", "100755"):
                raise ValueError("proposal contains a symlink or submodule")
    rows = git(repo, "ls-tree", current_parent).splitlines()
    rows = [row for row in rows if row.split("\t", 1)[1] != destination]
    rows.append("040000 tree " + proposal + "\t" + destination)
    return git(repo, "mktree", input="\n".join(rows) + "\n")
