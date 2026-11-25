#!/usr/bin/env python3
"""Check whether ccache is on the iOS 27 kernel compiler chain, offline.

Three questions, in the order that matters:

1. Is there a ccache here, and is it version 4 or newer?
2. Is CCACHE_DIR an existing directory we can write to?
3. Is ccache actually on the compiler command chain?

(3) is the question grep cannot answer, because the chain is not in this
repository:

    scripts/build-ios27-linux.sh        exports CCACHE, or does not
      -> unixnu build kernel            fw scripts/unixnu/kernel.py:186 copies os.environ
      -> scripts/build-xnu-4k-baseline.sh -> scripts/build-xnu-generic.sh
      -> make                           XNU makedefs/MakeInc.def:175  KCC = $(CCACHE) $(CC)

so the only wiring that counts is a literal CCACHE=<ccache> that reaches that
make: exported by the entry script, or named on the kernel make line.  A PATH
shim does not count, because MakeInc.cmd:227 resolves CC with
`xcrun -find clang`, so a wrapper called clang on PATH is never consulted for the
kernel compiler.  That case reports "cannot tell" instead of guessing.

Exit codes: 0 wired, 1 not wired (or ccache/CCACHE_DIR unusable), 2 cannot tell.

--probe answers the question the wiring cannot: is this ccache able to cache the
flags XNU really uses?  Every XNU compile rule passes -MJ (MakeInc.rule:513,
:521, :543) and ccache rejects that option as unsupported, so the objects stay
uncacheable and Hits stays 0.  The probe replays that comparison with the
toolchain clang: one tiny file, twice with -MJ and twice without.

--self-test builds throwaway trees (wired, not wired, comment only, computed
value, PATH shim, missing scripts, old ccache, missing cache dir) in a scratch
directory and checks the exit codes.  It runs no build.

Related reading: docs/research/ios27/CCACHE.md.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ENTRY = "scripts/build-ios27-linux.sh"
BUILDER = "scripts/build-xnu-generic.sh"
SCANNED = (ENTRY, BUILDER)
DEFAULT_CACHE_DIR = "/opt/k60/trees/.ccache"
KNOWN_COMPILERS = (
    "/opt/unixnu-linux/llvm/bin/clang-24",
    "/opt/unixnu-linux/llvm/bin/clang",
)

WIRED = "wired"
NOT_WIRED = "not wired"
CANNOT_TELL = "cannot tell"

# CCACHE=value, but not the tail of some other name such as x.o_CFLAGS_ADD.
ASSIGN_RE = re.compile(r"(?<![\w.])CCACHE=(\"[^\"]*\"|'[^']*'|[^\s;|&()\"']+)")
# The directory the build writes to has to be the directory the reader reads.
DIR_ASSIGN_RE = re.compile(r"(?<![\w.])CCACHE_DIR=(\"[^\"]*\"|'[^']*'|[^\s;|&()\"']+)")


# --------------------------------------------------------------------------- #
# configuration checks
# --------------------------------------------------------------------------- #


def human_bytes(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TiB"


def check_binary(override: str | None) -> tuple[bool, str, str | None]:
    """(a) ccache exists and is version 4 or newer."""
    path = override or shutil.which("ccache")
    if not path:
        return (False, "no ccache on PATH (and --ccache was not given)", None)
    if not (os.path.isfile(path) and os.access(path, os.X_OK)):
        return (False, f"{path} is not an executable file", path)
    try:
        proc = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return (False, f"{path} --version failed: {exc}", path)
    if proc.returncode != 0:
        return (False, f"{path} --version exited {proc.returncode}", path)
    version = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", proc.stdout + proc.stderr)
    if not version:
        return (False, f"cannot read a version from: {proc.stdout.strip()!r}", path)
    if int(version.group(1)) < 4:
        return (False, f"{path} version {version.group(0)}; 4.0 or newer is required", path)
    return (True, f"{path} version {version.group(0)}", path)


def check_cache_dir(path: Path) -> tuple[bool, str]:
    """(b) CCACHE_DIR exists, is a directory, and really takes a write."""
    if not path.exists():
        return (False, f"{path} does not exist")
    if not path.is_dir():
        return (False, f"{path} is not a directory")
    probe = path / f".check-ccache-{os.getpid()}"
    try:
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as exc:
        return (False, f"{path} is not writable ({exc.strerror or exc})")
    return (True, f"{path} writable, {human_bytes(shutil.disk_usage(path).free)} free")


# --------------------------------------------------------------------------- #
# wiring scan
# --------------------------------------------------------------------------- #


@dataclass
class Wiring:
    state: str = CANNOT_TELL
    evidence: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    cache_dir: str | None = None
    cache_dir_at: str | None = None


def strip_comment(line: str) -> str:
    """Drop a shell comment, respecting quotes.  `echo '#x'` keeps its hash."""
    quote = ""
    prev = ""
    for i, ch in enumerate(line):
        if quote:
            if ch == quote and prev != "\\":
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1].isspace() or line[i - 1] in ";|&("):
            return line[:i]
        prev = ch
    return line


def logical_lines(path: Path):
    """(first physical line number, text) with backslash continuations joined."""
    buf = ""
    start = 0
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for n, raw in enumerate(fh, 1):
            raw = raw.rstrip("\n")
            if not buf:
                start = n
            if raw.endswith("\\"):
                buf += raw[:-1] + " "
                continue
            yield start, buf + raw
            buf = ""
    if buf:
        yield start, buf


def classify_value(value: str) -> tuple[str, str]:
    """wired / off / unknown, plus a phrase that explains the verdict."""
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    if not v:
        return ("off", "explicitly empty; ccache is off")
    if "$" in v or "`" in v:
        return ("unknown", f"computed value {v!r}; this checker cannot run it")
    if v == "ccache":
        found = shutil.which("ccache")
        if found:
            return ("wired", f"`ccache` resolves to {found}")
        return ("unknown", "`ccache` is not on PATH")
    if v.endswith("/ccache"):
        if os.path.isfile(v) and os.access(v, os.X_OK):
            return ("wired", f"absolute ccache {v}")
        return ("unknown", f"absolute path {v} is not an executable")
    return ("unknown", f"unrecognised value {v!r}")


def scan_wiring(root: Path) -> Wiring:
    w = Wiring()

    def exported_before(prefix: str) -> bool:
        return bool(
            re.search(r"(^|[\s;&|])(export|env|make)(\s|$)", prefix)
            or prefix.rstrip().endswith("make")
        )

    found: list[str] = []
    assigns: list[tuple[str, int, str, bool]] = []
    bare_exports: list[tuple[str, int]] = []
    off: list[str] = []
    comment_lines: dict[str, list[int]] = {}
    path_injections: list[str] = []
    dir_assigns: list[tuple[str, int, str, bool]] = []
    dir_exports: list[tuple[str, int]] = []

    for rel in SCANNED:
        path = root / rel
        if not path.is_file():
            w.missing.append(rel)
            continue
        found.append(rel)
        try:
            lines = list(logical_lines(path))
        except OSError as exc:
            w.notes.append(f"{rel}: unreadable ({exc})")
            w.missing.append(rel)
            continue
        for lineno, joined in lines:
            code = strip_comment(joined)
            if "CCACHE" in joined and "CCACHE" not in code:
                comment_lines.setdefault(rel, []).append(lineno)
            if not code.strip():
                continue
            if re.search(r"unixnu\s+build\s+kernel", code):
                w.notes.append(f"{rel}:{lineno}: kernel build call (unixnu build kernel)")
            if re.search(r"make\b.*xnu-work", code):
                w.notes.append(f"{rel}:{lineno}: kernel make line (make -C .cache/xnu-work)")
            if "command -v ccache" in code:
                w.notes.append(
                    f"{rel}:{lineno}: install guard (`command -v ccache`); it gates the wiring, it is not the wiring"
                )
            if re.match(r"\s*export\s+CCACHE\s*$", code):
                bare_exports.append((rel, lineno))
            if re.match(r"\s*export\s+CCACHE_DIR\s*$", code):
                dir_exports.append((rel, lineno))
            if re.search(r"\bPATH=", code) and "ccache" in code:
                w.notes.append(
                    f"{rel}:{lineno}: PATH mentions ccache, but MakeInc.cmd:227 resolves CC with "
                    "xcrun, so PATH cannot put ccache in front of the kernel compiler"
                )
                path_injections.append(
                    f"{rel}:{lineno}: PATH-based injection; ccache is not named in CCACHE, "
                    "so it cannot reach the kernel compiler"
                )
            for m in ASSIGN_RE.finditer(code):
                prefix = code[: m.start()]
                assigns.append((rel, lineno, m.group(1), exported_before(prefix)))
            for m in DIR_ASSIGN_RE.finditer(code):
                prefix = code[: m.start()]
                dir_assigns.append((rel, lineno, m.group(1), exported_before(prefix)))

    wired: list[str] = []
    unknown: list[str] = list(path_injections)
    for rel, lineno, value, exported in assigns:
        kind, detail = classify_value(value)
        export_at = next((n for r, n in bare_exports if r == rel and n > lineno), None)
        text = f"{rel}:{lineno}: CCACHE={value} ({detail})"
        if kind == "wired" and (exported or export_at):
            if export_at:
                text += f", exported at {rel}:{export_at}"
            wired.append(text)
        elif kind == "wired":
            unknown.append(text + "; set but not exported, so make would not see it")
        elif kind == "off":
            off.append(text)
        else:
            unknown.append(text)

    w.evidence = wired + unknown + off + w.evidence
    wired_files = {item.split(":", 1)[0] for item in wired}
    for rel, linenos in comment_lines.items():
        if rel in wired_files:
            # The comments explain the wiring that is present; that is not noise
            # worth reporting.  They only matter where nothing else is wired yet.
            continue
        listed = ",".join(str(n) for n in linenos)
        w.notes.insert(
            0, f"{rel}:{listed}: only comments mention CCACHE; a comment is not wiring"
        )
    for rel, lineno, value, exported in dir_assigns:
        export_at = next((n for r, n in dir_exports if r == rel and n > lineno), None)
        if w.cache_dir is None and (exported or export_at):
            w.cache_dir = value.strip("\"'")
            w.cache_dir_at = f"{rel}:{lineno}"

    if wired:
        w.state = WIRED
    elif unknown or w.missing or not found:
        w.state = CANNOT_TELL
    else:
        w.state = NOT_WIRED
    return w


# --------------------------------------------------------------------------- #
# probe: can this ccache cache -MJ?
# --------------------------------------------------------------------------- #

PROBE_SOURCE = "int probe(int x) { return x * 3 + 1; }\n"
# The toolchain clang has no default triple; this is the one XNU compiles for.
PROBE_TARGET = "arm64e-apple-ios27.0.0"


def parse_print_stats(text: str) -> dict[str, int]:
    stats: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.replace("\t", " ").split()
        if len(parts) >= 2 and parts[-1].isdigit():
            stats[parts[0]] = int(parts[-1])
    return stats


def find_compiler(explicit: str | None) -> str | None:
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    for candidate in KNOWN_COMPILERS:
        if os.path.isfile(candidate):
            return candidate
    return shutil.which("clang")


def _ccache_env(cache_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["CCACHE_DIR"] = str(cache_dir)
    env.pop("CCACHE_DEBUG", None)
    env.pop("CCACHE_DISABLE", None)
    return env


def _stats(ccache: str, cache_dir: Path) -> dict[str, int]:
    proc = subprocess.run(
        [ccache, "--print-stats"],
        env=_ccache_env(cache_dir),
        capture_output=True,
        text=True,
        timeout=120,
    )
    return parse_print_stats(proc.stdout)


def _summarise(stats: dict[str, int]) -> dict[str, int]:
    return {
        "hits": stats.get("direct_cache_hit", 0) + stats.get("preprocessed_cache_hit", 0),
        "misses": stats.get("cache_miss", 0),
        # ccache 4.9 prints one counter per reason; -MJ lands in this one, and
        # `ccache -s` folds it into the "Uncacheable calls" line.
        "unsupported": stats.get("unsupported_compiler_option", 0),
    }


def _phase(
    ccache: str, compiler: str, workdir: Path, cache_dir: Path, with_mj: bool
) -> dict[str, int]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    source = workdir / "probe.c"
    source.write_text(PROBE_SOURCE, encoding="utf-8")
    subprocess.run(
        [ccache, "-z"], env=_ccache_env(cache_dir), capture_output=True, timeout=120
    )
    for i in (1, 2):
        args = [
            compiler,
            "-target",
            PROBE_TARGET,
            "-O1",
            "-c",
            str(source),
            "-o",
            str(workdir / f"p{i}.o"),
        ]
        if with_mj:
            args += ["-MJ", str(workdir / f"p{i}.json")]
        proc = subprocess.run(
            [ccache] + args,
            env=_ccache_env(cache_dir),
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip()[:400] or "probe compile failed")
    return _summarise(_stats(ccache, cache_dir))


def run_probe(ccache: str, compiler: str, base: Path) -> dict:
    """Compile one file twice with -MJ and twice without; report each.

    The cache and the objects live under `base`, which has to be a local
    filesystem: on the 9p mount under /mnt/e one `ccache -z` costs about ten
    seconds and one `--print-stats` about three, against 0.2 s and 0.0 s on the
    Linux side of the same machine.
    """
    workdir = Path(tempfile.mkdtemp(prefix="probe-", dir=str(base)))
    try:
        with_mj = _phase(ccache, compiler, workdir, workdir / "cache-mj", True)
        plain = _phase(ccache, compiler, workdir, workdir / "cache-plain", False)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    if with_mj["hits"] > 0:
        verdict = "cacheable"
    elif with_mj["unsupported"] > 0 and plain["hits"] > 0:
        verdict = "blocked (ccache calls -MJ unsupported)"
    elif with_mj["unsupported"] > 0:
        verdict = "inert (ccache refuses -MJ)"
    else:
        verdict = "unclear"
    return {"with_mj": with_mj, "plain": plain, "verdict": verdict}


def describe_probe(result: dict) -> str:
    mj, plain = result["with_mj"], result["plain"]
    head = (
        f"-MJ: {mj['hits']} hit(s), {mj['misses']} miss(es), "
        f"{mj['unsupported']} unsupported option | "
        f"no -MJ: {plain['hits']} hit(s), {plain['misses']} miss(es)"
    )
    return f"{result['verdict']}; {head}"


# --------------------------------------------------------------------------- #
# scratch and fixtures
# --------------------------------------------------------------------------- #


def scratch_parent(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        path.mkdir(parents=True, exist_ok=True)
        return path
    for candidate in (os.environ.get("K60_SCRATCH"), "/mnt/e/iOS Port/Work/scratch"):
        if candidate and os.path.isdir(candidate):
            return Path(candidate)
    home = Path(os.path.expanduser("~")) / ".cache" / "k60"
    home.mkdir(parents=True, exist_ok=True)
    return home


def probe_base(explicit: str | None) -> Path:
    """Where the probe keeps its two throwaway ccache directories."""
    path = Path(explicit) if explicit else Path(os.path.expanduser("~")) / ".cache" / "k60" / "ccache-probe"
    path.mkdir(parents=True, exist_ok=True)
    return path


FAKE_CCACHE = """#!/bin/sh
case "$1" in
  --version) echo "ccache version VERSION"; exit 0 ;;
  -z|--zero-stats) exit 0 ;;
  --print-stats|-s|--show-stats) echo "cacheable_calls\\t0"; echo "uncacheable_calls\\t0"; exit 0 ;;
esac
shift
exec "$@"
"""

FAKE_CLANG = """#!/bin/sh
echo fake-clang "$@" >&2
exit 0
"""


@dataclass
class Case:
    name: str
    expect: int
    entry: str  # file body; empty string means "no such file"
    builder: str
    cache_dir: bool = True
    old_ccache: bool = False


def fixture_cases() -> list[Case]:
    wired = (
        "#!/bin/sh\n"
        "if command -v ccache >/dev/null 2>&1; then\n"
        "\tCCACHE=ccache\n"
        "\texport CCACHE\n"
        "fi\n"
        "python3 ./unixnu build kernel --device \"$ROOT\"\n"
    )
    builder = (
        "#!/bin/sh\n"
        "make -C .cache/xnu-work build SDKROOT=iphoneos CFLAGS_EXTRA=\"$EXTRA_CFLAGS\"\n"
    )
    return [
        Case("wired", 0, wired, builder),
        Case(
            "not wired, comment only",
            1,
            "#!/bin/sh\n# export CCACHE=ccache  (tried; ccache cannot cache -MJ)\n"
            "python3 ./unixnu build kernel --device \"$ROOT\"\n",
            builder,
        ),
        Case(
            "computed value",
            2,
            "#!/bin/sh\nexport CCACHE=\"$(command -v ccache)\"\n"
            "python3 ./unixnu build kernel --device \"$ROOT\"\n",
            builder,
        ),
        Case(
            "PATH shim only",
            2,
            "#!/bin/sh\nPATH=\"$PWD/tools/ccache-bin:$PATH\"\n"
            "python3 ./unixnu build kernel --device \"$ROOT\"\n",
            builder,
        ),
        Case("missing scripts", 2, "", ""),
        Case("old ccache", 1, wired, builder, old_ccache=True),
        Case("missing cache dir", 1, wired, builder, cache_dir=False),
    ]


def build_fixture(case: Case, root: Path, new_bin: Path, old_bin: Path, cache: Path) -> Path:
    """Materialise one fixture tree; return the directory to pass as --root."""
    target = root / case.name.split(",")[0].replace(" ", "-")
    (target / "scripts").mkdir(parents=True, exist_ok=True)
    if case.entry:
        (target / ENTRY).write_text(case.entry, encoding="utf-8")
    if case.builder:
        (target / BUILDER).write_text(case.builder, encoding="utf-8")
    if case.cache_dir:
        cache.mkdir(parents=True, exist_ok=True)
    return target


def run_self_test(args) -> int:
    scratch = scratch_parent(args.scratch_dir)
    root = Path(tempfile.mkdtemp(prefix="check-ccache-selftest-", dir=str(scratch)))
    failures = 0
    try:
        new_bin = root / "bin-new"
        old_bin = root / "bin-old"
        for directory, version in ((new_bin, "4.9.1"), (old_bin, "3.7.9")):
            directory.mkdir(parents=True, exist_ok=True)
            fake = directory / "ccache"
            fake.write_text(FAKE_CCACHE.replace("VERSION", version), encoding="utf-8")
            fake.chmod(0o755)
            shim_dir = directory / "clang"
            shim_dir.mkdir(exist_ok=True)
            shim = shim_dir / "clang"
            shim.write_text(FAKE_CLANG, encoding="utf-8")
            shim.chmod(0o755)
        cases = fixture_cases()
        print(f"self-test  {len(cases)} fixture trees under {root}")
        for case in cases:
            cache = root / ("cache-" + case.name.split(",")[0].replace(" ", "-"))
            target = build_fixture(case, root, new_bin, old_bin, cache)
            bindir = old_bin if case.old_ccache else new_bin
            env = dict(os.environ)
            env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
            env.pop("CCACHE_DIR", None)
            cmd = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--root",
                str(target),
                "--cache-dir",
                str(cache),
                "--quiet",
            ]
            proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
            ok = proc.returncode == case.expect
            failures += 0 if ok else 1
            print(
                f"self-test  {'PASS' if ok else 'FAIL'}  {case.name:<26} "
                f"exit {proc.returncode} (expect {case.expect})"
            )
            if not ok:
                print(proc.stdout.rstrip().replace("\n", "\n          "))
                if proc.stderr.strip():
                    print("          stderr: " + proc.stderr.strip()[:400])
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print(f"self-test  {'all passed' if not failures else f'{failures} failed'}")
    return 0 if not failures else 1


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #


def report(label: str, text: str, quiet: bool) -> None:
    if not quiet:
        print(f"{label:<14}{text}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline check of ccache on the iOS 27 kernel build.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", default=str(REPO), help="checkout to scan")
    parser.add_argument("--ccache", dest="ccache_path", default=None, help="ccache executable")
    parser.add_argument(
        "--cache-dir",
        default=os.environ.get("CCACHE_DIR") or DEFAULT_CACHE_DIR,
        help=f"CCACHE_DIR to check (default: $CCACHE_DIR or {DEFAULT_CACHE_DIR})",
    )
    parser.add_argument("--probe", action="store_true", help="test whether -MJ compiles are cacheable")
    parser.add_argument("--probe-compiler", default=None, help="compiler the probe should use")
    parser.add_argument("--scratch-dir", default=None, help="parent for temporary directories")
    parser.add_argument(
        "--probe-dir",
        default=None,
        help="where the probe keeps its throwaway caches (default: ~/.cache/k60/ccache-probe)",
    )
    parser.add_argument("--self-test", action="store_true", help="run the built-in fixtures")
    parser.add_argument("--quiet", action="store_true", help="print only the result line")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test(args)

    root = Path(args.root)
    ok_bin, bin_detail, ccache_path = check_binary(args.ccache_path)
    ok_dir, dir_detail = check_cache_dir(Path(args.cache_dir))
    wiring = scan_wiring(root)

    report("ccache", ("ok    " if ok_bin else "FAIL  ") + bin_detail, args.quiet)
    report("CCACHE_DIR", ("ok    " if ok_dir else "FAIL  ") + dir_detail, args.quiet)
    report("wiring", wiring.state, args.quiet)
    for item in wiring.evidence:
        report("  evidence", item, args.quiet)
    for item in wiring.notes:
        report("  note", item, args.quiet)
    for rel in wiring.missing:
        report("  missing", rel, args.quiet)

    if wiring.cache_dir:
        report(
            "build dir",
            f"{wiring.cache_dir} (pinned at {wiring.cache_dir_at})",
            args.quiet,
        )
        pinned = os.path.expanduser(wiring.cache_dir)
        reading = os.path.expanduser(args.cache_dir)
        if "$" not in wiring.cache_dir and os.path.normpath(pinned) != os.path.normpath(reading):
            report(
                "  MISMATCH",
                "the build writes to one cache and this check reads another; "
                "`ccache -s` against the reading path would report 0 hits for a build "
                "that never wrote there",
                args.quiet,
            )
    else:
        report(
            "build dir",
            "not pinned; ccache falls back to its default (~/.cache/ccache)",
            args.quiet,
        )

    effect = "unknown (pass --probe, or compare `ccache -s` before and after a build)"
    if args.probe:
        compiler = find_compiler(args.probe_compiler)
        if not compiler:
            effect = "skipped (no clang; pass --probe-compiler)"
        elif not (ok_bin and ccache_path):
            effect = "skipped (no usable ccache)"
        else:
            base = probe_base(args.probe_dir)
            try:
                effect = describe_probe(run_probe(ccache_path, compiler, base))
            except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
                effect = f"failed ({exc})"
    report("effect", effect, args.quiet)
    if not args.quiet and wiring.state == WIRED:
        print(
            "               wired means CCACHE reaches make; it does not mean any object is\n"
            "               cacheable.  Hits only move when the -MJ rules stop blocking ccache."
        )

    if wiring.state == WIRED and ok_bin and ok_dir:
        code = 0
        outcome = "wired"
    elif wiring.state == CANNOT_TELL and ok_bin and ok_dir:
        code = 2
        outcome = "cannot tell"
    else:
        code = 1
        if wiring.state == WIRED:
            outcome = "wired, but ccache or CCACHE_DIR is unusable"
        else:
            outcome = wiring.state
    if args.quiet:
        print(f"result         {outcome} (exit {code})")
    else:
        report("result", f"{outcome} (exit {code})", False)
    return code


if __name__ == "__main__":
    sys.exit(main())
