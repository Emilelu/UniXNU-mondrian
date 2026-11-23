# 解冻清单（BOOT-FREEZE 的五条件，逐条可判定）

冻结令见 `docs/engineering/BOOT-FREEZE.md`：只有用户本人改 `state` 才放行。
本文件把五个条件写成**可判定的读数**，避免下一轮靠叙述判断「够不够解冻」。

| # | 条件 | 判据（必须能贴出读数） | 现状（2026-11-22 05:41） |
| --- | --- | --- | --- |
| ① | 同一次启动内的日志通路 | 构建绿 **且** 镜像里能搜到 `pong-ramoops: console attached` **且** 上机后同一次启动内看到该行（或 usblog 枚举成功） | 构建绿 ✅、镜像内命中 1 次 ✅、**上机未做** |
| ② | 离线三连证据 | `check-ios27-artifacts.py <board>` 返回 0、`check-kernel-console.py` 返回 0、`check-image-args.py` 不拒 | 前两项 ✅，第三项本轮未跑 |
| ③ | 菜单自动引导 | `board.toml` `timeout != -1` 且默认条目是 27 内核（`boot.img` 内 `unixnu.toml` 的 entry 顺序） | `timeout = 10` ✅，默认条目未核 |
| ④ | 自动复位 | `0334b` 搬完并且上机后能自行回到 fastboot | **未搬**：`0308` 含 SPMI 写，等 A/B 裁决 |
| ⑤ | blocker 表不再有「无法观测」 | `docs/engineering/IOS27-FLIGHT-BLOCKERS.toml` 里每条 open 都有 `observe_via`（可执行的观测手段），没有「只能猜」的条目 | 未做（本清单之外的下一个离线任务） |

### ② 的一个已知缺陷（2026-11-22 05:44 实测）

`check-image-args.py --image <boot.img>` 报三条「来自 board.toml 的参数在镜像里缺失」：
`sheng-gpu-addon=1`、`k60_autoreset=300`、`applog=1`。

**这不是镜像的问题，是检查器读错了层。** 27 的启动行来自
`[os_overrides."ios-27.0.1-24A446"].kernel`，实际镜像里是 7 条
（`-v serial=3 debug=0x14e kt_fixed_zones=120 -no_slto_panic use_contiguous_hint=0
amfi_get_out_of_my_way=1 k60_fontscale=3`）。检查器直接读 `board.toml` 顶层参数列表，
拿 16 线的 `pong_metal` / `k60_autoreset` 去对一个 27 镜像。

⇒ 与 P-305 同族（合规是差分，必须读生效层）。在它修好之前，② 的第三项判据改成
**「`check-image-args.py` 跑完并逐条解释每个 missing，或改用合并后的启动行重跑」**，
不能把这三条当成镜像缺陷。

## 纪律

- 判据必须是**一条命令的读数**，不是「我看过了」。贴不上读数就是没满足。
- ①的构建部分已经满足，但它**不能**顶替上机部分：符号在 ≠ 代码跑（P-300/P-301 各咬过一次）。
- ④ 在 A/B 裁决前不动代码；A = 只搬 `smc #0` / `hvc #0` 复位，B = 整段搬并申请 HR-01 豁免。
- 合并层纪律有自动检查：`scripts/check-board-read-merge.py`（`--strict` 用于 CI）。已复查的 13 个读基础表的脚本记在 `scripts/BOARD-READ-MERGE.toml`，新增读者会被点名；负向自测（临时树里放一个不合并的读者）退 1。
- ④ 代码侧已完整（2026-11-22）：`0547` usblog EP0 + `0549` 复位 + `conf-files` 两行，镜像 `0781f1f7…`；`llvm-nm` 三个符号在（`_k60_usblog_reset_to_fastboot`/`_k60_prime_restart`/`_k60_restart_reason`），但**是否真的复位过还没有上机证据**。
- ③ 已核实（2026-11-22，离线读镜像）：`payload.img` 里 `EFI/UniXNU/unixnu.toml` 为 `timeout = 10`、`default = "xnu"`，`[[entry]] id="xnu"` 的 `title = "iOS 27"`、`path = "Payloads/kernel.macho"`、`args` 8 项 120 B ⇒ 菜单会在 10 秒后自动引导 27 内核，不需要人按键；黑屏因此是交棒之后的事，与菜单无关。

## 2026-11-23 复核（冻结仍为 frozen，本段只补机器读数）

| 条件 | 现状 | 读数（可复跑） |
| --- | --- | --- |
| ① 同一次启动内日志通路 | 代码侧就绪，缺上机读数 | `check-kernel-console.py --kernel <board>/kernel/kernel.macho` 打印定义了 `_pong_ramoops_console_write` 与 `_pong_ramoops_console_init` |
| ② 无疏漏 | 机器证据齐 | `check-series-order.py` 打印 arch 65/0、soc 2/0、os 4/0、device 57/0，合计 applied=128 failed=0；`check-goal-constraints.py --parity-only` 报 1527 条、0 unknown |
| ③ 菜单自动引导 | 已核实 | `payload.img` 内 `unixnu.toml` 为 `timeout = 10`、`default = "xnu"` |
| ④ 自动复位 | 代码在，缺上机读数 | `llvm-nm` 三个符号在；`F2-PREDICTION.md` 的 `k60-autoreset: armed` 与 `resetting` 两行尚未出现 |
| ⑤ blocker 可观测 | 已满足 | `check-ios27-artifacts.py --flight-ready` 的 `open_blockers()` 拒绝无 `observe_via` 的条目，测试 48/48 |

结论：只剩 ① 与 ④ 的上机读数；两者都需要一次飞行，而飞行归 Lead 且受本冻结约束。③ 须用户过目
`PORT-AUDIT-20261123.md`、`PORT-DECISIONS-2.md`、`BORROWABLE-MECHANISMS.md` 后才解冻。

### ⑤ 不只是「可观测」（2026-11-23 实测）

`python3 scripts/check-ios27-artifacts.py <board> --flight-ready` 在上一张图上 **rc=1**：

```
error: structurally valid, but not flyable: 94 owner-target items have no address in the
prelink map (21 bundles); 203 items are redirected to the _unixnu_fileset_unmapped panic
stub (25 bundles); blocker prelink-map-unresolved: …
prelink regressed: 91 item(s) sit at addresses the policy does not name
```

⇒ ⑤ 的字面要求（每条 open 都有 `observe_via`）已满足，但 `--flight-ready` **还要求 blocker 全部
`state = "closed"`，并且本次构建的 prelink 残留必须已写成本地基线**
（`docs/engineering/IOS27-PRELINK-POLICY.json`，可用 `check-prelink-regressions.py --write --force` 生成）。

两件事都不是纯机械动作，必须由用户裁：

1. **`prelink-map-unresolved` 是否可关**：支持关闭的结构证据是 console 在 `osfmk/kern/startup.c:478`
   与 `:585` 就初始化，而 205 个桩站点全在 kext 指针槽（`PE_init_iokit()` `:689` 之后才可达）；
   `PRELINK-RESIDUE.md` 记了 94/203 的分组与 3 个未配对地址。反对关闭的理由是上游 policy 的基线是
   Apple 自己 kernelcache 的 2/24，我们 94/203 的差额没有被逐条解释。
2. **基线怎么落**：写本地 policy 会把 94/203 固化成「以后不许变差」的起点；不写则每次 `--flight-ready`
   都因 policy 未命名而报 regressed。写它不等于关 blocker，两者要分开决定。
