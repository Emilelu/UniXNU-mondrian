# DarwinBoot pool 通道账本：已知 silent 的七张图（其中 `c0` 判为测量无效；2026-11-15）

状态：账本。只列数，不分析——wifi 线的固件侧分析在
[BLOB-RESIDENCY.md](BLOB-RESIDENCY.md)，本文是 wifi 线写 pool 页的输入。

## 口径（先于数字读）

- **kernel B / `__TEXT` / `__DATA` / `__DATA_CONST`**：`mtype` 解出
  boot.img ramdisk 槽 `EFI/UniXNU/Payloads/kernel.macho` 后按 `LC_SEGMENT_64`
  读的 vmsize（脚本 `probe-silent6.py`，`E:/k60-work/scratch/refmine/`）。
  build-manifest 不存这些数。
- **`pong_wifi`**：镜像字节实测（`scripts/check-arg.py`）与
  build-manifest.json 的 `kernel_args_requested` 两道核对。
- **ADT 窗口**：boot.img ADT `darwinboot-memory-size` 解码（`probe-window3.py`）。
- **series**：build-manifest.json 的 `series` 字段；trial 镜像没有这个键。
- 没测到或不存在的格写 `—`；本文不许估。

## 七行

| 镜像 | kernel B | `__TEXT` | `__DATA` | `__DATA_CONST` | blob | `pong_wifi` | ADT 窗口 | series | 证据目录 |
|---|---|---|---|---|---|---|---|---|---|
| wifi-20261114a | 65,863,680 | 12,877,824 | 1,867,776 | 933,888 | 有（PWF2×2） | 1 | 0x130000000 | 无（trial） | `usblog-20261114-wifi-b` |
| wifi-20261116mhi3 | 65,978,368 | 12,992,512 | 1,867,776 | 933,888 | 有 | 1 | 0x130000000 | 229 `0076aa20902a…` | `usblog-20261115-002804` |
| wifi-20261116mhi4 | 65,978,368 | 12,992,512 | 1,867,776 | 933,888 | 有 | 1 | 0x120000000 | 229 | `usblog-20261115-002243` |
| wifi-20261115z0 | 117,305,344 | 12,992,512 | 53,149,696 | 933,888 | 有 | 0 | 0x120000000 | 224 `34cf51e4…` | `usblog-20261115-135859` |
| wifi-20261116t2 | 117,305,344 | **1,802,240** | 53,149,696 | **12,124,160** | 有（在 `__DATA_CONST`） | 0 | 0x120000000 | 224 `34cf51e4…` | `usblog-20261115-161102` |
| bt-s4b-20261115c | 106,541,056 | 1,720,320 | 52,920,320 | 1,949,696 | 无 | —（kargs `k60bt=1`） | 0x120000000 | 229 `67baff88e1bb` | `usblog-20261115-163144` |
| wifi-20261116c0 | 66,002,944 | 12,992,512 | 1,867,776 | 933,888 | 有（PWF2×2，真容器 6 条） | 0 | 0x120000000 | 224 `34cf51e4…` | `usblog-20261115-213221` |

七张都是 `port-not-observed` + `fastboot-return` + console.log 0 字节，判定器
（main 的 `scripts/judge-z0.sh`）都报 `silent` / exit 2。其中 `c0` 的 silent 已归因为
defconfig 种子 Data UUID（`invalid-measurement`，P-152 / BLOB-RESIDENCY.md §11）：
**pool 假说（窗口占用）既未被证实也未被否证，需 `c1` 复测**。

## 每行一句（不引申）

1. **wifi-20261114a**：65.9 MB 级最早的一张，blob 在 `__TEXT`，`pong_wifi=1`，
   4.75 GiB 窗口；trial 镜像，manifest 没有 series 键。silent。
2. **mhi3**：66 MB 级正式镜像，4.75 GiB 窗口。silent。
3. **mhi4**：与 mhi3 同尺寸同段表，窗口 4.5 GiB。silent。
4. **z0**：117 MB 版式，`pong_wifi=0`，4.5 GiB 窗口，series 224。silent。
5. **t2**：117 MB 版式，blob 容器移入 `__DATA_CONST`（`__TEXT` 1,802,240），
   `pong_wifi=0`，4.5 GiB 窗口，series 224。silent。
6. **bt-s4b-20261115c**：106.5 MB、无 wifi blob、kargs `k60bt=1`、4.5 GiB 窗口、
   series 229。silent；同尺寸同 blob 只差一个补丁的 bt-s4b-20261115b 同日 alive
   （`usblog-20261115-140927`，213,434 B；见 BLOB-RESIDENCY.md §2）。
7. **wifi-20261116c0**：正式 C 格（66 MB、blob 在 `__TEXT`、`pong_wifi=0`、
   无 GPU addon、无 battery），4.5 GiB 窗口，series 224；2026-11-15 21:32 飞，
   silent（`usblog-20261115-213221`，console.log 0 字节）。**这张的 silent 没有
   判别力**：boot.img 实测唯一带种子 Data UUID（`6DCCF70A-…` ×1、
   `1BCD69FF-…` ×0；其余 55 张 wifi/bt 图相反），内核在根挂载阶段自 panic——
   pool 假说既未被证实也未被否证，需 `c1`（只改该 UUID 一行）复测
   （BLOB-RESIDENCY.md §11）。

## 附：已否证组合（mhi5d 类不要再飞的清单）

mhi5d = 117 MB + blob（`__TEXT`）+ `pong_wifi=1` + 4.5 GiB + series 224
（与 mhi5 同尺寸同段表，payload `96ea535f…`）。它的每一根轴都已被一张 silent
图盖住，再飞同类只会 silent：

1. **66 MB + blob + `pong_wifi=1`**：mhi3 / mhi4 已飞 silent ⇒ 否证。
2. **117 MB + blob（`__TEXT`）+ `pong_wifi=0`**：z0 已飞 silent ⇒ 否证。
3. **117 MB + blob（`__DATA_CONST`）+ `pong_wifi=0`**：t2 已飞 silent ⇒ 否证
   （顺带否证「驻留位置」）。
4. **mhi5d 自身**（1、2 的交集版式）：两个驻留位置都死过、`pong_wifi=1` 在
   66 MB 上死过、117 MB 版式在 `pong_wifi=0` 上死过 ⇒ 拒飞。
5. **106.5 MB bt 版式**（无 wifi，`k60bt=1`，只差一个补丁的同尺寸对）：
   b alive / c silent 已飞完 ⇒ 同一组合再飞拒飞，结论只能靠新变量。
6. **66 MB + blob（`__TEXT`）+ `pong_wifi=0`**：`c0` 的 silent 已归因 defconfig
   种子 Data UUID（`invalid-measurement`，P-152），**不能**进否证清单；
   pool 假说既未被证实也未被否证，需 `c1` 复测。

仍未否证、也仍没有对应镜像的组合：C 格（66 MB + blob + `pong_wifi=0`）要用
`c1`（只改 UUID 一行）复测；tiny 家族 B 格（54.8 MB、4×23 B 假固件、
`pong_wifi=1`，t1c 从未飞）也还没有镜像。若要单变量对照，候选是
「GPU addon + 无 PWF2」或「66 MB 版式 + 同尺寸惰性 `__const`」——需 Lead 决定
（BLOB-RESIDENCY.md §11 末）。
