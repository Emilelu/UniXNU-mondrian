#!/usr/bin/env python3
"""Tests for check-arg.py -- the pre-flight that proves a flight carried its flag.

Why these cases and not others: the failure this guards against is not "the
argument is wrong" (that is loud) but "the argument was never passed" (silent --
the driver takes its default and returns, and the console looks exactly like a
kernel fault).  cellular-l3-20261114d is the real instance: manifest says [''],
no pong_modem= anywhere in the bytes.  So every case below is about telling a
deliberate control from a forgotten flag, and about the trial-build shape where
the manifest has no kernel_args_requested field at all.

Run: python3 scripts/tests/test-check-arg.py
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
CHECK = HERE.parent / "check-arg.py"

_SPEC = importlib.util.spec_from_file_location("check_arg", CHECK)
_CHECK_ARG = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_CHECK_ARG)

CASES = 0
FAILED = 0
SKIPPED = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global CASES, FAILED
    CASES += 1
    if ok:
        print("PASS " + name)
    else:
        FAILED += 1
        print("FAIL " + name + ("  " + detail if detail else ""))


def make(tmp: pathlib.Path, args: list[str], manifest: dict | None) -> pathlib.Path:
    """One capture directory: boot.json pointing at boot.img, plus a manifest."""
    art = tmp / "artifact"
    art.mkdir(parents=True, exist_ok=True)
    img = art / "boot.img"
    img.write_bytes(b"\x00" * 64 + " ".join(args).encode() + b"\x00" * 64)
    if manifest is not None:
        (art / "build-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    cap = tmp / "capture"
    cap.mkdir(parents=True, exist_ok=True)
    (cap / "boot.json").write_text(json.dumps({"image": str(img), "imageSha256": "00"}), encoding="utf-8")
    return cap


def run(cap: pathlib.Path, expect: str) -> tuple[int, str]:
    p = subprocess.run([sys.executable, str(CHECK), str(cap), expect],
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main() -> int:
    global SKIPPED
    with tempfile.TemporaryDirectory() as raw:
        tmp = pathlib.Path(raw)

        # unit: the WSL mount mapping is a pure function, test it on both hosts
        check("wsl_of maps E:/... to /mnt/e/...",
              _CHECK_ARG.wsl_of(r"E:\iOS Port\Work\artifacts\x\boot.img")
              == pathlib.Path("/mnt/e/iOS Port/Work/artifacts/x/boot.img"))
        check("wsl_of maps a drive root",
              _CHECK_ARG.wsl_of(r"C:\a\b") == pathlib.Path("/mnt/c/a/b"))
        check("wsl_of leaves non-Windows paths alone",
              _CHECK_ARG.wsl_of("/mnt/e/x") is None
              and _CHECK_ARG.wsl_of("relative") is None)

        cap = make(tmp / "carries", ["debug=0x140", "pong_wifi=0"],
                   {"kernel_args_requested": ["pong_wifi=0"]})
        rc, out = run(cap, "pong_wifi=0")
        check("an image that carries the flag passes", rc == 0, out)

        # the real cellular-l3-20261114d shape: the line carries other pong_
        # arguments, so the message must name the one that is missing rather
        # than say "no pong_ argument at all"
        cap = make(tmp / "forgot", ["debug=0x140", "pong_adreno_start=1"],
                   {"kernel_args_requested": [""]})
        rc, out = run(cap, "pong_modem=2")
        check("the real forgotten-flag shape is refused (rc=4)", rc == 4, out)
        check("the refusal names the missing argument",
              "does not carry pong_modem=2" in out, out)

        cap = make(tmp / "trial", ["pong_wifi=0"], {"tag": "t", "note": "trial"})
        rc, out = run(cap, "pong_wifi=0")
        check("a trial manifest without the field still passes on the bytes",
              rc == 0, out)
        check("and it says the bytes decided",
              "bytes decide" in out, out)

        cap = make(tmp / "wrong", ["pong_wifi=1"],
                   {"kernel_args_requested": ["pong_wifi=0"]})
        rc, out = run(cap, "pong_wifi=0")
        check("a manifest that lies about the bytes does not decide (rc=4)",
              rc == 4, out)
        check("the bytes are reported even when they disagree",
              "pong_wifi=1 x1" in out, out)

        cap = make(tmp / "empty", ["debug=0x140"], {"kernel_args_requested": [""]})
        rc, out = run(cap, "pong_wifi=0")
        check("an image with no pong_ argument at all is refused", rc == 4, out)

        cap = make(tmp / "skip", ["debug=0x140"], None)
        rc, out = run(cap, "")
        check("an empty expectation skips instead of failing", rc == 0, out)
        check("and it says so", "skipped" in out, out)

        # integration: a boot.json image path in Windows form must resolve
        # through the /mnt/e mount when running under WSL.  On hosts without
        # the mount the case is skipped out loud, never silently dropped.
        mount = pathlib.Path("/mnt/e")
        scratch = pathlib.Path("/mnt/e/iOS Port/Work/scratch/refmine")
        etmp = pathlib.Path("/mnt/e/tmp")
        base = scratch if scratch.exists() else (etmp if etmp.exists() else None)
        if mount.exists() and base is not None:
            with tempfile.TemporaryDirectory(dir=str(base)) as wraw:
                wtmp = pathlib.Path(wraw)
                art = wtmp / "artifact"
                art.mkdir()
                img = art / "boot.img"
                img.write_bytes(b"\x00" * 64 + b"pong_wifi=0" + b"\x00" * 64)
                cap = wtmp / "capture"
                cap.mkdir()
                win = "E:\\" + str(img.relative_to("/mnt/e")).replace("/", "\\")
                (cap / "boot.json").write_text(
                    json.dumps({"image": win, "imageSha256": "00"}),
                    encoding="utf-8")
                rc, out = run(cap, "pong_wifi=0")
                check("a Windows image path resolves through /mnt/e",
                      rc == 0, out)
        else:
            SKIPPED += 1
            print("SKIP (no /mnt/e mount on this host): wsl-path case")

    print()
    if FAILED:
        print("TESTS FAILED %d of %d cases" % (FAILED, CASES))
        return 1
    print("TESTS OK %d cases (%d failure(s), %d skipped)" % (CASES, FAILED, SKIPPED))
    return 0


if __name__ == "__main__":
    sys.exit(main())
