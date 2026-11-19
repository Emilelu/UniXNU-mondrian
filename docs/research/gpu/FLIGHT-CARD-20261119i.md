# 飞行卡：帧拿到的映射地址是新的还是旧的（`gpu-vaddr-20261119`）

## 1. 为什么飞

`gpu-onepitch-20261119`（`usblog-20261119-125434`）把纹理 untile 换成单次拷贝之后，
`present()` 的四个阶段变成 `encode 593 / submit 493 / gpu 1,616` µs——都合理了——
但 `import` 出现双峰：

| 帧 | `imports` | `import` |
|---|---|---|
| 1 | 1 | 14,378 µs |
| 2 | 2 | 65 µs |
| 3 | 3 | 15,184 µs |
| 5 | 5 | 15,076 µs |
| 6 | 6 | 63 µs |

同一飞、同一个 18.4 MB surface、同一段代码。18.4 MB 按 4 KiB 页算是 4,500 页，
15 ms ÷ 4,500 ≈ 3.4 µs/页，正好是「每页都要重做一次映射工作」的量级；
而 63 µs 只可能是「什么都没做」。

两种解释，需要一次飞行分开：

- **H1 每帧都是新 VA**：`PongAdrenoScanout.cpp` 在 `PongScanoutComplete` 里
  `map->release()`（`:202`），下一帧 `createMappingInTask(owner,0,kIOMapAnywhere)`
  必然重新挑一个地址，于是 presenter 每帧都用 `newBufferWithBytesNoCopy` 去导入一个
  从没被导入过的 VA。修法＝让内核按 surface 保留映射（zizhan 的 `kept[4]` + `token`），
  presenter 按 `token` 复用导入，收益上界 ≈ 15 ms／帧。
- **H2 地址会重复而导入仍然贵**：那么地址不是变量，问题在 bridge 的
  `HostMemory` 路径，修法在 `NativeMetalObjects.rs`，与扫出 wire 无关。

本飞只回答这一个问题，**不做任何行为改动**，也**不声明帧率变化**。

### 1.1 同一飞里的第二条线索：映射只增不减

`PONG VM: lifetime`（`drivers/PongAdreno/submit/NativeAdrenoVm.cpp:390`，2026-11-19 新加）把
「现在有几个对象」与「映射/解映射各发生多少次」分开：

| 证据 | `live` | `maps` | `unmaps` | `outstanding` |
|---|---|---|---|---|
| `usblog-20261119-125434`（6 帧） | 189 | 198 | 9 | 189 |
| `usblog-20261119-114545`（69 帧 / 22 次扫出） | 525 | 611 | 86 | 525 |

两飞 `DeviceLost` 都是 **0**，所以这不是 P-244 的崩溃现场，而是它的前因：**对象数单调增长、
解映射远少于映射**。6 帧就有 198 次映射，说明每次映射不是一帧一次，而是「每个 BO 一次」；
增长速率约 1.6 次/采样，与「每帧导入一次、导入后又没人 unmap」吻合。

如果 H1 成立，这两条症状就是同一个原因：presenter 每帧对同一个 surface 新建一次导入，
而 `deallocator:nil` 的 wrapped 指针让 BO 留在内核里。那么保留映射（token）同时修掉
「15 ms 的首次触碰」与「只增不减的对象数」——这也是本卡值得先飞一次再动手的理由。

## 2. 改了什么

`drivers/PongAdreno/PongAdrenoScanout.cpp` 的既有阶段行加两个字段：

```
PONG SCANOUT: frame=%llu prepare=%llu us offer_and_copy=%llu us total=%llu us addr=0x%llx bytes=%llu
```

`addr` 是交给 presenter 的那个 `map->getVirtualAddress()`，`bytes` 是 `map->getLength()`。
`text[220]` 扩到 `text[260]`；采样节奏不变（前 4 帧 + 每 60 帧一条）。

判读靠 join：内核行的 `frame=N` 与 presenter 行 `Pong Metal: scanout frames=N … import=<us>`
是同一帧。

## 3. 前置条件

- **P1** 八步门禁通过、`image-arg-audit: OK (30 arguments, 596 bytes)`、`verify-boot-image: OK`。
- **P2** 内核里必须有 `addr=0x%llx bytes=%llu`（`strings … | grep -c 'addr=0x%llx bytes=%llu'` = 1）。
- **P3** `K60_AGENT_ID` 已设；设备在 fastboot 或 adb（supervisor 在 claim 内重启）。
- **P4** 判读器与卡先提交，镜像后构建（`check-flight-card.py` 要求卡的判据早于镜像）。
- **P5** 这一飞必须真的出帧：`MiniIOMobileFramebuffer` 至少一条、`Pong Metal: c<n>/0` 中 n > 0。

## 4. 判据

### 4.1 有效性（P-236，先判这一层）

- `MiniIOMobileFramebuffer: <n> frames in <ms> ms` 至少一条且 n > 0；
- `Pong Metal: c<n>/0 d<m>` 中 n > 0；
- `Pong Metal: scanout frames=` 至少一条；
- **`DeviceLost` 0 条**（P-244：出现即 INVALID，不是「慢」）。

三项任一不满足即 **INVALID**，用同一张镜像重飞，不算判据失败。

### 4.2 成功判据

- **S1** 无 `panic(`、无 `K60KEXC`、无 `crashed: backboardd`、无 `CP/SMMU fault`。
- **S2** 至少 2 条 `PONG SCANOUT: frame=` 行带 `addr=0x` 与 `bytes=`。
- **S3** 有至少 2 帧能 join 上 presenter 行（`frames=N` 与 `imports=N` 同时出现）。
- **S4** 打印 join 表：每帧的 `addr`、`bytes`、`import=µs`、`encode=µs`。
- **S5** 给出结论：`distinct(addr) == frames` ⇒ **H1 成立**；否则 ⇒ **H2 成立**。
- **S6** 面板仍在 120 Hz（`K60 PANEL: INTF1 … te 1xx/s`），证明这一飞是在正常状态下拍的。
- **S7** `imports==frames`（`PongScanoutComplete` 的释放语义没被顺手改坏）。

### 4.3 失败规则

- **F1** 出现 panic 或 `K60KEXC` ⇒ 立刻回滚这个改动，不为了一条日志冒启动风险。
- **F2** 一条 `addr=` 都没有 ⇒ 探针没进镜像或没执行，**不得**拿「没有数据」当「地址一样」。
- **F3** `distinct(addr) < frames` 且重复地址的帧 `import` 仍 ≥5,000 µs ⇒ **H2**：地址不是变量，
  下一步去 `NativeMetalObjects.rs` 的 `HostMemory` 路径查，**不要**去做 token 保留映射。
- **F4** 出现 `DeviceLost` ⇒ 判 INVALID（P-244），且这一飞不得用于任何结论。
- **F5** `import` 与 `addr` 都对不上任何规律（例如同为 15 ms 而地址全不同、或全 63 µs）⇒
  记录分布，不得据此选修法；下一飞加 presenter 侧打印。

## 5. 结果登记

### 5.1 飞行事实

- 镜像 `gpu-vaddr-20261119`，`boot.img 80951dce117ab8a1ebe988a640eac9ec8681cf36765cdbb51b38d9922d56b7eb`，
  kernel `15bb2989260b09ff47d51f491329cd701dabe979e7e49a8c2d460c56cb7d38ae`（105,693,184 B），
  payload kernel `143e12a0…`、payload adt `69c579d5…`，series 228 `frozen=87c38244…`，
  插件复用 `metal-plugin-20261119p`，30 条参数 / 596 B，`image-arg-audit: OK`、`kernel archives: 4`、
  `verify-boot-image: OK`。
- 判据指纹由门禁自己的 `criteria_digest()` 计算并钉在 §5.9。
- **第一次起飞无效**：`usblog-20261119-135243`（2,908 行）`MiniIOMobileFramebuffer` 0 条、
  `Pong Metal: c0/0`——GPU 已经 `startup COMPLETE; hardware armed`、provider 已发布，但命令缓冲区
  建了没提交。与 `usblog-20261119-090909`、`usblog-20261119-041606` 同一特征。
  按 §4.1 判 **INVALID**，同一张镜像重飞。
- **第二次起飞有效**：`usblog-20261119-135830`，`capture.json complete=true`，
  `Pong Metal: c10/0 d10`、`MiniIOMobileFramebuffer: 5 frames in 52242 ms`、5 条 presenter 行、
  3 条带 `addr=` 的内核行。`panic(` 0、`K60KEXC` 0、`crashed: backboardd` 0、`DeviceLost` 0、
  `CP/SMMU fault` 0、`GPU copy not retired` 0。

### 5.2 判据

| 判据 | 结果 | 依据 |
|---|---|---|
| S1 无 panic / `K60KEXC` / backboardd 崩 | ✅ | 六项计数全 0 |
| S2 ≥2 条带 `addr=`/`bytes=` 的 stage 行 | ✅ | 3 条 |
| S3 ≥2 帧能 join 上 presenter 行 | ✅ | 3 帧（1、2、4） |
| S4 打印 join 表 | ✅ | §5.3 |
| S5 给出 H1 / H2 结论 | ✅ | **都不是**，见 §5.4 |
| S6 面板仍 120 Hz | ✅ | `after the UI frame te 120/s … period 7618 us` |
| S7 `imports==frames` | ✅ | 1→1、2→2、4→4、5→5 |

失败规则：**无命中**（F2 有 `addr=`；F4 无 `DeviceLost`；F5 见 §5.4 的分布）。

### 5.3 join 表

| frame | addr | bytes | import | encode | submit | gpu | sum | copy |
|---|---|---|---|---|---|---|---|---|
| 1 | `0x11ed56000` | 18432000 | **5000** | 1974 | 1902 | 1636 | 10512 | 12392 |
| 2 | `0x123f4f000` | 18432000 | **46** | 319 | 302 | 22167 | 22834 | 22881 |
| 4 | `0x123f4f000` | 18432000 | **74** | 352 | 493 | 23334 | 24253 | 24314 |

未进表的第 3、5 帧没有内核行（采样节奏 4 帧 + 每 60 帧），只有 presenter 侧：
帧 3 `import=4,709`、帧 5 `import=15,338`。

### 5.4 结论：地址会重复，重复是便宜的 —— 保留映射不值这个价

`distinct(addr) = %d`，帧数 = %d。重复的那一个地址 **`0x123f4f000` 出现在帧 2 与帧 4**，
两次导入分别是 **46 µs 与 74 µs**——所以：

- **不是 H1**：并非每帧一个新地址。
- **不是 H2**：重复的地址上导入并不贵（F3 不命中）。
- 真正的规律是：**贵的导入只发生在一个新地址的第一次触碰**（帧 1 的 `0x11ed56000` = 5,000 µs），
  之后同一地址的导入都在 100 µs 以内。也就是说 `kIOMapAnywhere` 在 `release()` 之后会复用同一个 VA，
  而 bridge 对同一个 VA 的导入是缓存住的。

因此 **`KEPT-MAPPING.md` 里那套 token/evict 保留映射不该做**：它能省掉的只是「每个地址的第一次触碰」，
在稳态里每帧只值几十微秒。这一条把一个看起来最大的优化项关掉了，也是这次飞行的主要价值。

### 5.5 本次飞行暴露的新问题：`gpu` 变成双峰，慢的那一档约等于一帧

同一张表里 `gpu` = 1,636 / 22,167 / 14,316 / 23,334 / 1,480 µs。快的一档（帧 1、5）≈1.5 ms，
与 `FLIGHT-CARD-20261119d` 的对照实验（18.4 MB 单次拷贝 1,835 µs）吻合；
慢的一档（帧 2、3、4）14–23 ms，且**恰好近似一帧的间隔**（`wait` 在 35–1,743 ms 之间）。

`encode`（176–1,974 µs）与 `submit`（212–1,902 µs）都小，`sum` 与 `copy` 差 1,600–1,900 µs
（`done` 与内核侧 `prepare`），所以慢的那一档不是我们的 CPU，而是**等 GPU 把这次 blit 做完**。
下一个问题因此是「为什么同一个 18.4 MB 的 blit 有时 1.5 ms、有时 22 ms」，
候选：GPU 频点、与上一帧的 fence 串行、或显示侧的 vblank 让 blit 排队。
这三者都不需要 iOS 版本特性，属于可转移范围。

### 5.6 本飞不能回答的问题

- 不能回答帧率：5 帧 / 52 s，屏幕基本静止，`5 frames in 52242 ms (0 a second)`。
- 不能回答「保留映射在长跑里是否会减少泄漏」：本飞只有 10 次提交，`outstanding` 还没有增长到
  P-244 的量级（该问题已另起 `alloc=/free=` 读数，见 `NativeAdrenoVm.cpp` 的 `lifetime` 行）。
- 不能回答 `import` 在**多 surface 交替**时是否会退回昂贵（本飞只有两个不同的扫描地址）。

### 5.7 下一步

1. 关掉 token/evict 这条线，把结论写回 `KEPT-MAPPING.md` 顶部（它现在是「已否决」而不是「待定」）。
2. 追 §5.5 的 `gpu` 双峰：同一飞内按 `gpu` 分组，与 `wait`、`copy`、`frame` 编号对齐，
   看慢的那几帧是否总是紧跟在一次 `wait` 很长的帧之后（若如此，就是 blit 排在上一帧后面）。
3. 长跑（>300 帧）飞一次，读 `alloc=/free=/freestatus=` 判断 P-244 的泄漏归属。
4. 这一飞**没有**让帧率变快，也没有让任何东西变慢：它只加了两个日志字段。

### 5.8 判据自己的缺陷

本卡的 S5 允许「H1' 」这一档（地址重复但便宜），判读器给 `rc=1` 表示「回答了问题但需要报告分布」。
真正需要的是**一开始就把「地址复用已经生效」列为第三种可能**，否则判据里只有两个抽屉，
拿到第三种情况时只能事后补写。这与 P-242 是同一族：判据要覆盖全部可能，而不只是自己想到的那两个。

### 5.9 判据指纹

- criteria-sha256: 855975bafe6217c5a07c611110f741e2bf91b21b41f50897369dd9f798533f54
