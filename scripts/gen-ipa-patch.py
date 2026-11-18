#!/usr/bin/env python3
"""Generate patches/xnu/0623-k60-ipa.patch from the PongCellular sources.

The kernel copy uses the bsd/dev names pong_ipa.h/pong_ipa.c and
pong_mdt.h/pong_mdt.c; the in-tree sources keep the K60 names. Nothing else
changes.
"""

import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
SRC = REPO / "drivers/PongCellular"
OUT = REPO / "patches/xnu/0623-k60-ipa.patch"


def newfile(path_in_tree: str, text: str) -> str:
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    body = "".join(("+" + line + "\n") if line else "+\n" for line in lines)
    return (
        "diff --git a/%s b/%s\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/%s\n"
        "@@ -0,0 +1,%d @@\n%s"
        % (path_in_tree, path_in_tree, path_in_tree, len(lines), body)
    )


def kernel_copy(name: str) -> str:
    text = (SRC / name).read_text()
    for source, target in (("K60Ipa.h", "pong_ipa.h"),
                           ("K60Mdt.h", "pong_mdt.h"),
                           ("K60ModemPas.h", "pong_modem_pas.h"),
                           ("K60PmicRail.h", "pong_pmic_rail.h"),
                           ("K60Smem.h", "pong_smem.h"),
                           ("K60IpaGsi.h", "pong_ipa_gsi.h"),
                           ("K60IpaSmmu.h", "pong_ipa_smmu.h"),
                           ("K60IpaQmap.h", "pong_ipa_qmap.h")):
        text = text.replace('#include "%s"' % source, '#include "%s"' % target)
    return text


def main() -> int:
    header = kernel_copy("K60Ipa.h")
    source = kernel_copy("K60Ipa.c")
    mdt_header = kernel_copy("K60Mdt.h")
    mdt_source = kernel_copy("K60Mdt.c")
    gsi_header = kernel_copy("K60IpaGsi.h")
    gsi_source = kernel_copy("K60IpaGsi.c")
    smmu_header = kernel_copy("K60IpaSmmu.h")
    smmu_source = kernel_copy("K60IpaSmmu.c")
    qmap_header = kernel_copy("K60IpaQmap.h")
    qmap_source = kernel_copy("K60IpaQmap.c")
    assert '#include "pong_ipa.h"' in source
    assert '#include "pong_mdt.h"' in header
    assert '#include "pong_mdt.h"' in mdt_source
    assert '#include "pong_pmic_rail.h"' in source
    assert '#include "pong_smem.h"' in source
    assert '#include "pong_ipa_qmap.h"' in qmap_source

    body = (newfile("bsd/dev/pong_ipa.h", header)
            + newfile("bsd/dev/pong_ipa.c", source)
            + newfile("bsd/dev/pong_mdt.h", mdt_header)
            + newfile("bsd/dev/pong_mdt.c", mdt_source)
            + newfile("bsd/dev/pong_ipa_gsi.h", gsi_header)
            + newfile("bsd/dev/pong_ipa_gsi.c", gsi_source)
            + newfile("bsd/dev/pong_ipa_smmu.h", smmu_header)
            + newfile("bsd/dev/pong_ipa_smmu.c", smmu_source)
            + newfile("bsd/dev/pong_ipa_qmap.h", qmap_header)
            + newfile("bsd/dev/pong_ipa_qmap.c", qmap_source))
    with OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    print("patch bytes", OUT.stat().st_size)

    result = subprocess.run(["git", "apply", "--numstat", str(OUT)], cwd=str(REPO),
                            capture_output=True, text=True)
    print("numstat rc", result.returncode, result.stdout.strip().replace("\n", " | "))
    if result.stderr:
        print(result.stderr.strip()[:400], file=sys.stderr)
    return 0 if result.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())