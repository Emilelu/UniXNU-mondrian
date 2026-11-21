#!/usr/bin/env python3
"""Check the source-side release conditions of the held 0531 audio call site.

0531 adds a call to pong_audio_amp_probe() in bsd_init.c.  It is held because
the call is compiled in under a literal #if 1: there is no switch that can
remove it.  The two materials that exist today are the series entry and the
patch hunk; this checker reads them and says whether the source-side release
conditions hold.

It is deliberately dormant while the guard is unconditional.  P-290: a gate
that is always red is not a gate.  The day the guard becomes a preprocessor
switch and 0531 is selected, the same check turns into a criterion:

  * the series must select 0531 at a concrete line;
  * the guard must be a switch that is visible to bsd_init.c, and a builder
    must give bsd_init.o the same -D (condition 2 of the proposal).

Conditions 3-5 are link proof, the weak-link gate and the real-kernel symbols;
they stay with check-audio27-weak-link.py and check-audio27-kernel.py.

Exit codes: 0 the source-side conditions hold or the check is dormant;
1 a source-side condition failed, or --strict was given while dormant;
2 the inputs cannot be read, or the guard cannot be classified.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

SERIES_MARKER = "0531"
PATCH_GLOB = "0531*.patch"
SYMBOL = "pong_audio_amp_probe"
DEFAULT_SERIES = Path("patches/xnu-12377/series")
DEFAULT_BUILDERS = (
    Path("scripts/build-xnu-generic.sh"),
    Path("scripts/build-xnu-4k-baseline.sh"),
)

MACRO_RE = r"[A-Za-z_][A-Za-z0-9_]*"
CALL_RE = re.compile(r"\b" + re.escape(SYMBOL) + r"\s*\(")
EXTERN_RE = re.compile(r"\bextern\b")
TYPE_START_RE = re.compile(
    r"^(?:static\s+)?(?:int|void|bool|long|unsigned|char|struct|enum|union)\b"
)


class InputError(Exception):
    """The checker cannot read or classify a material."""


def read_text(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise InputError(f"cannot read {label}: {path}: {exc}") from exc


def display(path: Path, repo: Path) -> str:
    """Repository-relative when possible, so the output is stable in docs."""
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


def resolve_path(value: str, repo: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo / path
    return path


def strip_comments(line: str, state: dict) -> str:
    """Remove C comments while keeping the line mapping.  Enough for guards."""
    out = []
    i = 0
    while i < len(line):
        if state.get("block"):
            end = line.find("*/", i)
            if end < 0:
                return "".join(out)
            state["block"] = False
            i = end + 2
            continue
        block = line.find("/*", i)
        line_comment = line.find("//", i)
        if line_comment >= 0 and (block < 0 or line_comment < block):
            out.append(line[i:line_comment])
            return "".join(out)
        if block >= 0:
            out.append(line[i:block])
            state["block"] = True
            i = block + 2
            continue
        out.append(line[i:])
        break
    return "".join(out)


def classify_condition(text: str) -> dict:
    """Classify one #if/#ifdef line; unknown is not a pass (P-279)."""
    stripped = text.strip()
    match = re.match(r"#\s*(if|ifdef|ifndef)\b(.*)$", stripped)
    if not match:
        return {"kind": "unknown", "text": stripped}
    directive = match.group(1)
    expr = match.group(2).strip()
    if directive == "ifdef":
        macro = expr.split()[0] if expr else ""
        if re.fullmatch(MACRO_RE, macro):
            return {"kind": "switch", "macro": macro, "text": stripped}
        return {"kind": "unknown", "text": stripped}
    if directive == "ifndef":
        macro = expr.split()[0] if expr else ""
        if re.fullmatch(MACRO_RE, macro):
            return {"kind": "switch-negative", "macro": macro, "text": stripped}
        return {"kind": "unknown", "text": stripped}

    if expr == "1":
        return {"kind": "unconditional", "text": stripped}
    if expr == "0":
        return {"kind": "disabled", "text": stripped}
    defined = re.fullmatch(
        r"defined\s*\(?\s*(" + MACRO_RE + r")\s*\)?", expr
    )
    if defined:
        return {"kind": "switch", "macro": defined.group(1), "text": stripped}
    negative = re.fullmatch(
        r"!\s*defined\s*\(?\s*(" + MACRO_RE + r")\s*\)?", expr
    )
    if negative:
        return {"kind": "switch-negative", "macro": negative.group(1), "text": stripped}
    return {"kind": "unknown", "text": stripped}


def push_condition(stack: list, condition: dict, source_line: int, patch_line) -> None:
    stack.append(
        {
            "condition": condition,
            "source_line": source_line,
            "patch_line": patch_line,
        }
    )


def apply_preprocessor(stack: list, text: str, source_line: int, patch_line) -> None:
    stripped = text.strip()
    if not stripped.startswith("#"):
        return
    match = re.match(r"#\s*(if|ifdef|ifndef|elif|else|endif)\b", stripped)
    if not match:
        return
    directive = match.group(1)
    if directive in ("if", "ifdef", "ifndef"):
        push_condition(stack, classify_condition(stripped), source_line, patch_line)
        return
    if directive == "elif":
        condition = classify_condition("#if " + stripped[len("#elif"):].strip())
        if stack:
            stack[-1]["condition"] = condition
            stack[-1]["source_line"] = source_line
            stack[-1]["patch_line"] = patch_line
        else:
            push_condition(stack, condition, source_line, patch_line)
        return
    if directive == "else":
        if stack:
            current = stack[-1]["condition"]
            if current["kind"] == "unconditional":
                condition = {"kind": "disabled", "text": "#else of #if 1"}
            elif current["kind"] == "disabled":
                condition = {"kind": "unconditional", "text": "#else of #if 0"}
            elif current["kind"] == "switch":
                condition = {
                    "kind": "switch-else",
                    "macro": current.get("macro", ""),
                    "text": "#else of " + current.get("text", "switch"),
                }
            else:
                condition = {"kind": "unknown", "text": "#else of " + current.get("text", "unknown")}
            stack[-1]["condition"] = condition
            stack[-1]["source_line"] = source_line
            stack[-1]["patch_line"] = patch_line
        return
    if directive == "endif":
        if stack:
            stack.pop()


def is_call_line(code: str) -> bool:
    stripped = code.strip()
    if not stripped or stripped.startswith("#"):
        return False
    if not CALL_RE.search(stripped):
        return False
    if EXTERN_RE.search(stripped):
        return False
    if TYPE_START_RE.match(stripped) and ";" not in stripped:
        return False
    return True


def summarize_guard(frames: list) -> dict:
    conditions = [frame["condition"] for frame in frames]
    kinds = [condition.get("kind") for condition in conditions]
    result = {
        "frames": frames,
        "kind": "none",
        "macros": [
            condition["macro"]
            for condition in conditions
            if condition.get("kind") == "switch" and condition.get("macro")
        ],
    }
    if not conditions:
        result["text"] = "no preprocessor guard"
        return result
    # A definite #if 0 wins over everything inside it.
    if "disabled" in kinds:
        result["kind"] = "disabled"
        result["text"] = next(condition["text"] for condition in conditions if condition["kind"] == "disabled")
        return result
    if "unknown" in kinds or "switch-else" in kinds:
        result["kind"] = "unknown"
        result["text"] = next(
            condition["text"]
            for condition in conditions
            if condition["kind"] in ("unknown", "switch-else")
        )
        return result
    if "switch-negative" in kinds:
        result["kind"] = "switch-negative"
        condition = next(condition for condition in conditions if condition["kind"] == "switch-negative")
        result["macro"] = condition.get("macro", "")
        result["text"] = condition["text"]
        return result
    if "switch" in kinds:
        result["kind"] = "switch"
        # Every switch on the path must be defined for the call to be in.
        # Report the innermost one in the human line; the caller checks all.
        condition = next(condition for condition in reversed(conditions) if condition["kind"] == "switch")
        result["macro"] = condition.get("macro", "")
        result["text"] = condition["text"]
        return result
    if "unconditional" in kinds:
        result["kind"] = "unconditional"
        result["text"] = next(condition["text"] for condition in conditions if condition["kind"] == "unconditional")
        return result
    result["kind"] = "unknown"
    result["text"] = conditions[-1].get("text", "unknown")
    return result


def parse_series(path: Path) -> dict:
    text = read_text(path, "series")
    entries = []
    comments = []
    for number, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            body = stripped.lstrip("#").strip()
            if SERIES_MARKER in body:
                comments.append({"line": number, "text": body})
            continue
        name = stripped.split()[0]
        if SERIES_MARKER in name:
            entries.append({"line": number, "name": name, "text": stripped})
    return {
        "path": path,
        "entries": entries,
        "comments": comments,
        "selected": entries[0] if entries else None,
    }


def parse_patch(path: Path, repo: Path) -> dict:
    text = read_text(path, "patch")
    added = []
    in_hunk = False
    new_line = 0
    for number, raw in enumerate(text.splitlines(), 1):
        if raw.startswith("@@ "):
            match = re.search(r"\+(\d+)(?:,(\d+))?", raw)
            if match:
                new_line = int(match.group(1))
                in_hunk = True
            else:
                in_hunk = False
            continue
        if not in_hunk:
            continue
        if raw.startswith("+"):
            body = raw[1:]
            added.append({"patch_line": number, "source_line": new_line, "text": body})
            new_line += 1
        elif raw.startswith("-"):
            continue
        elif raw.startswith(" "):
            new_line += 1
        # "\ No newline at end of file" and hunk trailers are not code.

    state = {"block": False}
    stack = []
    call = None
    frames_at_call = None
    for item in added:
        raw = item["text"]
        apply_preprocessor(stack, raw, item["source_line"], item["patch_line"])
        code = strip_comments(raw, state)
        if call is None and is_call_line(code):
            call = dict(item)
            call["text"] = code.strip()
            frames_at_call = [dict(frame, condition=dict(frame["condition"])) for frame in stack]
    if call is None:
        return {"path": path, "added": added, "call": None, "guard": summarize_guard([])}
    guard = summarize_guard(frames_at_call or [])
    return {
        "path": path,
        "added": added,
        "call": call,
        "guard": guard,
    }


def parse_source(path: Path, repo: Path) -> dict:
    text = read_text(path, "source")
    state = {"block": False}
    stack = []
    call = None
    frames_at_call = None
    for number, raw in enumerate(text.splitlines(), 1):
        apply_preprocessor(stack, raw, number, None)
        code = strip_comments(raw, state)
        if call is None and is_call_line(code):
            call = {"source_line": number, "patch_line": None, "text": code.strip()}
            frames_at_call = [dict(frame, condition=dict(frame["condition"])) for frame in stack]
    return {
        "path": path,
        "call": call,
        "guard": summarize_guard(frames_at_call or []),
    }


def guard_signature(guard: dict) -> tuple:
    return (guard.get("kind"), guard.get("macro", ""))


def find_define(repo: Path, macro: str, builders) -> dict:
    if builders:
        candidates = [resolve_path(value, repo) for value in builders]
    else:
        candidates = [repo / value for value in DEFAULT_BUILDERS]
    pattern = re.compile(r"(?<![A-Za-z0-9_])-D\s*" + re.escape(macro) + r"(?![A-Za-z0-9_])")
    searched = []
    for path in candidates:
        if not path.is_file():
            continue
        searched.append(path)
        text = read_text(path, "builder")
        for number, raw in enumerate(text.splitlines(), 1):
            if "bsd_init.o_CFLAGS_ADD" not in raw:
                continue
            if pattern.search(raw):
                return {"path": path, "line": number, "text": raw.strip(), "searched": searched}
    return {"path": None, "searched": searched}


def dormant(reason: str, strict: bool) -> int:
    print("HOLD dormant: " + reason)
    print("HOLD this check becomes a criterion the day the guard is a preprocessor switch and 0531 is selected")
    if strict:
        print("HOLD strict: the check is dormant, so --strict turns this into a failure")
        return EXIT_FAILED
    return EXIT_OK


def failed(reason: str, lines: list) -> int:
    print("HOLD FAILED: " + reason)
    for line in lines:
        print(line)
    return EXIT_FAILED


def run(argv: list) -> int:
    parser = argparse.ArgumentParser(
        description="Check the source-side release conditions of the held 0531 audio call site.",
        epilog=(
            "Exit 0: dormant (guard is literal) or source-side conditions hold. "
            "Exit 1: a condition failed, or --strict while dormant. "
            "Exit 2: an input is missing or the guard cannot be classified."
        ),
    )
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]),
                        help="checkout root (default: the parent of this script)")
    parser.add_argument("--series", default=str(DEFAULT_SERIES),
                        help="series file (default: patches/xnu-12377/series)")
    parser.add_argument("--patch", default=None,
                        help="0531 patch (default: the first patches/xnu-12377/0531*.patch)")
    parser.add_argument("--tree", default=None,
                        help="optional XNU source tree with bsd/kern/bsd_init.c")
    parser.add_argument("--builder", action="append", default=None,
                        help="builder to inspect (repeatable; default: the two xnu builders)")
    parser.add_argument("--strict", action="store_true",
                        help="treat a dormant result as a failure")
    args = parser.parse_args(argv)

    repo = Path(args.repo)
    if not repo.is_dir():
        raise InputError(f"repository does not exist: {repo}")
    series_path = resolve_path(args.series, repo)
    if series_path.is_dir():
        series_path = series_path / "series"
    if args.patch:
        patch_path = resolve_path(args.patch, repo)
    else:
        patch_dir = repo / "patches/xnu-12377"
        matches = sorted(path for path in patch_dir.glob(PATCH_GLOB) if path.is_file())
        if not matches:
            raise InputError(f"no {PATCH_GLOB} under {patch_dir}")
        patch_path = matches[0]

    series = parse_series(series_path)
    patch = parse_patch(patch_path, repo)

    if series["selected"]:
        entry = series["selected"]
        print(f"HOLD series: {display(series_path, repo)}:{entry['line']} selects {entry['name']}")
    elif series["comments"]:
        comment = series["comments"][0]
        print(f"HOLD series: {display(series_path, repo)}:{comment['line']} holds 0531")
    else:
        print(f"HOLD series: {display(series_path, repo)} has no 0531 entry")

    if patch["call"] is None:
        print(f"HOLD patch: {display(patch_path, repo)} carries no {SYMBOL} call")
        return dormant("the patch has no call to check", args.strict)

    guard = patch["guard"]
    call = patch["call"]
    guard_frames = guard.get("frames") or []
    guard_patch_line = guard_frames[-1].get("patch_line") if guard_frames else None
    guard_source_line = guard_frames[-1].get("source_line") if guard_frames else None
    guard_where = (
        f"{display(patch_path, repo)}:{guard_patch_line}"
        if guard_patch_line
        else display(patch_path, repo)
    )
    print(
        f"HOLD patch: {guard_where} guard \"{guard['text']}\" "
        f"(bsd_init.c:{guard_source_line or call['source_line']})"
    )
    print(
        f"HOLD call: {display(patch_path, repo)}:{call['patch_line']} "
        f"{SYMBOL}() (bsd_init.c:{call['source_line']})"
    )

    source_guard = None
    if args.tree:
        tree = resolve_path(args.tree, repo)
        source_path = tree / "bsd/kern/bsd_init.c"
        if not source_path.is_file():
            raise InputError(f"cannot read source: {source_path}")
        source = parse_source(source_path, repo)
        if source["call"] is not None:
            source_guard = source["guard"]
            source_frames = source_guard.get("frames") or []
            source_guard_line = (
                source_frames[-1].get("source_line") if source_frames else None
            )
            print(
                f"HOLD source: {display(source_path, repo)}:"
                f"{source_guard_line or source['call']['source_line']} "
                f"guard \"{source_guard['text']}\" "
                f"(call at :{source['call']['source_line']})"
            )
            if guard_signature(source_guard) != guard_signature(guard):
                return failed(
                    "the source guard and the patch guard disagree",
                    [
                        f"HOLD source guard: {source_guard['kind']} {source_guard.get('macro', '')}".rstrip(),
                        f"HOLD patch guard:  {guard['kind']} {guard.get('macro', '')}".rstrip(),
                        "HOLD why: the series would apply a different switch than the tree carries; fix the patch or the tree before judging the hold",
                    ],
                )
        else:
            print(f"HOLD source: {display(source_path, repo)} has no {SYMBOL} call; using the patch material")
    if source_guard is not None:
        guard = source_guard

    if not series["selected"]:
        return dormant(
            "0531 is not selected by the series; the switch, if any, is not in a build",
            args.strict,
        )

    kind = guard["kind"]
    if kind == "unconditional":
        return dormant(
            "the call-site guard is unconditional; release condition 2 (a switch visible to bsd_init.c) is not met",
            args.strict,
        )
    if kind == "disabled":
        return dormant(
            "the call is under #if 0; it is dead code, not a releasable switch",
            args.strict,
        )
    if kind == "none":
        return dormant(
            "the call has no preprocessor guard; there is no switch to turn it off",
            args.strict,
        )
    if kind == "switch-negative":
        return failed(
            "the call-site guard is inverted; defining the switch would compile the call out",
            [
                f"HOLD guard: {guard['text']}",
                "HOLD why: release condition 1 requires --switch off to remove the call; an inverted switch cannot provide that",
            ],
        )
    if kind == "unknown":
        print("HOLD cannot classify: " + guard["text"])
        print("HOLD why: an unclassified guard is not evidence that the call is controllable")
        return EXIT_USAGE
    if kind != "switch":
        print("HOLD cannot classify: " + guard["text"])
        return EXIT_USAGE

    macros = guard.get("macros") or ([guard["macro"]] if guard.get("macro") else [])
    if not macros:
        print("HOLD cannot classify: switch without a macro name")
        return EXIT_USAGE
    for macro in macros:
        define = find_define(repo, macro, args.builder)
        if define["path"] is None:
            candidates = ", ".join(
                display(path, repo) for path in define["searched"]
            ) or "the default builders"
            return failed(
                f"0531 is selected and the guard is a switch, but no builder gives bsd_init.o -D{macro}",
                [
                    f"HOLD guard: {guard['text']}",
                    f"HOLD build: no bsd_init.o_CFLAGS_ADD with -D{macro} in {candidates}",
                    "HOLD why: release condition 2 requires the same switch to be visible to bsd_init.c; a switch in the patch alone is not enough",
                ],
            )
        print(
            f"HOLD build: {display(define['path'], repo)}:{define['line']} "
            f"gives bsd_init.o -D{macro}"
        )

    print(
        "HOLD OK: 0531 is selected and bsd_init.c is guarded by a preprocessor switch "
        "that a builder defines for bsd_init.o"
    )
    print("HOLD source-side conditions 1-2 hold; link proof (3), the weak-link gate (4) and real-kernel evidence (5) remain")
    return EXIT_OK


def main() -> int:
    try:
        return run(sys.argv[1:])
    except InputError as exc:
        print(f"HOLD cannot read: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
