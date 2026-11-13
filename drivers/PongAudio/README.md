# drivers/PongAudio — K60 speaker amplifier probe (step 3 of the audio task)

Source-only directory. Nothing here is compiled into the kernel until the patch in
`patches/audio/` is applied: the audio driver reaches `bsd/dev/` the same way the
aw882xx/pong_audio skeleton does (patches/xnu/0503-0505) and the way PongPower's
content reaches `bsd/dev/pong_adsp_pas.h` (0613). `drivers/` is the holding area
the tree keeps for native drivers (PongAdreno, PongMetal, PongPower, ...); a
directory appearing here does **not** mean it is linked.

Why this file set exists: the codec half of the port is blocked. Every LPASS
block (TX/VA macro, the SoundWire master, the LPI pads) needs two PRM block
votes and the `0x30c` clock acknowledgement from the ADSP first
(`references/pong-power/PongWcd938.h:59-120`), and the ADSP does not boot yet
(`docs/research/audio/GAP-ANALYSIS.md`). The amplifiers do not have that
dependency: they hang off AP-owned QUPV3 wrapper 2, serial engine 0 at
`0x00880000`, and answer a chip-id read with no DSP involved. That read is the
one piece of hardware evidence this task can produce before PAS1 works, and it
decides whether the port needs an AW882xx driver or a WSA883x one — the open
question in `docs/research/audio/AMPS.md`.

## Files

| File | Contents |
| --- | --- |
| `PongAudioRegs.h` | Every K60 AP-side constant the probe uses, each tagged with its provenance: **L** live FDT (`E:/k60-work/scratch/audio-work/live-fdt.dts`), **G** `gcc-sm8450.c`, **S** the Pong reference tree, **M** mainline `geni-se.h`/`i2c-qcom-geni.c`, **H** `hakios.speaker.c`. No address appears without a tag. |
| `PongAudioGeniI2c.h` / `.c` | The GENI I2C transport from `references/pong-power/GeniI2c.c`, logic kept verbatim, symbols renamed to `pong_geni_*` so it cannot collide with the Pong copy. One transfer at a time; the caller feeds `M_IRQ` status in until done. |
| `PongAudioAmp.c` | The probe. Boot-arg gated, read-only against the amplifiers, prints evidence with the `PongAudio: amp ...` prefix. |

## What it does, in order

1. `pads_map` — eight one-page TLMM windows (GPIO 1, 3, 43, 52, 56, 57, 63, 88).
2. `pads_report` — prints the pad state inherited from the boot loader. This is
   evidence: it says whether Android already configured the bus pads and
   released the amplifier resets, and no write below contradicts it silently.
3. `gcc_map` + `gcc_wrapper2_on` — votes wrapper 2's five branch clocks in the
   wrapper-2 enable register (`0x62010`, not the `0x62008` the touch driver
   uses for wrapper 0) and waits for each CBCR to report running.
4. `i2c_pads_take` — GPIO56/57 to the QUP15 function with a pull-up, unless they
   are already there.
5. `se15_open` — reads the firmware revision, refuses anything that is not I2C,
   chooses a DFS level whose source is the always-on reference, then writes the
   engine's own registers in mainline `geni_se_init()` order.
6. `amp_reset_release` — releases GPIO1 (amp 0) and GPIO3 (amp 1). Deliberately
   after the bus works: releasing a reset first and then failing would leave an
   amplifier awake with no clock.
7. `amp_probe_one` — reads chip id `0x00` (three attempts), then status
   `0x01`, mask `0x03`, control `0x04`, I2S `0x06`, debug `0x14`, VBAT `0x21`,
   PVDD `0x23`, temp `0x22`, `0x50`, and the four fuse words `0x78/0x79/0x7c/0x7d`.
   Register `0x02` is skipped on purpose: reading it clears the interrupt status.

Nothing else is written. No software reset (`AW882xx` reset is a `0x55aa` write
to `0x00`), no ACF profile, no mute/unmute, no volume. Those are init, and init
is what this probe is supposed to earn.

## Running it

```
scripts/build-strict.sh <tag> --fd <SILICIUM_UEFI.fd> --kernel-arg pong_audio_probe=1
```

The boot argument is read with `PE_parse_boot_argn("pong_audio_probe", ...)`; without
it the probe costs one boot-arg lookup and returns. The argument is **not** in
`board.toml` `[kernel] kernel_args` yet — that file is outside this task's write
scope, so it is delivered as a merge request to the Lead (see
`docs/research/audio/AMPS.md` section 6).

Expected log shape on a working bus:

```
PongAudio: amp probe start (amplifiers are read-only; AMPS.md A1-A7)
PongAudio: amp pin gpio=... cfg=... io=...
PongAudio: amp gcc vote 0x... -> 0x... readback 0x...
PongAudio: amp gcc clk wrap2_core halt=... running=1
PongAudio: amp se15 fw=0x... proto=3 disabled=... clock=... scl=...
PongAudio: amp se15 ready config=0x... status=0x... level=N
PongAudio: amp reset amp0 gpio=1 ...
PongAudio: amp0 addr=0x34 id=0x2113 chip=AW88261 status=... faults=... pll=1
PongAudio: amp probe done found=2/2 transfers=... failed=0 timeouts=0 stray=0 gcc_misses=0
```

Failure is diagnostic, not fatal: the probe returns a count and never panics, so
the rest of the boot is unaffected either way.

## What it does not do

No LPASS register is touched. That is not an omission — the PRM votes and the
`0x30c` clock come from the ADSP, so the codec half starts when PAS1 works. See
`docs/research/audio/SOUNDWIRE.md` and `CODEC.md`.

## Provenance

- Addresses, interrupts, pads: live FDT, quoted line by line in `AMPS.md` section 2.
- AW882xx register map and status bits: `references/phk110-port/drivers/audio/hakios.speaker.c`
  (AW88261 on a POCO X5 Pro), lines 340-360 and 749-790.
- GENI transport and engine bring-up: `references/pong-power/GeniI2c.c` plus mainline
  `geni-se.h`, `qcom-geni-se.c`, `i2c-qcom-geni.c`.
- GCC branch clocks: `gcc-sm8450.c` register entries, listed with line numbers in `AMPS.md` section 3.

License follows the two references: BSD-2-Clause-Patent.
