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

（飞行后填写）
