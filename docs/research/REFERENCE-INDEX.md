# REFERENCE-INDEX.md —— 参考仓库事实索引

> 建立于 2026-11-14，分支 `feat/research-refindex`。只读产出：本文件不包含任何从参考仓库拷来的代码，只有「事实 + 出处（文件:行）」和可信度。
> 目的：把散落在 42 个参考仓库里的**同型号/同 SoC 事实**抽成可检索索引，让每一条硬件结论都能被追问到「某文件某行」，而不是「某人记得」。

---

## 0. 为什么需要这份文件

2026-11-12 的事实核查已经发现过一次：同 SoC 兄弟移植的 `wave12c-electrical.md` 在本地躺了两天没人打开，
却去抄了同一仓库里另一台机器（POCO X5 Pro）的驱动。根因不是「不知道要读」，是**没有清单 + 没有强制**。
`SOURCES.toml` 解决了「每个子系统必须读哪几个文件」，但没有解决「一个寄存器地址在哪个仓库第几行」——
后者才是真正卡住供电/音频/WiFi 三条线的东西。本文件补的就是后者。

三条使用原则：

1. **先查这里，再翻仓库。** 这里没有的，才去仓库里找；找到后请补一条进来。
2. **每条事实都带可信度。** 「同 SoC 异板」不等于「本板」，抄地址之前先看第 4 节的交叉验证矩阵。
3. **只读。** 参考仓库是证据，不是代码来源。不要把它们的 `.cpp` 拷进我们的树。

---

## 1. 读法

### 1.1 路径映射（重要，不看清会白跑）

本索引里的路径有三种前缀，含义完全不同：

| 写法 | 实际位置 | 说明 |
|---|---|---|
| `references/...` | `/mnt/e/k60-work/references/...`（Windows: `E:/k60-work/references/...`） | 参考仓库快照。**本仓库树内没有 `references/` 目录**，`research-gate.py` 靠 `alt = os.path.join('/mnt/e/k60-work', path)` 回退才能找到 |
| `E:/hackios/...` | 主工作区仓库 | 只出现在本文件正文；**不能写进 `SOURCES.toml` 的 `path`**（两种回退都不覆盖，gate 会判文件不存在） |
| `docs/...`、`scripts/...` | 本仓库 | 我们自己的树 |

设备页（`docs/devices/*.md`，本索引第 13 节）**不在本仓库**，也不在 `/mnt/e/hackios/UniXNU`：它们在 `references/UniXNU-upstream/docs/devices/`（上游文档树，由各 fork 的 `porting.toml` 生成）。`/mnt/e/hackios/UniXNU` 只有 `devices.toml` 与 `kits/`。

本板一手数据的两个来源，路径固定：

- `E:/k60-work/reports/live-6033dbec-fdt.dtb` —— 设备 6033dbec 于 2026-11-02 从 adb 导出的 **live merged FDT**（已含 dtbo 应用后的节点），919,210 B，SHA-256 `95c02052b773a1b8df8ec20f6368ba80c87717206ed40682046e2ad6f29fdac8`。
- `E:/k60-work/scratch/refmine/fdt_dump.txt` —— 上面那份 DTB 的解析结果（30,596 行），本索引引用的行号都指这个文件。解析器是 `E:/k60-work/scratch/refmine/fdt_dump.py`（本机没有 dtc、没有 Python libfdt，只能自己按 FDT 结构解）。

### 1.2 可信度分级

| 级别 | 含义 | 采信规则 |
|---|---|---|
| **本板实测** | 从 6033dbec 这台机器直接导出/实测（live FDT、uefi-mondrian 的 MemoryMapLib 实测注释、串口日志） | 可直接用 |
| **官方** | UniXNU / UniXNU-docs / uefi 上游的正式记录 | 可用，但注意官方记录里的设备页多数是各 fork 自报，不是官方验证 |
| **同SoC异板·已上机** | phk110-port、UniXNU-zizhan 这类同 SM8475 且已在本机跑通 | 地址可作强候选，**必须**与本板 DT 对一遍 |
| **同SoC异板** | pong-*、ShengUfs、UniXNU-sheng 等 SM8475 兄弟移植 | 只能作候选；已发现至少三处地址在本板是错的（见 14.1、14.3、14.4） |
| **反编译/推断** | 从 `.ko`、二进制、或从别的板推出来的 | 必须上机验证，不得直接进代码 |

### 1.3 怎么查

```bash
cd /mnt/e/hackios/k60-refmine
grep -n '0x17a20000' docs/research/REFERENCE-INDEX.md     # 按地址查
grep -n 'RPMh\|RSC' docs/research/REFERENCE-INDEX.md       # 按主题查
grep -n 'PongWifiPlatform' docs/research/REFERENCE-INDEX.md # 按文件查
```

查不到时，按第 2 节的仓库清单去找对应仓库，`grep -rn` 之后再回来补一条。

### 1.4 与其它文档的分工（别在这里重复写别人的内容）

| 想知道 | 去哪 | 本文件负责的部分 |
|---|---|---|
| 每个子系统必须读哪几个文件、读了没 | [`SOURCES.toml`](SOURCES.toml) | 只补「某个事实在第几行」；本文件新增的 18 条 required 就是第 16 节的表 |
| 八步流程走到哪一步、能不能构建 | [`EIGHT-STEPS.toml`](EIGHT-STEPS.toml)、`scripts/eight-step-gate.py` | 提供每一步需要的硬件事实，不判定流程状态 |
| 上游 13 个分支哪些提交取过、为什么不取 | [`UPSTREAM-TRIAGE.toml`](UPSTREAM-TRIAGE.toml)、[`../reference/BRANCHES.md`](../reference/BRANCHES.md) | 只写「这个分支里有什么本板可用的值」 |
| 历次 subagent 交付了什么、落在哪个 commit | [`SUBAGENT-DELIVERABLES.md`](SUBAGENT-DELIVERABLES.md) | 只写「这条事实的出处」 |
| 各子系统已经得出的结论 | [`wifi/RESEARCH.md`](wifi/RESEARCH.md)、[`audio/RESEARCH.md`](audio/RESEARCH.md)、[`battery/RESEARCH.md`](battery/RESEARCH.md) | 提供结论背后那一行的原始出处 |
| 踩过的坑、铁则、工具用法 | [`../engineering/PITFALLS.md`](../engineering/PITFALLS.md)、[`../engineering/HARD-RULES.md`](../engineering/HARD-RULES.md)、[`../engineering/TOOLBOX.md`](../engineering/TOOLBOX.md) | 第 14 节只记「参考仓库与本板的矛盾」，不重复通用坑 |
| 本地已有哪些资产（驱动、固件、反汇编） | [`../engineering/LOCAL-ASSETS.md`](../engineering/LOCAL-ASSETS.md) | 第 15 节只记「参考仓库里缺什么」 |

**写入规则**：本文件只写「仓库 + 分支 + 文件:行 + 事实 + 可信度」。任何需要判断、决策、计划的内容都不写在这里，写到上面那些文件去。

---

## 2. 参考仓库清单（实测 2026-11-14）

任务书里写的是 23 个；**实测为 42 个唯一仓库名**（`/mnt/e/hackios` 15 个 + `/mnt/e/k60-work/references` 31 个，其中 5 个在两处各有一份快照、1 个是空仓库）。
差异原因是清单本身已过期：`yibiya-*`、`ios-sweet-k60`、`phk110-port` 这批 K60 专属资产是 11-10 之后才进 workspace 的。

关键词命中用 `git ls-files | grep -c` 统计（mondrian / sm8475+taro / k60），用来判断「这个仓库到底有没有本板字样」。

### 2.1 /mnt/e/hackios —— 主工作区

| 仓库 | 分支 | HEAD | 文件 | 脏 | 命中(mondrian/sm8475/k60) | 用途 |
|---|---|---|---|---|---|---|
| Device-Binaries | main | d3f7cb72 | 22004 | 3172 | — | 二进制资产（固件、panel XML、bootloader 件）。**已普查（见第 15 节）**：78 个机型目录全部映射到 `Build/<Family>`，**无任何 SM8475/taro**；74 份 `uefiplat.cfg` 无一含本板 DXE Heap/video_region；零个 aw88/bdwlan/amss/.pwf |
| QcaBluetooth | main | 986d631 | 46 | 0 | 0/0/0 | 蓝牙 GENI/tty 传输完整实现（`src/qbt_*`）。**唯一副本，workspace 里没有** |
| QcomGeniSpi | main | eac47ba | 6 | 0 | 0/0/0 | GENI SPI 驱动范本（`GeniSpi.c` 15,536 B） |
| UniXNU | main | e3982fc | 1485 | 13 | 13/0/1 | 官方组件体系；`devices.toml:1585-1598` 是 mondrian 的官方记录 |
| UniXNU-docs | HEAD 分离 | 066c8d8 | 1080 | 0 | — | 官方文档站源 |
| UniXNU-liuqin | main | 907b8e9 | 105 | 0 | — | **Xiaomi Pad 6 Pro / liuqin / SM8475（cape）**，由 sheng 派生，不能构建。`docs/liuqin-hardware.md` 是从 stock 固件核实的板级真值，与 K60 逐条交叉验证（见 9.1） |
| UniXNU-mondrian | feat/touch-power | b18fe3b | 890 | 0 | 5/1/213 | **本板主 checkout，归 touch-agent**，不是参考仓库 |
| UniXNU-pong | main | e0ee6df | 406 | 9 | 0/7/0 | Pong 板级；`configs/pong-wifi-sm8475.json` 有 PCI 参数 |
| UniXNU-sheng | main | a68ee4e | 435 | 0 | 0/0/0 | Sheng 板级；`drivers/` 7 个、`package/` 100+ 个 Probe |
| UniXNU-sm8475-common | main | c5b50c3 | 8 | 7 | 0/2/0 | **SoC 层唯一共享包**：`dts/sm8475.dtsi`、`soc.toml` |
| UniXNU-zizhan | main | 034a0b0 | 615 | 0 | 0/9/0 | 同 SoC 已上机跑通 GPU+WiFi 的板，最佳对照 |
| pong-power | main | c37179e | 36 | 0 | — | **旧快照**（见 2.3） |
| pong-wifi | main | d2e33ca | 13 | 0 | — | **旧快照**（见 2.3） |
| uefi-mondrian | main | 9b79562 | 1063 | 6 | 25/1/6 | **本板固件**；`MemoryMapLib.c` 是 2026-10-27 实测的保留区表 |
| uefi-pong | main | 997ae23 | 1046 | 12 | 0/1/0 | Pong 固件；`Platforms/Nothing/pongPkg` 只有 11 个文件，是 mondrianPkg 的模板 |

### 2.2 /mnt/e/k60-work/references —— 参考快照

| 仓库 | 分支 | HEAD | 文件 | 用途 |
|---|---|---|---|---|
| AdrenoMetal | main | 73d582f | 110 | Metal 后端 + Adreno 插件 |
| ShengUfs | main | b6fe07b | 35 | 官方 UFS 实现（`NativeUfs.cpp` 148,723 B）+ 12 个测试 |
| UniXNU | feat/ipados27-gpu-parity | c93e965 | 1077 | 官方组件（GPU parity 分支） |
| UniXNU-pong | latest | e0ee6df | 406 | 同 2.1 |
| UniXNU-pong-upstream | main | 08c1f94 | 508 | Pong 上游化后的版本 |
| UniXNU-sheng | main | 1108068 | 521 | Sheng 板级（比 hackios 那份新） |
| UniXNU-sheng-upstream | main | 1108068 | 521 | 同上，同一 HEAD |
| UniXNU-sm8550-common | main | 2dc650c | 29 | SM8550 共享包；`ShengGmu.c` 等可对照 GPU/GMU |
| UniXNU-upstream | main | 7d85ede | 2140 | 官方最新；mondrian 命中 18 条，但**没有 K60 硬件实现** |
| darwin-xnu-build | main | 6639065 | 43 | XNU 构建脚本 |
| ios-sweet | main | 45263be | 141 | sweet（SM7325）移植基线 |
| ios-sweet-k60 | main | 886101c | 358 | **K60 专属**：`xnu/patches/0091-0107`、触摸测试台、`k60install` |
| phk110-port | phk110-port | a7d4575 | 2100 | **同 SoC 异板（OnePlus Ace 2 / PHK110，已上机）**，59 篇 wave 文档，密度最高 |
| pong-adreno | port/ios18e-native-302 | 5bc6f4c | 118 | Adreno 7 系 GPU 完整实现 |
| pong-adreno-metal | main | 418c550 | 106 | Metal 侧 |
| pong-arm-cpu | main | ac65513 | 6 | CPU 启动 |
| pong-arm-dt-platform | main | 09ecfcf | 5 | ADT 平台 |
| pong-boot-capture | main | af2c5ca | 4 | 启动抓取 |
| pong-darwin-boot24 | main | 86d300d | 20 | DarwinBoot24 |
| pong-metal | port/ios18e-native-302 | 0b3b34a | 27 | `NativeBridgeMetalFrontend.mm` 225,616 B |
| pong-power | port/ios18e-native-302 | c117a67 | 38 | **新快照**：ADSP/Audio/WCD938x/Backlight/RPMh |
| pong-ram-block | main | eebcdb6 | 8 | 内存盘 |
| pong-ufs | port/ios18e-native-302 | 138a9fb | 14 | UFS 传输 + GPT/three-window |
| pong-unixnu-upstream | main | 1a01c2a | 673 | 上游化 |
| pong-usb | port/ios18e-native-302 | 37e0ed4 | 8 | DWC3 寄存器表 |
| pong-wifi | port/ios18e-native-302 | 20e1e5b | 14 | **新快照**：QCA6490 PCIe/CNSS |
| uefi-pong | main | 997ae23 | 1046 | 同 2.1 |
| yibiya-uefi-upstream | main | 4a6966b | 1063 | yibiya 的 uefi 上游 |
| yibiya-unixnu-upstream | main | 982e41f | 1486 | yibiya 的 unixnu 上游；K60 相关只有 device-records 与 `mondrian_defconfig` |
| yibiya-upstream | upstream-fix | 522c6ea | 732 | **K60 专属资产最集中**：164 条 mondrian 命中，含 `K60-TOUCH-PARAMS.md`、`0210-0250` 补丁 |
| UniXNU-ruby | — | — | **0** | ⚠ **不是 git 仓库**：目录里只有一个 `porting.toml`（246 行 / 15,547 B，`soc = "MT6877"`、`os_profile = "ios-16.7.16-20H392"`，自述 *selects no UniXNU components and does not claim a UniXNU UEFI or format-2 build*）。「空仓库」的旧说法不准：**有内容**，只是不是构建树，不能当 catalog 引用 |

### 2.3 两处同名不同快照（引用前必须确认用哪一份）

`pong-power` 与 `pong-wifi` 在 `/mnt/e/hackios` 和 `/mnt/e/k60-work/references` 各有一份，**内容不同，references 那份更全**：

| 文件 | hackios 版 | references 版 |
|---|---|---|
| `PongAdsp.cpp` | 33,318 B | 34,547 B |
| `PongAudio.cpp` | 28,254 B | 29,263 B |
| `PongIOAudio2.h` | 22,298 B | 23,857 B |
| `PongWcd938.h` | 不存在 | 6,262 B |
| `PongWifiFirmware.cpp` | 不存在 | 3,984 B |

**本索引一律引用 `references/` 那份**（分支 `port/ios18e-native-302`）。行号只对那一份有效。

## 3. 供电 / RPMh / SPMI / PMIC

优先级最高的线：触摸、音频、WiFi、电池全部卡在「能不能投票成功」上。

### 3.1 RPMh RSC 与 TCS

| 仓库 | 文件:行 | 事实 | 可信度 |
|---|---|---|---|
| pong-power | `PongPlatformResources.cpp:68` | `IODeviceMemory::withRange(0x17a20000, 0x10000)` —— RSC 映射基址 | 同SoC异板 |
| pong-power | `PongPlatformResources.cpp:79` | `constexpr unsigned ActiveTcs=0xd00+4*0x2a0;` —— **用 DRV slot 4**，不是 2 | 同SoC异板 |
| pong-power | `PongPlatformResources.cpp:123` | `constexpr unsigned b = 0xd00 + 4 * 0x2a0, other = 0xd00 + 3 * 0x2a0;` | 同SoC异板 |
| pong-power | `PongPlatformResources.cpp:129-131` | 能力检查：`caps=rd(0xc); count=(caps>>12)&63; ncpt=(caps>>27)&31;` 判据 `((rd(0)>>16)&255)>=3 \|\| count<8 \|\| ncpt<1 \|\| !rd(b+0x18)` → `fail("active TCS4 unavailable")` | 同SoC异板 |
| pong-power | `PongPlatformResources.cpp:136` | `return fail("conflicting RPMh transaction");` —— 上一笔未 retire 就再投，直接拒绝 | 同SoC异板 |
| pong-power | `PongPlatformResources.cpp:138` | `wr(0xd00, rd(0xd00) & ~(1u << 4));` 清 trigger | 同SoC异板 |
| pong-power | `PongPlatformResources.cpp:139-143` | **原文注释**：`Hardware requirement: clear trigger, read it back, then clear AMC enable and read it back. Clearing both in one posted write violates Nothing's __tcs_set_trigger ordering and can lose the next trigger.` 代码：`control=rd(b+0x14)&~(1u<<24); if(!controlWrite(control)\|\|!controlWrite(control&~(1u<<16))) return fail("TCS4 trigger/enable clear not acknowledged");` | 同SoC异板 |
| pong-power | `PongPlatformResources.cpp:144-149` | `wr(b+0x1c, 0); wr(0xd08, 1u<<4);` 然后 `while(rd(0xd04)&(1u<<4))` 等完成 | 同SoC异板 |
| pong-power | `PongPlatformResources.cpp:150` | 写投票内容：`wr(b+0x30,0x10108); wr(b+0x34,addr); wr(b+0x38,value);` | 同SoC异板 |
| pong-power | `PongPlatformResources.cpp:151-154` | `wr(b+0x10,1); wr(b+0x1c,1);` → 回读校验 → `wr(b+0x14,(1u<<16)\|(1u<<24));` 触发 | 同SoC异板 |
| pong-power | `PongPlatformResources.cpp:96-108` | retireVote 完成判据：`status=rd(ActiveTcs+0x3c)`、`idle=rd(ActiveTcs+0x18)`、`rd(ActiveTcs+0x1c)==1 && rd(ActiveTcs+0x34)==addr && rd(ActiveTcs+0x38)==value`，外加 `pendingVote.progressed \|\| (rd(0xd04)&(1u<<4))`；收尾 `wr(ActiveTcs+0x1c,0); wr(0xd08,1u<<4);` | 同SoC异板 |
| pong-power | `PongPlatformResources.cpp:159-169` | 导出 `extern "C" void pong_rpmh_init(void)` / `extern "C" bool pong_rpmh_vote(uint32_t address, uint32_t value)`；:170-173 `pong_qup5_lock/unlock`；:174 `pong_smmu_lease_lock` | 同SoC异板 |
| live FDT | `fdt_dump.txt:4698` | `rsc@17a00000`：`reg=<0x17a00000 0x10000 0x17a10000 0x10000 0x17a20000 0x10000 0x17a30000 0x10000>`，`reg-names=drv-0..drv-3`，**`qcom,drv-id=<2>`** → APPS RSC = **0x17a20000** | 本板实测 |
| phk110-port | `wave12-touch-buttons.md:67` | 同结论：apps_rsc 0x17a00000 + drv-id 2 → 0x17a20000，tcs-offset 0xd00 | 同SoC异板·已上机 |

⚠ **K60 侧最贵的教训**：`references/ios-sweet-k60/xnu/patches/0246-k60-touch-skip-rpmh.patch` 的注释写着
「这台机器上 RSC 一个寄存器都读不得：首次读 TCS 就整机死」，`0248-k60-rsc-address-probe.patch` 因此只做只读探针。
根因（XPU / 电源域 / 互连）至今未定 —— 见 14.1。**在这条未解之前，任何「照着 Pong 写 RPMh 投票」的代码都不要上机。**

### 3.2 cmd-db（RPMh 资源名 → 地址）

| 仓库 | 文件:行 | 事实 | 可信度 |
|---|---|---|---|
| live FDT | `fdt_dump.txt:58` | `aop_cmd_db_region@80860000`，`compatible=qcom,cmd-db`，`reg=<0 0x80860000 0 0x20000>` | 本板实测 |
| uefi-mondrian | `MemoryMapLib.c:14` | `{"aop_cmd_db_region", 0x80860000, 0x00020000, AddMem, MEM_RES, SYS_MEM_CAP, Reserv, WRITE_BACK_XN}`（表头注释 :7 写明 2026-10-27 实测生成） | 本板实测 |
| pong-power | `PongAdsp.cpp:44` | `kCmdDb=0x80860000, kCmdDbSize=0x20000` | 同SoC异板 |
| pong-power | `PongWcd938.h:34` | `qcom_cmd_db_find(db,0x20000,"smpb10",&resource)` —— 按资源名查 B 轨（WCD 的 1.8 V） | 同SoC异板 |

⚠ K60 侧 **cmd-db 从未在运行时读过**（`K60-TOUCH-PARAMS.md` ⑤ 未决项），magic 与 entry 布局都未验证。

### 3.3 SPMI 仲裁器（PMIC 寄存器访问）

| 仓库 | 文件:行 | 事实 | 可信度 |
|---|---|---|---|
| live FDT | `fdt_dump.txt:8106` | `qcom,spmi@c42d000`，`reg-names=cnfg,core,chnls,obsrvr,intr`，`reg=<0xc42d000 0x4000 0xc400000 0x3000 0xc500000 0x400000 0xc440000 0x80000 0xc4c0000 0x10000>` | 本板实测 |
| ios-sweet-k60 | `xnu/patches/0101-k60-spmi-arbiter-addresses.patch:7-9` | 被替换掉的 sweet 旧值：`KEYS_CORE_PA 0x0c440000` / `KEYS_OBS_PA 0x0e600000` / `KEYS_CNFG_PA 0x0c40a000` | 反编译/推断 |
| ios-sweet-k60 | 同上 `:12` | 注释原文给出上面那张 reg 表，并说明「sweet 的常量在这台机器上指向无关块，keys 驱动会读到垃圾或把总线挂住」 | 本板实测（引 live FDT） |
| ios-sweet-k60 | 同上 `:16-19` | 新值：`KEYS_CORE_PA 0x0c400000` / `KEYS_OBS_PA 0x0c440000` / `KEYS_CNFG_PA 0xc42d000` / `KEYS_PON_RT 0x0810` | 本板实测 |
| uefi-mondrian | `MemoryMapLib.c:65` | `{"PMIC ARB SPMI", 0x0C400000, 0x2800000, AddDev, MMAP_IO, UNCACHEABLE, MmIO, UNCACHED_UNBUFFERED_XN}` | 本板实测 |
| phk110-port | `wave12-touch-buttons.md:80` | taro 的 SPMI 表：cnfg/core/chnls/obsrvr/intr = 0xc42d000 / 0xc400000 / 0xc500000 / 0xc440000 / 0xc4c0000 | 同SoC异板·已上机 |
| phk110-port | `wave12-touch-buttons.md:175` | 上机日志行 `buttons_core=0xc400000 buttons_cnfg=0xc42d000 buttons_obs=0xc440000` | 同SoC异板·已上机 |

**这是本索引里交叉验证最硬的一条**：K60 的 live FDT、sweet-k60 的补丁、phk110 的上机日志三处独立吻合。
但注意 `phk110 wave12:81` 的另一半警告：redwood 的 `core=0xc440000` 在 taro 上**恰好是 obsrvr 的基址**——照抄别的板会踩到别人的块。

### 3.4 PMIC 按键 / PON

| 仓库 | 文件:行 | 事实 | 可信度 |
|---|---|---|---|
| live FDT | `fdt_dump.txt:8121` `:8127` `:8133` `:8138` | `pmk8350@0` → `pon_hlos@1300` → `pwrkey` / `resin` | 本板实测 |
| phk110-port | `wave12-touch-buttons.md:74-76` | 电源键 = PMK8350 PON（slave 0，peripheral 0x13）KPDPWR_N bit 0x80；音量上 = 同块 RESIN_N bit 0x40；音量下 = PM8350 GPIO6（slave 1，pinctrl@8800，peripheral 0x18d）active low | 同SoC异板·已上机 |
| ios-sweet-k60 | `0101-...patch:19` | `KEYS_PON_RT 0x0810`、`KEYS_GPIO_RT 0xc110`、`KEYS_NO_APID 0xffff` | 本板实测 |

---

## 4. 音频（ADSP / PAS / GLINK / AudioReach / WCD938x / AW882xx）

### 4.1 ADSP PAS 与保留内存

| 仓库 | 文件:行 | 事实 | 可信度 |
|---|---|---|---|
| pong-power | `PongAdsp.cpp:43` | `kSmem=0x80900000, kSmemSize=0x200000, kMutex=0x1f40000+3*0x1000, kAoss=0xc300000` | 同SoC异板 |
| pong-power | `PongAdsp.cpp:44` | `kRscDrv=0x17a20000, kRscTcs=0xd00, kCmdDb=0x80860000, kCmdDbSize=0x20000` | 同SoC异板 |
| pong-power | `PongAdsp.cpp:45` | **`kAdspBase=0x85700000, kAdspSize=0x2800000`**、`kDtbBase=0x9e980000, kDtbSize=0x80000` | 同SoC异板 |
| pong-power | `PongAdsp.cpp:46` | `kPasAdsp=1, kPasDtb=36, kRemotePid=2, kItemIn=443, kItemOut=429, kItemCrash=423` | 同SoC异板 |
| pong-power | `PongAdsp.cpp:319` | `scm(QCOM_SCM_PAS_INIT_IMAGE, qcom_scm_args(2, QCOM_SCM_VAL, QCOM_SCM_RW, 0), pas, phys, 0)` | 同SoC异板 |
| pong-power | `PongAdsp.cpp:320-321` | relocatable 时再 `QCOM_SCM_PAS_MEM_SETUP(..., base, qcom_mdt_span(&image.mdt))` | 同SoC异板 |
| pong-power | `PongAdsp.cpp:537` | `if (qcom_mdt_span(&adsp.mdt)>kAdspSize) fail(StFirmware,-7);` —— 固件 span 必须小于保留区 | 同SoC异板 |
| pong-power | `PongAdsp.cpp:581` `:519-520` | `QCOM_SCM_PAS_AUTH_AND_RESET` / `QCOM_SCM_PAS_SHUTDOWN` | 同SoC异板 |
| pong-power | `PongAdsp.cpp:199` | `qcom_smp2p_find_in(&view, "slave-kernel")` | 同SoC异板 |
| pong-power | `PongAdsp.cpp:202-204` | AOSS 就绪校验：`rd(gAoss,0)==0x4d41494c`（"MAIL"）且 `rd(gAoss,0xc)==0xffff` | 同SoC异板 |
| **uefi-mondrian** | `MemoryMapLib.c:34` | `{"adsp_region", 0x9FD00000, 0x03100000, ...}` —— 与 Pong 的 0x85700000 **不同板不同址** | **本板实测** |
| UniXNU-upstream | `docs/devices/zizhan.md:55` | 原文：`ADSP uses 0x9fd00000+0x3100000, versus Pong 0x85700000+0x2800000. SMEM, IPCC, AOSS and cmd-db addresses agree.` —— 与 K60 完全一致 | 同SoC异板·已上机 |

**结论：ADSP 三件事必须一起改**——基址 0x9fd00000、尺寸 0x3100000、DTB 位置随 adsp_region 走。
Pong 的 0x85700000 在 K60 上是 `video_region`（见 12.1），照抄会写坏视频固件区。

### 4.2 GLINK / GPR / SMEM

| 仓库 | 文件:行 | 事实 | 可信度 |
|---|---|---|---|
| pong-power | `QcomGlink.c:104` | `qcom_glink_channel(g, name, intent_size, intent_count, storage, ...)` | 同SoC异板 |
| pong-power | `QcomGlink.c:107` | `intent_count > QCOM_GLINK_MAX_LOCAL_INTENTS` 直接返回 0 | 同SoC异板 |
| pong-power | `QcomGlink.c:4` | 注释：发送方留 8 字节使满 FIFO 不显空，另留 16 字节给 READ_NOTIF | 同SoC异板 |
| pong-power | `QcomGlink.c:341-342` | 注释：小 intent 表被 idle 小包占满时仍要保留大 intent（图命令需要更大 intent） | 同SoC异板 |
| pong-power | `QcomSmem.c:81` | `header = align_up(ENTRY, p->cacheline), last = rd(smem, p->offset + 16)` —— SMEM 条目布局 | 同SoC异板 |
| pong-power | `ShengGpr.c:12-14` | GPR 头布局：word0 = version 3:0 \| header size in words 7:4 \| packet size in bytes 31:8；word1 = dst domain 7:0 \| src domain 15:8 | 同SoC异板 |
| pong-power | `PongAdsp.cpp:142-143` | `kickGlink()` 打 `QCOM_IPCC_CLIENT_LPASS / QCOM_IPCC_SIGNAL_GLINK_QMP`；`kickSmp2p()` 打 `SMP2P` | 同SoC异板 |
| live FDT | `fdt_dump.txt:9272` | `ipcc@ed18000` | 本板实测 |
| live FDT | `fdt_dump.txt:9281` `:9301` `:9320` `:9327` `:9342` | `remoteproc-adsp@03000000` → `glink-edge` → `pmic_glink_rpmsg` / `qcom,gpr` / `q6prm` | 本板实测 |

### 4.3 AudioReach 参数 ID 与 GPR 打包

`references/pong-power/ShengAudioReach.c`（17,656 B）是唯一一份把 AudioReach 参数 ID 写全的参考：

| 参数 | ID |
|---|---|
| `PARAM_SG_CONFIG` | 0x08001001 |
| `PARAM_CONTAINER_CONFIG` | 0x08001000 |
| `PARAM_MODULE_LIST` / `_PROP` / `_CONN` | 0x08001002 / 0x08001003 / 0x08001004 |
| `PARAM_SG_LIST` / `PROP_SG_PERF` / `_DIRECTION` / `_SCENARIO` | 0x08001005 / 0x0800100E / 0x0800100F / 0x08001010 |
| `PROP_CONT_CAPS` / `_POS` / `_STACK` / `_DOMAIN` / `PROP_PORT_INFO` | 0x08001011 / 12 / 13 / 14 / 15 |
| `PARAM_I2S_INTF` / `PARAM_HW_EP_MF` / `PARAM_FRAME_SIZE_FACTOR` | 0x08001019 / 0x08001017 / 0x08001018 |
| `PARAM_PCM_OUTPUT` / `PARAM_MEDIA_FORMAT` | 0x08001008 / 0x0800100C |
| `PARAM_CODEC_DMA_INTF` / `PARAM_HW_EP_POWER_MODE` | 0x08001063 / 0x08001176 |
| `CONTAINER_GC` / `MEDIA_PCM` | 0x0B001001 / 0x09001000 |

| 仓库 | 文件:行 | 事实 |
|---|---|---|
| pong-power | `ShengAudioReach.c:64` | GPR 打包顺序：`put32(w,0); put32(w,ADSP\|APPS<<8); put32(w,port); put32(w,dst); put32(w,token); put32(w,opcode);` |
| pong-power | `ShengAudioReach.c:126` 起 | 导出 `ar_open_speaker_device` / `ar_open_playback_stream` / `ar_open_mic_device` / `ar_open_capture_stream` / `ar_config_speaker_device` / `ar_config_mic_device` / `ar_config_playback_stream` |

### 4.4 WCD938x codec

| 仓库 | 文件:行 | 事实 | 可信度 |
|---|---|---|---|
| pong-power | `PongWcd938.h:34` | cmd-db 查 `smpb10`（PM8350 S10B 供 WCD RXTX/buck/IO 1.8 V），然后 `vote(resource.address+8,7) && vote(resource.address,1800) && vote(resource.address+4,1)` | 同SoC异板 |
| pong-power | `PongWcd938.h:76` | MMIO：`va_macro 0x033f0000(0x1000)`、`tx_macro 0x03220000(0x1000)`、`lpass_lpi 0x03440000(0x17000)`、`lpi_slew 0x034da000(0x1000)`、`swr_master 0x033b0000(0x10000)` | 同SoC异板 |
| pong-power | `PongWcd938.h:88` | `version=swr.r(0); v17 = version==0x01070000u` —— SoundWire v1.7 判据 | 同SoC异板 |
| pong-power | `PongWcd938.h:111` | 从机 ID 匹配 `(id & 0xffffffffffff) == 0x000d01170223`（DTS `reg=<0x0d 0x01170223>`） | 同SoC异板 |
| pong-power | `PongWcd938.h:73` | `prmClock(AR_CLK_TX_CORE_MCLK, 19200000)` 必须先 ACK 才能碰 macro/bus | 同SoC异板 |
| pong-power | `PongWcd938.h:20` | 时钟速率表 `{rate, rate==19200000?9600000:19200000}` | 同SoC异板 |
| live FDT | `fdt_dump.txt:19556` | `spf_core_platform` → `lpass-cdc` 节点存在 | 本板实测 |

SoundWire v1.7 与 v2 的 FIFO 寄存器不同（v1.7: fifoStatus 0x328 / readCommand 0x320 / readFifo 0x334；v2: 0x5050 / 0x5024 / 0x5040），
**K60 到底是 v1.7 还是 v2 未验证** —— 这是音频线第一个要测的东西。

### 4.5 AW882xx smart PA（K60 独有，Pong 没有）

| 仓库 | 文件:行 | 事实 | 可信度 |
|---|---|---|---|
| live FDT | `fdt_dump.txt:11228` `:11240` | `aw882xx_smartpa@34` 与 `aw882xx_smartpa@35` 两个节点（I2C 地址 0x34 / 0x35） | **本板实测** |
| pong-power | `PongAudio.cpp:29` 起 | Pong 音频栈没有 AW882xx 任何痕迹（`grep -i aw882` 空） | 同SoC异板 |
| **本板实测（2026-11-14）** | `evidence/audio-probe-j/run1/console.log:214-220` | **型号已定：两颗都是 AW88261（chip ID `0x2113`）**。`amp0 addr=0x34 id=0x2113 chip=AW88261 status=0x0000 faults=0x0000 pll=0`、`mask=0xffff ctrl=0x3343 i2s=0x04e8 dbg=0xa003 vbat=0x0263 pvdd=0x0263 temp=0x0019`、`vcal=0x2000 fuse=0x83fd/0x5bf3/0x83fd/0x5bf3`；amp1 同（`fuse=0x8009/0x5bf7/0x8009/0x5bf7`）；`amp probe done found=2/2 transfers=28 failed=0 timeouts=0 stray=0 recovered=0 gcc_misses=0` | **本板实测（只读）** |

只读探针的前置条件也一并测得（`console.log:191-213`）：amp 相关 GPIO 为 **1 / 3 / 43 / 52 / 56 / 57 / 63 / 88**；`gcc gpll0 vote=0x00000001 mode=0xe0000005 locked=1`、`gcc vote 0x0 -> 0x1f readback 0x1f`；wrap2_core / core_2x / m_ahb / s_ahb / s0 的 halt 分别 `0x4220 / 0x4220 / 0x0 / 0x80000002 / 0x4220` 且 `running=1`；I2C pad GPIO56/57 由 `cfg=0x1` 改到 `0x7`；`se15 fw=0x00000303 proto=3 disabled=0x0 clock=0x11`；`se15 ready config=0x03000021 status=0x0 level=0`；reset amp0=GPIO1 / amp1=GPIO3 由探针释放（`0x1 -> 0x3c0`）。
镜像 `E:/k60-work/artifacts/audio-probe-20261114j/boot.img` sha256 `877D0A9D08AE0BFF591CCB6D470A47EAC46BDFA26A0D0FF4376A711C35723EF2`，serial 6033dbec，`bootAccepted=true`，capture 以 budget 结束（非 panic）。第二次 boot `bootAccepted=false`，无证据。

→ **参考仓库仍然覆盖不到实现**（Pong 只有 WCD938x），但「是哪颗芯片」这个缺口**已经闭合**：
音频线 `docs/research/audio/AMPS.md:15-16` 把它列为「ADSP 之前唯一可完成的实机验证（AW88261 = 0x2113）」，
`drivers/PongAudio/PongAudioPlan.h:129` 的 `case 0x2113: return "AW88261"` 现已被真机证实。
剩下的缺口是**寄存器序列/保护策略**，不是型号。

---

## 5. WiFi / 蓝牙共用射频（QCA6490）

### 5.1 PCIe 端点与 BAR

| 仓库 | 文件:行 | 事实 | 可信度 |
|---|---|---|---|
| pong-wifi | `PongWifiPci.cpp:117` | 端点身份：`read32(0) != 0x110317cb \|\| read32(0x2c) != 0x010817cb` → QCA6490 设备/子系统 ID（vendor 0x17cb） | 同SoC异板 |
| pong-wifi | `PongWifiPci.cpp:120` | BAR 判据：`(bar & 0xfffffff0) == 0x60200000`、`(bar & 1)` 未置、`(bar & 6) == 4`（64 位） | 同SoC异板 |
| pong-wifi | `PongWifiPci.cpp:134` | `bar.open(0x60200000, 0x200000)` —— BAR0 = 2 MiB | 同SoC异板 |
| pong-wifi | `PongWifiPlatform.cpp:344` | 二次校验，失败信息 `QCA6490 endpoint identity mismatch` | 同SoC异板 |
| pong-wifi | `PongWifiPlatform.cpp:339` | 注释：真实范围是 `0x60200000..0x63ffffff`，**不是 Sheng 的 0x60300000** | 同SoC异板 |
| pong-wifi | `PongWifiPlatform.cpp:350` | ATU 映射序列：`atu.w(b,0); atu.w(b+8,0x60200000); atu.w(b+12,0); atu.w(b+16,0x63ffffff); atu.w(b+20,0x60200000); atu.w(b+24,0); atu.w(b+4,0x80000000);` | 同SoC异板 |
| pong-wifi | `PongWifiPlatform.cpp:538` | `mapPhys` 只允许 pa ∈ [0x60200000, 0x60400000) | 同SoC异板 |
| UniXNU-pong | `configs/pong-wifi-sm8475.json` | 板级 PCI 参数：vendor 0x17CB / device 0x1103 / subsystem_device 264 / BAR0 0x60200000 2 MiB | 同SoC异板 |
| live FDT | `fdt_dump.txt:16407` | `pcie@1c00000` | 本板实测 |
| live FDT | `fdt_dump.txt:10479` | `cnss-qca6490@b0000000` —— **K60 的 WiFi 是 QCA6490，与 Pong 同款** | 本板实测 |

### 5.2 电源时序与 XO latch（最容易漏的坑）

| 仓库 | 文件:行 | 事实 | 可信度 |
|---|---|---|---|
| pong-wifi | `PongWifiPlatform.cpp:196` | 注释原文：`QCA6490 CNSS2: assert XO_CLK before WLAN_EN and keep the latch` | 同SoC异板 |
| pong-wifi | `PongWifiPlatform.cpp:177` | 注释：真正的 PCIe ref_clk_src 是 **RPMH_CXO_CLK**，不只是 GCC CLKREF_EN | 同SoC异板 |
| pong-wifi | `PongWifiPlatform.cpp:71-72` | Nothing 的 `msm_pinmux_set_mux` 用 bit12 声明 EGPIO 能力脚；**GPIO204（QCA6490 XO latch）报 PRESENT bit11** | 同SoC异板 |
| live FDT | `fdt_dump.txt:1138` `:3613` | `bt_qca6490` 节点；`cnss_pins` / `cnss_wlan_en_active` pinctrl 组 | 本板实测 |

### 5.3 固件包

| 仓库 | 文件:行 | 事实 | 可信度 |
|---|---|---|---|
| pong-wifi | `PongWifiFirmware.cpp:15` | 固件路径 `/pong/firmware/qca6490.pwf`（板名硬编码，K60 必须改） | 同SoC异板 |
| pong-wifi | `PongWifiFirmware.cpp:60` | 导出 `pong_wifi_firmware_get(name, &data, &bytes)` | 同SoC异板 |
| pong-wifi | `proprietary-files.txt:3-8` | 需要的镜像：`image/qca6490/{amss.bin, amss20.bin, m3.bin, regdb.bin, bdwlan.*, bdwlang.*}` | 同SoC异板 |

⚠ **`PongWifiFirmware.cpp` 只在 `references/` 那份快照里存在**（hackios 版没有），见 2.3。

---

## 6. 触摸（GENI SPI / Goodix m11a / TLMM）

本板触摸的一手真值全在 live FDT 与 `yibiya-upstream/docs/plans/K60-TOUCH-PARAMS.md`（267 行）里。

### 6.0 芯片身份：Goodix **GT9916R BerlinD**（2026-11-14 三源一致，已闭合）

真机日志直接读出了芯片身份，不是推断：

```
K60S19: bitbang dev_confirm -> OK
goodix: chip "BERLIN", firmware "9916R" 05.80.02.63, sensor 255
goodix: touch report at 0x10308, coordinates up to 1440 x 3200
K60S19: bitbang goodix_probe -> OK
Pong touch: Goodix initialization failed; normal UI boot continues
```

| 证据 | 文件:行 | 事实 |
|---|---|---|
| 本板实测 | `evidence/usblog-20261110-152720/console.log:692-698` | 先 `device confirm mismatch aa aa aa aa (attempt 0)` → `device confirm OK (0x10000 = 8 x 0xAA)` → 读到 `chip "BERLIN", firmware "9916R" 05.80.02.63, sensor 255`，report 地址 `0x10308`，坐标上限 1440x3200 |
| 覆盖范围 | 61 个 boot 目录 / 71 次出现 | 全量扫描 2,468 个 evidence 文件；型号串**每次都完全一致**（BERLIN / 9916R / 05.80.02.63 / sensor 255），不是一次性噪声 |
| report 地址稳定性 | 69 次 `0x10308`、1 次 `0x10400` | 唯一那次是 `usblog-20261110-174720:703-705`：`goodix: misc candidates +0=0x10174 +12=0x10218 +24=0x10400 +44=0x10308` → `using touch_address=0x10400 (misc+24), alt=0x10308 (misc+44)`，之后固定回 0x10308 |
| 同款芯片（异板） | `references/ruby-bringup/docs/touch-goodix-9916r.md:16-17` | ruby（MT6877）也是 **GT9916R BerlinD**，ROM PID `BERLIN` / patch PID `9916R` 从 `0x10014` 读出 |
| 固件二进制 | `docs/research/touch/03-reverse-and-device-data.md:42-46` | `goodix_firmware_m11a.bin` 头部 offset 0x08 = `"BERLIN"`、0x10 = `"9916R"` |

**但识别成功 ≠ 初始化成功**：同一份日志的下一行就是 `Pong touch: Goodix initialization failed`；全量扫描里另有 5 次 `goodix: firmware-version contains only bus default bytes, no chip response` 与 5 次 `Pong touch: chip identity unavailable; no /dev/pong-touch`。所以第 6.4 节「触摸仍未修好」的结论**成立**，只是失败点不在识别芯片，而在初始化序列/供电。

### 6.1 节点与属性（live FDT，本板实测）

| `fdt_dump.txt` 行 | 节点/属性 | 值 |
|---|---|---|
| `:10729` | `soc/spi@990000` | `compatible=qcom,spi-geni`，`reg=<0x990000 0x4000>`，`interrupts=<0 0x25d 4>`（GIC SPI 605，level-high），`spi-max-frequency=0x2faf080`（50 MHz 控制器上限），`clock-names=se-clk,m-ahb,s-ahb`，`clocks=<0x24 0x5e 0x24 0x86 0x24 0x87>`，`phandle=0x35b` |
| `:10748` | `xiaomi_touch@0` | `compatible="xiaomi,m11a-spi"`（**不是 `goodix,*`**），`reg=<0>`（CS0），`spi-max-frequency=0xe4e1c0`（15 MHz），`interrupt-parent=0x3c`（TLMM），`interrupts=<0x15 0x2008>`（GPIO 21），`pinctrl-0=0x585`，`pinctrl-1=<0x2f1 0x2f0>` |
| `:10748` | 电源/GPIO | `goodix,avdd-gpio=<0x3c 0x47 0x0>`（GPIO 71 高有效）、`goodix,iovdd-name="vdd"`、`vdd-supply=0x301`（**pm8350c_l2 / ldoc2**）、`goodix,irq-gpio=<0x3c 0x15 0x2008>`、`goodix,reset-gpio=<0x3c 0x14 0x0>`（GPIO 20，低有效）、`goodix,irq-flags=0x2`（下降沿） |
| `:10748` | 坐标 | `goodix,panel-max-x=0x3840`(14400)、`panel-max-y=0x7d00`(32000)、`panel-max-w=0xff`、`panel-max-p=0x1000`；`panel=<0x6a3 0x697>` |
| `:10748` | 固件 | `goodix,firmware-name=goodix_firmware_m11a`、`goodix,config-name=goodix_cfg_group_m11a`、`touch-expert-array=<2 3 2 2 4 3 3 2 3 3 4 2>` |
| `:1182` | `soc/pinctrl@f000000` | `compatible=qcom,cape-pinctrl`，`reg=<0xf000000 0x1000000>`，`phandle=0x3c` |
| `:727` | `clock-controller@3d90000` | GPUCC（与触摸无关，列在此备查） |

引脚组（`K60-TOUCH-PARAMS.md` 与 live FDT 一致）：

| 组 | phandle | 内容 |
|---|---|---|
| `mi_ts_spi_active` | 0x581 | GPIO 16/17/18，function=qup4，drive-strength 6，bias-disable |
| `mi_ts_cs_active` | 0x582 | GPIO 19，qup4，ds 6，pull-up |
| `mi_ts_spi_sleep` / `mi_ts_cs_suspend` | 0x583 / 0x584 | 同脚切回 gpio |
| `mi_ts_active` | 0x585 | GPIO 21、20，gpio 模式，ds 8，pull-up |
| `ts_int_suspend` / `ts_reset_suspend` | 0x2f1 / 0x2f0 | GPIO 21 / 20，ds 2，pull-down |

### 6.2 驱动需要的 9 个 ADT 属性（pong schema，K60 DT 里没有）

| 属性 | 值 | 可信度 | 备注 |
|---|---|---|---|
| `spi-base` | 0x00990000 | 高 | 与 live FDT 一致 |
| `tlmm-base` | 0x0f000000 | 高 | **必须与 `gpio-offset` 相加**得 0x0f100000 |
| `gcc-base` | 0x00100000 | 高 | cape GCC，size 0x1f4200 |
| `rsc-base` | 0x17a20000 | 高（地址）/ **可访问性为零** | 填 drv-2 不是 drv-0；见 14.1 |
| `cmd-db-base` | 0x80860000 | 高（地址） | 运行时从未读过 |
| `gpio-offset` | 0x00100000 | 中 | pong schema 推导，K60 DT 无此属性 |
| `pins` | `<16 17 18 19 21 20>` | 高 | 顺序 = MISO/MOSI/CLK/CS/INT/RESET（**角色未逐线确认**） |
| `max-x` / `max-y` | 14400 / 32000 raw | 中 | 面板是 1440x3200，raw 是 10 倍量级；单位待核 |

三个必踩的坑（`K60-TOUCH-PARAMS.md` 原文）：

1. `tlmm-base` 与 `gpio-offset` 是**相加**关系。写 `tlmm-base=0x0f100000` 就必须把 `gpio-offset` 设为 0。
2. `rsc-base` 填 **0x17a20000**（drv-2），不是 0x17a00000（drv-0）；pong 的 TCS 计算 `rsc + 0xd00 + reg` 直接以 drv-2 为基址。
3. `max-x/max-y` 的 14400/32000 是 Goodix raw，**不是**面板像素；pong 原值 1080/2412 是面板像素，混用会把触摸点缩到左上角。

### 6.3 同 SoC 异板的 GENI SPI 对照

| 仓库 | 文件:行 | 事实 | 可信度 |
|---|---|---|---|
| phk110-port | `wave12-touch-buttons.md:58` | PHK110 的触摸：QUPV3 wrap1 **SE4**，控制器 `0x09900000` size 0x4000，GIC SPI 0x25d=605 level-high，节点 `/soc/spi@990000/synaptics_tcm_hbp@0` | 同SoC异板·已上机 |
| phk110-port | 同上 `:133-137` | TLMM 0x0f100000：MISO=16 / MOSI=17 / CLK=18 / CS=19（function 1 = qup4），INT=21 输入，RESET=20 低有效，VDD 负载开关=97 高开 | 同SoC异板·已上机 |
| phk110-port | 同上 `:141` | GENI SPI 用 FIFO 轮询，`touch_spi_hz` 默认 10 MHz | 同SoC异板·已上机 |
| phk110-port | 同上 `:106-108` | `drivers/input/hakios.goodix.c`（1538 行）是完整范本：TLMM 直写 + RPMh 调压 + GCC 投票开 GENI 时钟（DFS 预设表）+ FIFO 轮询 + 125 Hz 轮询 INT | 同SoC异板·已上机 |
| QcomGeniSpi | `GeniSpi.c:9-13` | SE 初始化清中断：`SE_GSI_EVENT_EN=0`，再清 M/S/DMA TX/DMA RX 的 IRQ 全 1 | 范本代码 |

⚠ PHK110 的触摸芯片是 **Synaptics TCM**，K60 是 **Goodix**。总线/时钟/引脚可直接参考，协议层（v2 头 CRC-6、v1 裸帧 0xA5..0x5A）**不能**照搬。

### 6.4 K60 侧触摸已经失败过的 8 个补丁（不要再走一遍）

全部在 `references/ios-sweet-k60/xnu/patches/`，作者结论是「触摸仍未修好」：

| 补丁 | 做了什么 | 结局 |
|---|---|---|
| `0240-k60-touch-pins-rpmh` | TLMM/GCC/SE/RSC/cmd-db 全套地址 + GPIO 16-21/71 + IOVDD ldoc2 1800 mV mode 7 | 头部自称 drv-2 可读 `DRV_ID=0x20700`，但 0246 说首读 TCS 整机死 —— **两者矛盾未定因** |
| `0241-k60-touch-geni-spi` | GCC 投票、halt、RCG、SPI 4 MHz、packing；三道闸门（vote 回读 / halt bit31 全清 / root clock 非 ROOT_OFF） | **stage 3/4/5 从未在真机执行** |
| `0242-k60-touch-goodix` | Berlin 读 `0xf1+4` 地址、写 `0xf0`；GT9xx 0x8140/0x814e/0x8150 双 ABI | **全仓库没有任何一条真机 `K60 TOUCH: ID:` 日志**（该前缀确实为零；但另一条路径 `goodix: chip ...` 有 71 次真机输出，见 6.0 —— 这条补丁的失败原因不是识别不到芯片） |
| `0243-k60-touch-hid-thread` | 分级 stage 1-5，默认 stage 2 | 未跑到 stage 5 |
| `0244-k60-rpmh-slot-probe` | 只读打印 TCS ctrl/enable/status/irqen | 只读安全 |
| `0245-k60-touch-irq-pullup-pins` | IRQ pull-down 改 pull-up | 未解决 |
| `0246-k60-touch-skip-rpmh` | 加 `k60rpmhoff=1` **整段跳过 RSC 投票** | **绕过不是修复**（注释：RSC 一个寄存器都读不得） |
| `0248-k60-rsc-address-probe` | `k60rscprobe=1` 只读探针，读 0x20000/0x20d00/0x20d14/0x20d1c/0x20d20/0x21000 | 只读安全 |

首次上机参数（`K60-TOUCH-PARAMS.md` ④）：`k60touchstage=4 k60rpmhoff=1 k60touchdelay=8 k60touchhz=4000000`。
**不要**加 `k60rscprobe=1`；**不要**在 `k60rpmhoff=0` 时用 stage≥2。

stage 4 的验收日志（前缀 `K60 TOUCH:`）：`se4 fw 0x102 version 2 protocol 1 (SPI=1)`、`se4 spi cfg word 0x4 mclk 0x51`、
`se4 status 0x0 fifo 64 words`、`abi berlin selected, axes 14400 x 32000, panel 1440 x 3200`、`stage 4: goodix id ok, abi 1`。
失败分支：`pins failed` / `clocks not ready stopping before SE` / `abi none: the chip answers neither framing`（先怀疑 IOVDD）。

## 7. 显示 / 背光

> **结论层**：`docs/research/display/RESEARCH.md` —— 面板 m11a / DSI / MDP / 5 条供电轨的可执行结论与缺口清单。本节 7.2–7.6 是它的证据行；改结论时两边一起改。

### 7.1 面板与画布（K60 自己的契约）

| 仓库 | 文件:行 | 事实 | 可信度 |
|---|---|---|---|
| yibiya-upstream | `patches/xnu/0210-k60-display-native-canvas.patch:12-16` | 原文注释：`The panel is 1440 x 3200, DSC video mode, 60 Hz. CoreAnimation takes its canvas from the mode this display publishes; a canvas that is not the panel's own pixel grid -- an iPhone-shaped 1125 x 2436, or the 1170 x 2532 of the 8 Plus class -- makes WindowServer's BoundingPathBitmap assert... So on this board the canvas is the panel` | 本板（K60 补丁） |
| yibiya-upstream | 同上 `:22-23` | `#define K60_PANEL_WIDTH 1440` / `#define K60_PANEL_HEIGHT 3200`，tunable `k60_panel` 默认 1 | 本板 |
| yibiya-upstream | 同上（`k60PanelNative()`） | 要求 `vinfo.v_width==1440 && vinfo.v_height==3200`，命中时打印 `K60 DISPLAY: fbwidth/fbheight/fbscale refused, the canvas is the panel` | 本板 |
| UniXNU-upstream | `docs/devices/zizhan.md:104` | 同 SoC 异板：SimpleFbDxe framebuffer=0xb8000000、**2160x1916**、继承 cont_splash_region —— **分辨率不同，不能套用** | 同SoC异板·已上机 |
| 本板 | `fdt_dump.txt:13` | bootargs `msm_drm.dsi_display0=qcom,mdss_dsi_m11a_42_02_0a_dsc_cmd:` → **设备实际启用 m11a 面板（phandle 0x6a3）**；`dsi-display-primary` 的 `qcom,dsi-default-panel=<0x697>`（`:28881`）是 visionox r66451 视频面板（`:22521`，1440x2340），**不是本机在用的那个** | 本板实测 |
| 本板 | `fdt_dump.txt:27733-27811` | m11a 节点：`panel-type="dsi_cmd_mode"`、`bpp=0x18`、`dsi-ctrl-num=0`/`dsi-phy-num=0`（单 DSI）、`mi,panel-id=<0x4d313141 0x420200>`（`M11AB`+0x02）、`brightness-max=0xfff`、`hbm-bl-max=0x7ff`、`bl-inverted-dbv`、`bl-pmic-control-type="bl_ctrl_dcs"`、`platform-reset-gpio=<&tlmm 0 0>`（GPIO 0）、`esd-err-irq-gpio=<&tlmm 0x74 0x2008>`（GPIO 116）、`reset-sequence=<1 11 0 1 1 11>` | 本板实测 |

### 7.2 面板节点（live FDT，本板实测）

**决定性证据：设备实际启用的面板是 m11a，不是通用参考面板。** bootargs（`fdt_dump.txt:13`）写着 `msm_drm.dsi_display0=qcom,mdss_dsi_m11a_42_02_0a_dsc_cmd:`；而 `dsi-display-primary` 的 `qcom,dsi-default-panel=<0x697>`（`:28881`）指向的是 visionox r66451 视频面板（`:22521` `qcom,mdss_dsi_visionox_r66451_fhd_plus_video`，1440x2340）。**照 `dsi-default-panel` 写代码会选错面板。**

| 属性 | 值 | 行 |
|---|---|---|
| `qcom,mdss-dsi-panel-name` | `xiaomi 42 02 0a cmd mode dsc dsi panel` | `:27811` |
| `qcom,mdss-dsi-panel-type` | `dsi_cmd_mode`（**command mode，不是 video mode**） | `:27810` |
| `qcom,mdss-dsi-bpp` | 0x18 = 24 | `:27807` |
| `qcom,dsi-phy-num` / `qcom,dsi-ctrl-num` | 0 / 0 → **单 DSI**（对照 sharp_qhd 是 <0 1>/<0 1>） | `:27802-27803` |
| `mi,panel-id` | `<0x4d313141 0x420200>` = ASCII `M11AB` + 0x02 | `:27771` |
| `qcom,mdss-brightness-max-level` / `bl-max-level` / `bl-min-level` | 0xfff / 0xfff / 0x1 | `:27739-27741` |
| `mi,hbm-bl-max-level` | 0x7ff（HDR 高亮上限，普通上限 0xfff） | `:27765` |
| `mi,normal-max-brightness-clone` / `mi,max-brightness-clone` | 0x1fff / 0x3fff | `:27769-27770` |
| `qcom,mdss-dsi-bl-pmic-control-type` | `bl_ctrl_dcs`（**背光走 DCS 命令，不是独立背光控制器**） | `:27742` |
| `qcom,mdss-dsi-bl-inverted-dbv` | DBV 反相 | `:27780` |
| `qcom,platform-reset-gpio` | `<&tlmm 0 0>` = **GPIO 0** | `:27738` |
| `mi,esd-err-irq-gpio` | `<&tlmm 0x74 0x2008>` = **GPIO 116**，下降沿 | `:27772` |
| `qcom,mdss-dsi-reset-sequence` | `<1 11 0 1 1 11>`（三组 电平/延时 ms） | `:27791` |
| TE | `te-using-te-pin` + `te-pin-select=1` + `te-dcs-command=1` + `wr-mem-start=0x2c`/`continue=0x3c`；TE 脚是 `dsi-display-primary` 的 `qcom,platform-te-gpio=<&tlmm 0x56 0>` = **GPIO 86** | `:27783-27788`、`:28884` |
| 物理尺寸 | `pan-physical-height-dimension=0x609`、`width=0x2b7`（单位 0.1 mm → 约 154.5 x 69.5 mm） | `:27789-27790` |
| `qcom,bl-update-flag` | `delay_until_first_frame`（首帧前不写亮度） | `:27779` |

### 7.3 面板 timing（live FDT，三档 60 / 90 / 120）

| timing 节点 | 行 | `panel-framerate` | `panel-width` | `panel-height` | `display-topology` | `phy-timings`(14B) | `mdp-transfer-time-us` |
|---|---|---|---|---|---|---|---|
| `timing@0` | `:27813` | 0x3c = **60** | 0x5a0 = 1440 | 0xc80 = 3200 | <2 2 1> | `00270a0a1b250a0b0b0a0204200f` | 0x1c84 = 7300 |
| `timing@1` | `:27910` | 0x5a = **90** | 0x5a0 | 0xc80 | <2 2 1> | `00270a0a1b250a0b0b0a0204200f` | 0x1c84 |
| `timing@2` | `:28007` | 0x78 = **120** | 0x5a0 | 0xc80 | <2 2 1> | `00270a0a1b250a0b0b0a0204200f` | 0x1c84 |

三档共用的参数（`timing@0` 的 `:27890-27907`，另两档同值）：`v-pulse-width=0xe`、`v-front-porch=0x10`、`v-back-porch=0x6`、`h-pulse-width=0xc`、`h-back-porch=0x8`、`h-front-porch=0x8`、`h-sync-skew=0`、`panel-clockrate=0x47868c00`（**1.2 GHz**）、`panel-jitter=<5 1>`。
DSC 参数（`:27871-27879`）：`block-prediction-enable`、`bit-per-pixel=0x8`、`bit-per-component=0xa`、`slice-per-pkt=0x2`、`slice-width=0x2d0`、`slice-height=0x20`、`scr-version=0x0`、`dsc-version=0x12`、`compression-mode="dsc"`。
命令包：on-command **1534 B**（`:27889`）、off-command 18 B `390000001400022800390000006400021000`（`:27888`）、timing-switch-command **98 B 且三档各不相同**（`:27885` / `:27982` / `:28079`）。

### 7.4 面板供电链（live FDT）

`qcom,panel-supply-entries = <0x6a2>`（`:27743`）→ `/soc/dsi_panel_pwr_supply_M11a`（`:28938`）三条 entry；再叠加 `dsi-display-primary` 的 4 个 regulator（`:28874-28877`）与一个 GPIO 开关。

| 轨 | 电压 | 由谁提供 | 行 |
|---|---|---|---|
| `vddio` | 1,800,000 µV（0x1b7740） | `pm8350c_l12` = **rpmh-regulator-ldoc12**，phandle 0x30a，`init-mode=4` | supply-entry@0 `:28942-28951`；regulator `:5224-5231` |
| `vddd` | 1,070,000 µV（0x1053b0） | `display_panel_vddd`（gpio-regulator，**GPIO 66** 高有效，`regulator-boot-on`） | supply-entry@1 `:28952-28961`；regulator `:28974-28982` |
| `vci` | 3,000,000 µV（0x2dc6c0） | `pm8350c_l13` = **rpmh-regulator-ldoc13**，phandle 0x30b，`init-mode=4` | supply-entry@2 `:28962-28972`；regulator `:5240-5247` |
| `extvdd` | 1,200,000 µV（0x124f80） | `pm8350b_l1` = **rpmh-regulator-ldod1**，phandle 0x30e | `:28875`；regulator `:5282-5289` |
| `avdd`（`display_gpio_regulator@1`） | 5,500,000 µV（0x53ec60） | GPIO **186**（0xba）高有效，`ramp-delay=0xe9`（233 µs），`proxy-consumer-enable` | `:28912-28925` |

时序（supply-entry）：`vddio` post-on 0x14=20 ms / post-off 0xa=10 ms、enable-load 0x493e0；`vci` pre-on 0xa=10 ms / post-on 0xf=15 ms。
**这 5 条轨里有 3 条是 RPMh LDO 投票** → 与第 3 节、第 14.1 节同一个阻塞点：RSC 不可访问之前，面板供电只能在 bootloader 已开的状态下沿用。

### 7.5 DSI 控制器 / PHY / MDP 基址（live FDT）

| 块 | 基址与长度 | 关键属性 | 行 |
|---|---|---|---|
| DSI ctrl0 | `0xae94000+0x400`、`0xaf0f000+0x4`、`0xae36000+0x300` | `qcom,dsi-ctrl-hw-v2.6`、`vdda-1p2-supply=0x233`、`interrupts=<4 0>` | `:28107-28120` |
| DSI phy0 | `0xae94400+0xa00`、`0xae94900+0x400`、`0xae94200+0xa0` | `qcom,dsi-phy-v4.3.2`、`pll-label="dsi_pll_5nm"`、`vdda-0p9-supply=0x232`、`platform-regulator-settings=1d1d1d1d1d`、`platform-lane-config=<0xa0a 0xa0a 0xa0a 0xa0a 0x8a8a>` | `:28161-28176` |
| MDP | `0xae00000+0x84000`、`0xaeb0000+0x2008`、`0xaeac000+0x800` | `/soc/qcom,mdss_mdp@ae00000` | `:21793`、`:21958` |

### 7.6 背光（K60 走 DCS；Pong 的 NT37705 只作结构参照）

| 仓库 | 文件:行 | 事实 | 可信度 |
|---|---|---|---|
| pong-power | `PongBacklight.cpp:2` | `// Pong NT37705 DCS brightness.` | 同SoC异板 |
| pong-power | `PongBacklight.cpp:336` | 控制器判据 `board.version != 1 \|\| board.base != 0xae94000 \|\| board.span != 0x400` → **背光控制器基址 0x0ae94000（0x400）** | 同SoC异板 |
| pong-power | `PongBacklight.cpp:135` `:141` `:321` | DCS 包常量 `0x80370002`、`0xa0060052`、`0xc0390003` + `0xff000051 \| (wire<<8)` | 同SoC异板 |
| pong-power | `PongBacklight.cpp:171` | `// NT37705 returns DBV most-significant byte first.` | 同SoC异板 |
| pong-power | `PongBacklight.cpp:238` | 淡入淡出：`fadeStart=nowNs(); fadeDuration=(latest & 0xffff)*1000000ULL;` | 同SoC异板 |
| pong-power | `PongBacklight.cpp:218` | 成功日志 `PongBacklight: NT37705 DCS service ready, level=%u max=%u, readback PASS` | 同SoC异板 |

✅ **K60 的面板 XML 已找到（2026-11-14 更正本节与 14.6 / 15 节）。** 面板 = xiaomi **m11a**（`mi,panel-id` = `M11AB`/0x42/0x02），1440x3200、DSC、command mode、单 DSI、三档 60/90/120。厂商 XML 在 `Device-Binaries/marble/RawFiles/Panel_M11a_42_02_0a_amoled_dsc_cmd.xml` —— **它不在仓库根，而在 `marble/`（Xiaomi 13）子目录下**；先前「2,117 个无一匹配」是只按根目录/命名猜的方法错误（没跑 `git ls-files | grep -i m11a`）。逐包比对见 7.7。

### 7.7 K60 的厂商面板 XML（2026-11-14 找到并逐包比对）

| 项 | 值 |
|---|---|
| 路径 | `Device-Binaries/marble/RawFiles/Panel_M11a_42_02_0a_amoled_dsc_cmd.xml` |
| 大小 / 行数 / sha256 | 4,799 B / 203 行 / `65cd6826a2abcce28db60b7d82ab34aa9fa8ecd2aa82f5fc4f21f9853b4be482` |
| 引入提交 | `a1501e0c2e642d6ac0d8f52c85af2a67b75a7799` "gts9wifi: Initial support (#202)"（2026-10-04） |
| 仓库 | `Device-Binaries` HEAD `d3f7cb72`（main）；`git ls-files "*/RawFiles/Panel_*.xml"` = **2,117** 个，文件名含 `m11a` 的**恰好 1 个** |
| 为什么以前没找到 | 它不在仓库根，而在 `marble/` 目录下；先前只按根目录与命名猜，没做 `git ls-files | grep -i m11a` |

**XML 静态字段与 live FDT 逐项一致**（这是「就是这块面板」的依据）：

| 字段 | XML | live FDT（`timing@0`） |
|---|---|---|
| 分辨率 | H=1440 / V=3200 | `panel-width=0x5a0` / `panel-height=0xc80` |
| porch | hfp=8 hbp=8 hsync=12 / vfp=16 vbp=6 vsync=14 | `h-front-porch=0x8` `h-back-porch=0x8` `h-pulse-width=0xc` / `v-front-porch=0x10` `v-back-porch=0x6` `v-pulse-width=0xe` |
| DSC | Major=1 Minor=2 / slice 720x32 / per-pkt 2 / bpp 8 / bpc 10 | `dsc-version=0x12` / `slice-width=0x2d0` `slice-height=0x20` `slice-per-pkt=0x2` `bit-per-pixel=0x8` `bit-per-component=0xa` |
| 时钟 | `DSIBitClockFrequency=1200000000` | `panel-clockrate=0x47868c00` = 1,200,000,000 |
| lane | `DSILanes=4` | `lane-0..3-state` 四条齐全 |
| 面板 ID | 文件名 `M11a_42_02_0a` | `mi,panel-id=<0x4d313141 0x420200>` = `M11AB` + 0x42 + 0x02 |

**逐包比对结论：同族但不同修订，不能直接当 init 串用。** XML `DSIInitSequence` 有 131 行，其中 2 行是 `FF <ms>` 延迟——DTB 把延迟放进**前一个包的 wait 字节**（7 字节头 `<type> 00 00 <wait> <len_hi> <len_lo>`，wait 在偏移 4、长度是 16 位大端在偏移 5-6），合并后 XML = **129 包**。对 live FDT `timing@0` 的 135 包做 LCS：**125 包完全相同，只有 3 处差异**：

| 差异 | XML | live FDT |
|---|---|---|
| 删 3 包 | `39 f055aa520801`、`15 6f02`、`15 d22a`（第 17–19 包） | — |
| 插 9 包 | — | `39 f055aa520801`、`39 d20000000015`、`15 6f05`、`39 d2010000`、`15 6f0e`、`39 d20000101332`、`39 e480030000000000000033`、`15 6f0a`、`39 e4800300100053`（第 42–50 包） |
| 改 1 包类型 | `39 6f46`（长写） | `15 6f46`（短写） |

延迟语义的独立佐证：DTB `off-command` = `39 00 00 00 14 00 02 28 00` + `39 00 00 00 64 00 02 10 00`，即 wait=20 ms 后发 `0x28`、wait=100 ms 后发 `0x10`；XML `DSITermSequence` 正是 `05 28 / FF 14 / 05 10 / FF 64`。

全仓 2,117 个 XML 用同一套 wait-aware LCS 打分，第二名是 `nuwa/RawFiles/Panel_M11_42_02_0a_dsc_cmd.xml`（125/134，但有 6 处差异），其余全部 ≤4 包相同。→ **marble 这份是本板最接近的公开 XML**，但 init 序列仍是另一个修订；要用它必须先补上表里 3 处差异。

---

## 8. GPU / Adreno

| 仓库 | 文件:行 | 事实 | 可信度 |
|---|---|---|---|
| pong-adreno | `PongAdrenoRegisters.h:1` | 头注释：`Register facts from NothingOSS SM8475 gen7_reg.h. Dword offsets.` | 同SoC异板 |
| pong-adreno | `PongAdrenoRegisters.h:3-14` | GMU 寄存器（dword 偏移）：`GMU_CM3_BOOT_CONFIG 0x1f801`、`GMU_CM3_CFG 0x1f82d`、`GMU_CM3_FW_INIT_RESULT 0x1f81c`、`GMU_CM3_SYSRESET 0x1f800`、`GMU_HFI_CTRL_STATUS 0x1f980`、`GMU_HFI_CTRL_INIT 0x1f986`、`GMU_AHB_FENCE_RANGE_0 0x23b11` | 同SoC异板 |
| pong-adreno | `PongAdrenoGmu.c:11` | GMU 映射窗口 `{0x03d00000,0x40000},{0x03d68000,0x37000},{0x03d50000,0x10000}` | 同SoC异板 |
| pong-adreno | `PongAdrenoGmu.c:50` | `if(reg==GEN7_GMU_CM3_FW_INIT_RESULT && (v&0xe00)) return PongGpuIo;` —— 固件初始化失败位 | 同SoC异板 |
| pong-adreno | `PongAdrenoPlatform.cpp:318` `:326` | GPU 寄存器基址 `0x03d00000 + reg*4` | 同SoC异板 |
| pong-adreno | `PongAdrenoPlatform.cpp:291` | GPU SMMU 基址 `0x03da0000` | 同SoC异板 |
| pong-adreno | `PongAdrenoPlatform.cpp:279` | IOVA 表 `{0x4000, 0x60000000, 0x60002000, 0x60006000}`（cache/dummy/hfi/logmem） | 同SoC异板 |
| pong-adreno | `PongAdrenoPlatform.cpp:207` | 注释：Shared ASID 命名空间，reserve 1 给 GMU、2 给 GPU，互相独立 | 同SoC异板 |
| pong-adreno | `PongAdrenoPlatform.cpp:344` | `map(gcc,0x100000,0x1f4200) && map(rsc,0x17a20000,0x10000) && map(db,0x80860000,0x20000)` —— GPU 也用同一组窗口 | 同SoC异板 |
| pong-adreno | `PongAdrenoClocks.c:2` `:79` `:96` `:119` | 注释：Cape 时钟与 GDSC 事实来自 Nothing 的 `gpucc-waipio.c`；`qcom,cape-gpucc` DT 节点；HFI START 后 GMU 固件接管使能/改频；电源状态在独立的 `HW_CTRL 0x953c`，**不是 GDSCR bit31** | 同SoC异板 |
| pong-adreno | `PongAdrenoScanout.cpp:43` | `extern "C" void pong_scanout_initialize(address,bytes,stride,width,height)` | 同SoC异板 |
| live FDT | `fdt_dump.txt:727` | `clock-controller@3d90000`（GPUCC） | 本板实测 |
| live FDT | `fdt_dump.txt:10523` `:10876` | `qupv3_0_geni_se@9c0000` / `qupv3_1_geni_se@ac0000`（GPU 无关，列此备查） | 本板实测 |

⚠ **`PongAdrenoPlatform.cpp:181` 的时钟校验在本板不成立**：
`return !parents_ready || !(rd(gcc,0)&0x80000000) || rate!=600000000;` —— 它硬要求 600 MHz，而 K60 的 Adreno 最高 900 MHz。照抄会让 GPU 启动直接判失败。

---

## 9. 存储（UFS）

> **结论层**：`docs/research/storage/RESEARCH.md` —— UFS PHY / 控制器 / 中断的候选值与「哪些不能跨板抄」。本节 9.1 是双源交叉验证的证据行。

| 仓库 | 文件:行 | 事实 | 可信度 |
|---|---|---|---|
| pong-ufs | `PongUfsTransport.cpp:157` | UFS host controller 基址 `0x01d84000`（0x3000） | 同SoC异板 |
| pong-ufs | `PongUfsTransport.cpp:190` | APPS SMMU `0x15000000`（0x100000） | 同SoC异板 |
| pong-ufs | `PongUfsTransport.cpp:219-238` | 初始化序列：QUERY power mode → SCSI `0xd0` START STOP UNIT → TEST UNIT READY 轮询 → READ CAPACITY，**要求 blockSize==4096** 否则 `unsupported LUN geometry` | 同SoC异板 |
| pong-ufs | `PongUfsTransport.cpp:54-55` | LUN0 4K LBA 范围 `0x413248 .. 0x75a40ea` | 同SoC异板 |
| pong-ufs | `PongUfsTransport.cpp:240` | 就绪日志 `PONG_UFS: transport ready LUN=0 block=4096 blocks=%llu; WRITE(10) FUA=%s; writes stay inside declared SHNGROOT windows` | 同SoC异板 |
| pong-ufs | `RootLayout.h:67` | GPT 头校验 `le32(gScratch)!=0x20494645("EFI ") \|\| le32(+4)!=0x54524150("PART") \|\| le32(+84)!=128` | 同SoC异板 |
| pong-ufs | `RootLayout.h:72` | 分区项大小 `0x00010000`，headerBytes ∈ [92, 4096] | 同SoC异板 |
| pong-ufs | `RootLayout.h:157` | 窗口 magic `0x474e4853` / `0x544f4f52` = `"SHNGROOT"` | 同SoC异板 |
| uefi-mondrian | `MemoryMapLib.c:111` | `{"SMMU", 0x15000000, 0x00200000, ...}` —— **K60 的 SMMU 窗口是 2 MiB，Pong 驱动只映射 1 MiB** | **本板实测** |
| yibiya-upstream | `configs/mondrian_defconfig:28` | `CONFIG_XNU_NATIVE_UFS=y`；`:46` `CONFIG_XNU_OWNER_DATA_VOLUME_UUID="E313398B-D70A-4EB8-9425-4B1A7BE3E1F5"`；`:55` `CONFIG_XNU_PONG_RAMOOPS_CONSOLE=y` | 本板 |
| UniXNU-upstream | `docs/devices/mondrian-mzyxsl.md:45`（另见 `:249`） | 官方记录里的 `board.toml [userdata]`：**first_lba 53342976 / last_lba 61731583 / lba_bytes 4096**，窗口 OS + Cryptex1,SystemOS | 官方（fork 自报） |
| ShengUfs | `NativeUfs.cpp`（148,723 B） | 官方完整实现，但**硬编码 SM8550**，不能整体替换；`RootCommands.h`（29,932 B）与 `tests/` 下 12 个测试是移植范本 | 官方 |

### 9.1 跨板交叉验证：liuqin（同 SM8475，Xiaomi Pad 6 Pro）

`UniXNU-liuqin` 是另一块 SM8475 板，板级数值从 stock 固件与其 live FDT 核实过，**和 K60 自己的 live FDT 逐条吻合**，所以下面这几条从「单点」升到「两处独立来源一致」。

| 事实 | liuqin 出处 | K60 侧出处（`fdt_dump.txt` 行号） |
|---|---|---|
| **UFS PHY 基址 0x1d80000**（不是 SM8450 的 0x1d87000） | `docs/liuqin-hardware.md:23`（另 `board.toml:103`） | `:9577` `/soc/ufsphy_mem@1d80000`、`:9578` `reg=<0x1d80000 0x2000>` |
| UFS PHY compatible `qcom,ufs-phy-qmp-v4-cape` | `docs/liuqin-hardware.md:23` | `:9587` |
| UFS PHY 供电 vdda-phy / vdda-pll | — | `:9588` `vdda-phy-supply=<0x232>`、`:9589` `vdda-pll-supply=<0x233>`、`:9590` max 0x30188 µA、`:9591` max 0x5c94 µA |
| UFS 控制器 0x1d84000（+ ICE 0x1d88000 / HWKM 0x1d90000） | —（liuqin 只核了扇区大小：`docs/liuqin-hardware.md:4`，1TB SK Hynix HN8T35DZHKX079、4096 B 逻辑/物理扇区） | `:9593-9596` `reg=<0x1d84000 0x3000 0x1d88000 0x8000 0x1d90000 0x9000>`、`reg-names=ufs_mem,ufs_ice,ufs_ice_hwkm` |
| UFS 中断 GIC SPI 0x109（265）level high | — | `:9597` `interrupts=<0 0x109 4>` |
| UFS 通路亲和 `prime-mask 0x70` / `silver-mask 0xf`、lanes 2 | — | `:9601-9603` |
| **PMIC 家族 = pm8350 / pm8350b / pm8350c / pm8450 / pmk8350 / pmr735a**（SM8450 waipio 那套，**不是** SM8550 那套） | `docs/liuqin-hardware.md:22` | `:8121` `pmk8350@0`、`:8535` `pm8350@1`、`:8576` `pm8350c@2`、`:8808` `pm8350b@3`、`:8973` `pmr735a@4`、`:8998` `pmr735b@5`、`:9022` `pm8450@7` |
| ADSP 保留区 `0x9fd00000 + 0x3100000` | `docs/liuqin-hardware.md:21` | `MemoryMapLib.c:34`（`{"adsp_region", 0x9FD00000, 0x03100000, ...}`） |
| ramoops `0xa7000000 + 0x400000` | `docs/liuqin-hardware.md:19` | `MemoryMapLib.c:38` |
| xbl_ramdump `0xa6b80000+0x280000` / xbl_sc `0xa6e00000+0x40000` | `docs/liuqin-hardware.md:20` | `MemoryMapLib.c:35-36` |
| ABL splash framebuffer `0xb8000000 + 0x2b00000`（45 MiB） | `docs/liuqin-hardware.md:18`（`board.toml` 同值） | `MemoryMapLib.c:52` Display Reserved |
| UEFI FD 窗口 `0xA7000000 + 0x400000`（+ Reserved `0xA7400000+0x200000`） | `docs/liuqin-hardware.md:36` | K60 是 `Resources/Configs/mondrian.toml:9-13` 的 `0xA7400000 + 0x300000` —— **K60 把 FD 挪开以避开 ramoops**，布局不同但都自洽 |
| DXE Heap `0xF8000000 + 0x7C00000` | `docs/liuqin-hardware.md:40` | K60 是 `0xC7000000 + 0x18000000`（`MemoryMapLib.c:83`）—— **不同板不同值，不能互抄** |
| 共享 IMEM `0x146AA000`、`UefiMemUseThreshold 0x1900`、`SecPagePoolCount 0x800`、NumCpus 8 | `docs/liuqin-hardware.md:41/:43` | `ConfigurationMapLib.c` 同名项同值 |

**怎么用**：UFS 那几条以前只有 Pong 的控制器地址（`PongUfsTransport.cpp:157` 的 `0x01d84000`）可参照，现在 PHY 基址 0x1d80000 与 `qmp-v4-cape` compatible 有第二份独立确认，写驱动时可直接用。反过来 **DXE Heap / Kernel 预留区不要跨板抄**（liuqin 0xF8000000 vs K60 0xC7000000）。

**顺带线索**：liuqin 的面板 XML 名是 `Panel_M81_42_02_0b_dualdsi_dsc_lcd_video.xml`（`docs/liuqin-hardware.md:44`），和 K60 的 `M11a_42_02_0a` 是同一套 mi 命名法（`<项目>_<42>_<02>_<0a/0b>`），找 K60 面板 XML 时可按这个形状搜。

---

## 10. USB（DWC3）

| 仓库 | 文件:行 | 事实 | 可信度 |
|---|---|---|---|
| pong-usb | `Dwc3Registers.h:9-14` | 分区：XHCI 0x0000、GLOBALS 0xC100..0xC6FF、DEVICE 0xC700..0xCBFF、OTG 0xCC00 | 同SoC异板 |
| pong-usb | `Dwc3Registers.h:17-22` | `GSBUSCFG0 0xC100`、`GCTL 0xC110`、`GEVTEN 0xC114`、`GSTS 0xC118`、`GSNPSID 0xC120`、`GUID 0xC128` | 同SoC异板 |
| pong-usb | `Dwc3Registers.h:87-88` | `GSNPSID_MASK 0xFFFF0000`、`GSNPSID_DWC_USB3 0x55330000` | 同SoC异板 |
| uefi-mondrian | `MemoryMapLib.c:108` | `{"USB", 0x0A600000, 0x00200000, AddDev, MMAP_IO, ...}` | **本板实测** |
| uefi-mondrian | `FdtBlob/Source.txt` | DTB 由 `sm8450-mainline/linux` 的 `tyalie` 分支编译，含 `usb-role-switch`，第 1003 行加入以修 USB OTG Mode | 本板（固件注释） |
| phk110-port | `wave13-usb-host.md`（216 行） | Windows → libusb → loader USB gadget `18d1:d00d` 的完整工具链 | 同SoC异板·已上机 |

---

## 11. 电池 / launchd

### 11.1 PMIC GLINK 电池

| 仓库 | 文件:行 | 事实 | 可信度 |
|---|---|---|---|
| pong-power | `ShengBattmgr.c:1` | 注释：`NothingOSS qti_battery_charger.c standard property IDs; no Xiaomi extensions or charger writes.` | 同SoC异板 |
| pong-power | `ShengBattmgr.c:5` | 属性 ID：`TEMP=12`（deci-C）、`CHG_COUNTER=14` | 同SoC异板 |
| pong-power | `ShengBattmgr.c:215` | 注释：`0xe0004000 + n`: host 0 / DCP 4 / CDP 5 / unknown 7 / Type-C 9 / PD 10 | 同SoC异板 |
| pong-power | `ShengBattmgr.c:219` | `case 1: return 0xe0004000u;`（host）；`:219-224` 完整映射 | 同SoC异板 |
| pong-power | `ShengBattmgr.c:70` | 请求包 `put32(out+12, 0); /* battery 0 */` | 同SoC异板 |
| pong-power | `ShengBattmgr.c:55` 起 | 导出 `sheng_battmgr_init/enable_request/refresh/next/timeout/receive` | 同SoC异板 |
| UniXNU-mondrian | `docs/research/battery/RESEARCH.md` | 解锁链 PAS1 → GLINK → PMIC GLINK → 电池协议 → IOPMPowerSource，**跳不过去**；官方 power 页给了六步流程与单位转换 | 官方 + 本项目调研 |

⚠ `ShengBattmgr.c` 明确写着「无小米扩展、无充电写入」——**K60 是小米机器**，充电器协议（PD/PPS、Mi Turbo Charge）大概率不同。

### 11.2 launchd / hw.target

| 仓库 | 文件:行 | 事实 | 可信度 |
|---|---|---|---|
| phk110-port | `wave20-launchd.md` | 根因链：dyld 内嵌 libignition 启动时 `sysctlbyname("hw.target")`，`kern_mib.c:502-508` 在 `PEGetTargetName` 返回 false 时直接 `return EINVAL(22)`，libignition 拿到非 0 errno 即让 launchd 退场。`PEGetTargetName` 走 `IOPlatformExpert.cpp:944` → `IODTPlatformExpert`，DT 根无 `model` 属性时失败。双层修复：loader 用真身份（`xnuloader/mkidentity.sh`）+ 内核加 `hw_target` boot-arg fallback | 同SoC异板·已上机 |

## 12. 本板真值汇总（可直接引用，最高可信度）

> **结论层**：`docs/research/memory/RESEARCH.md` —— DDR 保留区、寄存器窗口，以及**跨板边界**（哪些值绝不可跨板抄）。本节是它的证据行。

来源：`uefi-mondrian/Platforms/Xiaomi/mondrianPkg/Library/MemoryMapLib/MemoryMapLib.c`（2026-10-27 实测生成）+ 设备 6033dbec 的 live FDT。

### 12.1 DDR 保留区（会挡住别人写代码的那些）

| 名称 | 基址 | 大小 | 行 |
|---|---|---|---|
| `video_region` | 0x85700000 | 0x00700000 | `MemoryMapLib.c:22` |
| `adsp_region` | **0x9FD00000** | **0x03100000** | `:34` |
| `SMEM` | 0x80900000 | 0x00200000 | `:19` |
| `aop_cmd_db_region` | 0x80860000 | 0x00020000 | `:14` |
| `ramoops` | 0xA7000000 | 0x00400000 | `:38` |
| `ABL Staging` | 0xA8300000 | 0x0FD00000 | `:51`（注释 :39-50 解释 ABL 在此停 DTB 与拼接 initrd，无 descriptor 时 level-2 translation fault） |
| `Display Reserved` | 0xB8000000 | 0x02B00000 | `:52` |
| `Kernel` | 0xBB000000 | 0x0C000000 | `:75` |
| `DXE Heap` | 0xC7000000 | 0x18000000 | `:83`（注释 :76-82：DarwinBoot 要一段连续 256 MiB，320 MiB 堆时报 biggest run 0xF0A0000） |
| `XNU High Arena` | 0x900000000 | 0x140000000 | `:94`（注释 :85-93：高 DDR 在 >= 0x800000000，`[0x100000000,0x800000000)` 是空洞，只暴露实测连续的 8 GiB） |

其中 `adsp_region`、`ramoops`、`xbl_ramdump`/`xbl_sc`、`Display Reserved` 四条在 liuqin（另一块 SM8475 板，Xiaomi Pad 6 Pro）的 stock 固件里是**同值**，属跨板交叉验证，见 9.1。`DXE Heap` 与 `Kernel` 则**不同板不同值**，不要跨板抄。

### 12.2 寄存器区窗口

| 名称 | 基址 | 大小 | 行 | 与本文其它章节的关系 |
|---|---|---|---|---|
| `QUP` | 0x00800000 | 0x00300000 | `:103` | 触摸 SPI 0x990000 在其内 |
| `USB` | 0x0A600000 | 0x00200000 | `:108` | 第 10 节 |
| `AOSS` | 0x0B000000 | 0x04000000 | `:109` | 第 4.1 节 `kAoss=0xc300000` 在其内 |
| `TLMM` | 0x0F000000 | 0x01000000 | `:110` | 第 6 节 gpio |
| `SMMU` | 0x15000000 | 0x00200000 | `:111` | 第 9 节 |
| `APSS_HM` | 0x17000000 | 0x02000000 | `:112` | RSC 0x17a00000 在其内 |
| `PMIC ARB SPMI` | 0x0C400000 | 0x2800000 | `:65` | 第 3.3 节 |

### 12.3 固件与启动配置

| 文件:行 | 事实 |
|---|---|
| `MemoryMapLib.c:63` | `UEFI FD 0xA7400000 + 0x300000`（与 `Resources/Configs/mondrian.toml:11-13` 一致） |
| `Resources/Configs/mondrian.toml:9` | 注释：K60 UEFI FD 挪到 0xA7400000，ramoops 占 0xA7000000，冲突规避 |
| `Resources/Configs/mondrian.toml:26-27` | `[boot_image] header_version = 4`（K60 stock boot.img 为 v4）；`:18-20` kernel gzip + `append_dtb = true` |
| `Include/RAW.inc:1-5` | 注释原文：`the SecParti.cfg and the ~72 Panel_*.xml below are the pong generic display library (Binaries/pong/RawFiles). None match the K60 1440x3200 panel; they are inert today... Before enabling a vendor display driver, replace them with the K60 panel XML extracted from the K60 dispdcbx partition or device tree.` |
| `FdtBlob/Source.txt` | DTB 来自 `sm8450-mainline/linux` 的 `tyalie` 分支，含 `usb-role-switch`，第 1003 行加入以修 USB OTG Mode |
| `mondrian.fdf:114` | `SECTION RAW = mondrianPkg/FdtBlob/sm8475-xiaomi-mondrian.dtb`（`FILE FREEFORM = 25462CDA-221F-47DF-AC1D-259CFAA4E326`，`SECTION UI = "DeviceTreeBlob"`，由 `EmbeddedPkg/Drivers/DtPlatformDxe` 消费）→ **本板 UEFI 跑的是编进固件的 mainline 派生 DTB，不是厂商 DTB** |
| `mondrian.dsc:83` | 内存表的唯一来源：`MemoryMapLib\|mondrianPkg/Library/MemoryMapLib/MemoryMapLib.inf`。改内存表只改 `MemoryMapLib.c` |
| `RawFiles/uefiplat.cfg`（**已删除**） | 2026-10-28 由 `43e245ea16b4dfa57c4295739b8fc1eb9d11a0a6`（"mondrian: repo hygiene"）删除；`git grep uefiplat` 现在全树**零命中** → 它既不参与构建，也不是内存表来源。旧快照可恢复：`git show 43e245e^:Platforms/Xiaomi/mondrianPkg/RawFiles/uefiplat.cfg`（81 行，2026-10-27 从 live FDT 生成），但其 `Kernel 0xBB000000+0x10000000`、`DXE Heap 0xCB000000+0x4000000` 与现行 `MemoryMapLib.c:75/:83` **不同**，**不要引用旧值** |

### 12.4 高频 FDT 节点（`fdt_dump.txt` 行号）

| 行 | 节点 | 用途 |
|---|---|---|
| `:58` | `aop_cmd_db_region@80860000` | cmd-db |
| `:84` | `smem_region@80900000` | SMEM |
| `:727` | `clock-controller@3d90000` | GPUCC |
| `:1138` | `bt_qca6490` | 蓝牙 |
| `:1182` | `pinctrl@f000000` | TLMM（phandle 0x3c） |
| `:3613` | `cnss_pins` / `cnss_wlan_en_active` | WiFi 电源脚 |
| `:4698` | `rsc@17a00000` | RPMh RSC |
| `:8106` | `qcom,spmi@c42d000` | SPMI 仲裁器 |
| `:8121` `:8127` | `pmk8350@0` / `pon_hlos@1300` | 按键 PON |
| `:9272` | `ipcc@ed18000` | IPCC |
| `:9281` `:9301` `:9320` `:9327` `:9342` | `remoteproc-adsp@03000000` → `glink-edge` → `pmic_glink_rpmsg` / `qcom,gpr` / `q6prm` | ADSP 链 |
| `:10479` | `cnss-qca6490@b0000000` | WiFi |
| `:10523` `:10876` | `qupv3_0_geni_se@9c0000` / `qupv3_1_geni_se@ac0000` | GENI SE |
| `:10729` | `spi@990000` | 触摸 SPI |
| `:10748` | `xiaomi_touch@0` | 触摸本体 |
| `:10774` | `i2c@994000`（`fsa4480@42`、`eusb2_repeater@4f`） | USB Type-C 开关 |
| `:11228` `:11240` | `aw882xx_smartpa@34` / `@35` | Smart PA |
| `:16407` | `pcie@1c00000` | WiFi PCIe |
| `:19556` | `spf_core_platform` → `lpass-cdc` | 音频 codec |
| `:21793` `:21958` | `qcom,mdss_mdp@ae00000`（reg 0xae00000+0x84000 等） | 显示 MDP |
| `:22033` | `qcom,mdss_dsi_sharp_qhd_plus_dsc_cmd`（phandle 0x6a4） | 通用参考面板，**yibiya 120Hz 文档抄的是这个** |
| `:22521` | `qcom,mdss_dsi_visionox_r66451_fhd_plus_video`（phandle 0x697） | `dsi-default-panel` 指向它，**本机并未启用** |
| `:27733` | `qcom,mdss_dsi_m11a_42_02_0a_dsc_cmd`（phandle 0x6a3） | **K60 实际面板**，见 7.2–7.5 |
| `:28107` `:28161` | `mdss_dsi_ctrl0@ae94000` / `mdss_dsi_phy0@ae94900` | DSI 控制器 / PHY |
| `:28872` | `qcom,dsi-display-primary` | 面板与 regulator/TE 的绑定点 |
| `:28938` | `dsi_panel_pwr_supply_M11a` | 面板三条 supply entry |
| `:28912` | `display_gpio_regulator@1`（avdd，GPIO 186） | 面板 avdd 开关 |

---

### 12.5 两个 DTB 的结构化差异：编进固件的 vs 设备实测的（2026-11-14）

本板存在**两棵** DTB，用途不同，混用会得出错误结论：

| | `FdtBlob/sm8475-xiaomi-mondrian.dtb`（编进固件） | `live-6033dbec-fdt.dtb`（设备实测） |
|---|---|---|
| 位置 | `uefi-mondrian/Platforms/Xiaomi/mondrianPkg/FdtBlob/` | `/mnt/e/k60-work/reports/` |
| 字节 / sha256 | 480,692 / `d09f4f10bb84d0e5481433b61bc969ea31b793ead394da18a5363d2e9d4b655c` | 919,210 / 见 1.1 路径映射 |
| 来源 | `sm8450-mainline/linux` `tyalie` 分支 + `usb-role-switch` 补丁 | 设备 `fastboot boot` 时 ABL 交接的厂商 DTB |
| 节点数 | **3,034** | **4,206** |
| `/reserved-memory` 带 reg 的区域 | 36 | 38 |
| `mdss@ae00000` 直接子节点 | **4** | **34** |
| 其中 DSI 面板节点 | **0** | **30** |

解析方法（`fdt_dump.txt` **不能**用于逐字节比对，它会截断长 hex 串）：纯 Python FDT 解析器 `/mnt/e/k60-work/scratch/refmine/treeparse.py`，`parse(fn) -> (data, nodes, props)`。要点：头 10 个 BE u32 依次是 magic、totalsize、**off_struct**、**off_strings**、off_rsv、version、last_comp、bootcpuid、**size_strings**、**size_struct**；BEGIN_NODE 后 name 与 PROP 值之后都要 4 字节对齐。

三条结论：

1. **保留区表两棵树是同一套**：36 条同名区域**地址与大小逐条相同**，无一条「同名不同址」。live 侧只多两条运行时才填的：`ramoops@0xa7000000`（0xA7000000+0x400000）与 `splash_region`（0xB8000000+0x2B00000）；树内 DTB 里 `ramoops_region` 的 `alloc-ranges` 是全 0/全 F 的动态分配。→ 引用保留区时两棵树可互换，但**要用写死地址就用 live 侧**。
2. **面板信息只在 live 侧**：树内 DTB 的 `mdss` 只有 4 个直接子节点（`qcom,platform-supply-entries`、`qcom,sde-dspp-blocks`、`qcom,sde-sspp-dma-blocks`、`qcom,sde-sspp-vig-blocks`），**一个面板都没有**；live 侧 34 个直接子节点里 30 个是 `qcom,mdss_dsi_*`（含本板的 `qcom,mdss_dsi_m11a_42_02_0a_dsc_cmd`，另有 l1/l2s/l18/l3s/m16t、r66451、sim/dual_sim 系列）。→ **做显示不要指望树内 DTB**；m11a 的 init 串只能从 live DTB 或 `dispdcbx` 取（7.7）。
3. **`/chosen` 只差运行时字段**：树内只有 `bootargs`/`phandle`/`stdout-path`，live 多 `kaslr-seed`、`linux,initrd-start`、`linux,initrd-end`；两边 `bootargs` 前缀**完全相同**。→ 树内 DTB 就是 live 那份的「去掉面板与运行时填充」版本，与 `Source.txt` 的 mainline 出处自洽。

复现脚本（都在 `/mnt/e/k60-work/scratch/refmine/`）：`treeparse.py`（解析器）、`resmem.py`（按地址打印保留区）、`dtbdiff.py`（两树保留区集合差 + mdss 子节点）、`mdss_count.py`（上表的计数）。

---

## 13. 官方记录（`UniXNU` 的登记表 + `references/UniXNU-upstream` 的设备页，可信但需辨别）

| 仓库 | 文件:行 | 事实 | 可信度 |
|---|---|---|---|
| UniXNU | `devices.toml:1585-1598` | `[[device]] name=mondrian repository=Emilelu/UniXNU-mondrian format=2 revision=c39ff292... board=mondrian soc=SM8475 os_profile=ipados-16.6.1-20G81 components=[ArmDTPlatform,ArmCpu,XnuPrelink,PongUfs] record_state=available`；另有 3 个 fork 记录（mondrian-mzyxsl :1600、mondrian-wohusaixing :1616、mondrian-xtom0706 :1631） | 官方（fork 自报） |
| UniXNU-upstream | `docs/devices/mondrian.md` | 只有 7 行的 hub 页：链到 `Emilelu/UniXNU-mondrian`，要求先把 porting.toml 补齐才发布子系统记录；唯一结论句是 `Emilelu/UniXNU-mondrian/storage: implemented work needs evidence`（**与 ZxbMsl 页的 storage=planned 矛盾**） | 官方 |
| UniXNU-upstream | `docs/devices/mondrian-zxbmsl160918.md:13-27` | 状态表（**ZxbMsl160918 fork 自报**）：Configuration=implemented、Firmware and boot=device-verified、CPU and interrupts=implemented、Memory and DMA=implemented、**Storage/Display/Input/GPU/Network/Audio/Power 全部 planned**、Image assembly=host-verified、Diagnostics=device-verified | 官方 |
| UniXNU-upstream | `docs/devices/mondrian-zxbmsl160918.md:102` | device 证据原文：`Darwin 24 loader boots the board every time: green bar from Entry.S, then the upstream probe's blue and magenta bars at the kernel entry and just before the MMU comes on.` 命令 `scripts/k60-device.sh boot /mnt/d/Android/k60-ios/boot-darwin24-bc8.img`，revision `d2af811a...` | 官方（fork 自报，已上机） |
| UniXNU-upstream | `docs/devices/mondrian-mzyxsl.md:37-46` | 四层合并顺序 profiles/arch/arm64 → **UniXNU-sm8475-common** 的 `soc.toml` → OS profile → `board.toml`；feeds 五条 pin（xnu 8796.141.3=1b191cb5 等）；OS profile 取 iPad7,1/16.6.1/20G81（chip 32785=0x8011、board 12）；`board.toml [userdata]` first_lba 53342976 / last_lba 61731583 / lba_bytes 4096；patches/xnu/series 98 条 | 官方（fork 自报） |
| UniXNU-upstream | `docs/devices/mondrian-mzyxsl.md:107-111` | 三条硬事实：① loader 只在 RAM 装 `UniXNULoader` 协议并在 unload 时恢复，**不写任何固件变量或分区**（fastboot boot 只读 bring-up 的前提）；② DarwinBoot 必须在 EL1 跑（`DarwinCurrentEl()!=4` 即 `EFI_UNSUPPORTED`），从 EL2 起的 payload 永远到不了 XNU；③ 绿条是 trampoline 不是内核 | 官方（fork 自报） |
| UniXNU-upstream | `docs/devices/zizhan.md:55` `:104` `:147-153` | 同 SoC 已上机板：ADSP 0x9fd00000+0x3100000 与 Pong 不同；SimpleFbDxe framebuffer 0xb8000000 **2160x1916**；SM8475 四 A510+三 A710+一 X2、GICv3、19.2 MHz timer、PSCI；`PONG_ADT_CLUSTERS=1`；`pong_fast_pri=47、pong_fast_cpu=7`；`ml-timeout-lock-panic-scale=40`、`interrupt-masked-debug-mode=1` | 同SoC异板·已上机 |
| UniXNU | `kits/` | 官方只有 6 个 kit：AdrenoFirmware、AdrenoPM4、AirNir、ArmSmmu4K、VerifiedRoot、XnuPrelink —— **没有音频/触摸/WiFi kit** | 官方 |
| yibiya-unixnu-upstream | `docs/devices/mondrian*.md` | 上游化仓库里 K60 相关只有设备记录与 `pong-driver/configs/mondrian_defconfig`，**没有硬件实现** | 官方 |

---

## 14. 已知矛盾与坑（照抄会坏）

### 14.1 RSC「可读」与「一读就死」互相矛盾（最贵的一条）

- `references/ios-sweet-k60/xnu/patches/0240-k60-touch-pins-rpmh.patch` 头部自称 2026-10-31 在 drv-2 读到 `DRV_ID=0x20700`。
- 同一批的 `0246-k60-touch-skip-rpmh.patch` 注释写：**「这台机器上 RSC 一个寄存器都读不得：首次读 TCS 就整机死」**，并加了 `k60rpmhoff=1` 整段跳过。
- `0248-k60-rsc-address-probe.patch` 因此只做只读探针（`k60rscprobe=1`）。

**结论：K60 的 RPMh 可访问性未定，根因（XPU / 电源域 / 互连）未证明。**
任何依赖 RPMh 投票的子系统（触摸 IOVDD、音频 ADSP LCX/LMX、GPU、WiFi ref_clk）在做之前，必须先有一个「只读、可回滚」的 RSC 探针结论。
这是本项目**当前最大的单点阻塞**。

### 14.2 ADSP 基址与 Pong 不同

Pong `PongAdsp.cpp:45` 用 `0x85700000`；K60 的 `0x85700000` 是 **video_region**（`MemoryMapLib.c:22`），ADSP 在 **0x9FD00000 + 0x3100000**（`:34`）。
UniXNU-upstream 的 zizhan 设备记录给出同样结论（`docs/devices/zizhan.md:55`）。**照抄 Pong 会把 ADSP 固件写进视频固件区。**

### 14.3 GPU 时钟校验写死 600 MHz

`pong-adreno/PongAdrenoPlatform.cpp:181`：`return !parents_ready || !(rd(gcc,0)&0x80000000) || rate!=600000000;`
K60 的 Adreno 最高 900 MHz，这一行会让 GPU 启动直接判失败。必须改成读本板 OPP 表。

### 14.4 WiFi BAR 范围两个版本

`pong-wifi/PongWifiPlatform.cpp:339` 注释：真实范围 `0x60200000..0x63ffffff`，**不是 Sheng 的 0x60300000**；`:538` 的 `mapPhys` 也只放行 `[0x60200000, 0x60400000)`。
引用时务必确认用的是 references 那份新快照（见 2.3）。

### 14.5 pong TCS 槽位是 4，不是 2

`PongPlatformResources.cpp:79` 用 `0xd00+4*0x2a0`（DRV slot 4），而 live FDT 声明的 `qcom,drv-id=<2>`。
两者不冲突（drv-id 指本核的 DRV，slot 4 指该 DRV 里用的 TCS 编号），但**混着抄会算错地址**。

### 14.6 Pong 的面板库不匹配 K60 —— 但 K60 自己的 XML 在 Device-Binaries 里（已更正）

`uefi-mondrian/Include/RAW.inc:1-5` 原文说约 72 个 `Panel_*.xml` 全是 pong 的、没有 K60 的 1440x3200 面板——**这一条对 pong 那个库成立**。

**2026-11-14 更正**：`Device-Binaries` 里**有** K60 的 m11a XML，只是不在仓库根，而在 `marble/RawFiles/` 下：`Panel_M11a_42_02_0a_amoled_dsc_cmd.xml`（4,799 B / 203 行 / sha256 `65cd6826a2abcce28db60b7d82ab34aa9fa8ecd2aa82f5fc4f21f9853b4be482`，引入提交 `a1501e0c`，2026-10-04）。全仓 `Panel_*.xml` 共 **2,117** 个，文件名含 `m11a` 的**恰好 1 个**。先前「2,117 个无一匹配」是**方法错误**：只按根目录与命名猜，没做 `git ls-files | grep -i m11a`。逐包比对与 3 处差异见 7.7。

### 14.7 yibiya 的 120Hz 文档引用的是通用 Sharp 面板，不是 K60 的 m11a

`references/yibiya-upstream/docs/plans/K60-120HZ-PLAN.md` 的 timing 表读自 `D:\Android\k60-ios\dtb\dtbo_a_fdt15.dtb` 的 `qcom,mdss_dsi_sharp_qhd_cmd` 节点。逐值核对后确认：它引用的就是 live FDT 里 `fdt_dump.txt:22033` 那个 `qcom,mdss_dsi_sharp_qhd_plus_dsc_cmd`（phandle 0x6a4，panel-name `Sharp qhd cmd mode dsi panel`）。

| 项目 | yibiya 文档 / sharp_qhd 节点 | **live FDT 的 m11a 节点（本机在用）** |
|---|---|---|
| 档位 | 2 档（120 / 60） | **3 档（60 / 90 / 120）** |
| panel-width / height | 0x2d0=720 / 0xc30=3120（DSC 压缩后） | **0x5a0=1440 / 0xc80=3200（未压缩）** |
| dsc-slice-width / height | 0x168=360 / 0x8 | **0x2d0=720 / 0x20=32** |
| dsc bit-per-component | 0x8 | **0xa** |
| h-front-porch / v-front-porch | 0x48=72 / 0x27=39 | **0x8 / 0x10** |
| mdp-transfer-time-us | 0x1efd=7933 | **0x1c84=7300** |
| display-topology | <2 2 **2**> | <2 2 **1**> |
| 单/双 DSI | 双（`dsi-ctrl-num=<0 1>`） | **单（`dsi-ctrl-num=0`）** |

**结论：120Hz 计划的数值不能直接搬。** 要做 120Hz 必须用 m11a 节点的 `timing@2`（`:28007`）与其 98 字节 `timing-switch-command`（`:28079`），不是 sharp 节点的 68 字节命令。

### 14.8 工具链缺口

- 本机**没有 dtc**（`command -v dtc` 为空）、**没有 fdtdump**、Python **没有 libfdt**（`import fdt` → ModuleNotFoundError）。
- `python3` 是 **Windows 侧解释器**：它读不了 `/mnt/e/...`（FileNotFoundError），必须写 `E:/...` 或先 `cd` 到 `/mnt/e` 再用相对路径。
- **`research-gate.py:34` 仍是 `REPO = '/mnt/e/hackios/UniXNU-mondrian'`**（2026-11-14 在 `origin/main` = `90d8271` 上实测）。在任何 worktree 里跑它，校验的都是主 checkout 的 `SOURCES.toml`（32 条），不是本树追加后的 50 条。本线自检一律用「复制到 scratch、只把 `REPO` 换成本树路径」的副本跑，不动仓库里的脚本（铁则⑧）。
- `check-docs.py:24` 在 `origin/main` 上**已改成自定位**（`REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`），所以在哪棵树跑就读哪棵树。
- **更正（2026-11-14）**：这里先前写过「`research-gate.py:88` 未传 `verbose`，problems 永不打印」——**这条是错的**，`def check(verbose=True)` 的缺省就是 True（`research-gate.py:38`），problems 会打印。结论撤回，对应补丁也撤回（见第 16 节）。
- 一次修好全部 9 个脚本、并新增 `scripts/check-repo-paths.py` 防回归的提交是 **`39a783c`**（`fix(scripts): judge the tree a gate lives in, and gate the pattern (P-183)`），它只在 `feat/audio-merge` 上，**没有进 main**。

---

## 15. 覆盖缺口（下一个人该挖的）

| 缺口 | 影响 | 建议动作 |
|---|---|---|
| ~~**AW882xx smart PA 无任何参考实现**~~ **型号已定（2026-11-14）** | 音频线（K60 独有） | 两颗都是 **AW88261（0x2113）**，真机只读读数见 4.5。剩下的是**寄存器序列与保护策略**（无 datasheet）。~~从 `Device-Binaries` 找 aw882xx 固件~~ **已证伪**：该仓库 `git ls-files | grep -ci aw88` = 0，也零个 bdwlan/amss/.pwf |
| ~~**K60 panel XML 未提取**~~ **已闭合（2026-11-14）** | 显示/背光 | `Device-Binaries/marble/RawFiles/Panel_M11a_42_02_0a_amoled_dsc_cmd.xml`（sha256 `65cd6826…`）就是 m11a 的厂商 XML，静态字段与 live FDT 逐项一致；但 init 序列是**同族不同修订**（129 包 vs 135 包，LCS 125 包相同、3 处差异），要用得先补差异。详见 7.7 与 `display/RESEARCH.md` 1.1 |
| **m11a 的 90Hz 档用途未知** | 显示 | `timing@1`（0x5a=90）在 live FDT 里存在但 MIUI 侧是否使用未验证；做 120Hz 时要决定是否同时暴露 90 |
| **面板 5 条供电轨里 3 条是 RPMh LDO** | 显示/供电 | vddio=ldoc12、vci=ldoc13、extvdd=ldod1；RSC 不可访问（14.1）前只能沿用 bootloader 状态 |
| **QCA6490 的 K60 固件包未定位** | WiFi/BT | Pong 用 `/pong/firmware/qca6490.pwf`；K60 需从 `vendor` 分区提 `amss.bin/m3.bin/bdwlan.*`。**2026-11-14 补：所有参考仓库都没有这些文件** —— `Device-Binaries` 的 `git ls-files` 里 bdwlan/amss/.pwf 命中数为 0；`QcaBluetooth` 是纯源码仓库（46 个 tracked 文件，HEAD `986d631`，唯一与固件相关的只有 `shim/linux/firmware.h`）。所以只能从设备分区取，别再翻参考仓库 |
| ~~**`Device-Binaries` 698 MB 未系统挖掘**~~ **已普查（2026-11-14）** | 全部 | 651 MB / 9,707 文件 / **78 个机型目录**已全部定性（机型 → `Build/<Family>`）：Palima=b4q/marble/pong/senna_a/senna_bc，Waipio=gts8p/ingres/r0q，Netrani=garnet，Kailua=aston/b5q/dm2q/gts9wifi/nuwa/nx729j/qrd8550/salami，Pakala=annibale/dodge/pagani/onyx，其余为 SM8250/SM8150/SM8350/SDM845 等老平台。**没有任何 SM8475/taro 机型** → 它不能给本板 UEFI 提供同 SoC 参考；唯一可用的产出是 `RawFiles`（面板 XML，见 7.7）与跨板布局对照（见 memory/RESEARCH.md 第 3 节）。74 份 `uefiplat.cfg` 中**没有一份**含 K60 的 `0xC7000000`（DXE Heap）或 `0x85700000`（video_region） |
| **RSC 可访问性根因未定** | 所有供电相关 | 见 14.1，优先 |
| ~~**Goodix 芯片型号未确认**~~ **已闭合（2026-11-14）** | 触摸 | 真机日志 71 次读到 `goodix: chip "BERLIN", firmware "9916R" 05.80.02.63, sensor 255`（61 个 boot 目录，型号串完全一致），三源一致 → **GT9916R BerlinD**，见 6.0。仍缺的是初始化失败根因，不是型号 |
| **`UniXNU-ruby` 不是空仓库、但不是 git 仓库**（2026-11-14 更正） | 文档错误 | `references/UniXNU-ruby/` 只有一个 `porting.toml`（246 行 / 15,547 B，`soc = "MT6877"`、`os_profile = "ios-16.7.16-20H392"`，自述 *selects no UniXNU components*）。它**有内容**，只是不是 git 仓库、不是构建树 —— 原表述「空仓库」不准 |

---

## 16. 机器可读部分

本文件的人读事实已同步成 `SOURCES.toml` 的 **20 条新 `required` 条目**（2026-11-14 追加；最近 2 条是本轮的真机日志）：

| 子系统 | 变化 | 条数 |
|---|---|---|
| `power` | **新建**段（RSC/TCS、SPMI、cmd-db、live FDT） | 4 |
| `touch` | 新增 K60 芯片身份真机日志（6.0） | 1 |
| `display` | **新建**段（面板画布契约、120Hz 参考面板 timing、DCS 背光、**m11a 面板与供电 live FDT**） | 4 |
| `usb` | **新建**段（DWC3 偏移、eUSB2 PHY、Type-C mux） | 3 |
| `bluetooth` | **新建**段（QCA6490 路线、K60 的 BT 节点） | 2 |
| `audio` | 补充 AudioReach 参数 ID、GLINK intent 约束、ADSP 保留区；**新增 AW88261 实机只读读数**（4.5） | 4 |
| `wifi` | 补充 PCIe 端点识别、K60 cnss 节点 | 2 |

追加后全文件 11 个子系统、52 条 `required`（原 7 个子系统、32 条）。查法：

```bash
python3 scripts/research-gate.py        # 校验每个 path 存在、examined 非空、finding >= 20 字
```

**路径规则（写 `path` 前先看这条）**：gate 只试两种解析——
① `os.path.join(REPO, path)`（REPO 是本仓库，如 `docs/research/...`）；
② `os.path.join('/mnt/e/k60-work', path)`（如 `references/...`、`reports/...`）。
所以 `path` **不能写 `E:/hackios/...`**。本索引里 `E:/k60-work/reports/live-6033dbec-fdt.dtb` 之所以能当 `path`，是因为它同时是 `reports/live-6033dbec-fdt.dtb`（回退②命中）。

不在上述两种回退内的仓库有两个，它们**进不了 gate**，只能在本文件正文以事实形式记录（已知的结构性限制）：
- `E:/hackios/QcaBluetooth`（蓝牙的唯一实现副本）—— 见第 5 节；
- `E:/hackios/UniXNU-liuqin`（Xiaomi Pad 6 Pro，同 SM8475）—— 见 2.1 与 9.1。
**软 blocker 的处理（2026-11-14）**：Lead 已决定由 Lead 侧加第三回退前缀或 `K60_REPO` 环境变量覆盖，本线按铁则⑧**不自己改 gate**；这条限制同时写进 `SOURCES.toml` 的文件头注释（那里是给写 `path` 的人看的，见本轮提交）。

**两份门禁补丁已撤回（2026-11-14）**：`docs/research/evidence/gate-repo-switch.diff` 与 `gate-repo-switch-lead.diff` 已删除，`evidence/README.md` 的登记行同步移除。Lead 的决定是「REPO 硬编码已由 USB 线在 main 上统一解决，不采用这两份补丁」。核对结果**只成立一半**：`check-docs.py:24` 确已自定位；`research-gate.py:34` 在 `origin/main`（`90d8271`）上**仍是硬编码**（实测见 14.8）。修它的正规路径不是本线的 diff，而是把 **`39a783c`**（P-183，含 `scripts/check-repo-paths.py` 防回归）从 `feat/audio-merge` 合进 main。另：原补丁声称的「`:88` 漏传 verbose 导致 problems 永不打印」是误判，已在 14.8 撤回。

---

## 17. 维护规则

1. **新增一条事实** = 一行表格：仓库 | 文件:行 | 事实 | 可信度。缺一列不收。
2. **行号必须实测过。** 不许写「大概是」；`grep -n` 出来的才算。
3. **换分支/换快照要重验行号。** 本索引的行号绑定 2.2 节列出的 HEAD（尤其 `pong-power@c117a67`、`pong-wifi@20e1e5b`、`phk110-port@a7d4575`、`yibiya-upstream@522c6ea`）。
4. **可信度降级要写原因。** 例如「同SoC异板」被你实测否定后，改成「本板实测（否定 X）」并保留出处。
5. **矛盾不合并，并列写。** 见 14.1：两个补丁互相矛盾时，两条都留，标未定因。

