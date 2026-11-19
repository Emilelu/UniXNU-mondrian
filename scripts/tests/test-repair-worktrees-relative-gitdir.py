#!/usr/bin/env python3
"""The worktree repair tool must write an admin pointer BOTH hosts can stat (P-258).

The 2026-11-20 incident had two causes and this is the first one: the previous
version of scripts/repair-worktrees.py wrote .git/worktrees/<id>/gitdir as the
caller spelled it, i.e. "E:/hackios/<name>/.git". WSL git cannot stat that, so
every tree it had just "repaired" was marked prunable - and a prunable tree is
what "git worktree prune" deletes. The repair created the precondition for the
next disaster.

So the assertion is not "the file was written"; it is "the pointer resolves from
both hosts, and a tree repaired by this tool is not prunable".
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "repair-worktrees.py"
# A unique directory per run: a leftover fixture from another host cannot be deleted
# (the objects are owned by whoever built it), and a shared name turns that into a
# spurious failure of the gate rather than of the tool (P-258).
WORK = ROOT / "build" / ("repair-worktrees-tests-" + str(os.getpid()))
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


def run(args, cwd):
    return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=ENV)


def load_tool():
    spec = importlib.util.spec_from_file_location("repair_worktrees", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(git):
    shutil.rmtree(WORK, ignore_errors=True)
    main = WORK / "main"
    linked = WORK / "linked"
    main.mkdir(parents=True)
    run([git, "init", "-q", "-b", "main", str(main)], WORK)
    (main / "tracked.txt").write_text("one\n", encoding="utf-8", newline="\n")
    gitc = [git, "-c", "user.name=t", "-c", "user.email=t@example.com"]
    run(gitc + ["add", "tracked.txt"], main)
    run(gitc + ["commit", "-qm", "one"], main)
    run([git, "worktree", "add", "-q", "-b", "side", str(linked)], main)
    return main, linked


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    module = load_tool()
    text = TOOL.read_text(encoding="utf-8", errors="replace")
    check("the tool has the WSL gitdir helper", hasattr(module, "wsl_gitdir"))
    check("the tool can report prunable trees", hasattr(module, "prunable_worktrees"))
    check("write_admin uses the WSL helper", "wsl_gitdir(worktree)" in text)
    check("the old absolute-path write is gone",
          "write_text(str(worktree / \".git\")" not in text)

    git = shutil.which("git")
    if not git:
        print("note: no git here; the fixture cases are skipped")
        print("TESTS OK %d checks (0 failure(s))" % checks)
        return 0

    main_dir, linked = fixture(git)
    admin = main_dir / ".git" / "worktrees" / "linked"
    gitdir_file = admin / "gitdir"
    check("the fixture admin dir exists", gitdir_file.is_file())

    module.write_admin(admin, linked, main_dir / ".git", "ref: refs/heads/side")
    pointer = gitdir_file.read_text(encoding="utf-8").strip()
    expected_pointer = module.wsl_gitdir(linked)
    check("the admin pointer uses the WSL-visible absolute form",
          pointer.startswith("/mnt/") and ":" not in pointer)
    check("the pointer is the one the helper computes", pointer, expected_pointer)
    if sys.platform == "win32":
        # Windows cannot follow /mnt/e, so the assertion is that the spelling is the
        # exact translation of the same file, not that this host can resolve it.
        check("the pointer is the /mnt translation of the worktree .git file",
              pointer, "/mnt/" + str(linked).replace("\\", "/")[0].lower()
              + str(linked).replace("\\", "/")[2:] + "/.git")
    else:
        check("the pointer resolves to the worktree .git file",
              os.path.normpath(pointer), os.path.normpath(str(linked / ".git")))
    worktree_pointer = (linked / ".git").read_text(encoding="utf-8").strip()
    check("the worktree points back with a relative path",
          worktree_pointer.startswith("gitdir: ../") and ":" not in worktree_pointer[8:])

    # The recovery pointer is spelled for the host that owns the guard: WSL. Windows
    # git resolves a worktree through that worktree's own .git file, not through the
    # admin pointer, so commits keep working there - but its "worktree list" reports
    # /mnt/e entries as prunable, and that asymmetry is the unguarded hazard P-258
    # describes. Asserting "not prunable" on Windows would therefore be asserting the
    # opposite of the design.
    usable = run([git, "-C", str(linked), "rev-parse", "--abbrev-ref", "HEAD"], main_dir)
    check("both hosts can still use the worktree through its own .git pointer",
          usable.stdout.strip(), "side")

    if sys.platform == "win32":
        print("note: /mnt/e visibility and prunable marks are WSL-specific; "
              "the worktree-list cases are skipped on Windows")
    else:
        listed = run([git, "worktree", "list", "--porcelain"], main_dir).stdout
        check("a tree repaired by the tool is not prunable under WSL", "prunable" not in listed)

        gitdir_file.write_text("E:/hackios/nowhere/.git\n", encoding="utf-8")
        prunable = module.prunable_worktrees(main_dir)
        check("an absolute foreign pointer makes the tree prunable", len(prunable) >= 1)
        check("the prunable entry names a worktree", bool(prunable))

        module.write_admin(admin, linked, main_dir / ".git", "ref: refs/heads/side")
        check("repairing with the tool clears the prunable mark",
              module.prunable_worktrees(main_dir), [])

    if failures:
        print("TESTS FAILED %d of %d" % (failures, checks))
        return 1
    print("TESTS OK %d checks (0 failure(s))" % checks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
