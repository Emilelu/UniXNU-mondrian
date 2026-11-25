#!/usr/bin/env python3
"""Report the three numbers that keep getting conflated.

`scripts/check-series-numbering.py` only validates entries that carry a
four-digit number, so quoting its count as "how many patches the series has"
is wrong for any series that also lists unnumbered files.  This prints all
three quantities side by side so a quotation can name which one it means:

  numbered   entries matching ^NNNN[a-z]*-...patch   (what the numbering gate sees)
  unnumbered entries ending .patch without a number  (listed, but not counted)
  lines      every non-comment line ending .patch    (the real size of the list)

With --list it also reports how many lines of the assembled
`xnu-patches.list` come from each series directory, which is the only count
that says what the build actually applied.
"""
import argparse
import pathlib
import re

NUMBERED = re.compile(r"^(\d{4})([a-z]*)-.*\.patch$")
ROOT = pathlib.Path(__file__).resolve().parents[1]


def entries(path):
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and s.endswith(".patch"):
            out.append(s)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", default=str(ROOT))
    ap.add_argument("--list", action="store_true", help="also attribute xnu-patches.list lines")
    args = ap.parse_args()
    root = pathlib.Path(args.tree)

    for series in sorted(root.glob("patches/*/series")):
        names = entries(series)
        numbered = [n for n in names if NUMBERED.match(n)]
        unnumbered = [n for n in names if not NUMBERED.match(n)]
        print(f"{series.relative_to(root)}: numbered {len(numbered)}, "
              f"unnumbered {len(unnumbered)}, patch lines {len(names)}")
        for n in unnumbered:
            print(f"    unnumbered: {n}")

    if args.list:
        listed = []
        for cand in root.glob("**/xnu-patches.list"):
            listed = [l.strip() for l in cand.read_text(encoding="utf-8").splitlines()
                      if l.strip() and not l.strip().startswith("#")]
            print(f"\n{cand}: {len(listed)} lines")
            break
        if not listed:
            print("\nno xnu-patches.list found")
            return
        dirs = sorted({p.name for p in root.glob("patches/xnu*") if p.is_dir()})
        for d in dirs:
            have = {p.name for p in (root / "patches" / d).glob("*.patch")}
            n = sum(1 for l in listed if pathlib.Path(l).name in have)
            print(f"    from patches/{d}: {n}")


if __name__ == "__main__":
    main()
