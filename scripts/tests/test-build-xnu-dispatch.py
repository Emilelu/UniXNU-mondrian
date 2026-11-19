#!/usr/bin/env python3
"""One repository, two kernel builders: the dispatch must follow board.toml.

Regression cover for the trap that cost a CI run and an F1 attempt (P-255): the
device file scripts/build-xnu-4k-baseline.sh shadows the framework's generic
builder in the assembled tree, so whichever machine config it hard-codes is the
one both lines get. PONG does not exist in the 12377 tree.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PICKER = REPO / "scripts" / "pick-xnu-builder.sh"
failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"{'ok  ' if condition else 'FAIL'} {name}" + ("" if condition else f": {detail}"))
    if not condition:
        failures.append(name)


def pick(board_text: str | None) -> str:
    if board_text is None:
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as handle:
            return subprocess.run(["sh", str(PICKER), handle.name], capture_output=True, text=True).stdout.strip()
    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as handle:
        handle.write(board_text)
        handle.flush()
        return subprocess.run(["sh", str(PICKER), handle.name], capture_output=True, text=True).stdout.strip()


def main() -> int:
    pong = REPO / "scripts" / "build-xnu-4k-baseline.sh"
    generic = REPO / "scripts" / "build-xnu-generic.sh"

    check("the picker exists", PICKER.is_file())
    check("the generic builder is vendored", generic.is_file() and generic.stat().st_size > 10_000,
          f"{generic.stat().st_size if generic.is_file() else 0} bytes")
    check("the Pong builder is still the entry point", pong.is_file())

    chosen = pick('[board]\nos_profile = "ipados-16.6.1-20G81"\n')
    check("the 16.6.1 profile picks the Pong builder", chosen.endswith("build-xnu-4k-baseline.sh"), chosen)

    chosen = pick('[board]\nos_profile = "ios-27.0.1-24A446"\n')
    check("the iOS 27 profile picks the generic builder", chosen.endswith("build-xnu-generic.sh"), chosen)

    chosen = pick('[board]\n')
    check("a board with no profile falls back to the generic builder", chosen.endswith("build-xnu-generic.sh"), chosen)

    chosen = pick(None)
    check("an unreadable board does not crash the picker", chosen.endswith("build-xnu-generic.sh"), chosen)

    source = pong.read_text(encoding="utf-8")
    check("the entry point calls the picker", "pick-xnu-builder.sh" in source)
    check("the entry point execs the choice", "exec bash \"$CHOSEN_BUILDER\"" in source)
    # Match the call, not the prose: line 33 is a comment that mentions the same
    # string, and an index() on the bare text finds the comment first.
    call = "MACHINE_CONFIGS=PONG KERNEL_CONFIGS"
    dispatch_at = source.index("pick-xnu-builder.sh")
    call_sites = [i for i in range(len(source)) if source.startswith(call, i)]
    check("the Pong machine config is actually used", len(call_sites) == 2,
          f"{len(call_sites)} call site(s)")
    check("the dispatch runs before every Pong machine config call",
          all(dispatch_at < i for i in call_sites),
          f"dispatch at {dispatch_at}, calls at {call_sites}")

    # The vendored copy must stay recognisably the framework's builder, not the
    # Pong one: the Pong builder is the file with PONG in it.
    vendored = generic.read_text(encoding="utf-8")
    check("the vendored builder is not the Pong one", "MACHINE_CONFIGS=PONG" not in vendored)
    check("the vendored builder reads the profile environment", "UNIXNU_XNU_ARCH" in vendored)
    check("the vendored builder records where it came from", "Verbatim copy of the UniXNU generic kernel builder" in vendored)

    print()
    if failures:
        print(f"TESTS FAILED ({len(failures)})")
        return 1
    print("TESTS OK: the picker follows board.toml and the Pong builder is still the entry point")
    return 0


if __name__ == "__main__":
    sys.exit(main())
