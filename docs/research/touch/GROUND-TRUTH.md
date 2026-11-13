# K60 touch evidence ledger (dated observations, not current hardware truth)

The rows below preserve historical device or console observations. Interpret each only in its recorded date, wiring, image and setup. Later source or image changes do not retroactively validate them. Any causal explanation is a hypothesis, not a direct measurement.

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

Android reported `pm8350c_l2` enabled at 1.8 V. The available records do not establish that Android's touch driver is the only voter, whether XNU or firmware votes it, or its state at `bring_up()`. The handoff state is unknown.

## 2. SPMI arbiter (read live from XNU, `usblog-20261113-001906`)

`K60SPMI ver=0x70000000 channels=768`  — v7 arbiter, same as `pong_buttons.c`
`K60SPMI obs_status0=0x1`               — observer window idle (DONE set)

Bases are hard-checked by `bsd/dev/pong_buttons.c`:
core `0xc400000`, cnfg `0xc42d000`, observer `0xc440000`.

## 3. Historical GPIO configuration records (2026-11-13)

`pins = <16 17 18 19 21 20>` — pins[5] = GPIO20 = RESET, avdd = GPIO71
Historical configured tuple: `<17 18 16 19>` labelled MISO 17, MOSI 18, CLK 16, CS 19. The later touch-20261114d candidate uses a different proposed tuple (MISO 16, MOSI 17, CLK 18, CS 19); neither tuple is established by the old bias samples.

## 4. Historical bus samples (2026-11-13 setup)

Every frame reads back **all ones**:

```
K60BB frame len=13 rx0=0 rx1=0 miso=104      (104 = 13*8, every sampled bit high)
K60BB frame len=16 rx0=0xff rx1=0xff miso=128
```

These readings show the sampled line followed the configured pull bias in this historical setup. They do not uniquely identify the physical MISO pin or establish IOVDD voltage, controller power state, reset state, CS timing, or SPI timing/mode. The old tuple differs from the later candidate lane map; treat these as historical electrical observations, not a current diagnosis.

## 5. Limits of the historical observations

The historical captures show the selected software path ran and reported transmit/read samples under the then-current configuration. They do not prove that the intended physical SPI pins, waveform, reset sequence, or rail were correct, and they do not exclude those as causes. The later touch-20261114d candidate uses a different proposed lane map and still does not obtain chip identity; see docs/research/touch/13-STAGE-ONE-ROOT-CAUSE-MATRIX.md.

## 6. Follow-up evidence

The historical SPMI attempts listed below establish only those tested register paths and outcomes. They do not prove all AP, firmware, or RPMh provider paths unavailable, and they are not authorization to write PMIC ownership or regulator registers. Current IOVDD handoff state remains unknown until supported by current provider ACK/retention evidence or an authorized direct measurement.

## SPMI write-path findings (2026-11-13, measured on device)

Every line below came off the serial console; nothing here is inferred.

| Target | Read | Write | Evidence |
|---|---|---|---|
| TLMM GPIO page (via `ml_io_map`) | ok | ok | `K60CFG gpio same b=0x84 a=0x84`, no abort |
| SPMI core `0xc400000+0x1008` | `0x3` | data abort | `K60KEXC pc=…b9a8 lr=…b99c` |
| SPMI core `0xc400000+0x1400` | `0x19b00` | data abort | `K60KEXC pc=…b9f0 lr=…b9a0` |
| SPMI observer `0xc440000` | ok | ok | command issued, status polled |
| channel `sid1/apid0x9b` (0x19b) | `v=0` | n/a | `K60CFG ap st=0x1 v=0` (DONE) |
| channel `sid2/apid0xc2` (0x1c2) | `v=0` | n/a | `K60REG type st=0x8 val=0` (DROPPED) |

Narrow conclusions from these historical captures:

- The logged GPIO write-back succeeded in that experiment.
- The tested observer-window command returned `DONE` for the AP channel, while the tested PMIC channel returned `DROPPED`.
- Writes to the tested core-window addresses faulted. This does not establish that every AP or firmware provider path is unavailable.

The behavior of the configuration window and current IOVDD handoff remain undetermined; do not infer a firmware-only remedy from these limited probes.

## Additional historical pad and bias records (2026-11-13)

| Historical configuration | CS setting | sampled input result | recorded observation |
|---|---|---|---|
| 上拉偏置 | 1 | 每帧每一位都是 1（`miso=104` = 13x8，`miso=128` = 16x8） | 线被拉高 |
| 下拉偏置，焊盘未配置 | 未配置 | 每一位都是 0 | 线跟随偏置 |
| 下拉偏置，焊盘已配置 | 1 | 每一位都是 0 | 线跟随偏置 |

Historical lines logged `K60PAD cs=1 miso=0 clk=0 mosi=0 rst=1` and `K60RST pin=20 after=1`. These are software-reported values in that experiment; they do not establish the physical signal roles, waveform at the chip, or reset voltage/timing at the controller. The contemporaneous 333 kHz and Mode 0 values describe configured settings, not an independent measurement of the electrical waveform.

The bias table and these GPIO logs do not exclude lane routing, CS/SCK timing, SPI mode, reset, protocol, controller state, or IOVDD as causes. They do not establish that IOVDD was absent, that the chip was not working, or that firmware is the only remedy. Current handoff and provider status require current ACK/retention evidence or an authorized direct rail measurement. See `docs/research/touch/13-STAGE-ONE-ROOT-CAUSE-MATRIX.md` for candidate-specific discriminating tests.
