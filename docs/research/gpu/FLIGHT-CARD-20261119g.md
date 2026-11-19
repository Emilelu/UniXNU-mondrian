# 飞行卡：谁建了那块 5888 行距的画布（`gpu-surface-20261119`）

## 1. 为什么飞

`gpu-pitch-20261119` 的判据是「把 surface 的行距统一成 5760，纹理 untile 就会变成单次拷贝」。
改动确实进了镜像（`grep -abo "plane pitch asked" boot.img` 在偏移 2,914,556 命中，
`build-manifest.json` 的 `kernel_built` 与打包内核逐字节相同），但整飞**只出现一行**
`MiniIOSurface` 输出（`2 big surfaces made`），而扫描行仍是
`scanout copy texture untile source=5888 scanout=5760 rows=3200`。

⇒ 合成器那块 5888 行距的画布**不是**经由我改的逐平面路径创建的。在继续改行距之前，
必须先回答「这块 surface 是谁建的、`bpr=5888` 是谁给的」。本飞只加日志，不改任何行为。

## 2. 改了什么

`patches/xnu/zzzzzzzzzzzzzzzzzzz-pong-hackios-ui-foundation.patch` 的 `surfaceCreate()` 在
surface 注册进表之后加一行（**每个 surface 一行，不是采样探针**，所以不需要早采样逃生口）：

```c
printf("MiniIOSurface: surface made sid=%u %ux%u bpr=%u planes=%u alloc=%llu asked=%llu%c",
    (unsigned) sid, width, height, (unsigned) bpr, (unsigned) s->info.planeCount,
    (unsigned long long) alloc, (unsigned long long) dictNumber(props, "IOSurfacePlaneBytesPerRow", 0), 10);
```

`asked=` 是客户端在字典里要求的平面行距，`bpr=` 是驱动最终采用的值。两者不同就说明行距差
是在这一层产生的；如果连 `bpr=5888` 都不出现，就说明这块画布根本不经过这里。

## 3. 前置条件

- **P1** 八步门禁通过（`scripts/eight-step-gate.py --flash`）。
- **P2** `image-arg-audit: OK`，参数仍是 30 条 / 596 字节。
- **P3** 内核 `strings` 里必须有 `surface made sid=%u %ux%u bpr=%u planes=%u alloc=%llu asked=%llu`，
  否则不要飞。
- **P4** `verify-boot-image: OK`。
- **P5** `K60_AGENT_ID` 已设置（先到先得，但必须署名）。
- **P6** 设备在 fastboot。

## 4. 判据

### 4.1 有效性（先判这一层，P-236）

- `MiniIOMobileFramebuffer: N frames in …` 至少一条且 N > 0；
- 客户端 `Pong Metal: c<n>/0 d<n>` 至少一条且 n > 0；
- `scanout frames=` 至少一行。

三条任一不成立 ⇒ **INVALID**，不是判据失败。

### 4.2 成功判据

- **S1** 无 `panic(`、无 `K60KEXC`、无 `DeviceLost`、无 `crashed: backboardd`。
- **S2** `MiniIOSurface: surface made` 至少 3 行（预链接那两块 + 至少一块合成器画布）。
- **S3** 存在一行 `bpr=5888`，或者能证明扫描那块画布来自别处（`surface made` 全部 `bpr=5760`
  且一行 5888 也没有）。
- **S4** 若某行 `asked ≠ bpr`，则同行数值被记录（这正是行距差在这一层产生的证据）。
- **S5** 形状行仍出现（`scanout copy … source=… scanout=… rows=…`），本飞不改它。
- **S6** `panel after UI: 1xx Hz` 仍在 ≥110 Hz。
- **S7** `imports == frames` 在每一行 `scanout frames=` 上成立。

### 4.3 失败规则

- **F1** 任何 panic / `K60KEXC` ⇒ 立即回滚这行日志，不得继续。
- **F2** `surface made` 一行都没有 ⇒ 探针没有进镜像或没有执行，本飞作废。
- **F3** 全部 `bpr=5760` 且没有一行 5888 ⇒ 画布不经此处创建，**不要再改 pitch**，
  转去读 `MiniIOMobileFramebuffer` 的 `set_id_mode` / `set_pixels` 分发（
  `0600-k60-display-composition.patch:475-491` 校验客户端给的 `info.bytesPerRow`），
  或者直接转 `docs/research/gpu/ZIZHAN-DBUF.md` §6 的零拷贝路线。
- **F4** 零帧 ⇒ INVALID（重飞，不得当失败）。
- **F5** 出现 `GPU copy not retired` 或映射被保留 ⇒ 记录条数，并把它当作 P-244 的又一次复现。

## 5. 结果登记

### 5.1 这一飞的事实

| 项 | 值 |
|---|---|
| 镜像 | `gpu-surface-20261119`，`boot.img 8e2456a8bcbe9f09fe27fa68123affdd8f63b1193cbbd6f3543b125f056f7679` |
| 内核 | `4ef869c8949a92c2d2d79fd95533cbaadd9eae4dd1f5d0d7458268b05e9036a4`（105,693,184 B） |
| 证据 | `usblog-20261119-114545`，supervisor rc=0，未因 panic/复位中断 |
| 有效性 | `compositor=69 frames · client_commits=288 · scanout_lines=22` ⇒ 有效，且有动画 |
| 面板 | `K60 PANEL: INTF1 after the UI frame te 120/s frames 120/s over 500 ms (frames 281->341) … period 7447 us` |
| 异常 | `panic(` 0、`K60KEXC` 0、`DeviceLost` 0、`crashed: backboardd` 0 |

### 5.2 判据

| 编号 | 判据 | 结果 |
|---|---|---|
| **S1** | 无 panic / `K60KEXC` / `DeviceLost` / backboardd 崩 | ✅ |
| **S2** | `surface made` ≥ 3 行 | ✅ **19 行** |
| **S3** | 存在 `bpr=5888`，或证明画布来自别处 | ✅ `sid=15 1440x3200 bpr=5888 planes=0 alloc=18841600` |
| **S4** | `asked ≠ bpr` 时数值被记录 | ✅ 两条（见 5.3） |
| **S5** | 形状行仍出现 | ✅ `texture untile (source 5888 scanout 5760)` |
| **S6** | 面板 ≥ 110 Hz | ✅ 120 Hz（`period 7447 us`） |
| **S7** | `imports == frames` | ✅ |

**判决：PASS。** 无 F 规则命中。（第一次判读报 S6 FAIL 是判读器的正则写错：真实行是
`K60 PANEL: INTF1 after the UI frame te 120/s`，而判读器找的是 `panel after UI: N Hz`。
两处都改了，重判 PASS。这是 P-242 的又一次实例：判据存在不等于判据覆盖真实格式。）

### 5.3 答案：5888 来自 `IOSurfaceBytesPerRow`，而且是 `planes=0` 那条路

19 块 surface 的完整清单（`sid` 顺序即创建顺序）：

```
sid=1..4   128x128  bpr=196   planes=2 alloc=28672
sid=5      128x128  bpr=512   planes=0 alloc=69632
sid=6      256x1    bpr=2048  planes=0 alloc=20480
sid=7      4096x1   bpr=16384 planes=0 alloc=135168
sid=8..11  2x30     bpr=64    planes=0 alloc=4096
sid=12     3584x3584 bpr=3584 planes=2 alloc=19267584
sid=13     72x52    bpr=160   planes=0 alloc=12288
sid=14     900x150  bpr=1824  planes=0 alloc=274432
sid=15     1440x3200 bpr=5888 planes=0 alloc=18841600   <-- 扫描的画布
sid=16     1440x3200 bpr=5760 planes=0 alloc=18432000   <-- 我们自己的两块
sid=17     1440x3200 bpr=5760 planes=0 alloc=18432000
sid=18     432x960  bpr=1728  planes=0 alloc=1658880
sid=19     24x132   bpr=128   planes=0 alloc=73728
```

两条 `plane pitch asked≠reported` 是 `asked=1440 reported=1472` 与 `asked=432 reported=448`
—— 也就是**我上一飞改的那段确实执行了**，只是它管的是 `planes≥1` 的 surface（sid=1–4、
sid=12），而扫描画布 `sid=15` 是 `planes=0`，走的是另一条分支：

```c
bpr = dictNumber(props, "IOSurfaceBytesPerRow", 0);   /* <-- 5888 从这里进来，客户端给的 */
if (bpr == 0) {
    bpr = planeCount ? s->planes[0].bytesPerRow
        : alignUp((uint64_t) ((width + ew - 1) / ew) * bpe, MINISURF_ROW_ALIGN);
}
```

⇒ **合成器显式要求 `IOSurfaceBytesPerRow = 5888`（1472×4，32 像素对齐）**，我们在这一层照单全收。
`sid=16/17` 是 `1440x3200 bpr=5760`，说明**我们自己**创建的画布本来就是 5760 —— 行距差只在
客户端要走的那一块上。

### 5.4 因此下一飞改哪里（一次性、可回滚）

把 `IOSurfaceBytesPerRow` 也纳入「只报一个行距」的策略：忽略请求值，一律
`alignUp(width*bpe, MINISURF_ROW_ALIGN)`（1440×4=5760 本来就是 64 的倍数），请求值不同时打印
`MiniIOSurface: row bytes asked=%llu reported=%llu (one pitch only)`。

风险与判据：客户端的正确性依赖「创建者报什么它用什么」，所以本飞必须**同时**看
(a) 形状是否变成 `single run`、(b) `encode` 是否从 46 ms 掉到 1 ms 量级、
(c) **画面是否斜切**——(c) 只能由用户目视，或由下一张卡描述的像素校验来判，
不得由「帧还在出」代替。

### 5.5 不能说明的事

- 不能说明「消除行距差一定安全」——客户端是否尊重我们回报的行距，本飞没有验证。
- 不能说明帧率有任何改善：本飞只加了一行日志，`copy` 仍是 5–55 ms 量级。

### 5.6 判据指纹

- criteria-sha256: 2019c891d9dd0fed95c752bd1a1b7430296b9dfbdedabb180adaea8ca86724de

判据一节（`## 4. 判据` 到 `## 5. 结果登记`）在本镜像构建之前写定，飞行后只追加本节；
指纹由 `scripts/check-flight-card.py` 自己的 `criteria_digest()` 计算。
