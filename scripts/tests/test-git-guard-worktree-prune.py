#!/usr/bin/env python3
"""The git guard must refuse `worktree prune` from a LINKED worktree (P-256).

P-203 and P-256 are the same command landing three times: on 2026-11-15 it took
twenty worktrees, on 2026-11-20 it took twelve more. Both times the guard was
tested only from the main checkout, where the refusal does not fire, so the
fixture was green while the command worked exactly where it hurt.

These cases therefore run from inside a linked worktree, and they assert the
admin directories are byte-identical afterwards: a refusal that still snapshots
or rewrites is not a refusal.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
GUARD = ROOT / "scripts" / "git-guard"
WORK = ROOT / "build" / ("git-guard-prune-tests-" + str(os.getpid()))
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}

failures = 0
checks = 0


def check(name, got, want=True):
    global failures, checks
    checks += 1
    ok = (got == want) if want is not True else bool(got)
    if not ok:
        failures += 1
        print("FAIL %s" % name)
        print("     got:  %r" % (got,))
        print("     want: %r" % (want,))
    return ok


def run(args, cwd, env=None):
    return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          env={**ENV, **(env or {})})


def tree_digest(path):
    h = hashlib.sha256()
    base = pathlib.Path(path)
    for item in sorted(base.rglob("*")):
        if item.is_file():
            h.update(item.relative_to(base).as_posix().encode())
            h.update(b"\0")
            h.update(item.read_bytes())
    return h.hexdigest()


def make_fixture(real_git):
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    main = WORK / "main"
    linked = WORK / "linked"
    run([real_git, "init", "-q", "-b", "main", str(main)], cwd=WORK)
    (main / "tracked.txt").write_text("one\n", encoding="utf-8", newline="\n")
    run([real_git, "-c", "user.name=t", "-c", "user.email=t@example.com", "add", "tracked.txt"], cwd=main)
    run([real_git, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "one"], cwd=main)
    run([real_git, "worktree", "add", "-q", "-b", "side", str(linked)], cwd=main)
    return main, linked


def main():
    text = GUARD.read_text(encoding="utf-8", errors="replace")
    check("the guard asks git which directory it is really using", "--absolute-git-dir" in text)
    check("the guard names the linked-worktree refusal", "LINKED worktree" in text)
    check("the refusal sits before the shared-verb consent block",
          text.index("LINKED worktree") < text.index("K60_I_OWN_ALL_TREES"))
    check("the guard still refuses plain shared verbs",
          "refused a command that rewrites SHARED repository metadata" in text)

    bash = shutil.which("bash")
    real_git = "/usr/bin/git" if os.path.exists("/usr/bin/git") else None
    if not bash or not real_git:
        print("note: no bash or /usr/bin/git here; the execution cases are skipped")
        print("TESTS OK %d checks (0 failure(s))" % checks)
        return 0

    main_wt, linked_wt = make_fixture(real_git)
    admin = main_wt / ".git" / "worktrees"
    before = tree_digest(admin)

    from_linked = run([bash, str(GUARD), "worktree", "prune"], cwd=linked_wt,
                      env={"K60_AGENT_ID": "guard-test", "K60_SNAPSHOT_DIR": str(WORK / "snaps")})
    check("a linked worktree is refused", from_linked.returncode, 128)
    check("the refusal says why", "LINKED worktree" in from_linked.stderr)
    check("the refusal has no side effects on the admin dirs", tree_digest(admin), before)
    check("the refusal does not snapshot", not (WORK / "snaps").exists())

    consented = run([bash, str(GUARD), "worktree", "prune"], cwd=linked_wt,
                    env={"K60_AGENT_ID": "guard-test", "K60_I_OWN_ALL_TREES": "1",
                         "K60_SNAPSHOT_DIR": str(WORK / "snaps")})
    check("the all-trees consent does not unlock a linked worktree", consented.returncode, 128)
    check("the admin dirs survive the consented attempt", tree_digest(admin), before)

    allowed = run([bash, str(GUARD), "worktree", "prune"], cwd=main_wt,
                  env={"K60_AGENT_ID": "guard-test", "K60_I_OWN_ALL_TREES": "1",
                       "K60_SNAPSHOT_DIR": str(WORK / "snaps")})
    check("the main checkout may still prune with consent", allowed.returncode, 0)

    listed = run([real_git, "worktree", "list", "--porcelain"], cwd=main_wt).stdout
    check("the fixture worktree is still registered", "linked" in listed)

    if failures:
        print("TESTS FAILED %d of %d" % (failures, checks))
        return 1
    print("TESTS OK %d checks (0 failure(s))" % checks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
