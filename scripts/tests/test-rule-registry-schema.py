#!/usr/bin/env python3
"""test-rule-registry-schema.py — P-239: a registry union must assert on the schema.

Why this exists
---------------
While merging `consolidate/20261119` into the GPU branch, both sides of
`docs/engineering/RULES.toml` had appended pitfall rules. The union split each
side on the literal `[[rule]]` header and re-emitted the blocks in numeric
order. P-230's block on the near side ended with its `check` line *after* the
last header, so the splitter treated that line as belonging to no block and it
was dropped. The registry then refused the build with

    ❌ 覆盖缺口：
       - P-230 既没有 check 也没有 waiver

The gate was right and the merge was wrong. The lesson is not "be careful": it
is that a block split is only safe if the whole side of the conflict is
consumed, so any union must re-assert the schema afterwards instead of trusting
the split. This test does that, and it is deliberately independent of the merge
script so it also catches a hand edit.

What it asserts
---------------
1. The file parses and every rule has a non-empty `id`.
2. Every rule has a `check` or a `waiver` — the condition the registry enforces,
   reported here by name instead of as a refused build.
3. Ids are unique.
4. Within each id family (iron / hard / P) numbers increase, so a union that
   appended in the wrong place is visible rather than merely valid. Families are
   allowed to interleave: the registry is grouped by origin, not by number.
5. Where `kind` is present it is one of the known kinds. It is optional because
   P-224..P-226 were registered without one and the registry does not require it.
6. Every `check` names files that exist, so a rule cannot point at a renamed test.
"""
import pathlib
import re
import sys
import tomllib

REPO = pathlib.Path(__file__).resolve().parents[2]
REGISTRY = REPO / "docs/engineering/RULES.toml"
KNOWN_KINDS = {"iron", "hard", "pitfall"}

failures: list[str] = []


def fail(message: str) -> None:
    failures.append(message)


def main() -> int:
    data = tomllib.loads(REGISTRY.read_text(encoding="utf-8"))
    rules = data.get("rule") or []
    if not rules:
        fail("the registry has no [[rule]] entries at all")
        return report()

    seen: set[str] = set()
    families: dict[str, list[tuple[int, str]]] = {}
    for rule in rules:
        ident = str(rule.get("id") or "").strip()
        if not ident:
            fail("a rule has no id")
            continue
        if ident in seen:
            fail(f"{ident}: duplicate id")
        seen.add(ident)

        if not rule.get("check") and not rule.get("waiver"):
            fail(f"{ident}: neither check nor waiver — the registry will refuse a build")

        kind = rule.get("kind")
        if kind is not None and kind not in KNOWN_KINDS:
            fail(f"{ident}: unknown kind {kind!r}")

        m = re.match(r"^(iron|hard|P)-?(\d+)$", ident)
        if m:
            families.setdefault(m.group(1), []).append((int(m.group(2)), ident))

        for token in str(rule.get("check") or "").split():
            if token.endswith((".py", ".sh")) and not (REPO / token).exists():
                fail(f"{ident}: check names a missing file {token}")

    for family, numbered in families.items():
        for (a_num, a_id), (b_num, b_id) in zip(numbered, numbered[1:]):
            if b_num < a_num:
                fail(f"{family}: {b_id} is registered after {a_id} — a union appended out of order")

    return report()


def report() -> int:
    if failures:
        for message in failures:
            print(f"FAIL {message}")
        print(f"\n{len(failures)} problem(s)")
        return 1
    print("TESTS OK: every rule carries a check or a waiver, ids are unique,")
    print("          numbers increase inside each family, and every check names a file that exists")
    return 0


if __name__ == "__main__":
    sys.exit(main())
