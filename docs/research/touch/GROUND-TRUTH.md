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

Conclusions that stand:

- `wr()` is sound and `ml_io_map()` mappings are writable — proven by the GPIO write-back.
- The SPMI command path (observer window, command word `(1u<<27)|reg<<4|(count-1)`, status poll on `+0x08`, data at `+0x18`) is correct — proven by `DONE` on the AP's own channel.
- The PMIC channel returns `DROPPED`, i.e. it is not owned by the AP execution environment.
- Changing ownership needs a write to the core window, and every such write faults. This is a bus-level refusal, not a code defect.

Not yet determined: whether the configuration window `0xc42d000` accepts writes; if it does, ownership can be set there. If it does not, the rail must be enabled from the firmware side before hand-off.

## MISO 悬空的判定（2026-11-13，实测三组）

| 构型 | CS | MISO 采样 | 结论 |
|---|---|---|---|
| 上拉偏置 | 1 | 每帧每一位都是 1（`miso=104` = 13x8，`miso=128` = 16x8） | 线被拉高 |
| 下拉偏置，焊盘未配置 | 未配置 | 每一位都是 0 | 线跟随偏置 |
| 下拉偏置，焊盘已配置 | 1 | 每一位都是 0 | 线跟随偏置 |

同一批实验里 `K60PAD cs=1 miso=0 clk=0 mosi=0 rst=1` 与 `K60RST pin=20 after=1`
证明 GPIO 控制器、焊盘配置、引脚映射（MISO 17 / MOSI 18 / CLK 16 / CS 19 /
RESET 20）、复位时序都正确。MISO 在两种偏置下都跟随偏置，说明没有任何一端
在驱动它——触摸芯片（Goodix GT9916R）没有工作。

已经排除的解释：时钟过快（333 kHz，上限 500 kHz）、SPI 模式（Mode 0 MSB-first
上升沿采样）、片选时序、复位未释放、引脚映射错误、映射表/寄存器地址错误。

剩下的解释只有一个：芯片没有 IOVDD。`pm8350c_l2` 1.8 V 在 Android 下是
`enabled`（`/sys/class/regulator/pm8350c_l2/state`），但在本移植的启动链上
没有任何一方投过票，而 AP 侧四条通路都不可用：

1. SPMI 映射表（`core+0x2000` 与 `core+0x900` 两种布局都遍历过）没有 PPID `0x241`；
2. 固件树里没有 RPMh/RSC 驱动（`find -iname '*rpmh*' -o -iname '*rsc*'` 零命中）；
3. 厂商 DTB 里 `pm8350c_l2` 是 `regulator-name` 形式的 RPMh 消费者，不带 SPMI 基址；
4. RSC `0x17a00000` 对 XNU 被 XPU 封锁（读即 abort）。

结论：这一项必须在 ABL/固件层解决，内核侧的探针到此为止。
