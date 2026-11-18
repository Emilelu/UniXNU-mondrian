# patches/audio — K60 amplifier probe and AFE selftest

Two patches, two purposes: put the AP-side amplifier probe from
`drivers/PongAudio/` into a buildable XNU tree and compile the AFE encoder into that same skeleton.

| File | What it does |
| --- | --- |
| `0001-k60-audio-amp-probe.patch` | Adds `bsd/dev/PongAudioRegs.h`, `PongAudioPlan.h`, `PongAudioGeniI2c.h`, `PongAudioGeniI2c.c`, `PongAudioAcf.h`, `PongAudioAmpProfile.h`, `PongAudioAmpReplay.h`, `PongAudioAmp.c`, `PongAudioAfe.h`, `PongAudioTlmm.h`, `PongAudioRing.h`, `PongAudioPlayback.h`, `K60PmicGlinkAudio.h` (byte-for-byte copies of `drivers/PongAudio/` and `drivers/PongPower/`), two `bsd/conf/files` entries, and one `bsd_init.c` call block. 125,436 bytes, 3,320 lines, 15 hunks, sha256 `e63648f85dd14a59688ea1e3bcb4cb068417812fdb6036c7a7e0d6b89e83713f`. `PongCodecPlan.h` is deliberately absent: no kernel `.c` includes it yet, so it would be dead weight in the tree. |
| `0003-k60-audio-afe-selftest.patch` | Adds `#include "PongAudioAfe.h"` and `K60PmicGlinkAudio.h`, the `pong_audio_afe_selftest()` 76-byte PRM clock request, the six-step `pong_afe_step_packet()` planner, the PCM submit ring and `/chosen/pong-audio-dma` lease consumer, and a bridge that queues the `adsp_apps` GLINK slot (560x20). On the first channel-up callback it sends a 24-byte GPR `GET_SPF_STATE` through that slot (token `0x00010001`), and the receive callback decodes GPR opcode/token. Reports `PongAudioErrApmNotReady` when queued, or the named no-lease refusal when the transport is absent. After the six-step completes it opens, configures and maps the speaker and playback graphs, waits for the 14400-frame PCM lead, then starts the graph and pumps 1024-frame periods through eight AR write slots, copying each period into its low-DMA slot and timing out a slot that misses eight pump passes; the single GRAPH_START carries both subgraph ids (the DSP refused the speaker subgraph alone with code 1) and falls back to the two single starts if the pair is refused, the slot address is the mapped physical address itself, a refused AFE or playback step is skipped so the rest of the graph path is still exercised, the low-DMA lease is mapped write-combined so the 8 KiB period copy is a legal memcpy, and the pump only streams once the playback graph has started. Image aw turned the run into an isolation probe: it skipped both speaker GRAPH_START commands, started the playback subgraph alone and streamed, which separated a PCM-write failure from a TDM-speaker failure. The answer was the write itself: the console stops inside the first submit. Image ax therefore leases apps SMMU stream `0x1801` (the device tree binds the audio ion node to it and masks the stream id) as a stage-1 bypass bank, the same handoff the Pong reference performs for its DMA buffer, reports the SMMU state before the first write, sends the tagged address (`| 1 << 32`) in both the shared-memory map and the writes, and returns the transfer token to `0x10000000 | sequence`. The lease keeps the lowest idle stream-match slot because the firmware's masked group at slot 3 swallows every audio stream above it, and it walks up to eight banks down from the top, skipping any bank whose SCTLR.M is set, whose CBAR/CBA2R are not bypass, or that any SMR still references. Image ay repeated the writes with that tagged address: the lease was refused because every free bank is already referenced, and the console still ends inside the first four writes without a single answer from the DSP, so the apps SMMU is not the fault. The series therefore traces the pump, the reaping and every silent refusal of a slot, and opens the stream with one zero-byte write: the DSP must answer, refuse or die there without reading the buffer, which separates the command path from the memory access. Image ba sent those traces with the zero-byte write still inside `begin_stream`, and the console ended right after `playback graph started without the speaker`: no pump line at all, so the graph dying on start comes before any write. The probe therefore moves to the moment the playback START completes, and the submit path pumps unconditionally, before the ring check as well, because the pump owns the lead wait that sends the two PREPARE commands and the START: image bb gated that pump on `playback_running` and never left `playback graph mapped`. Image bd added a flow control that keeps a single buffer in flight and the machine still died right after the zero byte probe, before the first real period printed its send line, so the probe became the only write of image be: a flag makes every real slot submission a no-op while the graph, the clock and the zero byte write still run, which separates the write command from the memory the DSP has to read. 44,537 bytes, 1,365 lines, 5 hunks, sha256 `080d9e6390c7b2357141acb8b0bf554305a527667a2e67f6aee014c5b04c209e`. The write path itself is alive: a zero-byte probe is accepted without an answer and without a reset, while a real period kills the machine before the DSP answers, so this image takes its PCM slots from the tail of shared memory whenever the heap and the item table leave the last 64 KiB unused. Image bf shipped that change and died on the first real period exactly as before, so image bg drops the shared-memory override and instead lends the leased 64 KiB to LPASS (0x16) and ADSP_HEAP (0x25) with the SCM memory-assign call the stock audio stack issues (service 0x0c, command 0x16, seven arguments with the last four passed through a buffer), giving the DSP a mapping for the pages it is handed to read. Image bg booted with the assign accepted (rc=0) and the DSP answered for the first time: the zero-byte probe drew a WRITE_DONE (0x05001004), but the first real period then died inside the copy into the buffer, because the call moves the page out of HLOS instead of lending it. Image bh keeps HLOS (0x03, read/write) in the destination list and books the probe slot so the completion clears it. Applied after 0001. |
| `series` | The intended order inside this directory. It lists `0001` then `0003`. |

`drivers/PongAudio/tests/` is deliberately **not** in the patch. It is a host-side
check (`cc` against the state machine, no kernel headers), so it belongs to the
repo's test story, not to a file list that ends up compiled into `bsd/dev/`.
Running it is described in `drivers/PongAudio/README.md` and `AMPS.md` section 6.1;
it covers the ⑦ unit-test column of the eight-step gate without changing what the
kernel builds.

## Ordering is not optional

The patch must be applied **after `patches/xnu/0505-k60-audio-integration.patch`**:
both of its non-file hunks are anchored on lines that 0505 introduces
(`bsd/dev/pong_audio.c` in `bsd/conf/files`, the `pong_audio_bootstrap()` block in
`bsd/kern/bsd_init.c`). Applying it earlier fails cleanly rather than silently
patching the wrong place.

Wiring it into a build is a Lead action (both files are outside this task's
write scope). The mechanism, read from the scripts rather than assumed:

- `patches/xnu/series` is copied **into** `scratch/SERIES-FINAL.txt` by
  `scripts/sync-device-input.py:131-138`, so the in-repo series is the file to edit
  and the scratch copy is regenerated; `scripts/porting-gate.py` then demands all
  three copies agree (repo series == `scratch/SERIES-FINAL.txt` == `device/series`).
  This reads differently from the P-90 wording, so whoever wires it should confirm
  against those line numbers before editing the wrong copy.
- The whole `patches/` tree is mirrored to the build input (`ITEMS` in
  `sync-device-input.py:35-47`), so an entry may point outside `patches/xnu/`:
  the framework resolves `path = series.parent / entry` and applies it by absolute
  path (`/mnt/e/hackios/UniXNU/scripts/unixnu/patches.py:23,59`). The verified
  entry form is therefore:

  ```
  ../audio/0001-k60-audio-amp-probe.patch
  ```

  `scripts/check-porting-paths.py` resolves the same relative way, so the entry and
  the file it points at are checked by the same gate.

## How the hunks were generated, and why they can be trusted

`E:/k60-work/scratch/audio-work/make-audio-patch.py` builds this file
mechanically: new-file hunks from the real source bytes, and the two edit hunks
by `difflib` between a synthesised pre-image and post-image. No hunk was typed
by hand, so counts and whitespace cannot drift.

No tree on this machine carried the `qbt_k60_start()` block that 0505 anchors on,
so the generator synthesised the pre-images: `bsd_init.c` = pristine + the exact
0505 block, `bsd/conf/files` = pristine + the qbt lines + the two 0505 lines.
Consequence: **context lines match a real post-0505 file exactly, header line
numbers are approximate.** Both `patch(1)` and `git apply` locate hunks by
context, so this is safe.

The synthesis was later replaced by a real end-to-end apply against a genuine
chain pre-image. The build cache `.../tree/.cache/xnu-work` of the usb-cdc
mainline build tree holds a `bsd/conf/files` that already has the
`k60_usblog` / `k60_uilib` / `k60_console_export` trio, which is exactly what
0501 anchors on. In a scratch copy of that state, 0501 → 0505 → this patch
applies in order with **rc=0 and no rejects**. 0505 itself lands with
`fuzz 1 (offset -19 lines)` — that fuzz belongs to 0505's own anchor, not to
this patch; **this patch applies with no fuzz**, offsets only (+6 for
`bsd/conf/files`, +15 for `bsd/kern/bsd_init.c`). The five new files come out
byte-identical to `drivers/PongAudio/`. Transcript below.

Verification performed (transcript in `E:/k60-work/evidence/`, reproducible with
`make-audio-patch.sh`):

```
checking file bsd/dev/PongAudioRegs.h
checking file bsd/dev/PongAudioPlan.h
checking file bsd/dev/PongAudioGeniI2c.h
checking file bsd/dev/PongAudioGeniI2c.c
checking file bsd/dev/PongAudioAmp.c
checking file bsd/conf/files
checking file bsd/kern/bsd_init.c
git apply --check OK
identical: bsd/dev/PongAudioRegs.h
identical: bsd/dev/PongAudioPlan.h
identical: bsd/dev/PongAudioGeniI2c.h
identical: bsd/dev/PongAudioGeniI2c.c
identical: bsd/dev/PongAudioAmp.c
```

Real chain apply (`patch -p1 --forward`, `set -o pipefail`, no rejects, rc=0):

```
### pre-image: build cache bsd/conf/files, lines 108-110
bsd/dev/k60_usblog.c				standard
bsd/dev/k60_uilib.c		standard
bsd/dev/k60_console_export.c	standard

### 0505's own hunk head (pre-existing fuzz, not ours)
bsd/kern/bsd_init.c: Hunk #1 succeeded at 1329 with fuzz 1 (offset -19 lines).

### after 0501 + 0505 (conf/files)
111:bsd/dev/qbt_k60.c			standard
116:bsd/dev/qbt/btqca.c			standard
117:bsd/dev/aw882xx.c			standard
118:bsd/dev/pong_audio.c			standard

### MINE
patching file bsd/dev/PongAudioRegs.h
patching file bsd/dev/PongAudioPlan.h
patching file bsd/dev/PongAudioGeniI2c.h
patching file bsd/dev/PongAudioGeniI2c.c
patching file bsd/dev/PongAudioAmp.c
patching file bsd/conf/files
Hunk #1 succeeded at 116 (offset 6 lines).
patching file bsd/kern/bsd_init.c
Hunk #1 succeeded at 1337 (offset 15 lines).
rc=0

### result: conf/files 119-120, bsd_init.c 1357-1358
117	bsd/dev/aw882xx.c			standard
118	bsd/dev/pong_audio.c			standard
119	bsd/dev/PongAudioGeniI2c.c		standard
120	bsd/dev/PongAudioAmp.c			standard
1336		extern int pong_audio_bootstrap(void);
1337		(void)pong_audio_bootstrap();
1357		extern int pong_audio_amp_probe(void);
1358		(void)pong_audio_amp_probe();

### cmp bsd/dev/PongAudio* vs drivers/PongAudio/
same PongAudioRegs.h / PongAudioPlan.h / PongAudioGeniI2c.h / PongAudioGeniI2c.c / PongAudioAmp.c
### rejects: none
```

Note for whoever wires the series: 0501 needs 0300/0243/0340 (the `k60_*` conf
lines) applied first, and this patch needs 0505. The entry must sit after 0505 in
the series, i.e. after `0505-k60-audio-integration.patch`.

### Framework mechanism (`git apply` on a fresh clone) — verified end to end

The framework applies the series with `git apply` on a fresh XNU clone, resolving
each entry as `series.parent / entry` (`/mnt/e/hackios/UniXNU/scripts/unixnu/patches.py:23`).
So the real question is not `patch(1)` but whether the whole chain applies under
`git apply`. It does: in a scratch copy of the build-cache `bsd/` (a tree with the
`k60_usblog` trio and nothing else from 05xx), the bsd-only part of the series
applies in order — **all rc=0, zero fuzz, zero rejects, ours included**:

```
--- 0500  (0500-k60-bt-qbt-new-files.patch)   rc=0
--- 0502b (0502b-k60-bt-qbt-kernel-stubs.patch) rc=0
--- 0501  (0501-k60-bt-qbt-bsd-conf.patch)    rc=0
--- 0502  (0502-k60-bt-qbt-bsd-init.patch)    rc=0
--- 0503  (0503-k60-audio-aw882xx.patch)      rc=0
--- 0504  (0504-k60-audio-pong-audio.patch)   rc=0
--- 0505  (0505-k60-audio-integration.patch)  rc=0
--- ../audio/0001-k60-audio-amp-probe.patch   rc=0

### landing
117:bsd/dev/aw882xx.c			standard
118:bsd/dev/pong_audio.c			standard
119:bsd/dev/PongAudioGeniI2c.c		standard
120:bsd/dev/PongAudioAmp.c			standard
1357:		extern int pong_audio_amp_probe(void);
1358:		(void)pong_audio_amp_probe();
identical: PongAudioRegs.h / PongAudioGeniI2c.h / PongAudioGeniI2c.c / PongAudioAmp.c
```

Reproduce with `E:/k60-work/scratch/audio-work/gitchain-verify.sh`. Note that the
`patch(1)` run further above exercised a shorter chain (0501 → 0505 without 0502),
which is why 0505 showed `fuzz 1` there; under the full chain 0505 applies cleanly.

## Testing it

The probe is inert without the boot argument:

```
scripts/build-strict.sh <tag> --fd <SILICIUM_UEFI.fd> --kernel-arg pong_audio_probe=1
```

`board.toml` is outside this task's write scope, so the argument is passed on the
command line until the Lead adds it to `[kernel] kernel_args`. Expected output
and the reading of each line: `drivers/PongAudio/README.md`.

## If an anchor ever breaks

Do not hand-edit the patch. Re-run the generator after fixing its anchor
constant; the pre-image synthesis is the only thing that needs to change.

## License

BSD-2-Clause-Patent, following the two references the code is derived from
(`references/pong-power/GeniI2c.c`, `references/phk110-port/drivers/audio/hakios.speaker.c`).
