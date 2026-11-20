#!/usr/bin/env python3
"""check-audio27-sheng-refs.py - re-derive the sheng inventory page.

Iron rule 12 (2026-11-20) says the kernel and driver layers must name
UniXNU-sheng among their reference sources, and that a page saying "we read
sheng" is not enough: the series has to be walked patch by patch. That
inventory lives in docs/research/audio/IOS27-SHENG-REFS.md and this script
checks the following structural claims:

  * every patch listed in sheng's patches/xnu-12377/series has exactly one row
    in the page table, judged audio, partial or no;
  * a row judged no is checked against the patch itself: the files it touches
    must not look like audio (audio, geni, i2c, codec, sound, wcd, glink,
    adsp, cs35), so the verdict cannot rot while the patch stays put;
  * a row judged audio or partial must cite its own patch, and every sheng
    file:line citation on the page must resolve in the same checkout;
  * docs/research/SOURCES.toml must list at least SOURCES_MIN distinct paths
    under [subsystem.audio] that exist in that checkout.

Usage: python3 scripts/check-audio27-sheng-refs.py [repo]
Exit: 0 the page agrees with the checkout, 1 it does not, 3 no checkout here.
"""
import os
import re
import sys
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
SHENG = Path(os.environ.get("SHENG_REPO") or "/mnt/e/k60-work/UniXNU-sheng")
PAGE = REPO / "docs" / "research" / "audio" / "IOS27-SHENG-REFS.md"
SERIES = SHENG / "patches" / "xnu-12377" / "series"
SOURCES = REPO / "docs" / "research" / "SOURCES.toml"
SOURCES_MIN = 3
NOT_AUDIO = re.compile(r"audio|geni|i2c|codec|sound|wcd|glink|adsp|cs35", re.I)
BT = chr(96)
ROW = re.compile(r"^\|\s*" + BT + r"([A-Za-z0-9._-]+\.patch)" + BT + r"\s*\|\s*(audio|partial|no)\s*\|", re.M)
CITE = re.compile(r"sheng:([A-Za-z0-9._/-]+):(\d+)")


def series_patches():
    names = []
    for line in SERIES.read_text(errors='replace').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        names.append(line)
    return names


def touched(text):
    files = []
    for line in text.splitlines():
        if line.startswith("+++ b/"):
            files.append(line[len('+++ b/'):].strip())
    return files


def rows(text):
    """name -> (verdict, full row line). Duplicates are reported by check()."""
    found = {}
    for match in ROW.finditer(text):
        name, verdict = match.group(1), match.group(2)
        start = text.rfind('\n', 0, match.start()) + 1
        end = text.find('\n', match.start())
        line = text[start:end if end != -1 else None]
        found.setdefault(name, []).append((verdict, line))
    return found


def citation_problems(text):
    problems = []
    for match in CITE.finditer(text):
        rel, number = match.group(1), int(match.group(2))
        target = SHENG / rel
        if not target.is_file():
            problems.append("the sheng checkout has no %s (cited at line %d)" % (rel, number))
            continue
        lines = len(target.read_text(encoding='utf-8', errors='replace').splitlines())
        if number < 1 or number > lines:
            problems.append("%s has %d lines, so :%d cannot be read" % (rel, lines, number))
    return problems


def sheng_sources():
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            return None
    if not SOURCES.exists():
        return None
    data = tomllib.loads(SOURCES.read_text())
    audio = data.get('subsystem', {}).get('audio', {})
    prefix = "UniXNU-sheng/"
    return {str(item["path"])[len(prefix):] for item in audio.get("required", [])
            if str(item.get("path", "")).startswith(prefix)}


def check():
    """(ok, problems, summary)"""
    problems = []
    if not PAGE.exists():
        return False, ["no %s" % PAGE.relative_to(REPO)], None
    text = PAGE.read_text()
    listed = series_patches()
    table = rows(text)
    counts = {'audio': 0, 'partial': 0, 'no': 0}
    for name in listed:
        if name not in table:
            problems.append("the series lists %s and the page has no row for it" % name)
            continue
        if len(table[name]) > 1:
            problems.append("the page gives %s %d rows" % (name, len(table[name])))
            continue
        verdict, line = table[name][0]
        counts[verdict] += 1
        patch = SERIES.parent / name
        if not patch.exists():
            problems.append("the series names %s and the patch file is not there" % name)
            continue
        files = touched(patch.read_text(errors='replace'))
        if verdict == 'no':
            hits = [f for f in files if NOT_AUDIO.search(f)]
            if hits:
                problems.append("%s is judged no and touches %s" % (name, hits[0]))
        elif not any(rel == 'patches/xnu-12377/' + name for rel, _ in CITE.findall(line)):
            problems.append("%s is judged %s and gives no sheng:path:line for its own patch" % (name, verdict))
    for name in table:
        if name not in listed:
            problems.append("the page has a row for %s, which the series does not list" % name)
    problems.extend(citation_problems(text))
    sources = sheng_sources()
    count = len(sources or ())
    if sources is None:
        problems.append("cannot read [subsystem.audio] from docs/research/SOURCES.toml (requires tomllib or tomli)")
    else:
        if count < SOURCES_MIN:
            problems.append("[subsystem.audio] lists %d distinct sheng path(s), fewer than %d" % (count, SOURCES_MIN))
        for rel in sorted(sources):
            if not (SHENG / rel).is_file():
                problems.append("[subsystem.audio] source is missing in the selected sheng checkout: %s" % rel)
    citations = len(CITE.findall(text))
    summary = '%d listed patches (%d audio, %d partial, %d no), %d citation(s) resolve, %d sheng source(s) in the record' % (
        len(listed), counts['audio'], counts['partial'], counts['no'], citations, count or 0)
    return (not problems), problems, summary


def main(argv):
    if any(a in ('-h', '--help') for a in argv):
        print((__doc__ or '').strip())
        return 0
    if not SERIES.exists():
        print("SHENG REFS: no sheng checkout at %s (set SHENG_REPO); nothing to compare" % SHENG)
        return 3
    ok, problems, summary = check()
    for problem in problems:
        print("SHENG REFS: %s" % problem)
    if not ok:
        print("SHENG REFS FAILED: %d problem(s)" % len(problems))
        return 1
    print("SHENG REFS OK " + summary)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))