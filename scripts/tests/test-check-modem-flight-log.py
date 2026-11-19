#!/usr/bin/env python3
"""Host regression for scripts/check-modem-flight-log.py."""
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHECKER = os.path.join(REPO, "scripts", "check-modem-flight-log.py")

P1_GOOD = """K60MODEM power ok cx=0x1c0000/7 mss=0x1c0000/8 xo=0x1c0000/3
K60MODEM power prepared
K60MODEM diagnostic stop after power: init_image not sent
"""

B_GOOD = P1_GOOD.replace("diagnostic stop after power: init_image not sent", "") + """K60MODEM init_image ok metadata=0xb7ff0000 bytes=5884
K60MODEM transport ok smp2p=0x809e3000/428 desc=0x80a00000/478 tx=0x80a01000/479
K60MODEM mem_setup ok base=0x8bc00000 span=0x13200000
K60MODEM auth_reset ok
K60MODEM qrtr: glink desc=0x80a00000 intents=3
K60MODEM qrtr: dms revision MPSS.DE.2.0.c1-CN
K60MODEM qrtr: verdict ok services=37 node0=1 wanted=7 malformed=0 locator=3 dms=MPSS.DE.2.0.c1-CN polls=12
K60MODEM baseband: bridge enabled (poll 500)
COACHZ baseband: 6 of 6 services published (AppleBaseband, AppleBasebandPCIControl, 4 channels, the PDP manager, AppleIPAppender)
"""

C_GOOD = """K60MODEM init_image ok metadata=0xb7ff0000 bytes=5884
K60MODEM mem_setup ok base=0x8bc00000 span=0x13200000
K60MODEM diagnostic stop after mem_setup: auth_reset not sent
"""


def run(phase, text):
    with tempfile.TemporaryDirectory() as work:
        path = os.path.join(work, "console.log")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        result = subprocess.run(
            [sys.executable, CHECKER, "--phase", phase, path],
            capture_output=True, text=True)
        return result.returncode, result.stdout + result.stderr


def expect(name, phase, text, code, needle=None):
    got, output = run(phase, text)
    if got != code:
        raise SystemExit("%s: rc=%d expected %d\n%s" % (name, got, code, output))
    if needle is not None and needle not in output:
        raise SystemExit("%s: output lacks %r\n%s" % (name, needle, output))


expect("p1-good", "p1", P1_GOOD, 0, "P1: PASS")
expect("p1-xo-index", "p1", P1_GOOD.replace("xo=0x1c0000/3", "xo=0x1c0000/4"), 1,
       "expected the literal 3")
expect("p1-extra-pas", "p1", P1_GOOD + "K60MODEM init_image ok metadata=0xb7ff0000 bytes=5884\n",
       1, "unexpected")
expect("p1-double-stop", "p1", P1_GOOD + P1_GOOD.splitlines()[-1] + "\n", 1, "exactly one")
expect("c-good", "c", C_GOOD, 0, "C: PASS")
expect("c-transport-leak", "c", C_GOOD + "K60MODEM transport ok smp2p=0x809e3000/428\n", 1,
       "unexpected")
expect("c-wrong-span", "c", C_GOOD.replace("0x13200000", "0x13000000"), 1, "expected 0x8bc00000")
expect("b-good", "b", B_GOOD, 0, "S3: PASS")
expect("b-no-transport", "b", B_GOOD.replace("K60MODEM transport ok smp2p=0x809e3000/428 "
                                             "desc=0x80a00000/478 tx=0x80a01000/479\n", ""),
       1, "expected exactly one K60MODEM transport ok line")
expect("b-no-dms", "b", B_GOOD.replace("K60MODEM qrtr: dms revision MPSS.DE.2.0.c1-CN\n", ""),
       1, "S4: FAIL")
expect("b-no-verdict", "b", B_GOOD.replace("K60MODEM qrtr: verdict ok services=37 ", "K60MODEM qrtr: verdict no reply services=0 "),
       1, "verdict is")
expect("b-verdict-zero", "b", B_GOOD.replace("verdict ok services=37", "verdict ok services=0"),
       1, "services=0")
expect("b-bridge-disabled", "b", B_GOOD.replace(
    "K60MODEM baseband: bridge enabled (poll 500)\n",
    "K60MODEM baseband: bridge disabled\n"), 1, "S6: FAIL")
expect("b-published-zero", "b", B_GOOD.replace("6 of 6 services published", "0 of 6 services published"),
       1, "published 0 services")
print("K60 FLIGHT LOG PASS p1 c b s5 s6 negative-cases")
