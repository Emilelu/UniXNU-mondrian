# iOS 迁移边界：只保留可转移的活

**决定（用户 2026-11-19，m44559）**：GPU 线只保留「可转移」的活。等 `xNekom/UniXNU-mondrian`
的 `feat/ios27` 推进到 `bsd_init` 后全面转向 iOS 27。本文件是这条边界的判据，用于回答
「这件事该不该继续做」。

## 1. 为什么 iOS 16 是这批参考实现里最没有先例的一档

本机四棵 SM8475 树的 OS 目标：

| 树 | 设备 | OS 目标 |
|---|---|---|
| `UniXNU-pong` | Nothing Phone (2) | iPadOS 18.7.10 / 22H374（另有 21H461 = 17.7.11） |
| `UniXNU-zizhan` | Xiaomi MIX Fold 2 | iPadOS 18.7.10 / 22H374 |
| `UniXNU-liuqin` | Xiaomi Pad 6 Pro | iPadOS 17.7.11 / 21H461 |
| `k60-gates` | Redmi K60 | **iPadOS 16.6.1 / 20G81** |

只有我们在 16。而我们的 Metal 栈（`metal2vulkan` runtime、插件、presenter）是从 18.x 时代的
代码搬来的，比目标 OS 新两代。三条可核实的后果：

1. `supportsConditionalLoadStore` / `supportsComputeCompressedTextureWrite` /
   `isLargeMRTSupported` 在 `MetalLevel::IOS16_6_1` 上拿不到设备答案——runtime 的实测属性表
   只有 macOS 行，iOS 层落到 Metal 表，`private().flag(f).value()` 返回 `None`，
   于是 `installAnswers()` 直接 `continue`，selector 从未装上。
2. 官方 GPU 二进制要求 iOS 17（`MTLLanguageVersion3_1`），在 16 上编译失败。
3. zizhan 在 18.7.10 上跑同一套代码达到 95.3 fps（合成负载），我们在 16.6.1 上功能通、性能不足。

结论：不是「抄得不够」，是选了一个参考栈不支持的代次。

## 2. 判据：一件事算不算「可转移」

按顺序问三个问题，任一为「是」就不算可转移：

1. 它是否只在某个 `os_profile`（现在是 `ipados-16.6.1-20G81`）下成立？
2. 它是否在补这一代的缺口（Metal 能力表、userland ABI、20G81 专属补丁）？
3. 它是否只有在「客户端绘制已经够快」的前提下才有意义？

反过来，满足下面任一条就是可转移：与 OS 无关的内核/驱动行为；与面板/DPU/SMMU/UFS 等硬件
契约有关的事实；能跨分支复用的工具与门禁；已量化的性能结论（数字本身不随 OS 变）。

## 3. 保留（可转移）

| 项 | 现状 | 为什么可转移 |
|---|---|---|
| `import` 双峰（63 µs / 15,000 µs） | 本飞新发现，未解 | presenter 侧的页处理，与 OS 版本无关 |
| 内核侧扫出路径（单跑 5760 已成立） | `gpu-onepitch-20261119` 实测 | `PongAdrenoScanout` 的 wire/缓冲契约 |
| 零拷贝扫出（`token/evict/target`，48→56 B） | 未做 | 硬件契约，27 上同样需要 |
| IO coherence 探针 | 已生效（publish ÷130） | 硬件特性，与 OS 无关 |
| P-244 映射泄漏（`maps/unmaps` 计数） | 计数已加，未修 | 内核记账 |
| 面板三档时序 / ADT / 启动参数预算 | 已成立 | 硬件事实 |
| 判读器与门禁（`judge-gpu-*`、`check-*`） | 在用 | 工具跨 OS 复用 |
| 上机流程（boot claim、watchdog、证据目录） | 在用 | 流程 |

## 4. 停止（iOS 16 专属）

| 项 | 为什么停 |
|---|---|
| Metal capability selector 回填（`value()` 为 `None` 时回落 `PrivateAnswer::metal()`） | 补的就是第 1 节那个代差缺口；18.x 上不存在该问题，27 上大概率也不需要 |
| 在 16 上追 120 fps（客户端绘制 ~48 ms、20 % 长停顿的调优） | 客户端栈会随 OS 换代整体更换，调优成果不带走 |
| `patches/metal2vulkan/*` 的 16 专属迭代 | `0008-pong-ios16-20G81-policy.patch` 这类补丁本身就要作废 |
| 为 16 新增任何一个以 OS 名命名的补丁/脚本 | 会让迁移面继续变大（现状见第 6 节） |

已经放弃、不要再捡回来的两件事，记在这里以免下次又有人「顺手补一下」：
`Patches` 里那三个 selector 的回落、以及 `present()` 在 16 上的进一步降时（在 27 上要重测基线）。

## 5. 迁移准备（低成本、随时可做）

1. **盯上游**：`xNekom/UniXNU-mondrian` 的 `feat/ios27`，里程碑 F0/F2/F3 已完成
   （PAC probe 补丁、host 上构建 prelink、Linux 上构建 userdata 镜像、无需 macOS 解密 AEA）；下一个
   门槛是 `bsd_init`。最后提交 2026-11-18 11:40 UTC。
2. **我们这边的暂存**在 `feat/bt-ios27-port`：`profiles/os/ios-27.0.1-24A446/{abi,configs,patches}`、
   `configs/mondrian_ios27_defconfig`、`docs/engineering/IOS27.md`、`docs/plans/BT-IOS27-PORT.md`。
3. **收缩 16 的迁移面**：现状统计（2026-11-19）
   `patches` 23 文件 / 104 处、`scripts` 59 / 199、`drivers` 15 / 61、`configs` 2 / 2、
   `docs` 114 / 900、`board.toml` 6、`porting.toml` 9。文件名自带代次的：
   `configs/pong-iogpu-20G81.json`、`patches/metal2vulkan/0008-pong-ios16-20G81-policy.patch`、
   `patches/xnu/ios16-*.patch`（6 个）、`prebuilt/20G81-trustcache.bundle`、
   `scripts/audit-ios16-*.py`、`.github/workflows/ios16-os-window.yml`。
   原则：**不再新增**以代次命名的文件；新东西一律按能力/硬件命名。
4. **保住 iOS 16 的硬件证据**：它能启动、面板 120 Hz、触摸可用、存储与 USB 已 device-verified。
   这些事实随 OS 换代仍然成立，是 27 起跳时的对照基线。

## 6. 这条边界怎么执行

- `porting.toml` 的 `gpu` 区 `next_action` 指向本文件；新开的 GPU 工作项必须先在第 2 节的判据下
  归类，归不进「可转移」就不开工。
- 关闭一个 16 专属项时，在 `docs/research/gpu/` 的对应用例里写明「按 IOS-SCOPE 第 4 节停止」，
  不要只删待办——删了下次会有人重新发现它。
- 相关门禁与判读器留在原地：它们是工具，不属于任何一代 OS。
