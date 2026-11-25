# 飞行卡 j：把行距改回客户端要的值 —— 负优化 A/B 的第一半

## 1. 为什么飞这一张

用户 2026-11-19 报「这几轮 gpu 改动是负优化 更卡了」。核查后确认有两项**行为改动从来没有做过单变量 A/B**：

| 改动 | commit | 当时的证据 | 缺的证据 |
|---|---|---|---|
| `TU_DEBUG` `sysmem,nocb` → `gmem,nocb` | `99cf832c` | 无（为它构建的 `gpu-gmem-20261119` 从未上机，设置随之后每张镜像生效） | 任何一次 A/B |
| `pong_surface_pitch` 默认 `1`（把合成器请求的 5888 行距改成 5760） | 卡 h | `encode` 19,396 → 593 µs、`gpu` 7,283 → 1,616 µs（`usblog-20261119-125434`） | 视觉正确性 S8 至今没有目视确认；卡 h 自己也把 S8 记为「待目视」 |

本卡验第一项的一半：**`pong_surface_pitch` 默认改回 `0`**，即恢复客户端请求的行距与纹理 untile 路径，其余一切不变。
如果设备的手感恢复，负优化就是这项几何改动造成的；如果仍然卡，第二半是把插件 `TU_DEBUG` 改回 `sysmem,nocb`（需在 Mac 重编 `PongAdrenoMetal`）再飞一次。

## 2. 改了什么

- `patches/xnu/zzzzzzzzzzzzzzzzzzz-pong-hackios-ui-foundation.patch` 里 `uint32_t onePitch` 默认值 `1` → `0`，并把「为什么不能默认开」写进那段注释。
- 同一个补丁顺带折进了原先由 `-pong-iosurface-bounds.patch` 与 `0212-k60-empty-accelerator.patch` 追加的内容，`series` 228 → 227（见 commit `build(patch): fold the MiniIOSurface edits into the patch that creates the file`）。这一项**不改行为**，只是让补丁链不再自相矛盾。
- 没有其它改动；插件仍是 `metal-plugin-20261119p`（含 `gmem,nocb`），启动参数仍是 30 条 596 字节。

## 3. 前置条件

- **P1** 上述 commit 已推送，构建输入已同步（`sync-device-input.py`）。
- **P2** 镜像 `gpu-pitchoff-20261119` 的 `image-arg-audit: OK (30 arguments, 596 bytes)`。
- **P3** 内核串里 `plane pitch asked=` 的命中数 = 1（补丁确实在）。
- **P4** 插件 bundle 的 `PongAdrenoMetal` sha256 前缀 `c7cfd63b`（与 `metal-plugin-20261119p` 一致）。
- **P5** `K60_AGENT_ID` 已设置（`flash.sh` 空则 rc=7）。
- **P6** 目标在 fastboot 或可被 supervisor 用 adb 重启到 fastboot。

## 4. 判据

### 4.1 有效性（先判这一层，P-236）

- 合成器产帧 > 0（`MiniIOMobileFramebuffer: N frames in M ms`，N > 0）。
- 客户端 commit > 0（`Pong Metal: c<n>/0 d<n>`，n > 0）。
- `scanout frames=` ≥ 2 条。
- 出现 `DeviceLost` ⇒ 本次判 **INVALID**（P-244），不得用来判断手感。

### 4.2 成功判据（本卡问的是「行为是否回到改动之前」）

- **S1** 无 `panic(`、无 `K60KEXC`、无 `crashed: backboardd`。
- **S2** 形状行是 `Pong Metal: scanout copy texture untile source=5888 scanout=5760 rows=3200` —— 即客户端请求的 5888 行距被尊重，纹理 untile 回来了。
- **S3** 没有 `MiniIOSurface: row bytes asked=… reported=… (one pitch only)` 这条强制行（默认 0 时它不该出现）。
- **S4** 面板仍是 120 Hz：`K60 PANEL: INTF1 after the UI frame te` ≥ 110。
- **S5** 记录本飞的分位数据（帧周期 p10/中位/p90/最大）与 `import`/`encode`/`submit`/`gpu`/`sum` 中位，供与 `usblog-20261119-125434`（单跑那飞）对照。
- **S6** 用户目视：主观手感是否回到「只是帧率低」而不是「更卡」。

### 4.3 失败规则

- **F1** 出现 panic / `K60KEXC` ⇒ 立刻回滚这次默认值改动。
- **F2** 形状仍是 `single run` ⇒ 默认值没有生效（补丁没进镜像），本飞无效。
- **F3** 出现 `row bytes asked=` ⇒ 默认仍是 1，本飞无效。
- **F4** 面板掉回 60 Hz ⇒ 与本卡无关的回归，先查切档调用点。
- **F5** 用户仍报「更卡」⇒ 第一半洗清嫌疑，做第二半（插件 `TU_DEBUG` 回 `sysmem,nocb`）。

## 5. 结果登记

### 5.1 飞行事实

| 项 | 值 |
|---|---|
| 镜像 | `gpu-pitchoff-20261119`，`boot.img a4cb3375b9e0e8c18a277c11b45547b8c27bb6549c02a9926f5d607177528d79` |
| 证据 | `E:/iOS Port/Work/evidence/usblog-20261119-151837`，`console.log` 283,510 B |
| supervisor | rc=0，`✅ 抓取完整、未因 panic/复位中断` |
| 启动参数 | 30 条 / 596 B（`image-arg-audit: OK`） |
| 插件 | `metal-plugin-20261119p`（`gmem,nocb` 仍在，本卡没动它） |

### 5.2 判据表

| 判据 | 结果 | 依据 |
|---|---|---|
| 有效性：合成器产帧 > 0 | ✅ | `MiniIOMobileFramebuffer: N frames in M ms` 5 条 |
| 有效性：客户端 commit > 0 | ✅ | `Pong Metal: c…` 4 条 |
| 有效性：`scanout frames=` ≥ 2 | ✅ | 34 条 |
| 有效性：无 `DeviceLost` | ✅ | 0 条（P-244 未出现） |
| **S1** 无 panic / K60KEXC / backboardd 崩 | ✅ | 三者各 0 |
| **S2** 形状是 `texture untile source=5888 scanout=5760` | ✅ | 行原文见下 |
| **S3** 没有 `row bytes asked=` 强制行 | ✅ | 0 条 ⇒ 默认值 0 真的生效 |
| **S4** 面板 ≥ 110 Hz | ✅ | `te 120/s … period 7679 us` |
| **S5** 记录分位与阶段中位 | ✅ | §5.3 |
| **S6** 用户目视手感 | ⏳ 待用户确认 | 本卡不能替人判断 |

形状行原文：

```
Pong Metal: scanout copy texture untile source=5888 scanout=5760 rows=3200 status=0x0
```

### 5.3 数字（34 条 stage 样本，`frames 1..260`，跨度 110.9 s）

| 段 | 中位 |
|---|---|
| `import` | 51 µs |
| `encode` | 335 µs |
| `submit` | 967 µs |
| `gpu` | 5,983 µs |
| `sum` | **8,281 µs** |
| `wait`（等客户端交帧） | 21,958 µs |
| `copy`（= present()） | 8,406 µs |
| `done` | 41 µs |
| 帧周期 | 30,654 µs（≈ 33 fps 的典型帧） |
| 全程平均 | 260 帧 / 110.9 s = **2.34 fps**（屏幕大部分时间静止） |

### 5.4 这一飞回答了什么

1. **默认值 0 生效**：形状回到 `texture untile`，且那条「强制单行距」日志一条都没有（S2/S3）。
2. **纹理 untile 并不天生贵**：同一形状的 `encode` 在这一飞是 **335 µs**，而 `usblog-20261119-025400` 里是 19,396 µs。差别不在路径，而在那一飞的 `encode` 取样多半落在启动/首帧上——所以「unttile 要 19 ms」这个早先结论只对首帧成立，不能当稳态。
3. **`present()` 已经在 120 fps 的预算之内**：`sum` 中位 **8,281 µs ≤ 8,333 µs**。典型帧 30.7 ms 里剩下的 22 ms 是 `wait`——**在等客户端交帧**，不是我们在拖。
4. 这也就把下一步指向客户端/合成器，而不是继续压 present()。

### 5.5 本卡不能回答什么

- **不能**说手感变好或变差：这是 34 条样本、屏幕大部分静止的一次飞行，且没有同一场景下的对照。S6 必须由用户目视。
- **不能**把它与 `usblog-20261119-125434`（单行距那飞）作严格 A/B：两飞的屏幕内容不同、帧数差两个数量级。严格 A/B 需要同一段动画在两个镜像上各飞一次。
- **不能**据此判断 `TU_DEBUG=gmem,nocb` 的影响：本卡没动它。

### 5.6 判据指纹

- criteria-sha256: 271aa97ef85d22ffa8e0449913d8637cae19ac5689bf4a2e5c416f1b662d1bb8
