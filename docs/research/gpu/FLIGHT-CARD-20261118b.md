# 上机卡：gpu-policy-20261118

## 1. 目的

验证 QuartzCore 策略从「严格 once 断言」换回「信任 dispatch_once 完成契约」后，
`20G81 decoded-image policy unavailable status=-6` 是否消失，以及解码图像路径是否
让 backboardd 开始提交帧。只改 `PongQuartzCorePolicy.h` 一个头文件（插件侧）。

## 2. 前提证据

| 编号 | 证据 | 位置 |
|---|---|---|
| P1 | 恢复的正确策略文件（5,838 B，只校验 `value>1`，不校验 once 词法） | `8aec0f65` |
| P2 | 插件 bundle `metal-plugin-20261118b`，`PongAdrenoMetal` 94,896 B sha `546a8caf…` | Mac → `E:/iOS Port/Work/impl/gpu-mac-build/out/metal-plugin-20261118b` |
| P3 | 除该头文件外与上一飞完全相同（同一 bridge dylib `3ee9e5c8…`、同一内核 series） | `git diff 324d6c81..8aec0f65 -- drivers/PongMetal` |
| P4 | `image-arg-audit: OK`、`verify-boot-image: OK` | `E:/iOS Port/Work/artifacts/gpu-policy-20261118/` |

## 3. 抓取

`bash scripts/flash.sh /mnt/e/iOS Port/Work/artifacts/gpu-policy-20261118/boot.img 240`

## 4. 判据

**S1** `K60KEXC` = 0。
**S2** `20G81 decoded-image policy unavailable` 出现次数 = 0（策略这次应用成功）。
**S3** `Pong Metal: real Vulkan-backed device created status=0x0` 至少 1 次。
**S4** `Pong Metal: c0/0 d0 p0` 中 `p` > 0（出现提交/绘制），或出现 `present #` 行。
**S5** `crashed: backboardd` = 0。

**F1** `K60KEXC` > 0 → 立即停止判读。
**F2** 策略仍报 `-6` → 该文件不是根因，回退。
**F3** 设备未创建 → 插件/桥接坏了，回退本镜像。
**F4** `p` 仍为 0 → 策略不是绘制门控，下一层查 backboardd 的 drawable 或 CA 事务。
**F5** `backboardd` 崩溃 → 回退。

## 5. 结果登记

判决：**FAIL(F4)**，但策略项由红转绿。

| 判据 | 结果 |
|---|---|
| S1 K60KEXC=0 | ✅ 0 |
| S2 `decoded-image policy unavailable`=0 | ✅ **0**（修复前是 `-6`） |
| S3 设备创建 | ✅ `real Vulkan-backed device created status=0x0`（:1421） |
| S4 p>0 或 present # | ❌ `Pong Metal: c0/0 d0 p0 x3`（:1733/:2143/:2393）、`present #` 0 |
| S5 bbcrash=0 | ✅ 0 |

其余：`real device returned to stock20G81 discovery`（:1423）、`real GPU scanout worker ready`（:1433）、
`SpringBoard` 3、`K60KEXC` 0。证据 `E:/iOS Port/Work/evidence/usblog-20261118-011543`。
=> QuartzCore 策略回归确认修好（S2 从 `-6` 变 0）；`p0` 仍未解决，按 F4 转到 backboardd 的
drawable/CA 事务路径，见 `docs/research/gpu/FIRST-FRAME-GAP.md`。
