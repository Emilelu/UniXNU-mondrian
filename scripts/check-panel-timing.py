#!/usr/bin/env python3
"""Static checks for the K60 m11a 120 Hz panel timing switch.

This is deliberately a source-level check: the panel is only present on the
device, so the exact 11-packet timing@2 sequence, the p120/vsync gates, the
measured-refresh report and the INTF1 observations must all be provable
before an image is built.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "drivers/PongAdreno/PongDsiPanel.cpp"
PATCH = ROOT / "patches/xnu/0506-k60-120hz-refresh.patch"
ARGS = ROOT / "scripts/check-image-args.py"

# qcom,mdss-dsi-timing-switch-command from the vendor m11a timing@2 node.
# The live FDT copy has ten packets (98 B); the vendor source adds CC 00.
EXPECTED = [
    [0x2f, 0x00],
    [0x8b, 0x00],
    [0xf0, 0x55, 0xaa, 0x52, 0x08, 0x00],
    [0x6f, 0x03],
    [0xc0, 0x10],
    [0x6f, 0x31],
    [0xdf, 0x20],
    [0xf0, 0x55, 0xaa, 0x52, 0x08, 0x02],
    [0xcc, 0x30],
    [0xce, 0x01],
    [0xcc, 0x00],
]


def fail(message: str) -> None:
    print(f"check-panel-timing: FAIL {message}")
    raise SystemExit(1)


def main() -> int:
    text = PANEL.read_text()
    patch = PATCH.read_text()
    args = ARGS.read_text()

    declarations = {
        name: [int(value, 16) for value in re.findall(r"0x([0-9a-fA-F]+)", body)]
        for name, body in re.findall(
            r"constexpr\s+uint8_t\s+(kTiming120_[A-Za-z0-9_]+)\[\]\s*=\s*\{([^}]*)\};",
            text,
        )
    }
    table = re.search(
        r"constexpr\s+PanelTimingCommand\s+kTiming120\[\]\s*=\s*\{(.*?)\};",
        text,
        re.S,
    )
    if not table:
        fail("kTiming120 command table not found")
    names = re.findall(r"\{\s*(kTiming120_[A-Za-z0-9_]+)\s*,", table.group(1))
    actual = [declarations.get(name) for name in names]
    if actual != EXPECTED:
        fail(f"timing@2 packet sequence changed: {actual!r}")
    if len(EXPECTED) != 11:
        fail("the vendor m11a timing@2 command must have eleven packets")
    if max(len(packet) for packet in EXPECTED) > 60:
        fail("a timing packet exceeds DsiMaxPayload")
    if "dsi_dcs(kTiming120[i].data, kTiming120[i].length, false)" not in text:
        fail("pong_panel_switch_120 does not send each table packet through dsi_dcs")
    if "kTiming120[i].wait_ms" not in text:
        fail("pong_panel_switch_120 does not honour the per-packet post-wait")
    if "IODelay(300 * 1000)" not in text:
        fail("missing the vendor timing-switch settle delay")
    if 'PE_parse_boot_argn("p120"' not in text:
        fail("p120 boot argument is not parsed")
    if 'PE_parse_boot_argn("vsync"' not in text:
        fail("vsync boot argument is not parsed")
    if "panel_120_switch_pending" not in text or "pong_panel_switch_120();" not in text:
        fail("pong_panel_switch_120 is not armed for the first GPU frame")
    if "panel_intf_rate(\"before the switch\", 200)" not in text:
        fail("missing the before-switch INTF1 rate observation")
    if "panel_intf_rate(\"after the switch\", 500)" not in text:
        fail("missing the after-switch INTF1 rate observation")
    if "panel_120_verify_pending" not in text or 'panel_intf_rate("after the UI frame", 500)' not in text:
        fail("missing the post-first-frame INTF1 rate observation")
    if "panel_120_requested" not in text or "pong_panel_refresh_hz" not in text:
        fail("missing the requested panel refresh report")
    if "IntfTearSyncVsync" not in text or "(cfg&~0x7ffffu)|50u" not in text:
        fail("missing the 120 Hz INTF vsync_count update")
    first_frame = ROOT / "patches/xnu/0365-k60-ui-owns-screen.patch"
    if "pong_panel_sample();" not in first_frame.read_text():
        fail("the first-frame patch does not call pong_panel_sample")

    if 'static TUNABLE(uint32_t, gK60Panel120, "p120", 0);' not in patch:
        fail("0506 patch does not declare the p120 tunable")
    if "pong_panel_refresh_hz()" not in patch:
        fail("0506 patch does not report the measured panel rate")
    if '"p120"' not in args or '"vsync"' not in args:
        fail("check-image-args.py does not allow p120 and vsync")

    print(f"check-panel-timing: ok ({len(EXPECTED)} packets, p120/vsync gates, first-frame switch and requested refresh present)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
