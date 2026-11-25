# 机制必须先有成功先例（用户口径，2026-11-22 12:46）

用户原话：**「没有成功先例的禁止瞎搞」**。

这条针对的不是「猜某个寄存器值」，而是**选机制**：任何一条要长期依赖的诊断/启动/存证机制，必须先在**已经成功走到 `bsd_init` 及之后的机型**上找到有人真的这么用过（给出 `仓库:文件:行`），否则不得进入实现，也不得靠它下结论。

## 已有的成功机型清单（截至 2026-11-22）

`sheng`（SM8550）、`vermeer`、`cupid`、`asteroids`、`uke`、`muyu`。它们的共同点：
`ios-27.0.1-24A446` + `xnu-12377` + 机器配置 `BCM2837` + **第一行输出走帧缓冲**。

## 按这条规则重排后的三条通道

| 通道 | 先例 | 裁定 |
| --- | --- | --- |
| **帧缓冲文本控制台**：`osfmk/kern/startup.c` 在 `initialize_screen(NULL, kPEAcquireScreen)` 之后加 `switch_to_video_console(); initialize_screen(NULL, kPETextScreen);` | **有**：`vermeer` 的 `patches/xnu/vermeer-framebuffer-console.patch`；且五台成功机第一行输出全是帧缓冲 | **允许**，下一步就是文件级搬它 |
| **分区日志**：userdata 末尾 32 MiB（8,192 × 4 KiB，头 `SHLOG001` v5） | **有 5 份**：`sheng/package/BootLog.c:1-8`、`community/{vermeer,cupid,asteroids,uke}` 各自的 `NativeUfs.cpp`/`BootLog.c`；框架 `docs/zh/porting/log-capture.md` §4 列为板型必做 | **允许**，但要求 `CONFIG_XNU_NATIVE_UFS=y` 与 SHNGROOT 窗口门，是中期活 |
| **ramoops 跨复位**（去掉固件 `RamoopsInit()` 的自擦后指望它活过一次复位） | **无**：五台成功机没有一台用 ramoops 存跨复位日志；`log-carrier` 报告也证明「RAM 环」这条在本仓 16 线全是内存环、pong 当年靠的是分区 | **禁止**（此前我建议的「一个二值实验定案」作废） |
| **IMEM 当日志环**（`0x146AA200..0x146AA65C`，1.2 KiB） | **无**：IMEM 在所有树里只被用来写 4 B `restart_reason` | **禁止** |

## 纪律

1. 提任何机制（诊断、存证、启动、超时、复位）时，先给先例行；给不出就写「无先例」，并且**不允许**把它接进代码或写进判据。
2. 「上游/同 SoC 有人这么干」不等于先例——先例只认**已成功启动到 `bsd_init` 之后**的机型，且必须 `仓库:文件:行` 可解析。
3. 自己的 fork 不算独立先例（见 `docs/engineering/REFERENCE-PROVENANCE.md`）。
4. 先例一旦被证伪（对方其实没跑成），用它支撑的结论同步作废并重新排序。
