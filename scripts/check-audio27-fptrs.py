#!/usr/bin/env python3
"""Assert the audio seam's function-pointer tables and its one weak call.

docs/research/audio/IOS27-PAC.md says the only indirect calls between the
audio driver and the rest of the kernel are four read/write tables -
PongGeniIo, PongCodecLpiIo, PongSwrIo and PongCodecMacroWindow - plus one
weak call into pong_audio_amp_probe(). Those are the surfaces an arm64e
kernel with pointer authentication has to keep consistent, so they are
checked here instead of described:

  * every callback is one half of a read/write pair, and both halves take the
    same context and register types, the write adding the value;
  * every pair is handed its own context field - slew_read/slew_write take
    slew_ctx, not ctx, or a slew write lands on pad 0;
  * every callback the driver installs is compared with the function that
    fills it: the return type and the parameter list must match the member it
    is assigned to, a copy from another field fails, and a table copied whole
    (bus->io = *io) must come from the same struct type;
  * every call passes the receiver's own context as its first argument, so a
    bare void * cannot cross a layer;
  * no other function-pointer table exists under drivers/PongAudio;
  * the weak declaration in patch 0531 has the same signature as the
    definition in PongAudioAmp.c, and the call is guarded, takes no argument
    and discards its result.

Static text only: no compiler runs, and a pass says nothing about a build or
about a signed pointer at run time.

Usage: check-audio27-fptrs.py [--repo <tree>]
"""

import os
import re
import sys
from pathlib import Path

DRIVER = "drivers/PongAudio"
WEAK_PATCH = "patches/xnu-12377/0531-k60-audio-amp-probe-call.patch"
AMP = "PongAudioAmp.c"
WEAK_NAME = "pong_audio_amp_probe"

# table type -> {pair prefix: context field}
TABLES = {
    "PongGeniIo": {"": "ctx"},
    "PongCodecLpiIo": {"": "ctx", "slew_": "slew_ctx"},
    "PongSwrIo": {"": "ctx"},
    "PongCodecMacroWindow": {"": "ctx"},
}
COMPOSITES = {"PongCodecMacroIo": ("va", "tx")}

STRUCT = re.compile(r"typedef\s+struct\s*(?:\w+\s*)?\{([^}]*)\}\s*(\w+)\s*;", re.S)
FPTR = re.compile(r"^(.*?)\(\s*\*\s*(\w+)\s*\)\s*\(([^()]*)\)$")
FIELD = re.compile(r"^(.*?)\s*\*?\s*(\w+)(?:\s*\[[^\]]*\])?$")
ANY_FPTR = re.compile(r"([A-Za-z_]\w*(?:\s*\*)?)\s*\(\s*\*\s*(\w+)\s*\)\s*\(")


def code_only(text):
    """Drop comments, string and character literals, keep the line count."""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "/" and text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("\n" * text.count("\n", i, j) or " ")
            i = j
        elif c == "/" and text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" ")
            i = j
        elif c in "\"'":
            q, j = c, i + 1
            while j < n and text[j] != q:
                j += 2 if text[j] == "\\" else 1
            out.append(q + q)
            i = min(j + 1, n)
        else:
            out.append(c)
            i += 1
    return "".join(out)


def split_params(text):
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(" ".join(cur.split()))
            cur = ""
        else:
            cur += ch
    if cur.strip() and cur.strip() != "void":
        parts.append(" ".join(cur.split()))
    return parts


def tables(root):
    """Every typedef struct in the driver, split into callbacks and fields."""
    found = {}
    for path in sorted((root / DRIVER).glob("*.h")):
        text = code_only(path.read_text(encoding="utf-8", errors="replace"))
        for body, name in STRUCT.findall(text):
            callbacks, fields = [], {}
            for member in body.split(";"):
                member = " ".join(member.split())
                if not member:
                    continue
                hit = FPTR.match(member)
                if hit and "(" not in hit.group(1):
                    callbacks.append((" ".join(hit.group(1).split()), hit.group(2),
                                      split_params(hit.group(3))))
                    continue
                hit = FIELD.match(member)
                if hit:
                    fields[hit.group(2)] = " ".join(hit.group(1).split())
            if callbacks or fields:
                found[name] = {"callbacks": callbacks, "fields": fields}
    return found


def check_tables(found, problems):
    for name, expected in TABLES.items():
        if name not in found:
            problems.append("%s is gone, so the seam it declares is no longer checked" % name)
            continue
        table = found[name]
        by_name = {m[1]: m for m in table["callbacks"]}
        if set(table["fields"]) & {"%sctx" % p for p in expected} != {"%sctx" % p for p in expected}:
            problems.append("%s has no %s field, so its callbacks have no context"
                            % (name, " or ".join("%sctx" % p for p in expected)))
        for prefix, field in expected.items():
            read, write = prefix + "read", prefix + "write"
            for member in (read, write):
                if member not in by_name:
                    problems.append("%s.%s has no %s half" % (name, member,
                                     "write" if member == read else "read"))
            if read in by_name and write in by_name:
                rret, _, rparams = by_name[read]
                wret, _, wparams = by_name[write]
                if rret != "uint32_t" or wret != "void":
                    problems.append("%s pair returns %s/%s, not uint32_t/void"
                                    % (name, rret, wret))
                if not wparams or wparams[0] != (rparams[0] if rparams else None):
                    problems.append("%s.%s does not take the context %s.%s takes"
                                    % (name, write, name, read))
                elif wparams[:len(rparams)] != rparams or len(wparams) != len(rparams) + 1:
                    problems.append("%s.%s takes (%s), not (%s, value)"
                                    % (name, write, ", ".join(wparams), ", ".join(rparams)))
                if rparams and not re.match(r"void\s*\*", rparams[0]):
                    problems.append("%s.%s takes %s, not a void * context"
                                    % (name, read, rparams[0]))
                if table["fields"].get(field) != "void":
                    problems.append("%s.%s is %s, not void *"
                                    % (name, field, table["fields"].get(field)))
            if field not in table["fields"]:
                problems.append("%s has no %s for %s/%s"
                                % (name, field, read, write))
    for name, members in COMPOSITES.items():
        if name not in found:
            problems.append("%s is gone, so the two windows are no longer checked" % name)
            continue
        got = [f for f in found[name]["fields"]]
        if got != list(members):
            problems.append("%s holds (%s), not (%s)"
                            % (name, ", ".join(got), ", ".join(members)))


def check_surface(root, found, problems):
    known = {m[1] for t in TABLES for m in found.get(t, {}).get("callbacks", [])}
    for path in sorted((root / DRIVER).glob("*.[ch]")):
        text = code_only(path.read_text(encoding="utf-8", errors="replace"))
        for line_no, line in enumerate(text.splitlines(), 1):
            for _, member in ANY_FPTR.findall(line):
                if member not in known:
                    problems.append("%s:%d declares the callback %s outside the four tables"
                                    % (path.name, line_no, member))


def calls(root, found):
    """Every call through a table member, with its receiver and first argument."""
    known = {}
    for t in TABLES:
        for _, member, _ in found.get(t, {}).get("callbacks", []):
            known[member] = member
    out = []
    for path in sorted((root / DRIVER).glob("*.c")):
        text = code_only(path.read_text(encoding="utf-8", errors="replace"))
        for member in known:
            pattern = re.compile(r"([A-Za-z_]\w*(?:\s*(?:->|\.)\s*\w+)*)\s*(?:->|\.)\s*"
                                 + re.escape(member) + r"\s*\(")
            for hit in pattern.finditer(text):
                start = hit.end()
                depth, arg, j = 0, "", start
                while j < len(text):
                    ch = text[j]
                    if ch in "([":
                        depth += 1
                    elif ch in ")]":
                        if depth == 0:
                            break
                        depth -= 1
                    elif ch == "," and depth == 0:
                        break
                    arg += ch
                    j += 1
                line_no = text.count("\n", 0, hit.start()) + 1
                out.append((path.name, line_no, " ".join(hit.group(1).split()),
                            member, " ".join(arg.split())))
    return out


def check_calls(root, found, problems):
    seen = set()
    prefixes = {}
    for t in TABLES:
        for _, member, _ in found.get(t, {}).get("callbacks", []):
            prefixes[member] = member[:-4] if member.endswith("read") else member[:-5]
    for name, line_no, recv, member, arg in calls(root, found):
        seen.add(member)
        field = prefixes[member] + "ctx"
        allowed = (recv + "." + field, recv + "->" + field)
        if arg not in allowed:
            problems.append("%s:%d calls %s with %s, not its own %s"
                            % (name, line_no, member, arg or "nothing", field))
    for member in prefixes:
        if member not in seen:
            problems.append("%s is declared in a table but never called, so the seam it opens is dead"
                            % member)


KEYWORDS = {"if", "for", "while", "switch", "return", "do", "else", "sizeof", "case"}
FDEF = re.compile(
    r"(?m)^[ \t]*(?:static[ \t]+)?([A-Za-z_][A-Za-z0-9_ \t\*]*?)(?:[ \t]*\n[ \t]*)?"
    r"([A-Za-z_][A-Za-z0-9_]*)[ \t]*\(([^;{]*?)\)[ \t]*\n?[ \t]*\{")
ASSIGN = re.compile(
    r"(?m)^[ \t]*([A-Za-z_]\w*(?:[ \t]*(?:->|\.)[ \t]*[A-Za-z_]\w*)*)[ \t]*=(?!=)[ \t]*([^;]+);")
PATH = re.compile(r"^([A-Za-z_]\w*)((?:\s*(?:->|\.)\s*[A-Za-z_]\w*)*)$")
LOCAL = re.compile(r"(?m)^[ \t]*(?:const[ \t]+)?([A-Z][A-Za-z0-9_]*)[ \t]+(\*?)[ \t]*([a-z_]\w*)[ \t]*(?:=|;|\[)")


def base(type_name):
    """The struct name a declaration mentions, without const, struct or stars."""
    if type_name is None:
        return None
    words = [w for w in type_name.replace("*", " ").split() if w not in ("const", "struct")]
    return words[-1] if words else None


def path_parts(expression):
    hit = PATH.match(" ".join(expression.split()))
    if not hit:
        return None
    return [hit.group(1)] + [w for w in re.split(r"\s*(?:->|\.)\s*", hit.group(2)) if w]


def body_end(text, brace):
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return len(text)


def functions(text):
    """Every function definition: return type, name, parameters, line and span."""
    out = []
    for hit in FDEF.finditer(text):
        head = " ".join(hit.group(1).split())
        if not head or head.split()[0] in KEYWORDS or hit.group(2) in KEYWORDS:
            continue
        brace = hit.end() - 1
        out.append({"return": head, "name": hit.group(2),
                    "params": split_params(hit.group(3)),
                    "line": text.count("\n", 0, hit.start()) + 1,
                    "start": brace, "end": body_end(text, brace)})
    return out


def named(params):
    """Parameter name -> declared type, for the parameters that carry a name."""
    out = {}
    for param in params:
        words = param.split()
        if len(words) < 2:
            continue
        name = words[-1].lstrip("*")
        if not re.match(r"[A-Za-z_]\w*$", name):
            continue
        stars = "*" if words[-1].startswith("*") else ""
        out[name] = (" ".join(words[:-1]) + stars).strip()
    return out


def resolve(parts, types, structs):
    """The struct type of the object a path names, and its last name."""
    if not parts:
        return None, None
    current = base(types.get(parts[0]))
    for name in parts[1:]:
        if current is None:
            return None, name
        current = base(structs.get(current, {}).get("fields", {}).get(name))
    return current, parts[-1]


def check_productions(root, found, problems):
    """Compare every assignment with the callback or field it fills."""
    members = {}
    for table in TABLES:
        for ret, member, params in found.get(table, {}).get("callbacks", []):
            members.setdefault(table, {})[member] = (ret, params)
    definitions = {}
    texts = {}
    for path in sorted((root / DRIVER).glob("*.c")):
        text = code_only(path.read_text(encoding="utf-8", errors="replace"))
        texts[path.name] = text
        for function in functions(text):
            definitions.setdefault(function["name"], (path.name, function))
    covered, sites = set(), 0
    for name, text in texts.items():
        for function in functions(text):
            types = named(function["params"])
            body = text[function["start"]:function["end"]]
            for local in LOCAL.finditer(body):
                types.setdefault(local.group(3), (local.group(1) + local.group(2)).strip())
            for hit in ASSIGN.finditer(body):
                line = text.count("\n", 0, function["start"] + hit.start()) + 1
                parts = path_parts(hit.group(1))
                if parts is None:
                    continue
                rhs = " ".join(hit.group(2).split())
                receiver, _ = resolve(parts[:-1], types, found)
                member = parts[-1]
                where = "%s:%d" % (name, line)
                if receiver in TABLES and member in members[receiver]:
                    sites += 1
                    covered.add((receiver, member))
                    expected_return, expected_params = members[receiver][member]
                    direct = re.match(r"^([A-Za-z_]\w*)$", rhs)
                    ternary = re.match(r"^([A-Za-z_]\w*)\s*!=\s*(?:NULL|0)\s*\?\s*(.*?)\s*:\s*(?:0|NULL)$", rhs)
                    if direct:
                        target = definitions.get(direct.group(1))
                        if target is None:
                            problems.append("%s assigns %s to %s.%s, but no driver source defines it"
                                            % (where, rhs, receiver, member))
                            continue
                        source, target = target
                        if target["return"] != expected_return or \
                                target["params"] != expected_params:
                            problems.append(
                                "%s:%d defines %s as %s (%s), but %s.%s is %s (*)(%s)"
                                % (source, target["line"], target["name"], target["return"],
                                   ", ".join(target["params"]), receiver, member,
                                   expected_return, ", ".join(expected_params)))
                    elif ternary:
                        source_parts = path_parts(ternary.group(2))
                        source_receiver, _ = resolve(
                            (source_parts or [])[:-1], types, found)
                        source_member = source_parts[-1] if source_parts else None
                        if source_parts is None or source_receiver != receiver \
                                or source_member != member:
                            problems.append(
                                "%s copies %s into %s.%s from a different field, so the two"
                                " halves need not agree" % (where, ternary.group(2), receiver, member))
                    elif rhs in ("NULL", "0") and member.endswith("ctx"):
                        pass
                    else:
                        problems.append(
                            "%s fills %s.%s with '%s', which is neither a function, a copy of"
                            " the same field nor a NULL context" % (where, receiver, member, rhs))
                    continue
                dest = base(found.get(receiver, {}).get("fields", {}).get(member))
                if dest in TABLES or dest in COMPOSITES:
                    copy = re.match(r"^\*\s*([A-Za-z_]\w*)$", rhs)
                    if copy:
                        sites += 1
                        source = base(types.get(copy.group(1)))
                        if source != dest:
                            problems.append(
                                "%s copies %s into %s, not into a %s"
                                % (where, copy.group(1), dest, dest))
                        for table in ([dest] if dest in TABLES else []):
                            covered.update((table, name) for name in members.get(table, {}))
                        for field_type in found.get(dest, {}).get("fields", {}).values():
                            covered.update((base(field_type), name)
                                           for name in members.get(base(field_type), {}))
                        continue
    for table in TABLES:
        for member in members.get(table, {}):
            if (table, member) not in covered:
                problems.append("%s.%s is never assigned, so the table is only half filled"
                                % (table, member))
    return sites


def weak_patch(root):
    """The 0531 patch this tree carries, or the one a gates checkout carries.

    The ADSP tree keeps driver sources but not the xnu-12377 series, so the
    call site lives in the gates checkout there. A tree that does carry the
    series directory must carry the patch itself: the fallback cannot hide a
    deleted file.
    """
    local = root / WEAK_PATCH
    if local.is_file():
        return local
    if (root / "patches" / "xnu-12377").is_dir():
        return None
    candidates = [os.environ.get("AUDIO27_WEAK_PATCH")]
    gates = os.environ.get("K60_GATES")
    if gates:
        candidates.append(str(Path(gates) / WEAK_PATCH))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def check_weak(root, problems):
    amp = root / DRIVER / AMP
    patch = weak_patch(root)
    if not amp.is_file():
        problems.append("%s is gone, so the weak call has no definition" % amp)
        return False
    if patch is None:
        return False
    text = code_only(amp.read_text(encoding="utf-8", errors="replace"))
    defs = re.findall(r"\bint\s+" + WEAK_NAME + r"\s*\(([^)]*)\)", text)
    if len(defs) != 2:
        problems.append("%s declares and defines %s %d time(s), not twice"
                        % (AMP, WEAK_NAME, len(defs)))
        return True
    if len(split_params(defs[0])) or len(split_params(defs[1])):
        problems.append("%s takes (%s), not no arguments" % (WEAK_NAME, defs[0]))
    body = patch.read_text(encoding="utf-8", errors="replace")
    decl = re.search(r"extern\s+int\s+" + WEAK_NAME + r"\s*\(([^)]*)\)\s*"
                     r"__attribute__\s*\(\(\s*weak\s*\)\)\s*;", body)
    if not decl:
        problems.append("%s does not declare %s weak" % (WEAK_PATCH, WEAK_NAME))
        return True
    if split_params(decl.group(1)) != split_params(defs[0]):
        problems.append("the weak declaration takes (%s) but %s defines (%s)"
                        % (decl.group(1), AMP, defs[0]))
    if not re.search(r"if\s*\(\s*" + WEAK_NAME + r"\s*!=\s*NULL\s*\)", body):
        problems.append("the weak call in %s is not guarded, so a kernel without the driver crashes"
                        % WEAK_PATCH)
    call = re.search(r"\(\s*void\s*\)\s*" + WEAK_NAME + r"\s*\(([^)]*)\)\s*;", body)
    if not call:
        problems.append("%s never calls %s and discards the result" % (WEAK_PATCH, WEAK_NAME))
    elif split_params(call.group(1)):
        problems.append("the call passes (%s), but %s takes no arguments" % (call.group(1), WEAK_NAME))
    return True


def main(argv):
    if any(a in ("-h", "--help") for a in argv[1:]):
        print((__doc__ or "").strip())
        return 0
    repo = Path(__file__).resolve().parent.parent
    args = [a for a in argv[1:] if a != "--repo"]
    if "--repo" in argv[1:]:
        index = argv[1:].index("--repo")
        try:
            repo = Path(argv[1:][index + 1]).resolve()
        except IndexError:
            print("FPTRS FAILED: --repo needs a tree")
            return 1
    elif args:
        print("FPTRS FAILED: unknown argument " + args[0])
        return 1
    if not (repo / DRIVER).is_dir():
        print("FPTRS FAILED: %s has no %s" % (repo, DRIVER))
        return 1
    found = tables(repo)
    problems = []
    check_tables(found, problems)
    check_surface(repo, found, problems)
    check_calls(repo, found, problems)
    sites = check_productions(repo, found, problems)
    checked = check_weak(repo, problems)
    if problems:
        for problem in problems:
            print("FPTRS FAILED: " + problem)
        print("FPTRS FAILED: %d problem(s)" % len(problems))
        return 1
    members = [m for t in TABLES for m in found[t]["callbacks"]]
    pairs = len(members) // 2
    call_count = len(calls(repo, found))
    weak = ("and the weak call is int (void) on both sides" if checked else
            "the weak call was not compared: no 0531 patch here, no"
            " AUDIO27_WEAK_PATCH and no K60_GATES")
    print("FPTRS OK: %d tables, %d callbacks in %d pairs, %d assignment site(s) whose"
          " signatures match what they fill, %d calls pass their own context, "
          "no other table under %s, %s"
          % (len(TABLES), len(members), pairs, sites, call_count, DRIVER, weak))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
