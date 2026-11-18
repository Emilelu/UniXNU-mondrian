#!/usr/bin/env python3
"""P-231: the metal summary line must be read through its format string, not guessed."""
import pathlib,re,sys
SRC=pathlib.Path(__file__).resolve().parents[2]/'drivers/PongMetal/NativeBridgeMetalFrontend.mm'
FIELDS=['c','d','p','x','R','D','F','M','C','B']
def main():
    text=SRC.read_text(errors='replace')
    m=re.search(r'row\("S (c%llu/%llu[^"]*)"',text)
    if not m: print('FAIL the summary format string is gone'); return 1
    order=re.findall(r'([A-Za-z])%llu',m.group(1))
    got=[]; [got.append(x) for x in order if x not in got]
    if got!=FIELDS:
        print('FAIL field order is %r, the documented order is %r'%(got,FIELDS)); return 1
    doc=pathlib.Path(__file__).resolve().parents[2]/'docs/research/gpu/METAL-SUMMARY-FIELDS.md'
    if not doc.exists(): print('FAIL METAL-SUMMARY-FIELDS.md is missing'); return 1
    body=doc.read_text(errors='replace')
    for f in FIELDS:
        if '`%s`'%f not in body:
            print('FAIL the document does not explain field %s'%f); return 1
    if 'gCommits' not in body or 'commit' not in body.lower():
        print('FAIL the document does not tie c to commit'); return 1
    print('PASS the summary fields are read from the format string and documented'); return 0
sys.exit(main())
