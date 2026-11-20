#!/usr/bin/env python3
"""Report what opening the Data mount gate actually requires.

0526/0527 only compile inside #if XNU_OWNER_DATA_MOUNT, so Bluetooth runtime
mounts need that switch. Since 3cc8cbc9 the iOS 27 kernel is built by
scripts/build-xnu-generic.sh, which refuses the switch unless a chain of owner
switches is already satisfied -- each link has its own echo and exit 1. Flipping
CONFIG_XNU_OWNER_DATA_MOUNT=y on its own therefore does not build, and the
rejection happens in the builder, not in the patch series.

This checker reads the builder, binds every link by its message text, evaluates
the chain against the selected defconfig, and answers two questions:

  * is the switch consistent today (off without partial prerequisites)?
  * what would F3 have to set, in order, to open it?

Usage:
    python3 scripts/check-bluetooth-data-gate-chain.py
    python3 scripts/check-bluetooth-data-gate-chain.py --defconfig configs/mondrian_defconfig
    python3 scripts/check-bluetooth-data-gate-chain.py --out out/data-gate
    python3 scripts/check-bluetooth-data-gate-chain.py \
        --layer ../UniXNU/profiles/arch/arm64e/configs/common.config \
        --layer ../UniXNU-sm8475-common/configs/sm8475.config \
        --layer ../UniXNU/profiles/os/ios-27.0.1-24A446/configs/ios.config

board.toml lists the fragments in [kernel] config_fragments and cli.py:123-135
concatenates them ahead of the device defconfig, so a value the profile sets and
the device defconfig does not repeat is still in the build. Without --layer the
checker sees only the device file and reports satisfied prerequisites as gaps.
"""
import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILDER = ROOT / "scripts" / "build-xnu-generic.sh"
DEFCONFIG = ROOT / "configs" / "mondrian_ios27_defconfig"

# (switch, requirement message in the builder, alternatives of (name, value))
# Every message is asserted to exist in the builder, so a reworded rule fails
# here instead of silently dropping out of the model.
CHAIN = [
    ("XNU_OWNER_DATA_MOUNT",
     "Scratch Data requires authenticated original OS/owner metadata startup",
     [[("XNU_OWNER_BOOT_MANIFEST", "1")]]),
    ("XNU_OWNER_BOOT_MANIFEST",
     "Owner boot metadata requires real authenticated owner root/cache startup",
     [[("XNU_OWNER_CACHE_STARTUP", "1")]]),
    ("XNU_OWNER_CACHE_STARTUP",
     "Owner dyld startup selection requires authenticated actual cache mounting",
     [[("XNU_OWNER_CACHE_MOUNT", "1")]]),
    ("XNU_OWNER_CACHE_MOUNT",
     "The offline SystemOS mount requires real independent owner root enforcement",
     [[("XNU_OWNER_ROOT_TRUST", "1")]]),
    ("XNU_OWNER_ROOT_TRUST",
     "Owner root acceptance requires actual mounted-media binding and verified block storage",
     [[("XNU_OWNER_ROOT_AUDIT", "1"), ("XNU_NATIVE_VIRTIO_BLOCK", "1")],
      [("XNU_OWNER_ROOT_AUDIT", "1"), ("XNU_SOURCE_STORAGE", "1")]]),
    ("XNU_OWNER_ROOT_AUDIT",
     "The root-binding audit requires real owner-verified block crypto",
     [[("XNU_VERIFIED_ROOT_PROBE", "1")], [("XNU_SOURCE_STORAGE", "1")]]),
    ("XNU_VERIFIED_ROOT_PROBE",
     "The owner crypto probe requires the qualified original prelinked crypto provider",
     [[("XNU_SOURCE_CORECRYPTO14", "1"), ("XNU_CRYPTO_BOOTSTRAP", "prelinked")]]),
    ("XNU_NATIVE_RAM_BLOCK",
     "NativeRamBlock requires the qualified original storage/AES prelink closure",
     [[("XNU_SOURCE_STORAGE", "1")], [("XNU_NATIVE_AES", "1")]]),
]

BACKENDS = ("XNU_NATIVE_RAM_BLOCK", "XNU_OWNER_DATA_UFS")


def parse_defconfig(layers):
    """CONFIG_XNU_FOO=y -> XNU_FOO=1, =n -> 0, ="text" -> text.

    Layers merge in the order the build concatenates them, so the last file
    wins; the origin map remembers which file and line supplied the value."""
    values = {}
    origin = {}
    for path in layers:
        for number, line in enumerate(path.read_text().splitlines(), 1):
            match = re.match(r'^\s*CONFIG_(XNU_[A-Z0-9_]+)\s*=\s*(.+?)\s*$', line)
            if not match:
                continue
            name, raw = match.group(1), match.group(2)
            if raw in ("y", "n"):
                values[name] = "1" if raw == "y" else "0"
            elif raw.startswith(chr(34)) and raw.endswith(chr(34)):
                values[name] = raw[1:-1]
            else:
                values[name] = raw
            origin[name] = f"{path.name}:{number}"
    return values, origin


def switch_on(values, name):
    return values.get(name, "0") == "1"


def requirements(values, name):
    for switch, message, alternatives in CHAIN:
        if switch == name:
            return message, alternatives
    return None, None


def unmet(values, name):
    """All (alternative index, missing pairs) that would reject this switch."""
    message, alternatives = requirements(values, name)
    if message is None:
        return []
    gaps = []
    for index, alternative in enumerate(alternatives):
        missing = [pair for pair in alternative if values.get(pair[0], "0") != pair[1]]
        if not missing:
            return []          # this alternative is satisfied; nothing to close
        gaps.append((index, missing))
    return gaps


def closure(values, start):
    """Breadth-first walk of the chain from start; returns ordered (switch, missing)."""
    order = []
    seen = set()
    queue = [start]
    while queue:
        name = queue.pop(0)
        if name in seen:
            continue
        seen.add(name)
        for index, missing in unmet(values, name):
            order.append((name, index, missing))
        for _, alternatives in [requirements(values, name)]:
            for alternative in alternatives or []:
                for pair in alternative:
                    if pair[0] in [entry[0] for entry in CHAIN] and pair[0] not in seen:
                        queue.append(pair[0])
    return order


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--builder", default=str(BUILDER))
    parser.add_argument("--defconfig", default=str(DEFCONFIG))
    parser.add_argument("--layer", action="append", default=[],
                        help="profile config fragment merged ahead of the defconfig; repeat in build order")
    parser.add_argument("--out", help="write a JSON report here")
    args = parser.parse_args()

    builder = pathlib.Path(args.builder)
    defconfig = pathlib.Path(args.defconfig)
    failures = []

    if not builder.exists():
        print(f"FAIL builder {builder} not found")
        print("bluetooth-data-gate-chain: FAILED")
        return 1
    text = builder.read_text()
    for switch, message, _ in CHAIN:
        if message not in text:
            failures.append(f"the builder no longer carries the rule for {switch}: {message!r}")

    layers = [pathlib.Path(entry) for entry in args.layer] + [defconfig]
    for layer in layers:
        if not layer.exists():
            print(f"FAIL layer {layer} not found")
            print("bluetooth-data-gate-chain: FAILED")
            return 1
    values, origin = parse_defconfig(layers)

    print(f"builder: {builder.name}, {len(CHAIN)} chained rules")
    print(f"config: {len(values)} CONFIG_XNU_* values from {len(layers)} layer(s): "
          + ", ".join(layer.name for layer in layers))
    chain_keys = {name for name, _, _ in CHAIN}
    for _, _, alternatives in CHAIN:
        for alternative in alternatives:
            for name, _value in alternative:
                chain_keys.add(name)
    for name in sorted(name for name in chain_keys if name in values):
        print(f"  {name}={values[name]} ({origin[name]})")
    mounted = switch_on(values, "XNU_OWNER_DATA_MOUNT")
    print(f"switch: XNU_OWNER_DATA_MOUNT={'1' if mounted else '0'}")

    # A switch that is on must satisfy its own prerequisites, otherwise the
    # builder stops on the next line and the kernel never gets built.
    for switch, message, _ in CHAIN:
        if not switch_on(values, switch):
            continue
        missing = unmet(values, switch)
        if missing:
            pairs = "; ".join(
                f"alternative {index + 1} needs " + ", ".join(f"{n}={v}" for n, v in gap)
                for index, gap in missing
            )
            failures.append(f"{switch}=1 but {message}: {pairs}")

    backends = [name for name in BACKENDS if switch_on(values, name)]
    if mounted and not backends:
        failures.append(
            "XNU_OWNER_DATA_MOUNT=1 without a Data backend: set "
            + " or ".join(BACKENDS)
        )
    if mounted and "XNU_OWNER_DATA_UFS" in values and "XNU_OWNER_DATA_UFS" not in text:
        failures.append(
            "XNU_OWNER_DATA_UFS is set but the generic builder has no such knob; "
            "the 16.6.1 builder carried it, the 12377 one does not"
        )

    print(f"backends: {', '.join(backends) or 'none declared'}")
    if mounted:
        print("state: open -- the gate and its prerequisites are set")
    else:
        print("state: closed -- expected on stage-0; the chain below is what F3 must close")

    walk = closure(values, "XNU_OWNER_DATA_MOUNT")
    if walk:
        print("chain to open the gate:")
        for name, index, missing in walk:
            gap = ", ".join(f"{n}={v}" for n, v in missing)
            print(f"  {name}: set {gap} (alternative {index + 1})")
    if "XNU_NATIVE_RAM_BLOCK" not in text:
        print("note: the generic builder does not mention XNU_NATIVE_RAM_BLOCK")

    report = {
        "builder": builder.name,
        "defconfig": defconfig.name,
        "gate_enabled": mounted,
        "backends": backends,
        "chain": [{"switch": n, "alternative": i + 1,
                   "missing": [f"{a}={b}" for a, b in m]} for n, i, m in walk],
        "failures": failures,
        "hardware_verified": False,
    }
    if args.out:
        out = pathlib.Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"report: {out / 'report.json'}")

    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        print("bluetooth-data-gate-chain: FAILED")
        return 1
    print("bluetooth-data-gate-chain: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
