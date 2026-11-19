#!/usr/bin/env python3
"""Fly one cellular candidate and judge it in the same command.

The lead asked for one command that decides a flight: this wraps the sanctioned
entry point (scripts/flash.sh, iron rule 8) and then hands the evidence to
scripts/judge-cellular-flight.py, so the verdict and the boot cannot drift apart.

Usage:
  python3 scripts/fly-cellular.py --image /path/boot-modem-b-full.img \
      --manifest /path/manifest-k53.json --seconds 420

Exit codes: 0 PASS, 1 FAILED, 2 INVALID, 3 refused (wrong device state, image or
manifest mismatch), 4 no evidence directory appeared.
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVIDENCE = "/mnt/e/k60-work/evidence"


def sha256(path):
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_of_file(path):
    return sha256(path)


def manifest_image(manifest, path):
    # The manifests written by the k4x/k5x scripts carry one top-level entry:
    # {"image": {"path": "boot-modem-b-full.img", "bytes": ..., "sha256": ...}}.
    with open(manifest, encoding="utf-8") as handle:
        data = json.load(handle)
    name = os.path.basename(path)
    for key in ("image", "boot_image"):
        entry = data.get(key)
        if isinstance(entry, dict):
            if os.path.basename(entry.get("path") or entry.get("name") or "") == name:
                return entry
    for entry in data.get("images", []):
        if os.path.basename(entry.get("path") or entry.get("name") or "") == name:
            return entry
    return None


def check_image(image, manifest):
    """Returns a list of refusal strings; empty means the image is the one built."""
    problems = []
    if not os.path.isfile(image):
        return ["image not found: %s" % image]
    digest = sha256_of_file(image)
    size = os.path.getsize(image)
    print("image   %s" % image)
    print("  sha256 %s" % digest)
    print("  bytes  %d" % size)
    if manifest:
        entry = manifest_image(manifest, image)
        if entry is None:
            problems.append("manifest %s does not describe %s"
                            % (manifest, os.path.basename(image)))
        else:
            for field, actual in (("sha256", digest), ("bytes", size)):
                want = entry.get(field)
                if want is not None and want != actual:
                    problems.append("manifest says %s %s, the file is %s"
                                    % (field, want, actual))
    return problems


def device_state():
    out = subprocess.run(["bash", os.path.join(REPO, "scripts", "k60-device.sh"),
                          "state"], capture_output=True, text=True)
    return (out.stdout or out.stderr).strip().splitlines()[-1:] or [""]


def newest_evidence(started):
    best = None
    for path in glob.glob(os.path.join(EVIDENCE, "usblog-*")):
        if not os.path.isdir(path):
            continue
        if os.path.getmtime(path) + 1.0 < started:
            continue
        if best is None or os.path.getmtime(path) > os.path.getmtime(best):
            best = path
    return best


def main():
    parser = argparse.ArgumentParser(description="Fly a cellular candidate and judge it")
    parser.add_argument("--image", help="boot image to boot")
    parser.add_argument("--manifest", help="manifest.json the image was built for")
    parser.add_argument("--seconds", type=int, default=420,
                        help="capture window handed to flash.sh (default 420)")
    parser.add_argument("--window", type=int, default=None,
                        help="judging window in seconds (default: the judge's own)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the commands instead of booting")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.image:
        parser.error("--image is required")

    problems = check_image(args.image, args.manifest)
    if problems:
        for problem in problems:
            print("REFUSED %s" % problem)
        return 3

    flash = ["bash", os.path.join(REPO, "scripts", "flash.sh"), args.image,
             str(args.seconds)]
    judge = [sys.executable, os.path.join(REPO, "scripts",
                                          "judge-cellular-flight.py")]
    if args.window is not None:
        judge += ["--window", str(args.window)]

    state = device_state()
    print("device  %s" % (state[0] if state else "unknown"))
    if state != ["fastboot"]:
        if args.dry_run:
            print("note    the real run would refuse: the board is %s, not fastboot"
                  % (state[0] if state else "unknown"))
        else:
            print("REFUSED the board is not in fastboot: flash.sh boots, it "
                  "does not rebuild the device state")
            return 3

    if args.dry_run:
        print("would run: %s" % " ".join(flash))
        print("would run: %s <evidence>" % " ".join(judge))
        return 0

    started = time.time()
    print("booting %s for %d s" % (os.path.basename(args.image), args.seconds))
    code = subprocess.call(flash)
    print("flash.sh exit %d" % code)

    evidence = newest_evidence(started)
    if evidence is None:
        print("NO EVIDENCE: flash.sh ran but no usblog-* appeared under %s" % EVIDENCE)
        return 4
    print("evidence %s" % evidence)
    console = os.path.join(evidence, "console.log")
    if os.path.isfile(console):
        print("console  %d bytes sha256 %s" % (os.path.getsize(console),
                                               sha256_of_file(console)))
    verdict = subprocess.call(judge + [evidence])
    print("verdict  %d (0 PASS, 1 FAILED, 2 INVALID)" % verdict)
    return verdict


def self_test():
    """The manifest check must refuse a mismatched image and accept the real one."""
    import tempfile
    with tempfile.TemporaryDirectory() as work:
        image = os.path.join(work, "boot-modem-b-full.img")
        with open(image, "wb") as handle:
            handle.write(b"K60" * 16)
        digest = sha256_of_file(image)
        manifest = os.path.join(work, "manifest.json")
        with open(manifest, "w", encoding="utf-8") as handle:
            json.dump({"images": [{"name": os.path.basename(image),
                                   "sha256": digest,
                                   "bytes": os.path.getsize(image)}]}, handle)
        if check_image(image, manifest):
            print("K60 FLY FAIL a matching manifest was refused")
            return 1
        with open(manifest, "w", encoding="utf-8") as handle:
            json.dump({"images": [{"name": os.path.basename(image),
                                   "sha256": "0" * 64,
                                   "bytes": 1}]}, handle)
        refused = check_image(image, manifest)
        if len(refused) != 2:
            print("K60 FLY FAIL expected two mismatches, got %r" % (refused,))
            return 1
        if check_image(os.path.join(work, "absent.img"), None) == []:
            print("K60 FLY FAIL a missing image was accepted")
            return 1
    print("K60 FLY PASS manifest match, mismatch, missing image")
    return 0


if __name__ == "__main__":
    sys.exit(main())
