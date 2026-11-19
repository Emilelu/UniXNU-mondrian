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

（飞行后写在这里；`criteria-sha256` 在第一次写入时钉入，且必须单独占一行。）
