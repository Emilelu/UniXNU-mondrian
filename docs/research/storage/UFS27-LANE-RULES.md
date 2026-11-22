# ufs27 lane rules — from the Lead's broadcast of 2026-11-22

This file is this lane's own copy of the standing rules, so they survive context
compression. Anything below is binding on every later ufs27 round; it does not
replace `docs/research/eight-step/ufs-27.toml`, it only says how work is done.

## 1. Shared RAG library, and the order of evidence

- Library root: `E:\k60-work\kb\kb.sqlite` (WSL `/mnt/e/k60-work/kb`), 6,194
  documents / 142,260 blocks.
- Engine: `C:/Users/Emilelu/.dsh/profiles/desktop/node_modules/dsh-kb-rag/kb_engine.py`
  (the Lead's command line assumes `kb_engine.py` on the path).
- Verified from this lane on 2026-11-22 (Windows Python, not WSL):

```sh
cd /c/Users/Emilelu/.dsh/profiles/desktop/node_modules/dsh-kb-rag
NO_PROXY='localhost,127.0.0.1,::1' HF_ENDPOINT='https://hf-mirror.com' python - <<'PY'
import json, subprocess, sys
req = {"kb_root": "E:/k60-work/kb", "query": "IOBlockStorageDevice prelink fileset entry", "top_k": 2}
print(subprocess.run([sys.executable, "kb_engine.py", "search"],
                     input=json.dumps(req), capture_output=True, text=True).stdout)
PY
# => rc 0, "mode_used": "hybrid", results include fuxi-xrc111.md §开发经验 on IOBlockStorageDevice
```

Two practical notes from that run: `kb_root` accepts the Windows path when the
engine runs under Windows Python, and the embedder prints a `FutureWarning` plus a
tqdm line on stderr — neither is a failure.

**Order of evidence, binding** (Lead, item 2): an assertion about official
documentation or about someone else's implementation is checked in the library
first, and the hit is cited as `file:section`; only on a miss does the web get
used, with a URL; if neither has it, the text says **「未证」**. Never assert from
memory when one of the three is available.

## 2. Environment traps

- `NO_PROXY=localhost,127.0.0.1,::1` — brackets around `[::1]` break the match.
- `HF_ENDPOINT=https://hf-mirror.com` for anything that pulls model weights.

## 3. P-300: a 0-byte log is not evidence the kernel did not run

The 27 kernel produces no serial output at all, so "0 bytes captured" must never
be read as "the kernel never started". Combined with the standing no-build /
no-boot-here rule, this lane has no path to that misreading — but any sentence
this lane writes about a boot must carry that caveat rather than infer liveness
from log volume.

## 4. Boot freeze (user, 2026-11-22 03:02)

`docs/engineering/BOOT-FREEZE.md` holds `state=frozen`; every `fastboot boot` is
blocked. Thawing requires, in one and the same boot: a log path inside that boot,
automatic boot, and a watchdog-triggered reset. This lane never boots, so the
freeze changes nothing operationally — it does change what may be claimed: no
result of this line may depend on a device boot happening soon.

## 5. P-307: ramoops lives in DRAM and dies with the power

Any channel-class document must answer four questions: **lifetime**,
**read_moment**, **writer**, **loss_condition**. The new
`scripts/check-channel-lifetime.py` enforces it. Two consequences here: this
branch does not yet carry that script (checked 2026-11-22 — the file is absent in
`E:/k60-work/ufs27/scripts/`), so the rule is followed by hand until the branch
picks it up; and none of this lane's documents describe a diagnostic channel, so
none is currently in scope — if one is ever added, the four answers come first.

## What this lane is still waiting on

Unchanged by the broadcast: ⑦ needs F3's real build tree, that tree's
`cpo.json`, a three-member `libNativeUfs.a` and a saved `ld` stderr pair; the two
bare `test -f` lines (`scripts/build-xnu-generic.sh:730`, `:767`) belong to the
Lead; the eleven `IOBlockStorageDevice` imports belong to bt's Route D; ring 5
belongs to the fileset-entry owner. No F3 diff, no boot, no build.

## 6. P-308 boundary: `-enable_kprintf_spam` and 0557 travel together (Lead, 2026-11-22)

The Lead re-opened `-enable_kprintf_spam`, but only on a tree that carries patch
**0557**: 0557 removes the print that ran in `initialize_screen()` before
`v_rows` existed and moves the same geometry numbers to after
`gc_initialize()`. `scripts/check-kprintf-enabled.py` now requires the flag and
0557 **together** — either one missing is red. Read a red there as "the pair is
incomplete", not as "the parameter is banned again". This lane does not touch
kprintf, and `check-kprintf-enabled.py` is not on this branch (checked
2026-11-22), so the rule changes nothing here; it only stops a future reader of
this file from misreading that gate.
