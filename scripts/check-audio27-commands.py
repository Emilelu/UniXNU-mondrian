#!/usr/bin/env python3
"""Every script the audio pages tell you to run, and every audio tool we own.

Two directions, because each has its own failure mode:

  docs -> files   a page names scripts/foo.py; if that file is not on this
                  branch the reader is sent to nothing. Files that legitimately
                  live elsewhere are named in EXTERNAL together with the place
                  that must hold them, and that place is checked too, so an
                  excuse never hardens into an assumption.

  files -> docs   an audio tool we own that no page mentions is a tool nobody
                  will find. Add the page or drop the file.

Citations that resolve are also asked for --help (python tools only): a script
that cannot describe its own arguments cannot be run from a page either.

Usage: python3 scripts/check-audio27-commands.py [repo]
"""

import glob
import os
import re
import subprocess
import sys

CITE = re.compile(r"scripts/[A-Za-z0-9._-]*\.(?:py|sh)")

# Cited from the pages, kept in another repository. The second element is the
# place that has to hold it; nothing here is taken on faith.
EXTERNAL = {
    "scripts/build-xnu-generic.sh": ("gates", "scripts/build-xnu-generic.sh"),
    "scripts/build-ios27-linux.sh": ("gates", "scripts/build-ios27-linux.sh"),
    "scripts/refresh-xnu-generic.py": ("gates", "scripts/refresh-xnu-generic.py"),
    "scripts/k60-fileset-pair.py": ("gates", "scripts/k60-fileset-pair.py"),
    "scripts/build-sheng-audio-hal.py": ("sheng", "scripts/build-sheng-audio-hal.py"),
    "scripts/check-audioreach-host.py": ("sheng", "scripts/check-audioreach-host.py"),
}

OWN = [
    "scripts/check-audio27-*.py",
    "scripts/apply-audio27-wiring.py",
    "scripts/emit-audio27-patch.py",
    "scripts/triage-audio27.py",
    "scripts/judge-audio-capture.py",
    "scripts/add-audio-conffiles.py",
    "scripts/check-sheng-inject.py",
    "scripts/check-sheng-abi.py",
    "scripts/check-audio-migration.py",
    "scripts/check-audio27-preflight.sh",
]

BASES = {
    "gates": ("K60_GATES", "/mnt/e/hackios/k60-gates"),
    "sheng": ("SHENG_REPO", "/mnt/e/hackios/UniXNU-sheng"),
}


def base(kind):
    env, default = BASES[kind]
    return os.environ.get(env) or default


def cited(repo):
    """(page, line number, cited path) for every citation in the audio pages."""
    out = []
    for page in sorted(glob.glob(os.path.join(repo, "docs/research/audio/*.md"))):
        handle = open(page, encoding="utf-8")
        for number, line in enumerate(handle, 1):
            for found in CITE.findall(line):
                out.append((os.path.relpath(page, repo), number, found))
        handle.close()
    return out


def own(repo):
    names = set()
    for pattern in OWN:
        for path in glob.glob(os.path.join(repo, pattern)):
            names.add(os.path.relpath(path, repo))
    return sorted(names)


def help_works(repo, path):
    """Exit status and first line of --help, or a reason it could not run."""
    try:
        done = subprocess.run([sys.executable, path, "--help"], cwd=repo,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=60)
    except OSError as problem:
        return None, str(problem)
    text = done.stdout.decode("utf-8", "replace").strip()
    return done.returncode, text.splitlines()[0] if text else "(no output)"


def main():
    if any(argument in ("-h", "--help") for argument in sys.argv[1:]):
        print((__doc__ or "").strip())
        return 0
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    pages = glob.glob(os.path.join(repo, "docs/research/audio/*.md"))
    if not pages:
        print("COMMANDS: %s has no docs/research/audio, that is not this tree" % repo)
        return 3
    found = cited(repo)
    tools = own(repo)
    if not tools:
        print("COMMANDS: no audio tools in %s/scripts" % repo)
        return 3

    problems = []
    outside = []
    absent = []
    for page, number, path in found:
        if os.path.exists(os.path.join(repo, path)):
            continue
        if path not in EXTERNAL:
            problems.append("%s:%d cites %s, which is not in this tree and not named in EXTERNAL"
                            % (page, number, path))
            continue
        kind, relative = EXTERNAL[path]
        home = os.path.join(base(kind), relative)
        if not os.path.isdir(base(kind)):
            absent.append((path, kind, BASES[kind][0]))
        elif not os.path.exists(home):
            problems.append("EXTERNAL says %s lives in %s, but %s is not on this machine (set %s)"
                            % (path, kind, home, BASES[kind][0]))
        else:
            outside.append(path)

    mentioned = set(path for _, _, path in found)
    for path in tools:
        if path not in mentioned:
            problems.append("%s has no page telling the reader to run it" % path)

    helped = 0
    for path in tools:
        if not path.endswith(".py") or path not in mentioned:
            continue
        status, line = help_works(repo, path)
        if status != 0:
            problems.append("%s --help exited %s: %s" % (path, status, line))
        else:
            helped += 1

    if problems:
        for problem in problems:
            print("COMMANDS FAILED: %s" % problem)
        return 1

    for path in sorted(set(outside)):
        kind, relative = EXTERNAL[path]
        print("COMMANDS NOTE: %s is not in this tree; the %s checkout holds it at %s"
              % (path, kind, os.path.join(base(kind), relative)))
    for path, kind, variable in absent:
        print("COMMANDS NOTE: %s is not in this tree, and no %s checkout is on this machine"
              " (set %s), so that citation cannot be followed from here"
              % (path, kind, variable))
    print("COMMANDS OK %d citation(s) resolve (%d followed into another checkout),"
          " %d audio tool(s) are cited, %d of them answer --help"
          % (len(found), len(outside), len(tools), helped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
