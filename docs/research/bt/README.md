# Bluetooth research (copied from the iOS 16 line)

These documents were written on `feat/bt-research` (worktree `E:/hackios/k60-bt`)
while the Bluetooth driver was built and flown against iOS 16.6.1 (20G81). They are
copied here unchanged so the iOS 27 line keeps the evidence, the criteria and the
mistakes. **Read them as history of the same driver, not as a description of this
branch.**

What does not carry over:

| Referenced there | Why it does not exist here |
| --- | --- |
| `patches/xnu/05xx` (242-line series) | the 16.6.1 series; the 12377 line carries its own 19 patches under `patches/xnu-12377/` |
| `patches/bt/` | a byte-identical mirror of `patches/xnu/0507`–`0515`, kept with the 16 test bed |
| `board.toml` `[payload.runtime]` | not enabled on this branch (see `docs/plans/BT-IOS27-PORT.md` §7) |
| flight logs under `E:/k60-work/evidence/` | host paths, not repository content |

## Reading order

1. `RESEARCH.md` — the hardware truth: QCA6490 on GENI UART, firmware family, what the
   official component does and does not do.
2. `S4-SPEC.md` — the transport ABI and the ledger of every change (0516…0525), each
   with file:line and artifact hashes.
3. `HANDOFF.md` — the chronological handoff: every flight, its criteria and its gaps.
4. `MARCONI-AOP-GAP.md` — why `marconi-bt` is an AOP/SPU control channel and not an HCI
   endpoint, and what `bluetoothd` actually matches.
5. `D8`–`D12` plans — the observation flights and what each one was meant to prove.
6. `../plans/BT-USERLAND-COMPARE.md` — the iOS 16 versus iOS 27 userland cost.

## What this branch adds on top

`scripts/check-bluetooth-dt.py`, `check-bluetooth-kernel.py` and
`check-bluetooth-userspace.py` are the executable form of the contract; the CI job
`ios27-kernel` runs the kernel one against every build.
