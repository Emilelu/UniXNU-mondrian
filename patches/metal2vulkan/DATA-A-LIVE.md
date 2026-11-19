# Data A Live 优化来源

0012、0013、0015–0019 从用户提供的 `data-a-live-cpu-gpu` 源码包移植，原项目 ShueiTsuki/data-a-live（包内标注 a417358）。保留补丁内原始作者和变更内容，适用原 metal2vulkan 许可及包中 MIT 许可。归档原作者说明见 `out/ipados18/services55-reference`。本分支仅导入运行时生产代码，不添加/运行包内的测试、采样器或自动滑动程序。

适用于22H374/SM8475/A730的独立适配：新增可协商的method17/128IB接口、保留method5/16IB接口；不修改A730真实芯片号、不复制SM8850/Adreno840寄存器、固件、SCMI通道或温度常数。padded Alias策略未启用，保留影子图像及边界规则。

## 未启用（当前构建不应用）

`scripts/build-pong-metal-bridge.py` 只应用 `0008`（20G81 policy）与 `0009`
（own-surface row padding），其余补丁在构建里**一次都没有被 apply**。保留它们是因为
它们是同一问题族的历史修法，但现状是「文件在树里、二进制里没有」——所以在此显式声明，
并由 `scripts/check-metal2vulkan-patches.py` 守卫（未声明即失败）：

- `0010-pong-ipados18-22H374-policy.patch` — 面向 22H374，本机是 20G81，不适用。
- `0011-pong-scoped-memory-pressure.patch` — 内存压力作用域，需先在 20G81 上证明缺失症状。
- `0012-data-a-live-final-pass-cache.patch` — pass 缓存，属性能项，非当前卡死原因。
- `0015-data-a-live-draw-commands-kept.patch` — draw 命令保留；同上，优先评估。
- `0016-data-a-live-draw-lists-kept.patch` — draw 列表保留；同上，优先评估。
- `0017-data-a-live-refuse-rebinds.patch` — 拒绝重绑定，属正确性项。
- `0018-data-a-live-tracker-key-map.patch` — tracker 键映射，属正确性项。
- `0019-data-a-live-two-plane-shadow-as-it-lies.patch` — 两平面 shadow 布局，属正确性项。
- `0021-zizhan-keep-two-empty-blocks.patch` — 来自 zizhan 的空块保留，来源不同族。

启用任一条前必须先在 Mac 侧对 pin 住的 translator 跑 `git apply --check`，并在宿主测试里
给出「应用前/应用后」的行为差异；不得只因为「看起来相关」就打开。

## 已应用（2026-11-18 起）

`scripts/build-pong-metal-bridge.py` 现在按顺序应用 `0008`、`0009`、`0013`：

- `0008-pong-ios16-20G81-policy.patch` — 20G81 policy 行。
- `0009-pong-owned-iosurface-row-padding.patch` — own-surface row padding。
- `0013-data-a-live-fewer-allocations-a-draw.patch` — **每 draw 分配次数收敛**：viewports/
  scissors/specialization 留在 encoder 里，不再每次 draw 复制一份。实测动机是一次 draw 触发
  5,517 次 `IOMemoryDescriptor` 映射后 `nmb_render_draw` 不返回；补丁自带说明为
  「frame_costs_plain: 24.6 -> 17.8 allocations a draw」。

应用前置验证（2026-11-18，Mac `192.168.31.204`，pin `2c8369999af72509ebc45e491f2368d4b0e7fc70`
= "metal2vulkan 720ef1ce snapshot"）：对 `git archive` 导出的干净树逐个 `git apply --check`，
结果 **8 个可应用**（`0008`、`0009`、`0011`、`0012`、`0013`、`0017`、`0019`、`0021`）、
**4 个已过时**（`0010` 面向 22H374；`0015`、`0016`、`0018` 的 hunk 与当前 pin 不符），
且累计应用 `0008+0009+0013` 与 `0008+0009+0013+0011+0012+0017+0019` 两次都干净通过。
本次只开 `0013` 一个变量，其余仍留在「未启用」里等单变量证据。

构建侧顺带修掉的真缺陷（2026-11-18）：`scripts/build-pong-metal-bridge.py` 原来把
`SDKROOT=<iPhoneOS>` 导出给整个 cargo 环境，rustc 的 **host** cc 也读它，于是 x86_64 主机
链接报 `missing required architecture x86_64`（`ld: ignoring ... iPhoneOS.sdk/usr/lib/libSystem.tbd`）。
修法：不再导出 `SDKROOT`，iOS sysroot 只经
`CARGO_TARGET_AARCH64_APPLE_IOS_RUSTFLAGS=-Clink-arg=-isysroot -Clink-arg=<ios sdk>`
给目标三元组，host 侧用 `CC_x86_64_apple_darwin` / `CFLAGS_x86_64_apple_darwin` 钉到 macOS SDK。
修好后桥接层产物：`PongMetalBridge.dylib` 32,962,136 B，sha256
`b16d367a295a0b7c888bb7d03ef32729343397a9efc9211c9caea08abd22476d`（上一版 33,246,528 B /
`3ee9e5c8…`，不含 0013）。
