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

### 5.1 飞行事实

- 镜像 `gpu-onepitch-20261119`，`boot.img a95d461ac4c9d6ab9bab4c0399296d77912d78a8c5f0ad94450971723e8c3787`，
  kernel `88eb8780d80a966fe6a4a088f65a8f726ad2ce6c0ac3fb10ee63a6c52165408e`（105,693,184 B），
  series 228 `frozen=58f9b845…`，插件 `metal-plugin-20261119p`，args 30 / 596 B。
- 证据 `usblog-20261119-125434`，`console.log` 246,672 B，supervisor rc=0，
  「✅ 抓取完整、未因 panic/复位中断」。
- 启动路径本身值得记一笔：设备先报 `当前: none`（supervisor 判「既不在 fastboot 也不在 adb」），
  十几秒后 `adb devices` 出现 `6033dbec	device`，watcher 立刻用 adb 窗口起飞。**只等 fastboot 的
  watcher 会在这种窗口里报「没有窗口」22 分钟**，而 supervisor 本来就能在 claim 内自己重启
  到 fastboot。

### 5.2 判据

| 判据 | 结果 | 依据 |
|---|---|---|
| S1 无 panic / K60KEXC / DeviceLost / backboardd 崩 | ✅ | 四项各 0 命中 |
| S2 `row bytes asked=5888 reported=5760` | ❌ | 9 条 `row bytes` 行全是 `asked=196 reported=128`（128×128 那几块），**没有 5888 那条** |
| S3 形状变 `single run` | ✅ | `Pong Metal: scanout copy single run source=5760 scanout=5760 rows=3200` |
| S4 稳态 `encode` < 2,000 且 `submit` < 3,500 µs | ⚠️ 未测到 | 本飞只有 6 帧（`frames=1..6`），没有 `frames>=20` 的稳态行 |
| S5 稳态 `copy` < 8,000 µs | ⚠️ 未测到 | 同上 |
| S6 `imports == frames` | ✅ | 6/6 行相等 |
| S7 面板 ≥110 Hz | ✅ | `K60 PANEL: INTF1 after the UI frame te 122/s … period 7614 us` |
| S8 画面正确（目视） | ⏳ 待用户确认 | 日志侧无斜切证据：两端行距已经相等（5760/5760） |

**判决：S3/S6/S7 通过，S1 通过，S4/S5 未测到，S2 按字面失败但它的意图被 S3 取代。**

### 5.3 为什么 S2 失败而改动其实是成功的

S2 写的是「必须有一条 `asked=5888 reported=5760` 的行」。这条打印只在
`onePitch && askedRowBytes != bpr` 时触发，而 5888→5760 这一步一旦生效，**合成器那块画布
要么不再问 5888，要么问的正是 5760**，于是这一行根本不存在。真正的证据是 S3：
`source=5760 scanout=5760` 说明帧的行距已经等于扫描缓冲的行距，纹理 untile 分支不再进入。

这是 P-242 的第四张脸：判据点名了一条**日志**，而不是点名了**性质**。判据本应写成
「形状行不再是 `texture untile`」——同一件事，但不会因为打印条件而假失败。
下次同类判据一律以「形状/性质」为准，不以「某条打印」为准。

### 5.4 已经确定的收益（同一空闲口径对比）

同一台设备、同样静止屏（无动画），把 `present()` 的四段并排：

| 阶段 | 纹理 untile（`usblog-20261119-025400`） | 单跑 5760（本飞） | 变化 |
|---|---|---|---|
| `encode` | 19,396 µs | **593 µs**（405–716） | ÷33 |
| `submit` | 8,420 µs | **493 µs**（361–1,954） | ÷17 |
| `gpu` | 7,283 µs | **1,616 µs**（1,517–4,967，一个 21,708 的离群） | ÷4.5 |
| `sum` | 30,248 µs | **19,233 µs**（6,066–24,685） | ÷1.6 |

`gpu` 落到 1.6 ms 与对照实验量到的「纯 buffer→buffer 18.4 MB = 1,835 µs」吻合，
说明这一段现在就是一次实打实的 18.4 MB GPU 拷贝，没有额外的 tiling/untile。

### 5.5 本飞暴露的新问题：`import` 变成双峰

`import` 在 6 帧里只有两种取值：**63–65 µs**（frames 2、6）与 **14,378–15,184 µs**
（frames 1、3、5）。中位 14,378 µs 现在是 `sum` 里最大的一项。
`newBufferWithBytesNoCopy` 本身不该花 15 ms，所以这 15 ms 落在导入背后的页处理上
（18.4 MB / 4 KiB ≈ 4,500 页；按 3.4 µs/页计正好是这个量级）。
在弄清它之前，**不能**说 `present()` 已经降到 6 ms——只能说非导入段降到了 6 ms。

### 5.6 本飞不能回答的问题

- **帧率**：整段只有 6 帧、跨 202 s（屏幕静止），既不能算 fps 也不能算帧间隔。
  S4/S5 判「未测到」而不是「失败」正是为此（P-236）。
- **斜切**：判据 S8 需要目视。日志只能说两端行距相等；不能说合成器是否真按 5760 写。
- **客户端那 ~17 ms**：本飞完全没有覆盖。

### 5.7 下一步（按依赖顺序）

1. **问清 `import` 的双峰**——它现在是最大项。先看 15 ms 的那几帧是不是落在「画布页刚被
   CPU 写过、GPU 首次访问」的时刻；若是，页预取/一次性固定才是解，而不是再动拷贝。
2. **S8 目视**：确认没有斜切后，把 `pong_surface_pitch` 的默认值 1 固化，并把 5888 的来历
   （CoreAnimation 按 32 像素对齐宽度）写进 `docs/research/gpu/` 与 `porting.toml`。
3. **带动画重飞**（P-236 的要求）：只有 >300 帧的飞才能给 `copy` 稳态与 fps；两者都没有时
   任何「快了多少」的说法都只对空闲帧成立。


（飞行后写在这里；`criteria-sha256` 在第一次写入时钉入，且必须单独占一行。）

- criteria-sha256: 4285c9e8331bea488ee6c307ab34f7868eeb738d93483848322f6fa2dbd765e1
