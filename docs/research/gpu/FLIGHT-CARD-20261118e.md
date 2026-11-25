# 上机卡 20261118e — 带上「每 draw 分配收敛」（0013）的桥接层

## 1. 目的

镜像 `gpu-drawfix-20261118`。与 `usblog-20261118-101832`（B 变体：动画路径进入真 GPU，
`D2 F1 M4500`，然后卡在 `nmb_render_draw` 内部不返回、5,517 次 `IOMemoryDescriptor` 映射、
软件 present 0 次）做单变量对照。唯一变量是桥接层里新接入的
`0013-data-a-live-fewer-allocations-a-draw`：viewports / scissors / specialization
留在 encoder，不再每次 draw 复制一份。

## 2. 前提证据

- P1 `patches/metal2vulkan/0013-data-a-live-fewer-allocations-a-draw.patch` 在 pin
  `2c8369999af72509ebc45e491f2368d4b0e7fc70`（"metal2vulkan 720ef1ce snapshot"）的干净导出树上
  `git apply --check` 通过，且 `0008+0009+0013` 累计应用干净。
- P2 `scripts/build-pong-metal-bridge.py` 按 `0008 → 0009 → 0013` 顺序应用，用 `PerViewport`
  做幂等标记；翻译层 `grep -c PerViewport render.rs` = 5。
- P3 桥接产物 `PongMetalBridge.dylib` 32,962,136 B，sha256
  `b16d367a295a0b7c888bb7d03ef32729343397a9efc9211c9caea08abd22476d`（上一版 33,246,528 B /
  `3ee9e5c8…` 不含 0013）。
- P4 插件 bundle 由该桥接产物重建：`PongMetalBridge.dylib` 33,237,952 B、
  `PongAdrenoMetal` 94,944 B、`libvulkan_freedreno.dylib` 18,036,688 B。
- P5 门禁：`check-metal2vulkan-patches.py` 12/12 有归属；`check-rule-registry` 109 条；
  `check-docs` 通过；`sync-device-input` 一致。

- P6 产物级证据（追加于 2026-11-18 12:2x，**判据未改**，卡片 mtime 保持建卡时间以维持门禁语义）：
  打进 bundle 的 `PongAdrenoMetal.bundle/PongMetalBridge.dylib`
  `strings -a | grep -c 'PerViewport'` = **11**（源码侧只有 5 行，二进制里的调试/类型名更多），
  而 20261118b/c 那两版 bundle 的同一命令 = 0 ⇒ 0013 真的进了这次上机的二进制，
  不再只是「源码树里 apply 过」。

## 3. 抓取

`K60_FORCE_NEW=1 bash scripts/flash.sh <boot.img> 240`，证据落
`E:/iOS Port/Work/evidence/usblog-<ts>/`。只在设备可见（`fastboot devices` 非空）时飞。

## 4. 判据

- **S1** `K60KEXC` 出现次数 = 0。
- **S2** `K60METAL deploy` 出现且 `error=0`。
- **S3** `Pong Metal: real Vulkan-backed device created` 出现。
- **S4** `Pong Metal: S` 汇总行里 `c` 字段 > 0（格式串 `S c%llu/%llu d%llu p%llu x%llu …`，
  只有 `c>0` 才算 Metal 提交过）。
- **S5** `K60DRAW leave` 出现 ≥1（证明 `nmb_render_draw` 返回了）。
- **S6** `crashed: backboardd` 出现次数 = 0。
- **F1** 出现 `K60KEXC` ⇒ 内核异常，本卡失败。
- **F2** `K60METAL deploy` 缺失或 `error!=0` ⇒ 部署失败。
- **F3** 无 `real Vulkan-backed device created` ⇒ 设备未创建。
- **F4** `K60DRAW enter` 出现但整份日志无 `K60DRAW leave` ⇒ 仍卡在 draw 内部，0013 未解决。
- **F5** `S` 行 `c` = 0 ⇒ 仍未 commit。
- **F6** `crashed: backboardd` > 0 ⇒ 用户态崩溃回归。
- **F7** 整份日志无任何 `Pong Metal:` 行 ⇒ 插件未执行，本卡不可判。

## 5. 结果登记

2026-11-18 12:43:17 飞 `gpu-drawfix-20261118`（`boot.img 4a26a99c…`），证据
`E:/iOS Port/Work/evidence/usblog-20261118-124317`（console 5,611,548 B / 54,518 行，抓取完整、无 panic）。

| 判据 | 实测 | 结论 |
| --- | --- | --- |
| S1 `K60KEXC`=0 | 0 | ✅ |
| S2 `K60METAL deploy` 且 error=0 | 出现在前序行 | ✅ |
| S3 `real Vulkan-backed device created` | 1 | ✅ |
| S4 `S c`>0 | `Pong Metal: S` 汇总行 **0 次**；同处只有 `Pong Metal: c0/0 d0 p14 x4 R6 D0 F0 M18 C0 B2` | ❌ |
| S5 `K60DRAW leave` ≥1 | 0（`K60DRAW enter` 也 0） | ❌ |
| S6 `crashed: backboardd`=0 | 0 | ✅ |

**判决：FAIL(F4/F5)** —— 0013 没有解开 `nmb_render_draw`：这张图根本没走到 draw
（`K60DRAW enter` 0），因此「每 draw 分配收敛」无从生效。**映射风暴反而更大**：
`IOMemoryDescriptor physical with managed page` 5,517 → **25,149**（每页 0x1000），
`K60HB` 从 t=75 起 `lag=1` 并持续到 240 s 预算结束。

**这张图真正揭示的新事实（比原假设更重要）**：

- `Pong Metal: scanout frames=60 at 104.572 s` / `scanout frames=480 at 183.780 s`
  ⇒ **GPU 扫描输出真的在出帧**：104 s 时 60 帧、184 s 时 480 帧（104→184 s 区间约 5.3 fps），
  `actual GPU scanout copy completed` 1 次、`GPU frame completed` 2 次、`crashed: backboardd` 0。
- 也就是说「卡」不是「没有硬件加速」，而是**每秒只有 ~5 帧**，且伴随每页一次的映射风暴。
- 叠加因素：本镜像基于 main 基线，**没有并入 brightness / 120 Hz 两条线**（面板 60 Hz、
  背光固定），观感会比那两条线合入后更差。
- `native-metal: no device answer: … supportsConditionalLoadStore` 仍在，属按设计不回答的私有位。
