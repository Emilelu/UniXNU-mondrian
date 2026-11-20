#!/usr/bin/env python3
"""Cases for scripts/check-bluetooth-data-gate-chain.py.

The generic builder has two routes through the chain and no debug escape, so the
fixtures model both of them instead of assuming the 16.6.1 shortcut exists.
"""
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CHECK = ROOT / "scripts" / "check-bluetooth-data-gate-chain.py"
REAL_BUILDER = ROOT / "scripts" / "build-xnu-generic.sh"

BASE = {
    "CONFIG_XNU_OWNER_DATA_MOUNT": "y",
    "CONFIG_XNU_OWNER_BOOT_MANIFEST": "y",
    "CONFIG_XNU_OWNER_CACHE_STARTUP": "y",
    "CONFIG_XNU_OWNER_CACHE_MOUNT": "y",
    "CONFIG_XNU_OWNER_ROOT_TRUST": "y",
    "CONFIG_XNU_OWNER_ROOT_AUDIT": "y",
    "CONFIG_XNU_NATIVE_RAM_BLOCK": "y",
}
STORAGE = dict(BASE, **{"CONFIG_XNU_SOURCE_STORAGE": "y"})
PROBE = dict(STORAGE, **{
    "CONFIG_XNU_VERIFIED_ROOT_PROBE": "y",
    "CONFIG_XNU_SOURCE_CORECRYPTO14": "y",
    "CONFIG_XNU_CRYPTO_BOOTSTRAP": '"prelinked"',
})

CASES = []
failures = []


def case(name, ok):
    CASES.append((name, ok))
    if not ok:
        failures.append(name)


def render(values):
    return "".join(f"{k}={v}\n" for k, v in values.items())


def run(values, builder=None, layers=None):
    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        (base / "defconfig").write_text(render(values))
        command = [sys.executable, str(CHECK),
                   "--defconfig", str(base / "defconfig"),
                   "--builder", str(builder or REAL_BUILDER)]
        for index, layer in enumerate(layers or []):
            path = base / f"layer{index}.config"
            path.write_text(render(layer))
            command += ["--layer", str(path)]
        return subprocess.run(command, capture_output=True, text=True)


def drop(values, name):
    return {k: v for k, v in values.items() if k != name}


shipped = subprocess.run(
    [sys.executable, str(CHECK),
     "--defconfig", str(ROOT / "configs" / "mondrian_ios27_defconfig")],
    capture_output=True, text=True)
case("the shipped defconfig is closed and consistent", shipped.returncode == 0)

# Route 1: the source-storage chain.
case("source storage alone carries the whole chain", run(STORAGE).returncode == 0)
for name in ("CONFIG_XNU_OWNER_BOOT_MANIFEST", "CONFIG_XNU_OWNER_CACHE_STARTUP",
             "CONFIG_XNU_OWNER_CACHE_MOUNT", "CONFIG_XNU_OWNER_ROOT_TRUST",
             "CONFIG_XNU_OWNER_ROOT_AUDIT", "CONFIG_XNU_SOURCE_STORAGE"):
    case(f"removing {name} is rejected", run(drop(STORAGE, name)).returncode != 0)

# Route 2: virtio block plus the prelinked crypto probe.
BLOCK = dict(STORAGE, **{"CONFIG_XNU_NATIVE_VIRTIO_BLOCK": "y"})
BLOCK = dict(BLOCK, **{"CONFIG_XNU_VERIFIED_ROOT_PROBE": "y",
                       "CONFIG_XNU_SOURCE_CORECRYPTO14": "y",
                       "CONFIG_XNU_CRYPTO_BOOTSTRAP": '"prelinked"'})
case("virtio block with the crypto probe carries the chain", run(BLOCK).returncode == 0)
case("the probe without prelinked crypto is rejected",
     run(drop(drop(drop(PROBE, "CONFIG_XNU_CRYPTO_BOOTSTRAP"), "CONFIG_XNU_SOURCE_STORAGE"), "CONFIG_XNU_NATIVE_RAM_BLOCK")).returncode != 0)

# The backend is a separate requirement from the switch.
case("the gate without a backend is rejected", run(drop(STORAGE, "CONFIG_XNU_NATIVE_RAM_BLOCK")).returncode != 0)

# The 16.6.1 knob has no counterpart in the generic builder.
case("XNU_OWNER_DATA_UFS is reported as unknown", run(
    dict(STORAGE, **{"CONFIG_XNU_OWNER_DATA_UFS": "y"})).returncode != 0)

# A rewritten rule must fail loudly instead of dropping out of the model.
with tempfile.TemporaryDirectory() as tmp:
    fake = pathlib.Path(tmp) / "builder.sh"
    fake.write_text(REAL_BUILDER.read_text().replace(
        "Scratch Data requires authenticated original OS/owner metadata startup",
        "Scratch Data needs something else now"))
    case("a reworded builder rule fails the checker", run(STORAGE, fake).returncode != 0)

# Closed state must still print the chain F3 has to close.
closed = run({})
case("the closed run still prints the chain", "chain to open the gate" in closed.stdout)
case("the closed run passes", closed.returncode == 0)

# The build concatenates the profile fragments ahead of the device defconfig
# (cli.py:123-135), so a value only the profile sets is still in the build.
PROFILE = {"CONFIG_XNU_SOURCE_CORECRYPTO14": "y"}
layered = dict(STORAGE, **{"CONFIG_XNU_VERIFIED_ROOT_PROBE": "y",
                           "CONFIG_XNU_CRYPTO_BOOTSTRAP": '"prelinked"'})
result = run(layered, layers=[PROFILE])
case("a profile layer satisfies a prerequisite the defconfig omits", result.returncode == 0)
case("the run names the layer that supplied the value",
     "XNU_SOURCE_CORECRYPTO14=1 (layer0.config:1)" in result.stdout)

# Without the layer the same values fail, which is what made the old checker
# report satisfied prerequisites as gaps.
case("without the layer the same defconfig is rejected", run(layered).returncode != 0)

# The device defconfig is appended last, so it wins over a profile fragment.
overridden = run(dict(layered, **{"CONFIG_XNU_CRYPTO_BOOTSTRAP": '"source"'}),
                 layers=[PROFILE, {"CONFIG_XNU_CRYPTO_BOOTSTRAP": '"prelinked"'}])
case("the device defconfig overrides a later profile value", overridden.returncode != 0)

with tempfile.TemporaryDirectory() as tmp:
    command = [sys.executable, str(CHECK),
               "--defconfig", str(ROOT / "configs" / "mondrian_ios27_defconfig"),
               "--builder", str(REAL_BUILDER),
               "--layer", str(pathlib.Path(tmp) / "absent.config")]
    gone = subprocess.run(command, capture_output=True, text=True)
case("a missing layer fails instead of being skipped", gone.returncode != 0)
case("the shipped defconfig alone still prints the chain",
     "chain to open the gate" in shipped.stdout)

print(f"bluetooth-data-gate-chain test: {len(CASES)} case(s)")
for name, passed in CASES:
    print(("  ok   " if passed else "  FAIL ") + name)
print("TESTS OK" if not failures else f"TESTS FAILED: {failures}")
sys.exit(0 if not failures else 1)
