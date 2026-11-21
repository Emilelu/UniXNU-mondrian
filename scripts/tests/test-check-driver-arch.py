#!/usr/bin/env python3
"""Tests for check-driver-arch.py: every way an unwritten decision hides."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("gate", ROOT / "scripts/check-driver-arch.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules["gate"] = MODULE
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

HEADER = "| 层 | 官方对应物 | 我们的现状 | 规则 | 决定 | 依据 |\n| --- | --- | --- | --- | --- | --- |\n"


def matrix(*rows: str) -> str:
    return "# t\n\n" + HEADER + "".join(row + "\n" for row in rows)


GOOD = {
    "音频": "| 音频 | sheng amp | PongAudio | 1（官方有） | adopt | `board.toml:9` |",
    "电源": "| 电源 | ShengPlatformPower | K60PmicRail | 1+2 | adopt 官框架 | `K60PmicRail.c:12` |",
    "蓝牙": "| 蓝牙 | QcaBluetooth | 0500 系列 | 3（硬件不同） | keep 传输层 | `board.toml:14` |",
    "WiFi": "| WiFi | Ath12kWifi | Ath11k | 3 | keep 设备驱动 | `board.toml:21` |",
    "蜂窝": "| 蜂窝 | 上游无实现 | IPA/QRTR | 3（官方无） | 允许自研 | 上游无实现，见 doc20 |",
    "输入": "| 输入 | ShengHidInput | Goodix | 3 | keep | `input-27.toml:3` |",
    "显示": "| 显示 | NativeLegacyDisplay | Mini 栈 | 1 | rewrite | `DISPLAY-27-DELTA.md:1` |",
    "GPU": "| GPU | Adreno740 | 落后副本 | 2 | re-vendor | `GPU-27-CONTRACT-DIFF.md:1` |",
    "存储": "| 存储 | ShengUfs | NativeUfs | 1 | adopt | `board.toml:360` |",
    "USB": "| USB | QcomDwc3 | 自研 | 1 | adopt | `board.toml:76` |",
    "CPU": "| CPU | ArmCpu 93a5030c | 779 行 fork | 1 | F2 后切回官方 | `ArmCpu.cpp:1` |",
}


def rows_with(**overrides: str) -> str:
    parts = []
    for key, value in GOOD.items():
        parts.append(overrides.get(key, value))
    return matrix(*parts)


ALL_ITEMS = {
    "audio": ["audio-27.toml"],
    "battery": ["power-27.toml"],
    "charger": ["power-27.toml"],
    "thermal": ["power-27.toml"],
    "bluetooth": ["bt-27.toml"],
    "wifi": ["wifi-27.toml"],
    "cellular": ["cellular-27.toml"],
    "touch": ["input-27.toml"],
    "buttons": ["input-27.toml"],
    "display": ["display-27.toml"],
    "gpu": ["gpu-27.toml"],
    "ufs": ["ufs-27.toml"],
    "usb": ["usb-27.toml"],
    "platform": ["platform-27.toml"],
}


class Tests:
    def __init__(self) -> None:
        self.checks = 0
        self.failures = 0

    def check(self, name: str, condition: bool) -> None:
        self.checks += 1
        if not condition:
            self.failures += 1
            print(f"FAIL {name}")

    def fails(self, name: str, matrix_text: str, needle: str, items=None) -> None:
        problems = MODULE.check(matrix_text, items or ALL_ITEMS)
        self.check(name, any(needle in problem for problem in problems))

    def passes(self, name: str, matrix_text: str, items=None) -> None:
        problems = MODULE.check(matrix_text, items or ALL_ITEMS)
        self.check(name, not problems)


def main() -> int:
    tests = Tests()
    tests.passes("pass.every_item_decided", rows_with())
    tests.fails("fail.undecided_row", rows_with(WiFi=GOOD["WiFi"].replace("keep 设备驱动", "待定")), "undecided")
    tests.fails("fail.no_rule", rows_with(GPU=GOOD["GPU"].replace("2 |", " |")), "rule 1, 2 or 3")
    tests.fails("fail.no_citation", rows_with(蓝牙=GOOD["蓝牙"].replace("`board.toml:14`", "见报告")), "cites no file:line")
    tests.fails("fail.missing_row", matrix(*[r for k, r in GOOD.items() if k != "存储"]), "no row for layer '存储'")
    tests.fails(
        "fail.unmapped_item",
        rows_with(),
        "no matrix layer is mapped",
        items={**ALL_ITEMS, "npu": ["npu-27.toml"]},
    )
    tests.passes(
        "pass.upstream_absent_counts_as_citation",
        rows_with(蜂窝=GOOD["蜂窝"]),
        items={"cellular": ["cellular-27.toml"]},
    )
    tests.check("fail.empty_matrix", bool(MODULE.check("# nothing\n", {"audio": ["a.toml"]})))
    tests.check("rows.parsed", len(MODULE.matrix_rows(rows_with())) == len(GOOD))
    tests.check(
        "cells.tolerates_unescaped_pipe_in_code",
        MODULE.cells("| a | `b:c` | d |") == ["a", "`b:c`", "d"],
    )
    print(f"{tests.checks - tests.failures}/{tests.checks} checks passed")
    if tests.failures:
        return 1
    print("OK the driver-architecture gate refuses every undecided or uncited ledger item")
    return 0


if __name__ == "__main__":
    sys.exit(main())
