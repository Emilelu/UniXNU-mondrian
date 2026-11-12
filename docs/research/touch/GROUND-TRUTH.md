# K60 touch ground truth (measured, not inferred)

Every fact below was read from the device itself or from a console capture.
Anything derived by reasoning is marked **推断**. Do not re-measure these; if a
value changes, update this file instead of re-deriving it in a later session.

## 1. IOVDD / AVDD rails (`/sys/class/regulator/*`, Android 17, root adb)

`pm8350c_l2  1800000  enabled`  ← touch IOVDD, 1.8 V, enabled under Android
`pm8350c_l1  1800000  disabled`
`pm8350c_l9  3200000  enabled`
`pm8350c_l10 1200000  enabled`
`pm8350c_bob 3296000  enabled`
`pm8350c_s1  1800000  enabled`
`pm8350c_l3..l8, l11..l13` — disabled

`/sys/kernel/debug/regulator` does not exist (no `CONFIG_REGULATOR_DEBUG`);
`/sys/class/regulator` does. Reproduce with `scripts/reg8350c.sh` in
`E:\k60-work\scratch`.

**推断**: `pm8350c_l2` is enabled only because Android's touch driver votes it.
Nothing in the XNU chain votes it, so the rail's state at our `bring_up()` is
unknown — this is the open question, not an established fact.

## 2. SPMI arbiter (read live from XNU, `usblog-20261113-001906`)

`K60SPMI ver=0x70000000 channels=768`  — v7 arbiter, same as `pong_buttons.c`
`K60SPMI obs_status0=0x1`               — observer window idle (DONE set)

Bases are hard-checked by `bsd/dev/pong_buttons.c`:
core `0xc400000`, cnfg `0xc42d000`, observer `0xc440000`.

## 3. GPIO pins (`board.toml`, confirmed by the driver's own prints)

`pins = <16 17 18 19 21 20>` — pins[5] = GPIO20 = RESET, avdd = GPIO71
`bitbang-pins = <17 18 16 19>` — MISO 17, MOSI 18, CLK 16, CS 19

## 4. Bus behaviour (measured, four permutations so far)

Every frame reads back **all ones**:

```
K60BB frame len=13 rx0=0 rx1=0 miso=104      (104 = 13*8, every sampled bit high)
K60BB frame len=16 rx0=0xff rx1=0xff miso=128
```

With the internal pull-up armed the idle level is `0` and every sampled bit is
high. A powered SPI slave with CS asserted does not leave MISO permanently at
VCC, so **推断**: the controller is unpowered or held in reset — not a pin
permutation problem. Confirmed for `17-18-16-19` and `17-16-18-19`; the
remaining permutations cannot change a permanently-high line.

## 5. What this rules out

- Pin role mismatch as the cause of all-ones (two permutations agree).
- Clock speed: bitbang runs ~333 kHz, inside the declared 500 kHz cap.
- SPI mode: Mode 0, MSB first, rising-edge sampling — correct for Berlin.
- Code path: `transport=bitbang` and `probe start` both print, frames do
  transmit.

## 6. Next action implied by the above

Vote `pm8350c_l2` from the kernel before the first frame. Requires an SPMI
write path, which the tree does not have yet; the arbiter read path is proven
and the write is the same command word with bit 27 cleared.
