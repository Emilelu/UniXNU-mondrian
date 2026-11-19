# 飞行卡：`gpu-pitch-20261119` —— 让 surface 只报一个行距

## 1. 为什么飞这一张

2026-11-19 的对照实验（`gpu-blitprobe2-20261119`，飞行 `usblog-20261119-070345`）把同一个
18,432,000 字节、同一个 `copyFromBuffer + commit + waitUntilCompleted` 形状拷到两个目标：

| 目标 | 耗时 | 吞吐 |
| --- | --- | --- |
| GPU 自有缓冲 | 1,993 µs | 9.25 GB/s |
| 固件帧缓冲 | 1,835 µs | 10.04 GB/s |

所以目标端不是瓶颈。真实路径的中位阶段是 `import 53` / `encode 424` / `submit 3,015` /
`gpu 5,302` / `sum 12,552` / `copy 12,631` µs —— 同一个拷贝比对照慢 6.7 倍，差别只有一个：
真实路径走的是 `copyFromTexture`（linear texture untile），因为 **surface 行距 5888、帧缓冲行距 5760**。

这 128 字节/行不是我们加的：`MiniIOSurface` 从 `IOSurfacePlaneBytesPerRow` 原样接受客户端给的值
（`patches/xnu/zzzzzzzzzzzzzzzzzzz-pong-hackios-ui-foundation.patch` 里那段 `dictNumber(pd,
"IOSurfacePlaneBytesPerRow", 0)`；注释与行号见 `docs/research/gpu/ZIZHAN-DBUF.md` 之外的
2026-11-19 追查记录）。1440×4 = 5760 本来就是 64 的整数倍，我们自己的公式给出 5760。

这张卡验证一个单变量改动：**plane 是我们的，就只报一个行距**（自然对齐值 5760），
并把客户端请求值打进日志。若成立，untile、它的 5.3 ms 与那 128 字节/行的搬运一起消失。

## 2. 改了什么

- 同一个补丁文件里那段：不再采用 `IOSurfacePlaneBytesPerRow` 的请求值，一律用
  `alignUp(width * bytesPerElement, MINISURF_ROW_ALIGN)`；请求值与上报值不同时打印
  `MiniIOSurface: plane pitch asked=… reported=… (one pitch only)`。
- 没有别的改动。CPU 侧行为、参数行、插件字节均不变。

## 3. 前置条件（任一不成立就不飞）

- **P1** 构建全绿：八步 48 项、`image-arg-audit`、`verify-boot-image`、`kernel archives`。
- **P2** 内核里必须有 `plane pitch asked=` 这条串；没有就是补丁没进镜像。
- **P3** 插件钉住 `metal-plugin-20261119p`（`PongAdrenoMetal` sha256 前缀 `c7cfd63b`）。
- **P4** `K60_AGENT_ID` 已设，设备在 fastboot 或 adb（supervisor 会在 claim 内重启）。

## 4. 判据

### 4.1 有效性（先判这一层，P-236）

三项同时成立才算有效：`MiniIOMobileFramebuffer: N frames`（N>0）、
`Pong Metal: c<n>/0 d<n>`（n>0）、至少一条 `scanout frames=`。
若 `DeviceLost` 出现 ⇒ 按 P-244 判 INVALID（GPU 已死，帧率无意义）。

### 4.2 成功判据

- **S1** 无 `panic(`、`K60KEXC`、`crashed: backboardd`。
- **S2** 恰一条 `MiniIOSurface: plane pitch asked=… reported=…`，并记录两个数。
- **S3** `scanout copy …` 行报告的形状是 `single run`（而不是 `texture untile`）。
- **S4** 若为 `single run`：`encode` 中位 < 1,000 µs，`gpu` 中位 < 2,500 µs。
- **S5** `copy` 中位 < 10,000 µs（基线 12,631 µs）。
- **S6** 仍出帧且 `imports == frames`。
- **S7** 画面正确性**不由本卡判**：这只能由用户目视。日志只负责证明形状与数字。

### 4.3 失败规则

- **F1** panic / backboardd 崩 ⇒ 立即回滚这条改动。
- **F2** 没有 `plane pitch asked=` 行 ⇒ 改动没进镜像，不要读成「没有效果」。
- **F3** 仍是 `texture untile` 且 `reported=5888` ⇒ 我们的计算没生效（走了别的分配路径）。
- **F4** `single run` 但 `gpu` ≥ 5,000 µs ⇒ 对照的 1.9 ms 不适用于这条路径，需重新对照。
- **F5** 用户目视发现画面斜切/错行 ⇒ 回滚，并记录「客户端确实按它请求的 5888 写入」。
- **F6** 零帧 ⇒ 按 P-236 判 INVALID 并重飞同一张镜像、同一套判据，不许改阈值。

## 5. 结果登记

### 5.1 这一飞的事实

| 项 | 值 |
|---|---|
| 镜像 | `gpu-pitch-20261119`，`boot.img 7c1398b41ed6a20d4b4db8fc0dc7d5351174f505cd82801fba91b803258148a2` |
| 内核 | `fdf291f785aeb85b6cfb20e36ad1d7e39db35f692aae7872171bbcbcfa4bea0c`（105,693,184 B，与 `build-manifest.json` 的 `kernel_built` 逐字节相同） |
| 固件卷 | `cf4485712c2999c1fb7c1937a5b1f836dd3e9150073fb9b151b581d375195d0f` |
| 证据 | `usblog-20261119-111003`，239,529 B，`complete=true`，supervisor rc=0，actor `lead` |
| 有效性 | `MiniIOMobileFramebuffer: 7 frames in 52495 ms`、客户端 `c…`、`scanout frames=3` ⇒ 有效 |
| 异常 | `panic(` 0、`K60KEXC` 0、`DeviceLost` 0 |

改动确实进了镜像：`grep -abo "plane pitch asked" boot.img` 在偏移 2,914,556 命中，内核 `strings`
也命中同一条格式串。**所以这不是「补丁没进镜像」，而是那段代码没被执行。**

### 5.2 判据

| 编号 | 判据 | 结果 |
|---|---|---|
| **S1** | 无 panic / `K60KEXC` / `DeviceLost` | ✅ |
| **S2** | 恰好一条 `MiniIOSurface: plane pitch asked=… reported=…` | ❌ **0 条** |
| **S3** | 形状变为 `scanout copy single run` | ❌ 仍是 `scanout copy texture untile source=5888 scanout=5760 rows=3200` |
| **S4** | `encode` < 1,000 µs 且 `gpu` < 2,500 µs | ❌ 首帧 `encode=681,731 µs`、`gpu=3,114 µs`；第 2 帧 `encode=588`、`gpu=2,779`；第 3 帧 `encode=46,087`、`gpu=5,176` |
| **S5** | `copy` < 10,000 µs | ❌ 718,072 / 4,856 / 54,924 µs（首帧冷启动，后两帧仍在 5–55 ms 之间） |
| **S6** | `imports == frames` | ✅ 3/3 |
| **S7** | 画面正确性由用户目视 | 未判（本飞没有改变任何画面内容） |

**F 规则命中：F2**（「一条 pitch 行都没有 ⇒ 改动没有生效，先查是谁创建了扫描 surface，
不要再改 pitch」），以及 F3 的实质（仍是 `texture untile` 且没有任何 `reported=5760`）。

**判决：FAIL（S2、S3、S4、S5；F2 命中）。**

### 5.3 为什么没生效（这一飞真正学到的东西）

`MiniIOSurface` 在本飞只打印了一行：

```
MiniIOSurface: 2 big surfaces made, 6262 us each: … memory not kept as somebody else had it 0 times …
```

也就是**只有两块大 surface 走了 mini 驱动**（那两块是预链接缓存的载体，不是合成器的画布）。
我改的那段在 `MiniIOSurface` 的**逐平面**创建路径里
（`patches/xnu/zzzzzzzzzzzzzzzzzzz-pong-hackios-ui-foundation.patch:534-535`）：

```c
p->bytesPerRow = alignUp((uint64_t) ((p->width + pew - 1) / pew) * p->bytesPerElement, MINISURF_ROW_ALIGN);
if (asked != p->bytesPerRow) printf("MiniIOSurface: plane pitch asked=%llu reported=%llu (one pitch only)%c", asked, p->bytesPerRow, 10);
```

一段都没执行 ⇒ 合成器那块 5888 行距的 surface **不是从这条路径创建的**。
`scanout copy texture untile source=5888` 是它存在过的直接证据，所以下一步不是继续改
pitch，而是先回答「这块 surface 是谁建的、5888 是谁给的」。

### 5.4 下一步（按代价排序）

1. **给 surface 创建的全部入口加一行（只加日志，不改行为）**：在 `MiniIOSurface` 里凡
   返回 surface 的地方都打 `MiniIOSurface: created bpr=%u w=%u h=%u caller=%s`，这样
   下一飞能直接看出扫描 surface 是否经由 mini 驱动、走的是哪条路径。
2. **查 `IOSurfaceRootUserClient`**：`k60_skip_iosurface=1` 跳过的是预链接 kext 的构造器，
   mini 驱动之后接管类名；但用户态仍可能通过 `IOSurfaceRoot` 的 user client 直接
   `create_surface` 并自带 `IOSurfacePlaneBytesPerRow`，那条路如果不经过逐平面循环，
   我的改动就永远打不到。要读的是 `MiniIOSurface` 里 `externalMethod` / `createSurface`
   的分发，而不是 `newUserClient`。
3. 若确认 5888 来自一个我们无法改的调用方，就接受现状，把力气转到
   `docs/research/gpu/ZIZHAN-DBUF.md` §6 的零拷贝路线（自有扫描缓冲 + DPU），
   那条路根本不看行距差。

### 5.5 这一飞不能说明的事

- **不能**说明「行距差不可消除」——改动没有执行，等于没测。
- **不能**给帧率结论：屏幕是静止的（7 帧 / 52 s），`copy` 的 718 ms 是冷启动帧。
  按 P-236，本飞的帧率数据不具代表性，只用于 S2/S3 这两条**结构性**判据。


### 5.6 判据指纹

- criteria-sha256: c9a88620babed35d2be43b75b902495f434946269348cbc4b20ce55a83107ff7

这一节独立成一行的原因：`scripts/check-flight-card.py` 的 `DIGEST` 正则要求指纹**单独占一行**
（`^\s*[-*]?\s*criteria-sha256:\s*([0-9a-f]{64})\s*$`），把它夹在句子里会被判成「没有记录指纹」，
即使写了也一样拒绝。指纹由门禁自己的 `criteria_digest()` 算，覆盖范围是 `## 4. 判据` 到
`## 5. 结果登记` 之间，所以本卡「构建前写、判据未改、飞行后只追加 §5」是成立的。
