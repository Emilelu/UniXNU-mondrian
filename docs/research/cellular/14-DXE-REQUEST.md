# 14 · 固件侧 modem 载具需求（DarwinBoot 库调用版）

> 收件人：固件线（uefi-mondrian）。
> 本轮只写需求，不改 `uefi-mondrian`、不出镜像、不上机。
> 已冻结的固件输入、输出与账目见 `12-DXE-CONTRACT.md`；验收断言见 `13-FIRMWARE-ACCEPTANCE.md`。

## 0. 一句话

在 `DarwinBootPkg` 的 boot 路径里新增一个库 `ImageCarrierLib`，对 `EFI/UniXNU/MODEM/` 下的
27 个文件做「按表拷贝 + 逐段清 bss + 空洞不动」，把结果写进已保留的 `mpss_region`
（`0x8BC00000`，长 `0x13200000`），并在自留的 ADT 副本里发布 16 字节属性 `K60ModemImage`。
不做独立 DXE（理由见 `12-DXE-CONTRACT.md` §3.3）。

本轮不要求固件实现 ADSP 载具：第一版只做 modem，`K60AdspImage` 这个名字与 16 B 布局保留但不发布。
ADSP 已改走内核内嵌 blob（`k60_adsp_blob`，23,506,184 B；0620 补丁 + `build-strict --adsp-blob`），
所以 DXE 只服务 modem——见 §4.1 的裁决。

## 1. 属性契约

### 1.1 名字、位置与类型

| 项 | 取值 | 依据 |
| --- | --- | --- |
| 属性名 | `K60ModemImage` | 12 号契约 §3.1；与 `RAMDisk`/`TrustCache` 同风格 |
| 所在节点 | 既有的 `/chosen/memory-map` | `DarwinBoot.c:279-282` 判定 `Depth==2 && ParentPath==1 && NameLength==11`；不新建节点、不新建保留区 |
| 类型 | OSData（ADT 属性，无类型标签） | `scripts/pong_adt_contract.py:13-47` 的解析格式 |
| 长度 | **恰好 16 字节** | `pong_adt_contract.py:83` 已按 16 B 检查；`DarwinBoot.c:251`/`:268` 的 RAMDisk/TrustCache 同样是 16 B |
| 字节序 | 小端 | `DarwinBoot.c:809-815` 用 `WriteUnaligned64`；参考实现 `NativeRamBlock.cpp:210-213` 两次 `memcpy` |
| 内存描述符 | **不需要新增** | `MemoryMapLib.c:31` 已有 `{"mpss_region", 0x8BC00000, 0x13200000, AddMem, MEM_RES, UNCACHEABLE, Reserv, ...}` |

### 1.2 二进制布局

```text
偏移 0  : u64 base    = 0x000000008BC00000
偏移 8  : u64 span    = 0x0000000013200000
总长    : 16 字节
```

- `base` 必须等于段表第一行的 `paddr`（0x8BC00000），`span` 必须等于 carveout 长度
  （0x13200000 = 320,864,256）。两者都是 2 MiB 对齐，比 4 KiB 要求更强。
- 全零 = **未发布**：构建期占位就是 16 个零字节，运行时未写成功时门禁按未发布处理。
- 这个属性是**声明**，不是加载证明：内核当前不读它（`K60ModemBoot.c:124` 直接用常量映射 4 KiB
  头页 + 16 B 签名自检）。发布它的意义是让「固件到底把镜像放到哪」有可机械验收的记录。

### 1.3 已裁：长度恒为 16 B（Lead，2026-11-15 23:27）

Lead 裁定：**16 B 就是对的**，按冻结契约写。必须显式记住一句：

> **span ≠ copy length**：`span` 是窗口大小（0x13200000 = 320,864,256），拷贝量由 30 行段表决定
> （109,060,761）。消费者一律用段表算拷贝量，属性只给窗口。

任何把 `span` 当「镜像长度/拷贝量」用的写法都是自造字段表（P-169 形状）。要表达拷贝量必须新开字段
并重新裁决，不能挤进现有 16 B；`pong_adt_contract.py:83`、13 号 A5 与 `DarwinBoot.c:251` 的兄弟属性
都依赖这个长度。

### 1.4 构建期占位

`scripts/make-pong-adt.py:232` 已经在 `/chosen/memory-map` 写 16 B 零占位（与 PackedRAMDisk 同处）。
构建期契约（12 号 §3.7）：

1. `K60ModemImage` 若存在，长度必须是 16 且值全零或精确等于 `(0x8bc00000, 0x13200000)`；
2. payload 里有 `EFI/UniXNU/MODEM/` ⇒ 属性必须存在；没有 ⇒ 必须不存在；
3. 既有的 `RAMDisk`/`PackedRAMDisk` 规则不动。

### 1.5 与 13 号断言的对应

| 字段 | 断言编号 | 怎么读出来 |
| --- | --- | --- |
| 属性存在、长度 16、值合法 | A5 | `parse_adt` 解 `kernel.macho.adt` 的 `/chosen/memory-map` |
| 固件源码真的读写它 | B3 | `grep -c K60ModemImage DarwinBoot.c` ≥ 2 |
| 运行时真的发布了 | C3 | 串口日志 `range 0x8bc00000..0x9ee00000 published` 恰好 1 行 |
| 表与生成器同源 | B5 | 固件表文件与 `gen-modem-table.py --firmware-header` 输出 diff 为空 |
| 没有整窗清零 | B6 | 源码里 `memset/SetMem/ZeroMem/AllocateZeroPool` 后不得出现 `0x13200000` |

## 2. 载入时机

### 2.1 硬边界

| 阶段 | `DarwinBoot.c` 行 | 说明 |
| --- | --- | --- |
| 读 ADT、解析 | `:709-711`、`:720-721` | 此时才有可写的树副本（`Tree`），也才知道 `WindowSize` |
| 打开 payload 卷 | `:693-695` | 之后 `Root` 一直有效到 `:821` 关闭 |
| 分配主窗口 | `:749-751` | `AllocateWindow` 只管内核/信任缓存/ramdisk，与 carveout 无关 |
| 写最终树 | `:801` `CopyMem(TreeAddress, Tree, TreeSize)` | 属性必须在**这次拷贝之后**写，否则改动丢失 |
| ExitBootServices | `:884` | 之后不能再调 boot services，文件读不了 |
| 进内核 | `:891` | 最后一个可能点 |

### 2.2 建议的两个调用点

1. **拷贝**：`:721`（ADT 解析完成）之后、`:749`（主窗口分配）之前调用
   `ImageCarrierLoad(Root, ModemSpec, &Base, &Bytes)`。这一步不做任何分配，只写固定物理地址
   `0x8BC00000`，不需要等待窗口分配。
2. **发布属性**：`:801` 之后、`:802-805`（audio DMA/RAMDisk 的 `WriteUnaligned64`）同一段里，
   对 `TreeAddress` 里已最终的树写 `K60ModemImage`。这与现有 RAMDisk 写法完全同构。

### 2.3 为什么不能再晚

内核侧最早的消费者不是 modem 探针，而是 ADSP 的 owner publish：`0619-k60-adsp-glink-handoff.patch`
在 `IOKitBSDInit.cpp` 的 `IOService::publishResource("IOBSD")` 之前就调 `k60_adsp_handoff_publish()`
（hunk `@@ -109,10 +109,18 @@`），把 PAS1 lease 发布出去。那之后内核只认「carveout 里已经有什么」。
镜像如果晚于内核第一条读 carveout 的代码载入，读到的就是上一轮的残料——这正是 P-197 的形态。

因此固件侧唯一安全的窗口是**进内核之前**，`ExitBootServices`（`:884`）是绝对截止线。

### 2.4 三行必打日志（Lead D3 硬要求）

三条都以 `modem-image: ` 开头，**level 1 默认可见**，不得挂在 `DEBUG(` 里，也不得合并/改名：

```text
modem-image: chosen dtb at 0x<物理地址>
modem-image: window 0x8bc00000..0x9ee00000
modem-image: abl staging ends at 0x<b8000000>
```

数据来源：

- chosen DTB 物理地址 = `Args->DeviceTree`（`DarwinBoot.c:798-799` 由
  `Kernel.Base + TreeAddress - Address` 算出），打印时用 `%lx` 原样输出；
- window 字面量 = `0x8bc00000..0x9ee00000`（与内核 `K60_MODEM_BASE`/`K60_MODEM_WINDOW` 同源）；
- ABL staging 结束 = `0xA8300000 + 0x0FD00000 = 0xB8000000`（`MemoryMapLib.c:51` 的
  `{"ABL Staging", 0xA8300000, 0x0FD00000, ...}`）。若固件侧该描述符改了，这一行随之变，
  但仍必须是「实际值」，不是抄常量。

这三行的作用是**让上机判据独立于内核**：镜像若几乎填满 staging 余量（12 号 §1.5 估算余 4.84 MiB），
DTB 地址与 staging 结束值一对比就能看出有没有踩到。

### 2.5 已裁：输入形态与容器（Lead，2026-11-15 23:27）

- modem 维持 **27 个平铺文件 + 30 行段表**，批准；不改成容器。
- `K60A` 容器记录语法（12 B 头 + 24 B 记录 + NUL 名）**只留给 ADSP 第二版**，与 modem 载具无关；
  modem 的记录里没有 `paddr` 可放（30 段是 30 个不同物理地址），改容器等于重开格式裁决。

## 3. 失败语义

### 3.1 四种情况，各打哪行、内核怎么判

| 情况 | 固件行为与日志 | 内核看到什么 | 判据 |
| --- | --- | --- | --- |
| 1. 镜像缺失（payload 里没有 `MODEM/`） | 打印 `modem-image: no carrier in payload, skipped`，**不拒绝启动** | `K60MODEM carrier absent: no modem image staged at 0x8bc00000` + `K60MODEM pas skipped, nothing was handed to the secure monitor`，不发任何 SMC | 这是「载具未实现」的唯一合法形态 |
| 2. 长度/内容不符（缺文件、大小≠表、表不自洽、行越界、未 4 KiB 对齐） | `EFI_COMPROMISED_DATA` + `modem-image: modem.bNN missing` / `modem.bNN size X, table says Y` / `row N outside ...` / `row N paddr 0x... unaligned` / `table inconsistent`，走 `Fail:`（`DarwinBoot.c:898-913`）画屏 `BOOT FAILED ... MODEM IMAGE`，回菜单 | 根本进不到内核 | 13 号 A3/A4/B5 在**构建期**就该先红，不该拖到上机 |
| 3. 地址冲突（属性非零、段重叠） | `modem-image: range already published`，同样 `EFI_COMPROMISED_DATA` 拒绝启动（照 `DarwinBoot.c:726-727` 的 RAMDisk 先例） | 进不到内核 | 说明上一轮没清干净或第二次加载；必须拒绝而不是覆盖 |
| 4. 属性没发布（拷贝成功但没写属性） | 仍打 `modem-image: 30 segments, copied 109060761, zeroed 211012967, gaps 790528 untouched`，但缺 `range ... published` | `K60MODEM carrier present at 0x8bc00000` 正常，PAS 序列照跑（内核不读属性） | C3 红：固件交付不完整，但**不会**让内核误判成 QRTR/PAS 失败 |

### 3.2 内核怎么区分「载具未实现」与「QRTR/GLINK 失败」

唯一判据是 4 KiB 头页里的 16 字节签名（`K60ModemBoot.c:124`）：

- 签名命中（`0e c0 00 58 / 00 c0 00 58 ×3`，即 `modem.b01` 前 16 B）⇒ 载具在位。后续任何失败都
  属于 QRTR/GLINK（`K60MODEM qrtr: glink fifo not fresh ...`、`modem not ready`、`verdict no reply`）
  或 PAS（`K60MODEM auth_reset failed rc=%d`、`init_image failed seg=...`、`mem_setup failed rc=%d`），
  日志前缀会明确写出是哪一层。
- 签名不命中 ⇒ 只有 `carrier absent` + `pas skipped` 两行，**一行 SMC 都没有**。这是「载具未实现」，
  而不是「modem 坏了」；不需要 ADB，不需要二次上机就能判。

这也是为什么第一版固件即使只做拷贝、不做 PAS，也能产生可判读的日志：签名本身是零成本的载体存在性证明。

## 4. 与 ADSP 的关系（DXE 只服务 modem）

**已裁（Lead，2026-11-15 23:27）：ADSP 不走这个 DXE。** 它的载具已经合进 main——内核内嵌只读 blob
（容器 23,506,184 B，符号 `k60_adsp_blob`，0620 补丁 + `build-strict --adsp-blob`，
见 `ADSP-CARRIER.md` 与 `CARRIER-BLOB-PLAN.md`）。因此：

- 本轮的 `ImageCarrierLib` **只服务 modem**；`K60AdspImage` 只是保留字，不发布；
- 12 号 §5.3 的两件事（`0x86300000` 缺 descriptor、段 10 非对齐）**不再是 DXE 的前置条件**，
  它们只属于「ADSP 若走固件装载」这条**未采纳**的路线；
- 下面 4.1–4.3 是「若将来 ADSP 也要走固件」的设计参考，不是本轮交付内容。

### 4.1 共用什么（将来）

同一份 `ImageCarrierLib`，接口收敛成 `Load(volume, spec) -> {base, bytes}`：

| 共用步骤 | 说明 |
| --- | --- |
| 打开卷 | `DarwinBoot.c:693-695` 已经拿到的 `Root` 传进来，库内不再 `OpenVolume` |
| 按名读 + 校验大小 | `ReadFile` + 与 spec 逐项比对；错误码统一 `EFI_COMPROMISED_DATA` |
| 写物理 + 清 bss + 空洞不动 | 先清后拷；空洞（modem 11 处共 790,528 B）一个字节都不碰 |
| 写 ADT 属性 | 调方传入 `TreeAddress` 与偏移；属性名由 spec 给 |
| 失败拒绝启动 | 统一走 `Fail:`，`Stage` 由 spec 给（`L"MODEM IMAGE"` / `L"ADSP IMAGE"`） |
| 日志前缀 | `modem-image:` / `adsp-image:`，均为 level 1 |

### 4.2 差异点（若将来 ADSP 也走固件）

| 维度 | modem（第一版） | ADSP（保留） |
| --- | --- | --- |
| payload 目录 | `EFI/UniXNU/MODEM/`，27 个平铺文件 | `EFI/UniXNU/ADSP/`，容器 `.bin` 单文件 |
| spec 形态 | 30 行表（paddr/bytes/bss/name），3 行为纯 bss 无文件 | `K60A` 容器：12 B 头 + 24 B 记录 + NUL 名，再解析 ELF32 段 |
| 目标窗口 | `0x8BC00000`，span `0x13200000` | `0x86300000`，span `0x03100000` |
| 属性名 | `K60ModemImage` | `K60AdspImage` |
| 内存描述符 | 已有（`MemoryMapLib.c:31`） | **缺**（12 号 §5.3：`0x86300000..0x89400000` 无 descriptor） |
| 段对齐 | 每段 4 KiB 对齐 | 段 10 是 `0x86e0b2c0`，非页对齐 |
| 账目 | 拷 109,060,761 / 清 211,012,967 / 空洞 790,528 | 拷 23,494,284 / 清 25,925,684 / 空洞 1,960,256 |

### 4.3 关于「借鉴 ADSP 容器 ABI」

**已裁：容器只留给 ADSP 第二版**（Lead，2026-11-15 23:27）；modem 不使用容器，理由见下。

可以借的只有**记录语法**（`name_len / mode / size / packed_size`，名字 NUL 结尾，8 字节对齐）。
modem 第一版**不能**改成容器，原因很硬：容器记录里没有 `paddr`，而 modem 的 30 段是 30 个不同的
物理地址（段间还有 11 处空洞必须保持原样）。把 `paddr` 塞进 `mode` 或名字里都会破坏已冻结的
12 号 §1.1/§1.2 输入契约。若将来要统一，需要 Lead 重新裁决一次容器格式，而不是本轮顺手改。

这两条（`0x86300000` 的 UNCACHEABLE descriptor、段 10 非对齐链接地址）只属于**未采纳**的 ADSP
固件路线，不是本轮 DXE 的条件；ADSP 继续走 §4 开头的内核内嵌 blob。

## 5. 验收：门禁已能独立执行

`13-FIRMWARE-ACCEPTANCE.md` §四 的 `gate.sh` 用四个参数工作：

```bash
bash gate.sh <payload.img> <boot.img> <console.log> <uefi-mondrian 检出目录>
```

2026-11-15 用合成输入（见 `13-FIRMWARE-ACCEPTANCE.md` §5.1）干跑，结果 **18 PASS / 0 FAIL / exit 0**：

```text
PASS A1 payload=224 MiB
PASS A2 boot.img=235446272 B
PASS A3 MODEM 目录 27 个文件、名字正确
PASS A4 每个文件大小==段表 bytes
PASS A5 ADT K60ModemImage 16 字节、值合法
PASS B1 ImageCarrierLib 存在
PASS B2 DarwinBoot 调用点
PASS B3 DarwinBoot 发布属性 (2 处)
PASS B4 三行 D3 日志、无 debug 门
PASS B5 固件表==生成器输出
PASS B6 无整窗清零
PASS C1 日志行: modem-image: chosen dtb at
PASS C1 日志行: modem-image: window 0x8bc00000..0x9ee00000
PASS C1 日志行: modem-image: abl staging ends at
PASS C2 拷贝/清除/空洞数字
PASS C3 区间发布行
PASS C4 内核侧 carrier present
PASS C5 内核侧 plan rows=30
TOTAL PASS=18 FAIL=0
```

这遍干跑的价值是**门禁自身先被验收**：合成输入能全绿，说明 18 条断言都可以机械判，
固件 commit 一到就能立刻跑，不需要临时写脚本。它同时抓出并修掉了 `gate.sh` 三个自身缺陷
（`mcopy -s` 套子目录、A5 heredoc 吞脚本、`mcopy` 覆盖提示挂起），细节见 13 号 §5.1。

真跑时把四个参数换成固件产出的真实文件；额外还要过 `verify-boot-image.py` 与
`check-image-args.py`（`pong_modem` 已在白名单），以及 12 号 §6 的内核侧五行判据。

## 6. 裁决记录（Lead，2026-11-15 23:27）

| 议题 | 裁决 |
| --- | --- |
| 属性长度 | 16 B `(base, span)`；`span` 是窗口、不是拷贝量（§1.3） |
| modem 输入形态 | 27 平铺文件 + 30 行段表，批准；容器语法留给 ADSP 第二版（§2.5） |
| 本轮范围 | 只做 modem；ADSP 已走内核内嵌 blob，DXE 只服务 modem（§4） |
| 下一步 | DXE 由 Lead 落（uefi-mondrian）；落地后给 uefi commit、27 文件清单与大小、boot.img sha256，本线用真实输入跑 `gate.sh`，18 行全绿再谈上机 |

待命期间不出镜像、不碰 `uefi-mondrian`（边界不变）。

## 7. 引用

- `12-DXE-CONTRACT.md`：输入/输出/失败语义/与 ADSP 的共用面
- `13-FIRMWARE-ACCEPTANCE.md`：18 条断言与 `gate.sh`
- `05-MODEM-IMAGE.md`：30 段表、拷贝/清除账目、空洞清单
- `06-MODEM-PAS.md`：PAS id=4 与三步 SMC
- `07-QRTR-ENUMERATION.md`：QRTR 只读枚举判据
- `docs/engineering/BOOT-ARGS.md`：`pong_modem` 取值语义
- `E:/k60-work/references/pong-power`、`phk110-port`：PAS 与 GLINK 参考实现
