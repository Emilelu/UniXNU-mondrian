#!/usr/bin/env python3
"""Host cases for scripts/check-audio27-commands.py.

The gate has two directions and an excuse mechanism, and each can fail in a
different way, so each case builds the smallest repository that shows one:
a citation that resolves, a citation nobody can follow, an excuse whose home
is missing, a tool with no page, and a tool whose --help does not answer.
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
GATE = os.path.join(REPO, "scripts", "check-audio27-commands.py")

ALPHA = '''#!/usr/bin/env python3
"""alpha: does nothing, describes itself."""

import sys


def main(argv):
    if any(argument in ("-h", "--help") for argument in argv):
        print((__doc__ or "").strip())
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''

BETA_BROKEN = '''#!/usr/bin/env python3
"""beta: help is not wired."""

import sys


def main(argv):
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''


def build(page_text, tools):
    root = tempfile.mkdtemp(prefix="cmd-")
    os.makedirs(os.path.join(root, "docs", "research", "audio"))
    os.makedirs(os.path.join(root, "scripts"))
    with open(os.path.join(root, "docs", "research", "audio", "PAGE.md"), "w") as handle:
        handle.write(page_text)
    for name, text in tools.items():
        path = os.path.join(root, "scripts", name)
        with open(path, "w") as handle:
            handle.write(text)
        os.chmod(path, 0o644)
    return root


def run(root, gates=None):
    environment = dict(os.environ)
    environment["K60_GATES"] = gates or os.path.join(root, "no-gates")
    environment["SHENG_REPO"] = os.path.join(root, "no-sheng")
    done = subprocess.run([sys.executable, GATE, root], stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, env=environment)
    return done.returncode, done.stdout.decode()


def case_all_resolve():
    root = build("run `python3 scripts/check-audio27-alpha.py .`\n",
                 {"check-audio27-alpha.py": ALPHA})
    code, out = run(root)
    shutil.rmtree(root)
    assert code == 0, out
    assert "COMMANDS OK 1 citation(s) resolve (0 followed into another checkout)," " 1 audio tool(s) are cited, 1 of them answer --help" in out, out


def case_citation_without_file():
    root = build("run `python3 scripts/check-audio27-alpha.py .` and\n"
                 "then `python3 scripts/check-audio27-ghost.py .`\n",
                 {"check-audio27-alpha.py": ALPHA})
    code, out = run(root)
    shutil.rmtree(root)
    assert code == 1, out
    assert "PAGE.md:2 cites scripts/check-audio27-ghost.py" in out, out


def case_excuse_without_file():
    root = build("build it with `sh scripts/build-xnu-generic.sh`\n"
                 "then `python3 scripts/check-audio27-alpha.py .`\n",
                 {"check-audio27-alpha.py": ALPHA})
    gates = tempfile.mkdtemp(prefix="gates-")
    os.makedirs(os.path.join(gates, "scripts"))
    code, out = run(root, gates)
    assert code == 1, out
    assert "EXTERNAL says scripts/build-xnu-generic.sh lives in gates" in out, out
    open(os.path.join(gates, "scripts", "build-xnu-generic.sh"), "w").write("#!/bin/sh\n")
    code, out = run(root, gates)
    shutil.rmtree(root)
    shutil.rmtree(gates)
    assert code == 0, out
    assert "COMMANDS NOTE: scripts/build-xnu-generic.sh is not in this tree" in out, out


def case_excuse_without_checkout():
    root = build("build it with `sh scripts/build-xnu-generic.sh`\n"
                 "then `python3 scripts/check-audio27-alpha.py .`\n",
                 {"check-audio27-alpha.py": ALPHA})
    code, out = run(root, os.path.join(root, "not-on-this-machine"))
    shutil.rmtree(root)
    assert code == 0, out
    assert "no gates checkout is on this machine" in out, out


def case_tool_without_page():
    root = build("run `python3 scripts/check-audio27-alpha.py .`\n",
                 {"check-audio27-alpha.py": ALPHA, "check-audio27-gamma.py": ALPHA})
    code, out = run(root)
    shutil.rmtree(root)
    assert code == 1, out
    assert "scripts/check-audio27-gamma.py has no page telling the reader to run it" in out, out


def case_help_broken():
    root = build("run `python3 scripts/check-audio27-alpha.py .` and\n"
                 "`python3 scripts/check-audio27-beta.py .`\n",
                 {"check-audio27-alpha.py": ALPHA, "check-audio27-beta.py": BETA_BROKEN})
    code, out = run(root)
    shutil.rmtree(root)
    assert code == 1, out
    assert "scripts/check-audio27-beta.py --help exited 1" in out, out


def main():
    cases = [case_all_resolve, case_citation_without_file, case_excuse_without_file,
             case_excuse_without_checkout, case_tool_without_page, case_help_broken]
    for case in cases:
        case()
    print("TESTS OK %d cases" % len(cases))
    return 0


if __name__ == "__main__":
    sys.exit(main())
