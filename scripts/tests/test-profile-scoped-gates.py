#!/usr/bin/env python3
"""A gate that reads one OS profile must not grade the other one.

Two gates hardcoded the iOS 16.6.1 world and then judged a build that no longer
reads it:

* `scripts/check-config-consistency.py` compared the generated `.config` against
  `configs/mondrian_defconfig` and `out/mondrian/ipados-16.6.1-20G81/mondrian/`.
  Once main's default profile became `ios-27.0.1-24A446` the build writes
  `out/mondrian/ios-27.0.1-24A446/mondrian_ios27/` from
  `configs/mondrian_ios27_defconfig`, so the gate reported a missing file in a
  tree nobody builds (P-256).
* `scripts/check-blob-patches.py` policed 0340 / 0391 / 0401 / 0616, which live in
  `patches/xnu/series`. The 27 profile applies `patches/xnu-12377/series`, where
  none of them appears, so "the blob baseline is gone, boot again" was a false
  verdict for every 27 build.

Both now resolve the profile through `board.toml` the way scripts/unixnu does.
These cases pin the resolution, not the verdicts, so flipping the default profile
does not require editing this file.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CASES = []
FAILURES = []


def case(fn):
    CASES.append(fn)
    return fn


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module          # dataclasses resolves through sys.modules
    spec.loader.exec_module(module)
    return module


def board() -> dict:
    with (REPO / "board.toml").open("rb") as handle:
        return tomllib.load(handle)


def merged_kernel(data: dict, profile: str) -> dict:
    import copy

    chosen = copy.deepcopy(data.get("os_overrides", {}).get(profile, {}))
    chosen.pop("remove", None)
    kernel = dict(data.get("kernel", {}))
    kernel.update(chosen.get("kernel", {}))
    return kernel


@case
def the_default_defconfig_follows_the_board():
    data = board()
    profile = data["board"]["os_profile"]
    name = merged_kernel(data, profile)["defconfig"]
    module = load("check_config_consistency", "scripts/check-config-consistency.py")
    expected = REPO / "configs" / f"{name.removesuffix('_defconfig')}_defconfig"
    assert module.DEFAULT_DEFCONFIG == expected, (
        f"DEFAULT_DEFCONFIG {module.DEFAULT_DEFCONFIG} but board selects {expected}"
    )
    assert expected.is_file(), f"{expected} does not exist"


@case
def the_defconfig_suffix_is_not_doubled():
    module = load("check_config_consistency_suffix", "scripts/check-config-consistency.py")
    want = REPO / "configs" / "mondrian_ios27_defconfig"
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "board.toml"
        for spelling in ("mondrian_ios27_defconfig", "mondrian_ios27"):
            path.write_text(
                f'[board]\nos_profile = "x"\n[kernel]\ndefconfig = "{spelling}"\n',
                encoding="utf-8",
            )
            got = module.board_defconfig(path)
            assert got == want, f"{spelling} resolved to {got}"


@case
def the_merged_kernel_differs_from_the_bare_table():
    """The default profile's values live in [os_overrides], not in [kernel].

    After main flipped to iOS 27 the override table describes the *default*
    profile, so the interesting assertion is not "two overrides disagree" but
    "merging changes the answer": a resolver that ignored [os_overrides] would
    return the bare [kernel] table, which is the iOS 16.6.1 board.
    """
    data = board()
    profile = data["board"]["os_profile"]
    bare = data["kernel"]["defconfig"]
    merged = merged_kernel(data, profile)["defconfig"]
    assert merged != bare, (
        f"the override for {profile} does not change defconfig ({bare}); "
        "nothing here would notice a resolver that ignores [os_overrides]"
    )
    for name in (bare, merged):
        want = REPO / "configs" / f"{name.removesuffix('_defconfig')}_defconfig"
        assert want.is_file(), f"{name} is not a defconfig on disk"
    module = load("check_config_consistency_override", "scripts/check-config-consistency.py")
    assert module.DEFAULT_DEFCONFIG.name == f"{merged.removesuffix('_defconfig')}_defconfig", (
        f"the gate resolved {module.DEFAULT_DEFCONFIG.name}, the merged board says {merged}"
    )


@case
def the_blob_gate_reads_the_profile_series():
    module = load("check_blob_patches", "scripts/check-blob-patches.py")
    entries = module.applied_series()
    assert entries, "applied_series() resolved nothing; patch_series was not read"
    data = board()
    kernel = merged_kernel(data, data["board"]["os_profile"])
    marker = str(kernel["patch_series"][0]).partition(":")[2]
    inside = [e for e in entries if e.startswith(marker.split("/")[0] + "/")]
    assert inside, f"{marker} contributed no entries; got {sorted(entries)[:3]}"


@case
def out_of_scope_blob_patches_are_reported_not_silently_dropped():
    module = load("check_blob_patches_scope", "scripts/check-blob-patches.py")
    entries = module.applied_series()
    source = (REPO / "scripts/check-blob-patches.py").read_text(encoding="utf-8")
    assert "不在当前 OS profile 的 series 里" in source, (
        "the out-of-scope note is gone; a skipped patch would look like a pass"
    )
    profile = board()["board"]["os_profile"]
    resolved = [rel for rel in module.BLOB_PATCHES if rel in entries]
    if profile.startswith("ios-27"):
        assert not resolved, f"the 27 profile resolved 16-line blob patches: {resolved}"


def main() -> int:
    for fn in CASES:
        try:
            fn()
        except AssertionError as error:
            FAILURES.append(f"{fn.__name__}: {error}")
            print(f"FAIL {fn.__name__}")
        except Exception as error:                     # noqa: BLE001 - report everything
            FAILURES.append(f"{fn.__name__}: {type(error).__name__}: {error}")
            print(f"ERROR {fn.__name__}: {type(error).__name__}: {error}")
        else:
            print(f"ok   {fn.__name__}")
    print(f"TESTS {'OK' if not FAILURES else 'FAILED'}: "
          f"{len(CASES) - len(FAILURES)}/{len(CASES)}")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    raise SystemExit(main())