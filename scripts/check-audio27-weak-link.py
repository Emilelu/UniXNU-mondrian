#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Check that the 0531 audio call site can be linked, or that it is not selected.

This is a private preflight for the audio lane, not a global blocker.  Stage 0
deliberately links no audio object: the board stops at bsd_init before the lane
matters, and a global ledger must not carry debt for work that is not scheduled.
So this file has no row in scripts/check-audio27-preflight.sh yet; it is meant to
be called by the lane (or by a --pac-only preflight) and read as evidence.

The call site is unconditional.  patch 0531 carries `#if 1`, not
`#if defined(XNU_PONG_AUDIO)`: XNU_PONG_AUDIO is a per-object Make variable
(PongAudioAmp.o_CFLAGS_ADD), so it never reaches bsd_init.c and cannot select or
remove this call.  The only honest off state is therefore "the series does not
list 0531".  The checker proves that state from a real series file, never from a
compiler flag.

The only honest on state is a definition in the link.  A strong definition that
merely exists in the source tree, or in an object outside `link.filelist`, is not
a definition source: the linker can only resolve from an object it was given.
The checker reads a real-shaped `llvm-nm -A -m` (or `-A`) transcript and accepts
`T _pong_audio_amp_probe` only from PongAudioAmp.o and only when the transcript
names an object that appears in the supplied link.filelist.  A T in another
linked object can be a local stub; it does not prove the driver is linked.  `$auth_ptr$ia` is treated as the arm64e
authenticated-pointer stub it is; a reference to it is not a definition.

The weak declaration is a source policy, not a linker proof.  This project's
ld64-port rejects an undefined weak function reference in the static/dynamic
images the kernel is linked as (N_WEAK_REF is emitted, but the auth-pointer stub
still needs a target), so the checker never turns a weak declaration into a
green line.  It prints a policy NOTE when the declaration is explicit and a
comment says why, then keeps the missing-definition verdict.

Sources (explicit, never auto-skipped):

    python3 scripts/check-audio27-weak-link.py --tree /mnt/e/hackios/k60-gates
    python3 scripts/check-audio27-weak-link.py --series /mnt/e/hackios/k60-gates/patches/xnu-12377
    python3 scripts/check-audio27-weak-link.py --tree /path/to/xnu --series /path/to/series \
        --link-filelist /path/to/build/xnu/snapshot-obj/RELEASE_ARM64_.../link.filelist \
        --symbols /path/to/nm.txt

`--tree` may be the gates checkout (it carries patches/xnu-12377/series), a
seeded XNU tree, or an iOS 27 output tree.  `--series` may be the series file or
its directory.  `--patch` names one patch explicitly.  The adsp tree has no
local 0531; point --tree or --series at the gates checkout.  With neither
source the checker exits 1: it does not guess, and a missing measurement surface
is never a success.

Exit codes: 0 not selected (the call site is not linked) or a fully proven
definition; 1 selected but unproven, selected and switch-off contradicting
`#if 1`, or inputs missing/ambiguous; 2 usage.
"""
import argparse
import os
import pathlib
import re
import sys

SYMBOL = "pong_audio_amp_probe"
PATCH_NAME = re.compile(r"^0531[-_].*\.patch$", re.I)
AUTH_STUB = re.compile(r"l_[A-Za-z0-9_$]*\$auth_ptr\$ia[A-Za-z0-9_$]*")
WEAK_DECL = re.compile(
    r"extern\b[^;]*?\b" + re.escape(SYMBOL) + r"\s*\([^;]*?\)[^;]*?"
    r"__attribute__\s*\(\(\s*weak\s*\)\)[^;]*?;", re.S)
IF1 = re.compile(r"^\s*#\s*if\s+1\s*$")
IF0 = re.compile(r"^\s*#\s*if\s+0\s*$")
IF_DEFINED = re.compile(r"^\s*#\s*if\s+defined\s*\(\s*XNU_PONG_AUDIO\s*\)\s*$")
NM_PATH = re.compile(r"^(?P<path>.+?\.(?:o|obj|a(?:\([^)]*\))?)):\s*(?P<rest>.*)$")
NM_TYPE = re.compile(r"^(?:[0-9a-fA-F]{8,16}\s+)?(?P<type>[A-Za-z?])\s+(?P<name>\S+)$")


class SourceError(Exception):
    """The inputs do not name a measurement surface."""


def norm_path(text):
    return text.replace("\\", "/").lstrip("./")


def basename(path):
    return norm_path(path).rsplit("/", 1)[-1]


def resolve_tree(path):
    """The directory holding bsd/, or None for a patch/scripts checkout."""
    for root in (path, path / ".cache/xnu-work"):
        if (root / "bsd/conf/files").is_file():
            return root
    return None


def read_text(path, what):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise SourceError("cannot read %s %s: %s" % (what, path, error.strerror or error))


def parse_series(path):
    """(entries, comments): entries are (line, basename), comments are (line, text)."""
    entries, comments = [], []
    for number, raw in enumerate(read_text(path, "series").splitlines(), 1):
        stripped = raw.strip()
        if stripped.startswith("#"):
            comments.append((number, stripped))
            continue
        code = raw.split("#", 1)[0].strip()
        if code:
            entries.append((number, os.path.basename(code)))
    return entries, comments


def find_series(args):
    tree = pathlib.Path(args.tree).expanduser().resolve() if args.tree else None
    if tree is not None and not tree.is_dir():
        raise SourceError("--tree is not a directory: %s" % tree)

    explicit = None
    if args.series:
        candidate = pathlib.Path(args.series).expanduser().resolve()
        explicit = candidate / "series" if candidate.is_dir() else candidate
        if not explicit.is_file():
            raise SourceError("--series names no series file: %s" % explicit)

    series = explicit
    if tree is not None:
        in_tree = tree / "patches/xnu-12377/series"
        if in_tree.is_file():
            if series is not None and in_tree.resolve() != series.resolve():
                raise SourceError("--tree carries %s and --series names %s; pass one selection source"
                                  % (in_tree, series))
            series = in_tree
        elif series is None and (tree / "series").is_file():
            series = tree / "series"

    if series is None:
        raise SourceError("no 0531 selection surface: pass --tree with patches/xnu-12377/series,"
                          " or --series FILE|DIR (the adsp tree has no local 0531; point at gates)")
    return tree, series.resolve()


def patch_candidates(patch_dir):
    try:
        return sorted(p for p in patch_dir.iterdir() if p.is_file() and PATCH_NAME.match(p.name))
    except OSError:
        return []


def choose_patch(args, series, patch_dir, entries):
    selected = [(number, name) for number, name in entries if PATCH_NAME.match(name)]
    chosen = None
    source = "series"
    if selected:
        number, name = selected[0]
        chosen = patch_dir / name
        if not chosen.is_file():
            chosen = None
            for candidate in patch_candidates(patch_dir):
                if candidate.name == name:
                    chosen = candidate
                    break
    if args.patch:
        chosen = pathlib.Path(args.patch).expanduser().resolve()
        source = "explicit"
        if not chosen.is_file():
            raise SourceError("--patch does not exist: %s" % chosen)
    return selected, chosen, source


def split_patch(text):
    """Added lines as (patch line number, text), removed lines likewise."""
    added, removed = [], []
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith("+++ ") or line.startswith("--- "):
            continue
        if line.startswith("+"):
            added.append((number, line[1:]))
        elif line.startswith("-"):
            removed.append((number, line[1:]))
    return added, removed


def comment_text(lines):
    """The comments, not the code: code is never a reason."""
    text = "\n".join(line for _, line in lines)
    comments = re.findall(r"/\*.*?\*/", text, flags=re.S)
    comments += re.findall(r"//[^\n]*", text)
    clean = " ".join(" ".join(comments).split())
    clean = re.sub(r"/\*|\*/", " ", clean)
    clean = re.sub(r"(^|\s)\*\s?", " ", clean)
    return " ".join(clean.split())


def reason_in_comment(text):
    """A stated reason, not merely the word weak next to the declaration."""
    if len(text) < 30:
        return None
    if re.search(r"\b(because|since|so that|so the|so it|would|without|absent|optional|missing|"
                 r"not linked|not defined|only)\b", text, re.I) or \
       re.search(r"(因为|所以|否则|缺失|未定义)", text):
        return text[:180]
    return None


def guard_value(condition):
    """True/False for a literal, None when the condition is not a literal."""
    value = condition.strip()
    while value.startswith("(") and value.endswith(")"):
        value = value[1:-1].strip()
    if value in ("1", "true", "TRUE"):
        return True
    if value in ("0", "false", "FALSE"):
        return False
    if value.startswith("!"):
        inner = guard_value(value[1:].strip())
        return None if inner is None else not inner
    return None


def analyse_guards(added):
    """For each added line: (active, unknown).  Unknown is active but unproven."""
    stack = []
    active = True
    rows = []
    if1 = if0 = macro_guarded = False
    for number, text in added:
        stripped = text.strip()
        if1 = if1 or bool(IF1.match(stripped))
        if0 = if0 or bool(IF0.match(stripped))
        macro_guarded = macro_guarded or bool(IF_DEFINED.match(stripped))

        if re.match(r"^#\s*if\b", stripped):
            condition = stripped.split(None, 1)[1] if len(stripped.split(None, 1)) > 1 else ""
            value = guard_value(condition)
            stack.append({"parent": active, "value": value, "unknown": value is None})
            active = active and value is not False
        elif re.match(r"^#\s*elif\b", stripped):
            if stack:
                frame = stack[-1]
                condition = stripped.split(None, 1)[1] if len(stripped.split(None, 1)) > 1 else ""
                value = guard_value(condition)
                frame["value"] = value
                frame["unknown"] = value is None
                active = frame["parent"] and value is not False
        elif re.match(r"^#\s*else\b", stripped):
            if stack:
                frame = stack[-1]
                frame["value"] = not frame["value"] if frame["value"] is not None else None
                active = frame["parent"] and frame["value"] is not False
        elif re.match(r"^#\s*endif\b", stripped):
            if stack:
                frame = stack.pop()
                active = frame["parent"]
        unknown = any(frame["unknown"] for frame in stack)
        rows.append((number, text, bool(active), unknown))
    return rows, if1, if0, macro_guarded


def analyse_patch(path):
    text = read_text(path, "patch")
    added, removed = split_patch(text)
    rows, if1, if0, macro_guarded = analyse_guards(added)
    added_text = "\n".join(line for _, line in added)
    declared = WEAK_DECL.search(added_text) is not None
    weak_line = None
    if declared:
        for number, line in added:
            if "weak" in line and (SYMBOL in line or "extern" in line):
                weak_line = number
                break
    reason = reason_in_comment(comment_text(added))
    refs, calls = [], []
    for number, line, active, unknown in rows:
        code = line.split("//", 1)[0]
        if re.search(r"\b" + re.escape(SYMBOL) + r"\b", code):
            ref = {"line": number, "active": active, "unknown": unknown, "text": line.strip()}
            refs.append(ref)
            if re.search(r"\b" + re.escape(SYMBOL) + r"\s*\(", code) and \
               not re.match(r"^\s*extern\b", code) and \
               not re.match(r"^\s*(?:int|void|long|static)\s+" + re.escape(SYMBOL) + r"\b", code):
                calls.append(ref)
    active_refs = [ref for ref in refs if ref["active"]]
    active_calls = [ref for ref in calls if ref["active"]]
    inactive_refs = [ref for ref in refs if not ref["active"]]
    stubs = sorted(set(AUTH_STUB.findall(text)))
    return {
        "path": path,
        "added": added,
        "removed": removed,
        "declared_weak": declared,
        "weak_line": weak_line,
        "reason": reason,
        "refs": refs,
        "calls": calls,
        "active_refs": active_refs,
        "active_calls": active_calls,
        "inactive_refs": inactive_refs,
        "if1": if1,
        "if0": if0,
        "macro_guarded": macro_guarded,
        "stubs": stubs,
        "text": text,
    }


def parse_nm(text):
    records = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        provenance = None
        rest = line
        match = NM_PATH.match(line)
        if match:
            provenance = match.group("path").strip()
            rest = match.group("rest").strip()
        if not rest:
            continue
        weak = False
        undefined = False
        name = None
        symbol_type = "?"
        if rest.startswith("(undefined)"):
            undefined = True
            weak = "weak" in rest.lower()
            name = rest.split()[-1]
        elif rest.startswith("(defined)") or rest.startswith("(weak)"):
            name = rest.split()[-1]
            weak = "weak" in rest.lower()
            undefined = False
        else:
            match = NM_TYPE.match(rest)
            if not match:
                continue
            symbol_type = match.group("type")
            name = match.group("name")
            if symbol_type == "U":
                undefined = True
            elif symbol_type == "u":
                undefined = True
                weak = True
            elif symbol_type == "w":
                undefined = True
                weak = True
            elif symbol_type == "W":
                undefined = False
                weak = True
            elif symbol_type in ("T", "t", "D", "d", "B", "b", "S", "s", "A", "a"):
                undefined = False
            else:
                # Unknown nm type: keep it, but never as a definition.
                undefined = True
        if not name:
            continue
        bare = name.lstrip("_")
        stub = "$auth_ptr$ia" in name
        stub_base = name.split("$auth_ptr$ia", 1)[0].lstrip("_")
        if stub_base.startswith("l_"):
            stub_base = stub_base[2:]
        records.append({
            "provenance": provenance,
            "name": name,
            "bare": bare,
            "type": symbol_type,
            "undefined": undefined,
            "weak": weak,
            "defined": not undefined and symbol_type not in ("U", "u", "w"),
            "stub": stub,
            "stub_probe": stub and stub_base == SYMBOL,
            "probe": bare == SYMBOL,
            "line": line,
        })
    return records


def object_matches(provenance, entries):
    """True when this transcript object is one the link filelist gives the linker."""
    if not provenance:
        return False
    p = norm_path(provenance)
    for entry in entries:
        e = norm_path(entry)
        if not e:
            continue
        if p == e or p.endswith("/" + e) or e.endswith("/" + p):
            return True
        if "(" in e and ")" in e:
            archive = e.split("(", 1)[0]
            if p == archive or p.endswith("/" + archive) or archive.endswith("/" + p):
                return True
        if "/" not in e and basename(p) == e:
            return True
    return False


def read_filelist(path):
    try:
        text = read_text(path, "link filelist")
    except SourceError:
        raise
    entries = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        entries.append(line)
    return entries


def conf_evidence(tree):
    """What the source checkout can say about compiling the driver object."""
    root = resolve_tree(tree) if tree else None
    if root is None:
        return None, "no bsd/conf/files under %s (the checkout is not an XNU source tree)" % tree
    conf = root / "bsd/conf/files"
    lines = [line.split("#", 1)[0] for line in read_text(conf, "conf/files").splitlines()]
    amp = [line for line in lines if "PongAudioAmp.c" in line]
    geni = [line for line in lines if "PongAudioGeniI2c.c" in line]
    if not amp:
        return None, "%s does not list PongAudioAmp.c, so the object is not compiled" % conf
    if not geni:
        return None, "%s lists PongAudioAmp.c but not PongAudioGeniI2c.c" % conf
    return (conf, amp[0].strip(), geni[0].strip()), None


def hook_evidence(tree):
    if not tree:
        return None
    for candidate in (tree / "scripts/k60-conf-files-hook.py", tree / "scripts/add-audio-conffiles.py"):
        if candidate.is_file():
            return candidate
    return None


def policy_note(analysis):
    if not analysis["declared_weak"]:
        return ("WEAK-LINK source: %s never declares %s weak; a missing definition is an ordinary"
                " undefined symbol" % (analysis["path"].name, SYMBOL))
    where = "patch line %s" % analysis["weak_line"] if analysis["weak_line"] else "the patch"
    if analysis["reason"]:
        return ("WEAK-LINK policy NOTE: %s declares %s __attribute__((weak)) at %s and states a reason:"
                " \"%s\"; this is source policy, not a linker proof" % (
                    analysis["path"].name, SYMBOL, where, analysis["reason"]))
    return ("WEAK-LINK policy NOTE: %s declares %s __attribute__((weak)) at %s but no comment says why;"
            " that is not an accepted policy exception" % (analysis["path"].name, SYMBOL, where))


def tree_call_site(tree):
    """A call already in bsd_init.c, even when the series does not list 0531.

    The series is the selection source, but a tree can carry the hook from the
    applier or from a hand edit.  Saying "not linked" while looking at that tree
    would be false, so the off path asks the source too.
    """
    root = resolve_tree(tree) if tree else None
    if root is None:
        return None
    path = root / "bsd/kern/bsd_init.c"
    if not path.is_file():
        return None
    text = read_text(path, "bsd_init.c")
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    for number, line in enumerate(text.splitlines(), 1):
        code = line.split("//", 1)[0]
        if "extern" in code:
            continue
        if re.search(r"\b" + re.escape(SYMBOL) + r"\s*\(", code):
            return path, number, line.strip()
    return None


def check_link(args, tree, selected):
    """Return (ok, issues, notes).  Reads text only; never opens an object or image."""
    issues, notes = [], []
    filelist_path = pathlib.Path(args.link_filelist).expanduser().resolve() if args.link_filelist else None
    symbols_path = pathlib.Path(args.symbols).expanduser().resolve() if args.symbols else None

    if filelist_path is None:
        issues.append("no --link-filelist supplied; the object set the linker sees is not measured")
        entries = []
    else:
        entries = read_filelist(filelist_path)
        if not entries:
            issues.append("link.filelist %s is empty" % filelist_path)
        print("WEAK-LINK link input: %s (%d object(s))" % (filelist_path, len(entries)))

    if entries:
        amp_in = [entry for entry in entries if basename(entry) == "PongAudioAmp.o"]
        init_in = [entry for entry in entries if basename(entry) == "bsd_init.o"]
        if amp_in:
            print("WEAK-LINK link input: PongAudioAmp.o is selected (%s)" % amp_in[0])
        else:
            issues.append("PongAudioAmp.o is not in %s, so no definition of %s reaches the link"
                          % (filelist_path, SYMBOL))
        if init_in:
            print("WEAK-LINK link input: bsd_init.o is selected (%s)" % init_in[0])
        else:
            issues.append("bsd_init.o is not in %s, so the 0531 call site is not in the link"
                          % filelist_path)

    conf, conf_problem = conf_evidence(tree)
    if conf:
        print("WEAK-LINK source: %s lists PongAudioAmp.c and PongAudioGeniI2c.c" % conf[0])
    else:
        notes.append(conf_problem)
    hook = hook_evidence(tree)
    if hook:
        print("WEAK-LINK source: conf-files hook present at %s" % hook)
    else:
        notes.append("no conf-files hook found under %s; source alone does not force-load the object" % tree)

    if symbols_path is None:
        issues.append("no --symbols supplied; no symbol table proves a definition (a string match is not a symbol)")
        return False, issues, notes
    if filelist_path is None:
        issues.append("--symbols without --link-filelist cannot tell a linked definition from an unselected object")
        return False, issues, notes

    records = parse_nm(read_text(symbols_path, "symbol table"))
    if not records:
        issues.append("no symbol records parsed from %s; the transcript shape is not understood" % symbols_path)

    definitions = [record for record in records if record["probe"] and record["defined"]]
    # A real entry point is a text definition.  A W is a weak (return-zero) shell
    # and D/B/S are data; neither proves the driver is wired.
    providers = [record for record in definitions if record["type"] in ("T", "t")]
    driver_providers = [record for record in providers
                        if record["provenance"] and basename(record["provenance"]) == "PongAudioAmp.o"]
    linked_providers = [record for record in driver_providers
                        if object_matches(record["provenance"], entries)]
    other_providers = [record for record in providers if record not in driver_providers]

    weak_definitions = [record for record in records
                        if record["probe"] and record["defined"] and record["weak"]]
    if weak_definitions:
        notes.append("weak definition(s) present: %s; a weak definition can be a return-zero shell and"
                     " is not the real driver entry point" % ", ".join(
                         record["provenance"] or "<no object>" for record in weak_definitions))

    if linked_providers:
        record = linked_providers[0]
        print("WEAK-LINK symbol: %s %s %s is defined in a linked object %s"
              % (SYMBOL, record["type"] if record["type"] != "?" else "defined",
                 record["name"], record["provenance"]))
    else:
        if providers and not driver_providers:
            issues.append("a T/t definition of %s was found in %s, but not in PongAudioAmp.o; a local or"
                          " stub definition does not prove the driver is linked"
                          % (SYMBOL, ", ".join(record["provenance"] or "<no object>" for record in other_providers)))
        elif driver_providers:
            issues.append("a T/t definition of %s is in PongAudioAmp.o, but that object is outside link.filelist: %s;"
                          " the linker never sees it" % (SYMBOL, ", ".join(
                              record["provenance"] or "<no object>" for record in driver_providers)))
        elif definitions:
            issues.append("definitions of %s exist, but none is a T/t function definition in PongAudioAmp.o;"
                          " a weak W or data symbol is not the driver entry point" % SYMBOL)
        else:
            issues.append("no definition of %s in the symbol table" % SYMBOL)

    references = [record for record in records
                  if (record["probe"] or record["stub_probe"]) and record["undefined"]]
    linked_refs = [record for record in references
                   if record["provenance"] and object_matches(record["provenance"], entries)]
    unlinked_refs = [record for record in references if record not in linked_refs]
    if unlinked_refs:
        notes.append("reference(s) outside link.filelist were not counted: %s"
                     % ", ".join(record["provenance"] or "<no object>" for record in unlinked_refs))
    if linked_refs:
        for record in linked_refs[:3]:
            print("WEAK-LINK symbol: %s %s %s is referenced from linked object %s"
                  % ("$auth_ptr$ia" if record["stub"] else SYMBOL,
                     record["type"] if record["type"] != "?" else ("weak" if record["weak"] else "undefined"),
                     record["name"], record["provenance"]))
    else:
        issues.append("the symbol table shows no undefined reference to %s or its $auth_ptr$ia stub"
                      " from a linked object; it is not the link's bsd_init.o" % SYMBOL)

    for record in records:
        if record["stub"] and record["defined"]:
            print("WEAK-LINK symbol: %s has a definition at %s" % (record["name"], record["provenance"] or "<no object>"))

    return bool(linked_providers) and bool(linked_refs) and not issues, issues, notes


def main(argv):
    parser = argparse.ArgumentParser(
        description="Prove 0531 audio call-site off (not selected) or on (definition in the link); no build.")
    parser.add_argument("--tree", help="gates checkout, seeded XNU tree, or 27 output tree")
    parser.add_argument("--series", help="series file or the directory holding it")
    parser.add_argument("--patch", help="explicit 0531 patch (selection still comes from --series/--tree)")
    parser.add_argument("--link-filelist", "--link-input", dest="link_filelist",
                        help="the link's filelist (text); PongAudioAmp.o must be in it")
    parser.add_argument("--symbols", help="llvm-nm -A -m (or -A) transcript with object paths")
    parser.add_argument("--switch", choices=("auto", "on", "off"), default="auto",
                        help="the explicit XNU_PONG_AUDIO state; off cannot remove a #if 1 call site")
    args = parser.parse_args(argv[1:])

    try:
        tree, series = find_series(args)
        entries, comments = parse_series(series)
        selected, patch, patch_source = choose_patch(args, series, series.parent, entries)
        mentions = any("0531" in text for _, text in comments)
        present = patch_candidates(series.parent)

        if not selected:
            if not present and not mentions:
                raise SourceError("%s has no 0531 entry, patch file, or HOLD comment; this is not the"
                                  " 27 series (the adsp tree has no local 0531), so nothing is measured" % series)
            print("WEAK-LINK source: series %s" % series)
            for number, text in comments:
                if "0531" in text:
                    print("WEAK-LINK HOLD: %s:%d: %s" % (series, number, text.lstrip("# ")))
                    break
            if patch:
                print("WEAK-LINK patch: %s (present, not selected)" % patch)
            elif present:
                print("WEAK-LINK patch: %s (present, not selected)" % present[0])
            else:
                print("WEAK-LINK patch: no 0531 file under %s (not selected)" % series.parent)
            site = tree_call_site(tree)
            if site:
                print("WEAK-LINK FAILED: the series does not select 0531, but %s:%d already carries"
                      " the call site; off is not proven and the line would still be linked" % (site[0], site[1]))
                print("WEAK-LINK why: switching XNU_PONG_AUDIO off does not remove a call already in bsd_init.c")
                return 1
            print("WEAK-LINK: the series does not select 0531, so its call site is not linked")
            print("NOTE audio: switch off, the call site is not linked")
            return 0

        line, name = selected[0]
        print("WEAK-LINK source: series %s:%d selects %s" % (series, line, name))
        if len(selected) > 1:
            print("WEAK-LINK note: %d 0531 entries are listed; the first is checked" % len(selected))
        if patch is None:
            print("WEAK-LINK FAILED: %s:%d lists %s but no such patch file exists under %s"
                  % (series, line, name, series.parent))
            return 1
        if patch_source == "explicit" and patch.name != name:
            print("WEAK-LINK note: --patch %s is not the selected %s; it is parsed because it was named"
                  % (patch.name, name))

        analysis = analyse_patch(patch)
        print("WEAK-LINK patch: %s (%s)" % (patch, "unconditional #if 1" if analysis["if1"]
              else "no #if" if not analysis["if0"] and not analysis["macro_guarded"]
              else "guarded"))
        print(policy_note(analysis))
        if analysis["stubs"]:
            print("WEAK-LINK stub: %s" % ", ".join(analysis["stubs"]))

        if not analysis["active_calls"]:
            print("WEAK-LINK FAILED: %s is selected but its added lines never call %s under an"
                  " active guard; the patch cannot reach the probe" % (patch.name, SYMBOL))
            return 1

        if args.switch == "off":
            if analysis["if1"]:
                print("WEAK-LINK FAILED: 0531 is unconditional (#if 1), so switching XNU_PONG_AUDIO off"
                      " does not remove the call site")
                return 1
            if analysis["macro_guarded"]:
                print("WEAK-LINK FAILED: 0531 is guarded by #if defined(XNU_PONG_AUDIO), but that macro"
                      " is per-object and does not reach bsd_init.c; the call site is not reliably selected")
                return 1
            print("WEAK-LINK FAILED: --switch off contradicts the selected call-site guard; the patch still"
                  " adds a reference to %s" % SYMBOL)
            return 1

        ok, issues, notes = check_link(args, tree, selected)
        for note in notes:
            print("WEAK-LINK note: %s" % note)
        if ok:
            print("WEAK-LINK OK: 0531 is selected and %s has a definition in the link" % SYMBOL)
            return 0

        print("WEAK-LINK FAILED: 0531 is selected and references %s, but the link has no definition source"
              % SYMBOL)
        for issue in issues:
            print("WEAK-LINK missing: %s" % issue)
        if analysis["declared_weak"]:
            print("WEAK-LINK why: ld64-port rejects an undefined weak function reference in the kernel"
                  " image; N_WEAK_REF is emitted but the $auth_ptr$ia stub still needs a target")
        else:
            print("WEAK-LINK why: %s is not declared weak, so the undefined reference is already fatal"
                  % SYMBOL)
        if analysis["stubs"]:
            print("WEAK-LINK symbol: %s is the arm64e auth-pointer stub the link must resolve"
                  % analysis["stubs"][0])
        return 1
    except SourceError as error:
        print("WEAK-LINK FAILED: %s" % error)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
