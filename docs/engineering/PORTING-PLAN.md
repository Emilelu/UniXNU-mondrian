# K60（mondrian / SM8475）移植方案

本文是 Redmi K60 上 UniXNU / iOS 27 移植的总方案。目标是让设备进入 iOS 27.0.1
（24A446）用户态并逐步驱动全部硬件。文档面向接手者，按「能复现、能判定、能回退」写。

## 1. 四层仓库

| 层 | 仓库 | 内容 |
|---|---|---|
| 框架 | [Emilelu/UniXNU](https://github.com/Emilelu/UniXNU)（上游 [UniXNU/UniXNU](https://github.com/UniXNU/UniXNU)） | `unixnu` CLI、共享脚本、组件目录、profile |
| SoC | [Emilelu/UniXNU-sm8475-common](https://github.com/Emilelu/UniXNU-sm8475-common) | `soc.toml`、`configs/sm8475.config`、`dts/sm8475.dtsi` |
| 设备 | [Emilelu/UniXNU-mondrian](https://github.com/Emilelu/UniXNU-mondrian)（本仓库） | `board.toml`、`dts/mondrian.dts`、`patches/`、交付记录 |
| 固件 | [Emilelu/uefi-mondrian](https://github.com/Emilelu/uefi-mondrian) | EDK2 / Mu-Silicium 构建树、DarwinBoot、payload 菜单 |

四层通过 `board.toml` 的 `[package]` 与 `[os_overrides]` 组合；补丁按
`arch → soc → os → device` 顺序重放，任何一层缺失都会在后续层表现为「补丁打不上」。

## 2. 目标与阶段

- **stage-0**：iOS 27.0.1（`--os ios-27.0.1-24A446`，arm64e / 4 KiB / xnu-12377.121.6）
  内核从 `fastboot boot` 进入 `arm_init → bsd_init → 根设备挂载 → launchd → SpringBoard`。
- **stage-1**：SpringBoard 起后按硬件线回补：显示（GopFramebuffer）、触摸（Goodix GT9916R）、
  电源/电池（PongPower、ADSP PAS）、WiFi（QCA6490）、蓝牙（QCA6490）、USB（DWC3）、
  GPU（Adreno A730 + metal2vulkan）。
- iOS 16.6.1（20G81）线保留在 `archive/ios16-final-*`，用
  `--os ipados-16.6.1-20G81` 仍可构建，作为行为对照与回退基线。

## 3. 启动链

```
ABL → fastboot boot boot.img
   → BootShim（112 B）
   → UEFI 固件卷（FD，3 MiB，含 UniXNU 菜单 / DarwinBoot / Rambo ops）
   → DarwinBoot 解析 payload（FAT，192 MiB）内的 kernel.macho + ADT
   → 内核 Entry.S（整屏绿标记）→ arm_init → pexpert → pmap → IOKit → bsd_init
   → 根设备（unixnu 分区，三窗口 SHNGROOT v1）→ launchd → SpringBoard
```

关键事实：
- boot.img 的内核槽 = gzip(112 B shim + 3 MiB FD) + 末尾 4 KiB 裸 DTB。
- 真正的内核在 payload 的 `EFI/UniXNU/Payloads/kernel.macho`，不是 boot.img 内核槽。
- 27 内核是 `MH_FILESET`（49 个条目）；16.6.1 是单 `MH_EXECUTE`，这是两者构建/运行差异的根源。

## 4. 当前状态（2026-11-25）

已完成：
- 27 内核可构建、可打包、可被固件装载；内核能打印完整文本（P-313 字形修复后）。
- unixnu 分区已写入正式 27 三窗口镜像（OS 0x100000 / SystemOS 0x261700000 / Data 0x3c9700000，
  Data 18,095,276,032 B 真 APFS）；写后四段 `cmp -n` 全部 MATCH。
- GIC（`0580-k60-pong-interrupt-map.patch`）、UFS 源存储（sheng SourceStorage runtime +
  本仓 `drivers/NativeUfs` 工厂）、USB 控制台参数、Darwin 23 BootArgs ABI 均已落库。

未完成 / 已知缺口：
- **prelink 映射**：155 个 owner-target 项无地址、234 项指向 `_unixnu_fileset_unmapped`
  （AMFI 41、apfs 20、sandbox 23 等）。运行到对应用户态路径会触发桩 panic。
- **r313h 回归**：能打印文字的 r290n（`311f4f54…`）之后叠加了 0580 GIC、source-storage 链接与
  整屏清零，r313h（`932d50ad…`）在 console 前死亡（屏幕停在 Entry.S 绿屏）。需要按单变量二分。
- 显示：27 没有 `GopFramebuffer` 组件；文本控制台可用，但 SpringBoard 需要 framebuffer provider。
- GPU：Metal 插件与 A730 后端已有材料，尚未在 27 上跑通帧。

## 5. 关键路径与产物

- 构建工作树：`E:/iOS Port/Sources/Hardware/k60-gates`（本仓库的构建/门禁副本）。
- 构建输入镜像：`/opt/k60/trees/gates-device`（由 `scripts/sync-device-input.py` 同步）。
- 输出：`/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/`
  （`kernel/kernel.macho`、`payload/payload.img`、`boot/boot.img`）。
- 证据：`E:/iOS Port/Work/evidence/usblog-*`（console.log + capture.json + boot.json）。
- 镜像归档：`E:/iOS Port/Work/artifacts/`。

## 6. 风险与回退

- 任何上机都要有预写判据和串口/屏幕见证；绿屏 = 内核在 console 前死亡，不是固件问题。
- 只允许 `fastboot boot`，**永不** `fastboot flash`，**永不**写 `/dev/block/sda38` 以外的分区。
- 每张镜像记录 `boot.img` / `kernel.macho` / `payload` 三个 sha256；改动前后必须能对账。
- 遇到门禁红：先读门禁源码确认它量的是什么，再改代码；门禁本身出错要登记 pitfall 并修门禁。

## 7. 参考

- 官方文档：https://unixnu.com/zh/porting/
- 同 SoC 参考：`UniXNU-zizhan`（SM8475）、`UniXNU-sheng`（SM8550，27 线最完整）
- 行为参考：`UniXNU-t970`（SM8550）、`UniXNU-pong`（iPadOS 18 线）
- 历史记录：`docs/engineering/STATUS.md`、`docs/engineering/PITFALLS.md`、`docs/research/ios27/`
