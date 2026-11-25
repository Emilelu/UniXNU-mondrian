# 交付包 δ2-㉑ · 首启失败模式矩阵（P3；判读手册）

- **作者**：Agent-δ2（只读研究线）· 2026-10-28
- **用途**：首启现场（δ2-10 S5/S6）遇到异常时的**查表手册**——症状 → 证据（δ2-12 的 V 源）→ 判据 → 下一步 → 需要谁。只读整合，无新挖矿；全部行号引用前包。
- **四段坐标**（δ2-12 §2）：S-A UEFI 前 / S-B UEFI 内 / S-C DarwinBoot 内 / S-D XNU 内。

---

## 0. 矩阵

### F1 · 完全黑屏（连 QR 都没有）
| 维度 | 内容 |
|---|---|
| 段位 | S-A |
| 证据 | 无 V1–V5；对照 boot51.img 能否进 QR |
| 判据 | boot51 也黑 = 设备/ABL 层变化；boot51 正常 = 新 boot.img 打包问题 |
| 下一步 | 查 δ2-10 S4 参数（fd/dtb 路径、header v4）；`unpackbootimg` 抽检【可选】；用 07 §1 链路反推 |
| 需要谁 | α（重新打包）；GHA 线（若 fd 来自 GHA 轮） |

### F2 · 进得了 QR，菜单/entry 后死
| 维度 | 内容 |
|---|---|
| 段位 | S-B |
| 证据 | V1 AdvLog（复位后可读）；V2 DiagDraw 首行是否出现 |
| 判据 | AdvLog 有 payload 卷枚举失败 = RamDisk DXE 没挂上；有 DarwinBoot 载入失败 = kernel.macho/adt 缺或坏 |
| 下一步 | `mtype` 抽检 payload.img（δ2-10 S3 校验③）；`payload.json` 的 sha256 对表 |
| 需要谁 | α |

### F3 · DiagDraw 停在中途 / 打印 "unsupported inputs"
| 维度 | 内容 |
|---|---|
| 段位 | S-C |
| 证据 | V2 最后一行；V3 `command line N bytes` 判例行 |
| 判据 | "unsupported inputs or exception level; firmware retained"（DarwinBoot22.c:527-530）= unixnu.toml entry 带了 dtb/kexts；`EFI_BAD_BUFFER_SIZE`（:538）= args 超 1023B 或含非 ASCII |
| 下一步 | unixnu.toml 去掉 dtb 键；args 缩短/查非法字符（payload.py:31 校验应已拦）；核对 N 与 payload.json |
| 需要谁 | α |

### F4 · XNU 滚屏开始后卡死（无 panic 输出）
| 维度 | 内容 |
|---|---|
| 段位 | S-D |
| 证据 | V4 最后 5 行滚屏；`startup_debug=1` 使最后一行 = 卡住的 STARTUP() 函数名 |
| 判据 | 最后行所在子系统 → 定位：PE/ArmCpu 早期 = 平台/内存描述问题（dram_size 嫌疑）；IOMedium/ArmDT = ADT 契约问题；corecrypto/kalloc = prelink 组件问题 |
| 下一步 | 对照 δ2-05 挂点表；dram_size 复核（δ2-04 §T1.3）；slide 复核（δ2-06 R2） |
| 需要谁 | α；owner（若 dram_size/常量决策） |

### F5 · panic（屏上 panic screen / 滚屏崩）
| 维度 | 内容 |
|---|---|
| 段位 | S-D |
| 证据 | V5 panic screen（keepsyms=1 给符号）+ V6 volatile log（仅屏上可见） |
| 判据 | panic 字符串分类：`No PMGR`（payload.py:50 预警的 UFS 配对缺失）、AMFI/AMNM 类（early_security/ADT 契约）、SLTO（`-no_slto_panic` 已带仍出 = prelink 组件异常）、page fault（内存描述） |
| 下一步 | 符号名 + δ2-05 §1 表定位；`amfi_get_out_of_my_way=1` 仅诊断轮（docs 警示） |
| 需要谁 | α；owner（AMFI/安全策略类） |

### F6 · 自动重启循环
| 维度 | 内容 |
|---|---|
| 段位 | 任意 |
| 证据 | 唯一复位存活源 = V1 AdvLog（复位后 QR 立刻读）；V7 ramoops 现状地址错（δ2-12 E1 修前不可用） |
| 判据 | AdvLog 里最后一段 vs 上轮最后一段比较；panic-loop 由 watchdog/冷复位窗兜底的间隔特征【推测 ~60s】 |
| 下一步 | E1 落地（0x85200000→0xA7000000）后，复位证据升级为 Android pstore 可读；先按 F4/F5 处理循环本体 |
| 需要谁 | α（E1 单行）；机主配合快速进 QR |

### F7 · 花屏/几何错
| 维度 | 内容 |
|---|---|
| 段位 | S-C/S-D |
| 证据 | V2/V4 画面 |
| 判据 | 花屏但可辨 = stride/格式错（GOP 1440×3200×4/5760 vs 实际 splash 几何）；无花屏但内容乱 = 字体 scale（liuqin 的 ui_scale 经验） |
| 下一步 | SimpleFbDxe 的 splash 几何与 DarwinBoot `ReadBootVideo` 对表（DarwinBoot22.c:68-80）；`fb=` 参数无效（δ2-10 §4 已撤回），几何只随 GOP |
| 需要谁 | α（UEFI 侧几何） |

### F8 · 编译/prelink 阶段失败（还没到设备）
| 维度 | 内容 |
|---|---|
| 段位 | 构建期 |
| 证据 | logs/kernel.log、kernel-bootstrap.log、prelink.log；GHA run 日志 |
| 判据 | δ2-05 §1 表逐行（A5 ArmDT test -f、A7 libcc_kext、A3 补丁冲突、B3 sparse ABI、B2 slide） |
| 下一步 | 对应包的修复清单（δ2-09 §3、δ2-04 §T2.3、δ2-01 §4-G4） |
| 需要谁 | α（Linux 侧）；GHA 线（macOS 侧）；owner（core 改动决策） |

## 1. 证据源速查（δ2-12 §1 的 V1–V7）

V1 AdvLog（复位存活）｜V2 DiagDraw 行级进度｜V3 command line 判例行｜V4 video console｜V5 panic screen｜V6 volatile panic log｜V7 ramoops console（E1 修前无效）。

## 2. 待确认 / 推测

- 【推测】F6 的重启间隔特征（watchdog vs 冷复位窗）未实测；以 AdvLog 内容为准。
- 【推测】F4 的子系统归因表是经验性映射（STARTUP 子系统名 → 嫌疑面），首轮实测后校准。
- 【推测】F5 的 SLTO panic 与 prelink 组件的关联（sheng/liuqin 经验移植）。

*Agent-δ2 · 2026-10-28 · 交付物 21/21*
