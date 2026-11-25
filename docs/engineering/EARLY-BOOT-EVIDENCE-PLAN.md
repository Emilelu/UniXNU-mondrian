# 交付包 δ2-⑫ · 无串口首启的证据采集计划（P1）

- **作者**：Agent-δ2（只读研究线）· 2026-10-28
- **问题**：K60 无外引 UART，首启（黑屏/自动重启/卡住/花屏）时怎么拿到"死在哪"的证据？
- **方法**：只读核对 XNU 侧（pexpert/patches）、DarwinBoot22 侧、UEFI 侧的全部输出通道与持久性。命令只写不执行。
- **证据等级**：【源码】file:line（4dea540/ae68700）｜【板上】｜【推测】标注。

---

## 0. 结论摘要（4 行）

1. K60 首启有 **6 个证据源**，持久性分三档：**UEFI AdvLog（QR 可看，复位后仍在）**、**DarwinBoot22 的 GOP 行级进度（DiagDraw，XNU 接管前）**、**XNU video console + panic screen（XNU 接管后）**——这三档覆盖首启全程；volatile panic log 是内核 RAM 缓冲（`pe_init.c:108-118`，复位即丢，只能靠 panic screen 现场看）。
2. **新发现（坑）**：`CONFIG_XNU_PONG_RAMOOPS_CONSOLE=y` 的 console 持久镜像写死 **Pong 地址 `PONG_RAMOOPS_PHYS_BASE = 0x85200000`**（`xnu-work/osfmk/arm64/pong_ramoops_console.h:7`），而 K60 的 ramoops 区是 `0xA7000000`（UEFI FD 已为此挪到 0xA7400000，`mondrian.toml:11-15` 注释）→ **现状下 XNU console 的"持久"镜像落在一个无人读取的地址，复位后诊断价值为零**。修复是一个常量（§4-E1）。
3. 判读顺序铁律：先分"UEFI 前/UEFI 内/DarwinBoot 内/XNU 内"四段（各段证据源不同，§2）；**进 XNU 前黑屏看 DiagDraw 最后一行，进 XNU 后看 panic screen 与最后滚屏**。
4. 复位自动循环（watchdog/panic-loop）场景下唯一可靠证据 = UEFI AdvLog（复位后 QR 里看）+ 把 AdvLog 里的 DarwinBoot 行与 XNU 最后一行分开判读（§3）。

## 1. 证据源清单（位置 / 怎么读 / 持久性）

| # | 证据源 | 物理位置 / 触发 | 怎么读 | 持久性 | 覆盖段 |
|---|---|---|---|---|---|
| V1 | **UEFI Advanced Logger** | AdvLogDxe RAM 缓冲（PcdUniXNUDebugLevel=0x80000000 已调，HANDOFF §3.1） | 设备复位/重启回 UEFI 后进 QR（Tools→Advanced Log）；或 AdvLog 输出经 DIAG 落屏 | **复位后仍在**（RAM 未被 XNU 覆盖时；XNU 若已跑，前段可能被覆写【推测：取决于缓冲地址与 XNU 用法】） | UEFI 全段 + DarwinBoot 打印（同缓冲？【待确认：DarwinBoot Print 是否走 AdvLog】） |
| V2 | **DarwinBoot22 GOP 行级进度** | `DarwinBoot22.c:462`（启动行）、`:467`（循环行）、`:404-407 DiagDraw`（每步一行画到 GOP） | 直接看屏；**进 XNU 前黑屏 = 最后一行就是死者** | 复位即丢 | BootShim 后 → XNU 接管前 |
| V3 | **DarwinBoot22 判例行** | `:657-658` `boot_args size 0x2e0, command line N bytes`；失败路径 `:526-530`（unsupported inputs → "firmware retained"） | 屏上文本；与 `payload.json` 的 args 对表（δ2-07 §3） | 复位即丢 | handoff 瞬间 |
| V4 | **XNU video console** | `zzzzz-pong-video-console.patch:9-17`（`-v` + `PE_state.video` ← DarwinBoot22 GOP） | 屏上滚屏 | 复位即丢 | XNU 接管后 |
| V5 | **panic screen** | board `[payload] panic_screen = true` → `patch-xnu-entry-probe.py --panic-screen`（`payload.py:131-143`）补进 kernel.macho | panic 时屏上画寄存器/符号（配合 `keepsyms=1`） | 复位即丢 | panic 瞬间 |
| V6 | **volatile panic log** | `pe_init.c:108-118`（PONG+VOLATILE=y：`gPanicBase = pong_volatile_panic_log` 内核 RAM 缓冲） | 只经 V4/V5 间接可见；**无独立读回通道** | 复位即丢（注释原文 "volatile and never advertised to firmware as persistent"） | panic 瞬间 |
| V7 | **ramoops console** | `CONFIG_XNU_PONG_RAMOOPS_CONSOLE=y` → `pong_ramoops_console_init()`（`arm_init.c` patch :528-534）写 `0x85200000`（2 MB，magic `0x43474244`，`pong_ramoops_console.h:7-10`） | **现状无人读**：Android pstore 在 0xA7000000；UEFI 也不扫 0x85200000 | 写入持久（PoC clean :76）但**地址错** | XNU 全段（本该） |

## 2. 四段判读（失败在谁家里）

| 段 | 特征 | 该看的证据 | 下一步 |
|---|---|---|---|
| S-A UEFI 前 | 屏全黑、无任何 UniXNU/QR 痕迹 | 无 V1–V5 → 与 boot51 时代对比（boot51 能进 QR）；ABL/BootShim 层 | 对比 boot51.img 能否仍进 QR（排除 boot.img 打包问题：header v4/尺寸/dtb）；查 δ2-10 S4 的 dtb/fd 参数 |
| S-B UEFI 内 | 能亮屏/进 QR，但菜单异常或选 entry 后死 | V1（AdvLog 完整栈）、V2（DiagDraw 首行 `DarwinBoot` 行出现与否） | AdvLog 里找 DarwinBoot 载入 payload 失败行；payload 卷用 `mtype` 抽检（δ2-10 S3 校验③） |
| S-C DarwinBoot 内 | DiagDraw 行停在中间 / "unsupported inputs" | V2 最后一行 + V3 判例行 | `command line N bytes` 的 N 与 payload.json 对表；`unsupported inputs` → unixnu.toml entry 被加了 dtb 键或 kexts（δ2-07 §1 旁路） |
| S-D XNU 内 | 滚屏开始后死/panic | V4 最后滚屏 + V5 panic screen + V6（若屏上可见） | 滚屏最后函数 → δ2-21 矩阵；`keepsyms=1` 给符号名 |

## 3. 与 UEFI/QR 的串联（一次上机拿最多证据）

```text
fastboot boot boot.img
  ├─ 黑屏（<10s）→ 拔电重进 bootloader，先跑一次 boot51.img 对照（隔离 S-A/S-B）
  ├─ 进 QR → Tools→Advanced Log 抄 V1（重点：DarwinBoot 载入、payload 卷枚举、FD 窗口）
  ├─ 菜单选 xnu entry → 观察 V2/V3
  │    ├─ 停在 DiagDraw → 记最后一行（S-C）
  │    └─ XNU 滚屏 → 记最后 5 行 + panic screen 内容（S-D）
  └─ 自动重启循环 → 复位后第一件事：进 QR 读 V1（唯一复位存活的源）
```

- 60s 冷复位窗（UEFI 侧既有）兜底；全程只 `fastboot boot`。
- 每次现场**拍照**（V2/V4/V5 是易失画面），连同 AdvLog 文本一起回传。

## 4. 给 α 的增强（E 系列；单行/小 diff，α 落盘）

| # | 增强 | diff 形状 | 收益 |
|---|---|---|---|
| E1 | **ramoops console 指到 K60 的 ramoops 区**：`pong_ramoops_console.h:7` `0x85200000` → `0xA7000000`（UEFI FD 已挪开让位，`mondrian.toml:11-15`） | 常量一行 | XNU console/panic 有复位后可读的持久镜像（UEFI 侧可加一个 QR 读取项，或 Android pstore 直接认领——后续验证） |
| E2 | board `[payload] panic_screen = true`（δ2-01 草稿 A 未含，建议加上） | board.toml 一行 | 黑屏场景唯一屏上 panic 证据（V5） |
| E3 | DarwinBoot22 打印 command line 内容（δ2-07 §2.2-E1） | 单行 Print | args 生效性现场可证 |
| E4 | （可选）UEFI QR 加"读 0xA7000000 ramoops 头"菜单项 | 中等 | 复位后 GUI 读回 XNU 最后一屏 |

## 5. 待确认 / 推测

- 【待确认】V1 AdvLog 的 RAM 缓冲地址是否与 XNU 写区重叠（决定"XNU 跑过后 AdvLog 是否仍完整"）——读 AdvLogDxe 的缓冲分配即可闭。
- 【待确认】K60 的 `0x85200000` 在 K60 reserved-memory 表中不存在（γ2 扫描前段未见）→ XNU 往普通 DRAM 写 console；与 Android 共存无冲突（XNU 独占 DRAM），但复位后 Android 视其为普通内存。
- 【推测】panic screen 的绘制在 panic 早段（prelink/早安全初始化）是否已可用——video console 依赖 `PE_state.video`（pe_init 早期已填），倾向可用；首启实测确认。
- 【源码已核】V7 的 2 MB 区、magic、PoC clean、init 调用点——见 §1-V7 行号。

*Agent-δ2 · 2026-10-28 · 交付物 12/21*
