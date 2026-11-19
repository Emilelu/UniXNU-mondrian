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

（飞行后写在这里；`criteria-sha256` 在第一次写入时钉入，且必须单独占一行。）
