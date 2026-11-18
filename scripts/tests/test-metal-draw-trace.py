#!/usr/bin/env python3
"""P-232: a draw that never returns must be visible in the log."""
import pathlib,sys
SRC=pathlib.Path(__file__).resolve().parents[2]/'drivers/PongMetal/NativeBridgeMetalFrontend.mm'
def main():
    t=SRC.read_text(encoding='utf-8',errors='replace')
    if t.count('K60DRAW enter')!=1: print('FAIL expected exactly one enter trace'); return 1
    if t.count('K60DRAW leave')!=1: print('FAIL expected exactly one leave trace'); return 1
    e=t.index('K60DRAW enter'); l=t.index('K60DRAW leave')
    if not e<l: print('FAIL leave is before enter'); return 1
    seg=t[e:l]
    if 'nmb_render_draw' not in seg: print('FAIL the traced region does not wrap the runtime draw'); return 1
    if 'gDraws.load()<=4' not in t: print('FAIL the trace is not bounded to the first draws'); return 1
    print('PASS the runtime draw is bounded-traced on both sides'); return 0
sys.exit(main())
