#!/usr/bin/env python3
"""P-232b: creation, present and commit must each be visible once."""
import pathlib,sys
SRC=pathlib.Path(__file__).resolve().parents[2]/'drivers/PongMetal/NativeBridgeMetalFrontend.mm'
def main():
    t=SRC.read_text(encoding='utf-8',errors='replace')
    for needle in ('K60CB first command buffer requested','K60CB first presentDrawable'):
        if t.count(needle)!=1:
            print('FAIL expected exactly one %r'%needle); return 1
    cb=t.index('K60CB first command buffer requested')
    if 'nmb_command_buffer_new' not in t[cb:cb+400]:
        print('FAIL the command buffer trace is not in the factory'); return 1
    pd=t.index('K60CB first presentDrawable')
    if 'addCompletedHandler' not in t[pd:pd+300]:
        print('FAIL the present trace is not in presentDrawable'); return 1
    if t.count('gCommits.fetch_add')!=1:
        print('FAIL commit counting moved; the trace premise changed'); return 1
    print('PASS creation and present are traced once, commit has a single counter'); return 0
sys.exit(main())
