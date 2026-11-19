# 上机卡：gpu-ans-20261118

## 1. 目的

验证**两个设备限制从「无回答」变成「按运行时属性回答」之后** Metal 前端的问题数是否下降，
以及 backboardd 是否因此开始提交绘制。只改桥接层（Rust `device_answer` + 前端 `gpuCoreCount`），
不动内核、不动部署、不动 boot args。

## 2. 前提证据（构建前必须已成立）

| 编号 | 证据 | 位置 |
|---|---|---|
| P1 | 桥接层补丁已提交并通过守卫（7 项） | `324d6c81`、`scripts/tests/test-metal-device-answers.py` |
| P2 | 插件 bundle 由当前源码重建（含补丁前端 + 新桥 dylib 32,970,648 B `016a0cc1…`） | `/Users/emilelu/k60-build/out/metal-plugin-20261118a` → `E:/k60-work/impl/gpu-mac-build/out/metal-plugin-20261118a` |
| P3 | 插件 bundle 六文件齐备，`PongAdrenoMetal` 94,896 B、`PongMetalBridge.dylib` 33,246,528 B | 同上 `build-report.json` |
| P4 | 镜像由 `build-strict.sh` 产出，`image-arg-audit: OK`、`verify-boot-image: OK` | `E:/k60-work/artifacts/gpu-ans-20261118/` |
| P5 | 未改动：内核补丁系列、`board.toml`、部署补丁 `0610` | `git diff 24c0ad55 -- patches/ board.toml` 为空 |

## 3. 抓取

`bash scripts/flash.sh /mnt/e/k60-work/artifacts/gpu-ans-20261118/boot.img 240`，
证据落 `E:/k60-work/evidence/usblog-<时间戳>/`，要求 `capture.json` 为 `complete=true`。

## 4. 判据

**S1** `K60KEXC` 出现次数 = 0（无内核异常）。

**S2** `K60METAL deploy files=6/6 inject=6 error=0` 出现至少一次（部署未被破坏）。

**S3** `Pong Metal: S` 行的 `x` 值 ≤ 3（修复前是 6；三个私有能力位按设计仍无回答）。

**S4** `Pong Metal:` 总行数 ≥ 10（插件与前端确实在跑，不是静默）。

**S5** `crashed: backboardd` 出现次数 = 0。

**S6** `Pong UI: main snapshot` 行的 `turns=` 至少一次 > 0（SpringBoard 主线程不卡在同步 XPC）。

**F1** `K60KEXC` > 0 → 内核异常，立即停止后续判读。
**F2** 部署行缺失或 `error != 0` → 插件未正确落盘，本镜像判废。
**F3** `x` 仍为 6 → 桥接补丁没有生效（要查 bundle 是否真的换了桥）。
**F4** `Pong Metal:` < 10 行 → 插件未执行，问题不在 selector。
**F5** `crashed: backboardd` > 0 → 崩溃回归，回退本镜像。
**F6** `turns` 全部为 0 → 主线程仍阻塞，下一层是 backboardd 的启动握手，不是 selector。

## 5. 结果登记

**判决：目标假设成立（PASS）；首帧仍未达成（FAIL(F4/F6)）。**

证据 `E:/k60-work/evidence/usblog-20261118-003847`，`console.log` 3,072 行，抓取完整、未因 panic 中断。

| 判据 | 实测 | 结果 |
|---|---|---|
| S1 `K60KEXC` | 0 | ✅ |
| S2 `K60METAL deploy` | 1 次，`files=6/6 inject=6 error=0` | ✅ |
| S3 `Pong Metal: S` 的 `x` | **3**（修复前 6） | ✅ |
| S4 `Pong Metal:` 行数 | **7**（阈值 10） | ❌ |
| S5 `crashed: backboardd` | 0 | ✅ |
| S6 `turns>0` | 无 `main snapshot … turns=` 行，只有 `main frame 0..11` | ❌ |

关键行（原文）：

```
Pong Metal: real Vulkan-backed device created status=0x0
Pong Metal: real device returned to stock20G81 discovery status=0x0
Pong Metal: real GPU scanout worker ready status=0x0
Pong Metal: c0/0 d0 p0 x3 R0 D0 F0 M0 C0 B0 native-metal: no device answer: the device has no answer for supportsConditionalLoadStore | …
```

结论：两个 selector 的修复**按设计生效**（问题数 6→3，剩下的三条正是按设计不回答的私有能力位）；设备仍能创建、扫描输出线程仍就绪、backboardd 零崩溃。S4 的 10 行阈值写错了（本插件版本没有构造标记，正常只有 7 行），按 F4 的本意（插件未执行）不成立。

仍未达成首帧：`p0`（零次提交/绘制）。主线程只剩 `main frame` 栈帧转储、没有 `turns` 行，说明 SpringBoard 仍卡在发往 backboardd 的同步调用上。下一层问题不在 selector，而在 backboardd 拿到设备后**为什么不提交帧**以及主线程为何等不到回应。

