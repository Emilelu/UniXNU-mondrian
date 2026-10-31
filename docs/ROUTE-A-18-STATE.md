# route-a-18 状态（2026-10-31 round 5）

## 本轮达成：darwin24 内核 → payload → 启动镜像，全程 Linux

```
xnu-11417.140.69 + pong darwin24 聚合补丁
  ↓ build-darwin24-linux.sh（九步，Linux 工具链）
mach.development.pong.unstripped.noctf   20,847,560 B   sha256 57b01c64…
  ↓ unixnu build payload（我们自己的 K60 板级管线）
payload.img                             201,326,592 B   sha256 28a73763…
  ADT 1440×3200（我们的）  dfea52ad…
  ↓ unixnu bootimg
boot-darwin24.img                       201,887,744 B
  镜像内 ramdisk sha256 = 28a73763…  与 payload 字节一致 ✓
  镜像结构校验：magic / hdr_ver 4 / gzip 成员 / UEFI FD / dtb 全部 OK
```

产物：`D:\Android\k60-ios\boot-darwin24.img`

## 关键架构决策

**不采用 pong 的整套构建系统**。核查后发现：
- pong 的 `build-xnu-ipados18.sh` 无 Linux 分支、CI 全是 macos-15-intel、`build-ipados18.py`
  依赖 `xcrun`；
- 但它的**内核可以**在 Linux 上构建（九步已解决）；
- 而 ADT / prelink / payload / 打包，我们自己的 K60 管线已经工作（16.6.1 全程验证过，
  且带 1440×3200 面板契约）。

所以 route-a-18 = **pong 的内核 + 我们的板级管线**。本轮已验证这条线路的每一步。

## profile 整合

- `profiles/os/ipados-18.7.10-22H374/` 已装进框架（format 2 → format 1 转换）
- `[os]`/`[ipsw]` 取 pong 的 darwin24 身份；`[adt]` 保留我们的 K60 身份（iPad7,1 / J120AP / 1440×3200）
- `unixnu status` rc=0，profile 正确解析
- `unixnu defconfig` + `build payload` 全部 rc=0

## 已知待修（诚实登记）

1. **trust cache 仍是 20G81 的**（`344ae644…`）。darwin24 用户态二进制需要 22H374 的
   trust cache。内核阶段影响小，用户态阶段必须换。22H374 的两个 trustcache 已下载
   在 `/tmp/k60build/out/ipsw/22H374/`，但格式是 `.dmg.trustcache`，需要转成 payload
   期望的 bundle 格式。
2. **prelink 参数仍是 20G81 的**（kernelcache_sha256、roots 列表、slide）。首次 boot 若
   停在 kext 加载，这就是原因。
3. **UEFI 仍是 DarwinBoot22**。darwin24 需要 DarwinBoot24（pong 有 `drivers/DarwinBoot24/`）。
4. `verify-k60-boot-img.sh` 硬编码 16.6.1 的 payload 路径，会误报 FAIL（本轮已用
   `verify-darwin24-img.sh` 直接核对字节确认正确）。修复方式：给脚本加 payload 参数。

## 下一步（按依赖顺序）

1. 上机测试 `boot-darwin24.img`——看 darwin24 内核能否起来（这是最重要的未知数）
2. 若停在 kext/OS 加载：换 22H374 trust cache + 解析 22H374 kernelcache 的段表更新 prelink
3. 若 UEFI 层就挂：移植 DarwinBoot24
4. 之后才是面板参数、UFS、用户态

## fork 审计（本轮完成）

- mzyxsl/UniXNU-mondrian `76552b88`（ahead=2）
- XTOM0706/UniXNU-mondrian main `9d1a14f8`（ahead=6）；`a5-timeout` `fef75eaa`
  - **`9d1a14f` adt: 1440×3200 canvas + display-scale 3** ← 与我们的 K60 值一致，可对照
  - `a351ef1` board: target iPadOS 17.7.11（他试过 17 又回退了）
- wohusaixing/UniXNU-mondrian `092a61d8`（ahead=2）
  - **16 GiB 机型的低 2 GiB 连续 DRAM 窗口**：`reg = <0x0 0x80000000 0x0 0x80000000>`，
    说明 16 GiB K60 的 DRAM 不连续（低 2 GiB 在 0x80000000，其余在 0x800000000+）。
    我们的机器是 12 GiB，暂不适用，但记录了这条硬件事实。
- 本轮无需要 cherry-pick 的代码；三条都是数据/参考，已在上面记录。
