# 飞行卡：只报一个行距（`gpu-onepitch-20261119`）

## 1. 为什么飞

`gpu-surface-20261119` 的 19 块 surface 表把行距差的入口指到了唯一一行：

```
sid=15  1440x3200 bpr=5888 planes=0 alloc=18841600   <-- 合成器的扫描画布
sid=16  1440x3200 bpr=5760 planes=0 alloc=18432000   <-- 我们自己创建的两块
```

5888 = 1472×4（32 像素对齐），只能来自 `MiniIOSurface::surfaceCreate()` 里的
`bpr = dictNumber(props, "IOSurfaceBytesPerRow", 0)`。而扫描目标固定 5760，
这个 128 字节/行的差**正是扫描 blit 必须走线性纹理 untile 的唯一原因**——
同一飞里 `encode` 是 46 ms 量级，而对照实验证明同样的 18.4 MB 普通拷贝只要 1.9 ms。

## 2. 改了什么

`MiniIOSurface::surfaceCreate()`：`pong_surface_pitch` 默认 `1`，此时忽略
`IOSurfaceBytesPerRow`，一律 `alignUp(width*bpe, MINISURF_ROW_ALIGN)`（1440×4=5760 本来就是
64 的倍数），请求值不同时打印
`MiniIOSurface: row bytes asked=%llu reported=%llu (one pitch only)`；`pong_surface_pitch=0`
回到旧行为。客户端通过 `IOSurfaceGetBytesPerRow` 得到我们回报的同一个数。

`PongMetal` 侧没有改动：行距一旦相等，现有代码自己就会走
`scanout copy single run stride=5760`。

## 3. 前置条件

- **P1** 八步门禁通过。
- **P2** `image-arg-audit: OK`，参数仍 30 条 / 596 字节（本参数默认开，**不占**启动行）。
- **P3** 内核 `strings` 里必须有 `row bytes asked=%llu reported=%llu (one pitch only)`。
- **P4** `verify-boot-image: OK`。
- **P5** `K60_AGENT_ID` 已设置。
- **P6** 设备在 fastboot。

## 4. 判据

### 4.1 有效性（P-236）

`MiniIOMobileFramebuffer: N frames` 且 N > 0；客户端 `Pong Metal: c<n>/0 d<n>` 且 n > 0；
`scanout frames=` 至少一行；且**必须有 ≥3 条 `scanout frames=`**（本飞要的是稳态数字，
只有 1–2 帧的飞不足以判 S4/S5）。

### 4.2 成功判据

- **S1** 无 `panic(`、`K60KEXC`、`DeviceLost`、`crashed: backboardd`。
- **S2** 至少一条 `MiniIOSurface: row bytes asked=5888 reported=5760`。
- **S3** 形状行变成 `scanout copy single run stride=5760`（不再是 `texture untile`）。
- **S4** 稳态（`frames>=20`）`encode` 中位 **< 2,000 µs**，且 `submit` 中位 **< 3,500 µs**。
- **S5** 稳态 `copy` 中位 **< 8,000 µs**（上一飞同口径 12,631–23,802 µs）。
- **S6** `imports == frames` 在每条 `scanout frames=` 上成立。
- **S7** 面板仍是 ≥110 Hz（`K60 PANEL: INTF1 … te 120/s`）。
- **S8** **画面正确**：用户目视不得出现斜切/错行。

### 4.3 失败规则

- **F1** 任何 panic / `K60KEXC` / `DeviceLost` ⇒ 立即 `pong_surface_pitch=0` 回滚。
- **F2** 没有 `row bytes asked=` 行 ⇒ 改动没进镜像或没执行，本飞作废。
- **F3** 有 `row bytes` 行但形状仍是 `texture untile` ⇒ 行距不是唯一原因，
  停止在这条路上加码，转 `ZIZHAN-DBUF.md` §6 的零拷贝。
- **F4** 出现斜切/错行 ⇒ 客户端不尊重回报行距，立刻 `pong_surface_pitch=0`，
  并在文档里记下「客户端要求 5888 是有原因的」。
- **F5** 零帧 ⇒ INVALID（重飞）。
- **F6** `copy` 反而变大 ⇒ 纹理 untile 并非我以为的开销来源，撤回结论。

## 5. 结果登记

（飞行后写在这里；`criteria-sha256` 在第一次写入时钉入，且必须单独占一行。）
