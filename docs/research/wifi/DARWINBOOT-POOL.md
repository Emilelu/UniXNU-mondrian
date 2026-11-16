# DarwinBoot pool 通道账本（已关闭）：九张 silent 图 + 两张 alive 对照（2026-11-16）

状态：**通道已关闭，本页转存档**。2026-11-15 建这张表是为了给「DarwinBoot 把整个内核
读进 DXE pool，再申请 4.5 GiB 连续窗口」这条通道提供逐图数据。2026-11-16 的 `c3`
把这条通道关掉了（同 pool 占用一活一死），随后 `patches/wifi/0012` 把真死因钉在
UFS SMMU lease（P-215）。**表格数据保留**——它是 wifi 线写 pool 页时的输入，
也是「观测轴 ≠ 因果轴」的原始素材。分析在 [BLOB-RESIDENCY.md](BLOB-RESIDENCY.md)
§7（pool 通道为什么关闭）与 §10（死因）。

底稿：分支 `feat/wifi-ledger-fold` 的 `96e0a23` / `f9e5d0c`。

## 口径（先于数字读）

- **kernel B / `__TEXT` / `__DATA` / `__DATA_CONST`**：`mtype` 解出
  boot.img ramdisk 槽 `EFI/UniXNU/Payloads/kernel.macho` 后按 `LC_SEGMENT_64`
  读的 vmsize（脚本 `probe-silent6.py`、`probe-c456b.py`，`E:/k60-work/scratch/refmine/`）。
  build-manifest 不存这些数。
- **`pong_wifi`**：镜像字节实测（`scripts/check-arg.py`）与
  build-manifest.json 的 `kernel_args_requested` 两道核对。
- **ADT 窗口**：boot.img ADT `darwinboot-memory-size` 解码（`probe-window3.py`、
  `probe-win2.py`）。
- **series**：build-manifest.json 的 `series` 字段；trial 镜像没有这个键。
- 没测到或不存在的格写 `—`；本文不许估。

## 逐图账本

| 镜像 | kernel B | `__TEXT` | `__DATA` | `__DATA_CONST` | blob | `pong_wifi` | ADT 窗口 | series | 证据目录 |
|---|---|---|---|---|---|---|---|---|---|
| wifi-20261114a | 65,863,680 | 12,877,824 | 1,867,776 | 933,888 | 有（PWF2×2） | 1 | 0x130000000 | 无（trial） | `usblog-20261114-wifi-b` |
| wifi-20261116mhi3 | 65,978,368 | 12,992,512 | 1,867,776 | 933,888 | 有 | 1 | 0x130000000 | 229 `0076aa20902a…` | `usblog-20261115-002804` |
| wifi-20261116mhi4 | 65,978,368 | 12,992,512 | 1,867,776 | 933,888 | 有 | 1 | 0x120000000 | 229 | `usblog-20261115-002243` |
| wifi-20261115z0 | 117,305,344 | 12,992,512 | 53,149,696 | 933,888 | 有 | 0 | 0x120000000 | 224 `34cf51e4…` | `usblog-20261115-135859` |
| wifi-20261116t2 | 117,305,344 | **1,802,240** | 53,149,696 | **12,124,160** | 有（在 `__DATA_CONST`） | 0 | 0x120000000 | 224 `34cf51e4…` | `usblog-20261115-161102` |
| bt-s4b-20261115c | 106,541,056 | 1,720,320 | 52,920,320 | 1,949,696 | 无 | —（kargs `k60bt=1`） | 0x120000000 | 229 `67baff88e1bb` | `usblog-20261115-163144` |
| wifi-20261116c0 | 66,002,944 | 12,992,512 | 1,867,776 | 933,888 | 有（真容器 6 条） | 0 | 0x120000000 | 224 `34cf51e4…` | `usblog-20261115-213221`（测量无效） |
| wifi-20261116c1 | 66,002,944 | 12,992,512 | 1,867,776 | 933,888 | 有（真容器 6 条） | 0 | 0x120000000 | 224 `34cf51e4…` | `usblog-20261115-231707` |
| wifi-20261116c2 | 117,305,344 | **1,802,240** | 53,149,696 | **12,124,160** | 有（`__DATA_CONST`，真容器 6 条） | 0 | 0x120000000 | 224 `34cf51e4…` | `usblog-20261116-000136` |
| wifi-20261116c3（**alive**） | 117,325,824 | **1,802,240** | 53,149,696 | **12,124,160** | 有（`__DATA_CONST`，与 `c2` 逐字节相同） | 0 | 0x120000000 | 226 `d83fb1890e93…` | `usblog-20261116-015128`（221,429 B） |
| wifi-20261116c4/c5/c6（**alive**） | 117,325,824 | **1,802,240** | 53,149,696 | **12,124,160** | 有（同上） | 1（c5 加 `rsc=1`、c6 加 `rsc=2`） | 0x120000000 | 226 `d83fb1890e93…` | `usblog-20261116-072728` / `-075300` / `-081646` |
| adsp-20261115c/d/e（对照，**alive**） | 128,991,232 | 1,720,320 | 76,414,976 | 917,504 | 无 | —（无此参数） | 0x120000000 | 226 `d83fb1890e93…` | `usblog-20261115-213413` / `-220912` / `-223916` |

十二行里九张 silent（`c0` 一张测量无效，其余八张有效），三组 alive 对照。

九张 silent 图都是 `port-not-observed` + `fastboot-return` + console.log 0 字节，判定器
（main 的 `scripts/judge-z0.sh`）都报 `silent` / exit 2。

`c0` 的 silent 已归因为 defconfig 种子 Data UUID（`invalid-measurement`，P-152/P-209；
BLOB-RESIDENCY.md §10.3）；`c1` 就是把那行 UUID 改回设备卷的重测，**仍然 0 字节**
（段表与 `c0` 逐项相同）——所以「种子 UUID ⇒ 零字节」这条单变量假设不成立。

## 这张表最后证明了三件事，但都不是 pool

1. **pool 通道已关闭**（`c3`）：`c3` 与 `c2` 同 117 MB 版式、同 pool 占用、同窗口、
   同真 PWF2 容器，只多 20,480 B 惰性锁代码，**进了桌面**
   （`usblog-20261116-015128`，console 221,429 B、SpringBoard 133）。同池占用一活一死
   ⇒ pool 不是通道。
2. **阈值模型两次被否证**：最后一行 `adsp-*` 是对照行不是 silent 图——三张
   **128,991,232 B** 内核（`__DATA` 76,414,976、span 141,111,296，都比 117 MB 家族大）
   在同一 4.5 GiB 窗口下全部进桌面；更早的 `bt-s4b-20261115b`/`c` 同尺寸一活一死。
3. **驻留位置不是轴**：`t2`/`c2` 把容器搬进 `__DATA_CONST`（`__TEXT` 1,802,240）
   仍然 silent，而 `c3` 同版式 alive。

**真因不在本页任何一列**：`patches/wifi/0004` 让 `PongUfsTransport::hostBringUp()`
在 UFS 启动时索取 Apps SMMU lease，而锁只在 `pong_rpmh_init()` 里分配、后者晚于 UFS
⇒ lock() 返回 false ⇒ `transportFailure("Apps SMMU lease unavailable")` ⇒ 没有根设备
⇒ 0 字节（P-215；BLOB-RESIDENCY.md §10.2）。所以九张 silent 的共因是**同一段 lease
代码**，不是窗口占用——它们全是「链了 wifi 归档」的镜像，而 `pong_wifi=0` 挡不住
UFS 侧更早的那次索取。

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
7. **c0**：正式 C 格（66 MB、blob 在 `__TEXT`、`pong_wifi=0`、无 GPU addon、
   无 battery），4.5 GiB 窗口，series 224。**这张的 silent 没有判别力**：boot.img
   实测唯一带种子 Data UUID（`6DCCF70A-…` ×1、`1BCD69FF-…` ×0；其余 52 张
   wifi/bt 图相反），内核在根挂载阶段自 panic。
8. **c1**：`c0` 只改该 UUID 一行，段表逐项相同，仍然 0 字节 ⇒ 有效 silent，
   并否证「种子 UUID ⇒ 零字节」。
9. **c2**：`t2` 的复现（段表节表逐项相同），0 字节 ⇒ 驻留位置与生死无关。
10. **c3**（alive）：与 `c2` 同版式、同容器、同窗口、同 `pong_wifi=0`，只多
    20,480 B 惰性锁代码 ⇒ **本页的止血点**，同时否证 pool 与「blob 在场」两条轴。
11. **c4/c5/c6**（alive）：`c3` + `pong_wifi=1`（`c5` 加 `rsc=1`、`c6` 加 `rsc=2`），
    段表与 `c3` 逐项相同 ⇒ 洗清 `pong_wifi=1` 与 RSC 投票本身。
    `c6` 停在 MHI 的 `-110`（`device in READY state` 之后），属另一类故障（有日志）。
12. **adsp-20261115c/d/e**（alive）：129 MB、无 blob、同 4.5 GiB 窗口 ⇒ 阈值模型的反证。

## 附：已否证组合（拒飞清单）

> 这张清单的**性质变了两次**。2026-11-15 的理由是「同类只会 silent」；
> 2026-11-16 01:51 之后是「同类必然撞同一段 lease 代码，除非带上 `patches/wifi/0012`」；
> 现在（`c4`–`c6` 之后）是「`c3` 之后所有 silent 组合都可以带 0012 重出，
> 没有 0012 的同类镜像一律拒飞」。

mhi5d = 117 MB + blob（`__TEXT`）+ `pong_wifi=1` + 4.5 GiB + series 224
（与 mhi5 同尺寸同段表，payload `96ea535f…`）。它是 0012 之前的产物：

1. **66 MB + blob + `pong_wifi=1`**：mhi3 / mhi4 已飞 silent ⇒ 否证（缺 0012）。
2. **117 MB + blob（`__TEXT`）+ `pong_wifi=0`**：z0 已飞 silent ⇒ 否证（缺 0012）。
3. **117 MB + blob（`__DATA_CONST`）+ `pong_wifi=0`**：t2 / c2 已飞 silent ⇒ 否证
   （缺 0012；顺带否证「驻留位置」）。
4. **mhi5d 自身**：1、2 的交集版式 ⇒ 拒飞（缺 0012）。
5. **106.5 MB bt 版式**（无 wifi，`k60bt=1`，只差一个补丁的同尺寸对）：
   b alive / c silent 已飞完 ⇒ 同一组合再飞拒飞，结论只能靠新变量。
6. **66 MB + blob（`__TEXT`）+ `pong_wifi=0`**：`c1` 已飞 silent ⇒ 组合否证
   （缺 0012）。
7. **117 MB + blob（`__DATA_CONST`）+ `pong_wifi=0` 的第二次复现**：`c2` 与 `t2`
   逐项相同、已飞 silent ⇒ 拒飞。

**唯一还值得飞的旧组合**：tiny 家族 B 格（54.8 MB、4×23 B 占位头、`pong_wifi=1`，
`t1c` 从未飞）。它是唯一能把「真 blob」与「驱动代码存在」分开的一格，但它同样
链了 wifi 归档 ⇒ **要飞就必须带 0012**，否则只会复现 lease 拒绝服务。
`c3` 之后这一格的判别价值已大幅下降：真死因已经钉住，飞它只能再确认一遍
「链了归档就得带 0012」。

**本页的下一步**：不是再飞 silent 图，也不是 pool——pool 通道已关闭。MHI 阶段
（`c6` 的 `-110`）的判据是 `c7` 的四种组合，见 BLOB-RESIDENCY.md §11。
