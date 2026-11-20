#!/usr/bin/env python3
"""Exercise the proposed stage-0 hook status block, never the build driver."""

import os
import pathlib
import subprocess
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
PATCH = REPO / "docs/research/audio/STAGE0-HOOK-STATUS.patch"
ORIGINAL = """# Seam 1 (P-266): K60 carries the conf/files entries for in-tree drivers in a
# hook rather than in a patch, because a hunk cannot survive the tree being
# re-seeded. The builder calls it after .cache/xnu-work exists; all this has to
# do is name it. Left unset when it is not on disk -- a hook that aborted on an
# owner whose sources are not in this tree would make stage 0 unbuildable.
if [ -f "$ROOT/scripts/k60-conf-files-hook.py" ]; then
	K60_CONF_FILES_HOOK="$ROOT/scripts/k60-conf-files-hook.py"
	export K60_CONF_FILES_HOOK
fi

# Seam 2 (P-260): the audio driver wants -DXNU_PONG_AUDIO for its own object
"""


def run_case(root, block, override=None):
    environment = dict(os.environ, ROOT=str(root))
    environment.pop("K60_CONF_FILES_HOOK", None)
    if override is not None:
        environment["K60_CONF_FILES_HOOK"] = str(override)
    # The child shell sees only an exported hook, not a local shell variable.
    probe = "sh -c 'printenv K60_CONF_FILES_HOOK || echo HOOK=unset'"
    return subprocess.run(["/bin/sh", "-c", "set -eu\n" + block + "\n" + probe],
                          env=environment, capture_output=True, text=True)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        script = root / "scripts/build-ios27-linux.sh"
        script.parent.mkdir()
        script.write_text("#!/bin/sh\nset -eu\n" + ORIGINAL, encoding="utf-8")
        applied = subprocess.run(["git", "apply", "--check", str(PATCH)], cwd=root,
                                 capture_output=True, text=True)
        assert applied.returncode == 0, applied.stdout + applied.stderr
        subprocess.run(["git", "apply", str(PATCH)], cwd=root, check=True,
                       capture_output=True, text=True)
        block = script.read_text(encoding="utf-8").split("# Seam 2", 1)[0]

        absent = run_case(root, block)
        assert absent.returncode == 0, absent.stderr
        assert "no conf/files hook in this tree; stage 0 links no lane objects" in absent.stdout
        assert "HOOK=unset" in absent.stdout, absent.stdout

        default = root / "scripts/k60-conf-files-hook.py"
        default.write_text("# fixture only\n", encoding="utf-8")
        present = run_case(root, block)
        assert present.returncode == 0 and str(default) in present.stdout, present

        explicit = root / "external hook.py"
        explicit.write_text("# fixture only\n", encoding="utf-8")
        selected = run_case(root, block, explicit)
        assert selected.returncode == 0 and str(explicit) in selected.stdout, selected

        missing = run_case(root, block, root / "missing.py")
        assert missing.returncode == 2, missing
        assert "K60_CONF_FILES_HOOK is not a file" in missing.stderr, missing.stderr
        assert "HOOK=" not in missing.stdout, missing.stdout

        directory = run_case(root, block, root / "scripts")
        assert directory.returncode == 2, directory
    print("HOOK STATUS OK 5 cases; patch applies; no build command executed")


if __name__ == "__main__":
    main()
