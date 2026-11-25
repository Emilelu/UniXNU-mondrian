# Build and flight freeze — 2026-11-23

`state = "frozen"` (build and flight)

The user's instruction on 2026-11-23: the iOS 27 repositories that reach userland
have not been copied completely, and no build or boot may happen until every
difference is accounted for ("没彻底抄完 没确保无任何疏漏之前 禁止构建和上机").

What this freezes:

* no `scripts/build-ios27-linux.sh`, no `unixnu build`, no firmware build;
* no `fastboot boot`, no flashing, no `/dev/block/sda38` writes;
* read-only work only: reading the precedent repositories, diffing them against
  this tree, writing documents and gates.

Exit conditions:

1. `docs/research/ios27/PRECEDENT-PARITY.md` lists every artefact of every
   working 27 repository (patch series, board.toml keys, defconfig keys, boot
   args, ADT keys, tools) with one of: `have`, `copied`, `missing-must-copy`,
   `deliberately-different` (with a reason and a file:line), and the
   `missing-must-copy` count is **zero**;
2. every `deliberately-different` row names the evidence that makes it safe;
3. the user reviews the ledger.

Baseline at freeze time: `k60-gates` HEAD `f4d96936` (0557 wired), `uefi-mondrian`
HEAD `518f2c5` (GOP ruler), last image `1a57304de7eb` (not flown successfully).
