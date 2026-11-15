# modem 固件载体决策（L3 上机后，2026-11-15）

L1 的段表与搬运计划、L2 的 PAS 握手、L3 的 QRTR 枚举都已经在内核里（`patches/xnu/0620`、
`0621`、`0622`，`pong_modem` 门控默认关闭）。唯一缺的仍然是**镜像字节本身**：
306 MiB 的 30 个 PT_LOAD 段必须先躺进 `0x8bc00000..0x9ee00000` 的 carveout，
PAS/QRTR 才有东西可喂。

2026-11-15 的上机（`cellular-l3-20261115a`）第一次证明了这个缺口的形态，也暴露了
本线判据里的一个顺序错误。这份文档把证据、三种载具的算术和裁决建议钉死，
避免下一轮重新试错。

## 〇、上机证据（2026-11-15 14:18:45）

日志 `E:\k60-work\evidence\usblog-20261115-141845\console.log`（221,401 B，SpringBoard 133 行，
无 panic，backboardd 0 行）。`pong_modem=2` 确实进了命令行（manifest `kernel_args_requested`
`= ['pong_modem=2']`，`payload_args` 末位也是它）。日志 480-483 行：

```
480 | K60MODEM probe begin
481 | K60MODEM qrtr: smem item 480 missing rc=-5
482 | K60MODEM carrier absent: no modem image staged at 0x8bc00000
483 | K60MODEM pas skipped, nothing was handed to the secure monitor
```

`judge-qrtr.sh` 的结果：五个 wanted 号全 0、`service` 行 0、没有 verdict 行。

### 0.1 `smem item 480 missing rc=-5` 的准确含义

- 480 是 **modem 的 GLINK their-queue SMEM item**（`K60ModemLink.c:158` 的 `items[2]`，
  参考 `hakios.mpss.c:2563-2565`），不是 `mpss_region` 的元数据。
- `rc=-5` 是 `K60SmemMissing`（`drivers/PongPower/K60Smem.h:15`：item 不在分区表里），
  不是映射失败、也不是越界。
- 因此这一行的含义是：**AP↔modem 的 SMEM 握手项根本不存在**，也就是 modem 从未在本轮启动过。

### 0.2 由此暴露的顺序错误（重要）

`pong_modem=2` 的当前顺序是「先 QRTR 枚举，再 PAS」——理由是 PAS 的 `AUTH_AND_RESET` 会复位 modem，
把已经在跑的名字服务一起清掉（`K60ModemBoot.c:115-122` 的注释）。这个理由只在**热启动**
（modem 已被 bootloader 或上一次 PAS 拉起）时成立；**冷启动**时 modem 还停在复位态，
SMEM 里不可能有 478/479/480/435 这四项。

所以即使载具立刻到位，冷启动第一次探测**必然**先打 `smem item 480 missing`，然后 PAS 才把
modem 启动起来。要拿到 verdict，必须二选一：

1. **先 PAS 后 QRTR**：载具在位时先 `AUTH_AND_RESET` → `INIT_IMAGE` → `MEM_SETUP`，等 SMP2P
   `slave-kernel` 就绪后再枚举；热启动的「reset 掩盖名字服务」问题可以用「PAS 之后重新握手」绕开，
   因为名字服务会在 modem 重启后重新发布；
2. **两段式探测**：第一次只跑 PAS，记下 modem 已启动；同一轮 boot 内再跑 QRTR（或在
   `pong_modem=3` 里复用同一段代码），把「载具/PAS」与「枚举」分开判。

这条改动属 L4 范围（会动 `K60ModemBoot.c` 的调用顺序），本轮的文档与脚本只把结论记下来，
不改进镜像的源文件。

## 一、已排除

| 路径 | 结论 | 证据 |
| --- | --- | --- |
| `vmd0` / `md0` 引导参数 | **死路**：ADSP 线实测第一次读 FAT 引导扇区就同步外部中止（`esr: 0x96000010`），地址不是 AP 可访问物理地址；同一块板、同一套 `mdevadd` 路径，modem 没有理由不同 | `docs/research/audio/ADSP-MD0.md`；`usblog-20261113-124204` |
| 内核自己读 `modem_a` 分区 | **当前不可行**：`drivers/NativeUfs/RootCommands.h:289` 的 `hostRead4k()` 是 `static`，BSD 侧没有块设备读接口；要走这条路必须给 `NativeUfs` 加 IOKit 方法或导出 C 符号，等于独立工程 | `drivers/NativeUfs/*.h` 无 read 导出（与 ADSP 同一条结论） |
| 固件直接读 `modem_a` 分区 | **当前不可行**：`uefi-mondrian` 里没有 UFS 块设备驱动——`Silicon/Qualcomm` 下 grep 命中 `ufs` 的只有 `AcpiTableUpdateLib`（改 ACPI 表，不是块读），`Binaries/pong/QcomPkg` 是预编译 DXE，没有可用的分区读接口 | `uefi-mondrian` 源码树实测（2026-11-15） |
| 把 306 MiB 整窗嵌进内核 | **算术上不可能**：见 §2.3 | payload 卷 192 MiB |

## 二、三种载具的算术

### 2.1 容器现状（全部实测）

| 量 | 值 | 来源 |
| --- | --- | --- |
| payload 卷容量 | 201,326,592 B（192 MiB） | `board.toml:96` `size_mib = 192` |
| 已用 | 105,520,740 B（`kernel.macho` 105,504,768 + `kernel.macho.adt` 15,972） | `mdir` 实测 |
| 剩余 | 94,994,432 B（90.6 MiB） | 同上 |
| modem 文件字节 | 109,072,529 B（30 个文件，含 `modem.mdt` 与不装载的 b00/b31） | 01 篇设备实测 |
| modem 段字节（真正要拷的） | 109,060,761 B | `K60ModemImage` 计划 |
| modem bss（要清零的） | 211,012,967 B | 同上 |
| carveout（窗口） | 320,864,256 B（306 MiB） | ELF 段表与 DT 两条独立证据 |
| 当前 boot.img | 201,891,840 B | `cellular-l3-20261115a` |

### 2.2 案 A：固件把镜像摆到固定物理地址 `0x8bc00000`（ADSP 同款）

机制与 `docs/research/audio/ADSP-CARRIER.md` §二相同：

1. **构建期**：`board.toml [payload]` 增加 assets 来源（`firmware/modem` 的 30 个文件），
   payload.py 复制进 `EFI/UniXNU/MODEM/`；30 段表由 `scripts/gen-modem-table.py` 另外生成一份
   固件可用的头文件（同一份表，避免两处漂移）。
2. **固件期**：`uefi-mondrian` 新增一个小 DXE，挂载 payload FAT 后按表把每个文件拷到它的 `paddr`
   （`0x8bc00000` 起，全部 4096 对齐），再把 211 MiB 的 bss 段清零；carveout 在
   `MondrianBootMemoryDxe` 里登记为 reserved。base/window 不需要走 ADT——内核侧
   `pong_modem_table.h` 已经把 `K60_MODEM_BASE/WINDOW` 编译成常量，与 DT 一致。
3. **内核期**：零改动。`k60_modem_carrier_ok()` 的 16 字节签名（`modem.b01` 头）会命中，
   `k60_modem_bring_up(NULL, 0, NULL)` 走「已在位」分支，直接进 PAS。

**算术**：`105,520,740 + 109,072,529 = 214,593,269 B` ⇒ 卷至少要 204.7 MiB ⇒
`size_mib = 224`（234,881,024 B，余 20,287,755 B）。boot.img 从 201,891,840 B 涨到
**约 235,446,272 B（+33,554,432 B，+32 MiB）**。

代价：改另一个仓库（`uefi-mondrian`）加一个 DXE；启动时多 320 MiB 的内存写（109 MiB 拷贝 +
211 MiB 清零，DDR 上属毫秒级）；boot.img +32 MiB。

### 2.3 案 B：内核内嵌 blob（Metal 那条路）

Metal 路线是「构建期把目录生成 `.s`、编进内核 `__DATA`、启动时部署」，
`scripts/gen-k60-metal-blob.py` + `0610-k60-metal-plugin-deploy.patch`，当前装 6 个文件
51,278,451 B（上机日志 `K60METAL deploy files=6/6 error=0`）。**它的上限不是机制，是卷容量。**

**算术（这是 Lead 要的那笔账）**：

- 只嵌「要拷的 27 个段文件」109,060,761 B：`105,520,740 + 109,060,761 = 214,581,501 B`
  **> 201,326,592 B**（192 MiB 卷）⇒ **装不下**。要装下得把卷扩到 224 MiB，
  等于付掉案 A 的全部体积代价，还白涨内核 `__DATA`。
- 嵌整个 306 MiB 窗口（`modem.mdt` 的原始布局，最省事）：`105,520,740 + 320,864,256 =`
  `426,384,996 B` ⇒ 卷要 ≥ 407 MiB（`size_mib = 448`）⇒ boot.img ≈ **470 MB**，
  内核 `__DATA` 涨 306 MiB，prelink 与每次 `git apply` 都会变慢。
- 压缩后再嵌：PAS 要求段字节原样到位，内核得在启动时解压 109 MB，`__DATA` 里仍要留解压后的
  306 MiB 目标（那本来就是 carveout，不占内核），但压缩率未知、且多一条解压代码路径。

**结论：不可行。** Metal 能装 51 MB 是因为卷里当时还剩 90.6 MiB；modem 的 104 MiB 刚好越过
这条余量线。案 B 在任何变体下都不比案 A 省体积，只多一份内核膨胀。

### 2.4 案 C：Data seed（initrd 数据种子）

机制：构建期把 modem 文件放进 initrd 数据种子，首启时落到 Data 卷，内核从 `/private/var` 读。

- 种子当前 32 MiB（`docs/research/audio/ADSP-CARRIER.md` §二口径），109 MB 放不下；
  扩到 ≥ 128 MiB 等于 boot.img **+104 MiB**，是案 A 的 3 倍多。
- 时序也不行：`k60_modem_probe_from_handoff()` 现在跑在 Data 卷挂载处理块的早期
  （日志 480 在 `K60DATA root lookup` 485 之前），种子还没落盘；要挪调用点到种子展开之后，
  等于把 PAS 的时序整体后移，风险比案 A 大。
- 数据要经 initrd → 内核内存 → 写入 Data（109 MB 写）→ 再读回（109 MB 读），比案 A 多两趟 IO。

**结论：可行但最贵**（体积 3 倍、多两趟 IO、要改时序），不推荐。

## 三、裁决建议

| 案 | boot.img 增量 | 改动仓库 | 风险 | 结论 |
| --- | --- | --- | --- | --- |
| A 固件 DXE → `0x8bc00000` | +32 MiB | `uefi-mondrian`（DXE）+ `UniXNU-mondrian`（payload assets、表头） | 低（内核零改动） | **推荐** |
| B 内核内嵌 blob | 装不下；扩卷后 +32 MiB，整窗 +268 MiB | 仅本仓库 | 内核膨胀 | 不可行 |
| C Data seed | +104 MiB | 本仓库 + payload 布局 | 时序后移 | 不推荐 |
| D 内核读 `modem_a`（NativeUfs 导出） | 0 | `drivers/NativeUfs`（独立工程） | 中（新 IOKit 接口） | 长期正解，另立任务 |

**需要 Lead 裁决的两件事**：

1. 是否接受 boot.img 从 201.9 MB 涨到约 235 MB（+32 MiB）——案 A 的全部代价；
2. `uefi-mondrian` 侧的 DXE 由谁做（本线不跨仓库改固件；ADSP 线的同类 DXE 也还没落地，
   两条线可以共用一次固件改动）。

在裁决之前**不再出镜像**：没有载具，`pong_modem=2` 的每一次上机都只会重复 480-483 这四行。

## 四、验收标准（案 A 落地后）

1. 固件日志：`modem-image: 30 segments, 109060761 bytes, bss 211012967 at 0x8bc00000`；
2. 内核日志：`K60MODEM carrier present at 0x8bc00000`（现有签名检查，`K60ModemBoot.c:129-135`）；
3. 随后 `K60MODEM plan rows=30 copied=109060761 zeroed=211012967`、`auth_reset ok`、
   `init_image ok segments=27`、`mem_setup ok`；
4. QRTR 按 §0.2 的顺序问题处理后才会有 `verdict`：冷启动第一次仍会 `smem item 480 missing`，
   这是**预期**，不是新故障。

## 五、本轮不做的事

- 不写固件 DXE、不改 `uefi-mondrian`；
- 不改 `K60ModemQrtr.c` / `K60ModemLink.c` / `K60ModemBoot.c`（顺序问题只记录，见 §0.2）；
- 不再出镜像、不申请上机；
- `porting.toml` 的 `completion` 不动。
## 六、待办（L4 及以后）

1. **顺序错误（L4，只记录不改）**：`pong_modem=2` 现在是先 QRTR 后 PAS（`K60ModemBoot.c:115-122`），
   理由是避免 AUTH_AND_RESET 掩盖已在跑的名字服务——这只在热启动成立。**载具到位后的第一次冷启动**
   modem 停在复位态，SMEM 里没有 item 478/479/480/435，`k60_modem_qrtr_probe()` 会先打
   `K60MODEM qrtr: smem item 480 missing rc=-5` 然后 `carrier present` / PAS 流程照走。
   ⇒ 冷启动的第一次探测**必然先出现这一行，属预期**，不按 09 篇的 A–J 用例判；真修走两段式探测
   （先 PAS 等 modem 复位完成，同一轮 boot 内再 QRTR），届时要改 `K60ModemBoot.c` 的调用顺序。
2. 固件 DXE 契约已落盘为 `docs/research/cellular/12-DXE-CONTRACT.md`，等 Lead 裁决 D1/D2/D3。
3. 载具验收按 12 篇 §6 四条，全部过了才排队上机。

