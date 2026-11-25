# 官方文档 / 知识库 / 网页证据表（黑屏与早期控制台）

本表只回答一个问题：**「先看见字」这件事，官方文档怎么说、哪台机器做到过、我们抄的对象有没有官方依据。**
每条都给出取回方式（可复跑），不接受「我记得」。

## 1. 官方文档把「文本控制台 + panic 屏」写成首启验收项

`https://unixnu.com/devices/luming-infinityex-rsxq`（Xiaomi Civi 5 Pro / SM8735 / format-2 bring-up）§Procedure：

> First boot validates the text console and panic screen. Then port/select a display component publishing IOMobileFramebuffer for luming (panel/backlight/rail work), recording frame timing and pixel format.

同一段在 `https://unixnu.com/zh/devices/luming-infinityex-rsxq` 有中文版。KB 里对应条目：`luming-infinityex-rsxq.md`（§操作步骤 / §Procedure）。

**读法**：官方把顺序写死了——先文本控制台与 panic 屏，再谈 IOMobileFramebuffer / 面板 / 背光。我们之前反过来先做面板与 GPU，方向与官方相反。这条直接支持「0558/0559/0560 是正确优先级」。

## 2. 成功机型把「帧缓冲当文本控制台 + 内存里保留日志 + 小分区保留日志」列为硬件与依赖

`https://unixnu.com/devices/sheng-mataht`（Xiaomi Pad 6S Pro / sheng，macOS 26.5 全系统进桌面）§硬件与依赖：

> The framebuffer as a text console, a retained log in memory and in a small partition, a QR code of the panic state, and read-only TWRP 8 MiB chunk scans of the OS window.

KB 条目：`sheng-mataht.md`。

**读法**：官方认可的观测手段是三件套——帧缓冲文本控制台、内存日志、小分区日志。这解释了两件事：①我们做 ramoops（内存日志）方向不错但把「读」做在了错误的一端；②分区日志（userdata 末尾 32 MiB）正是官方列的第三件，属于必做项而不是可选优化。

## 3. 官方站点上有大量 `Development findings / Diagnostics` 页在讲同一件事

`python3 scripts/k60-docsearch.py --lang both --limit 6 "framebuffer console text console"` 的命中（全部是设备页的 Diagnostics/Development findings 节）：

| 页面 | 节 |
| --- | --- |
| `/devices/oneplus13t` | Development findings / Display |
| `/devices/sirius-huajifruit` | Development findings / Diagnostics |
| `/devices/j716f-emptyghost` | Development findings / Diagnostics |
| `/devices/uke-imposterissus13` | Evidence / Firmware and boot |

`"serial console"` 同样命中 `sirius-huajifruit` 与 `uke-imposterissus13` 的同一节。

**读法**：这些页面正是「别人怎么让早期控制台出字」的第一手记录，而我们的 `OFFICIAL-REQUIREMENTS.toml` 一页 `docs/devices/**` 都没登记（registry 103 页只有 guide/porting/drivers）。这是审计口径的漏洞：把最相关的 266 页设备记录排除在外，却把 78 页未审的 guide 当成「覆盖率 76% 未审」。待办：把 `docs/devices/**` 纳入 registry（至少 4 页 Redmi K60 + 上面这些带 Diagnostics 的页面）。

## 4. 官方调试页给出的诊断阶梯（已抓正文 821 行）

`https://unixnu.com/zh/guide/debugging`（registry 里 unmapped、从未审）原文要点：

- 阶梯是「日志来源 → 入口探针（绿色交接条）→ panic 屏幕 → 用户态证据」；
- 「每次应用一项诊断修改，重新构建受影响的产物。启动参数修改需要 `./unixnu payload` 和 `./unixnu bootimg`」；
- 固件菜单可用二维码导出日志，内核入口用 UART 或屏幕诊断；
- 官方支持 `scripts/debug_terminal.py` + `debug-terminal.cmd`（协议 2：`collect`/`status`/`logs wifi|gpu|panic`/`screen.start`/`shell`/`reboot.fastboot`，115200 8N1 + DTR，`--vid 0x1209 --pid 0x0001`），并明确「修改 USB ID 本身不提供协议兼容性」。

**读法**：官方把「入口探针（绿条）」列为第二级诊断手段——我们花了四次飞行才用上它，而它本来就在文档里。这条要写进八步的③④。

## 5. 我们自己的 16 线记录也印证同一顺序

`patches/xnu/zzzzz-pong-video-console.patch`（16.6.1 上这块面板确实能打印）两处：`PE_create_console()` 的 `-v` 分支、以及把 `video_console.c` 的 `#if HAS_UCNORMAL_MEM` 扩成 `|| defined(PONG)`（WCOMB）。第二处在 27 上没有等价物（`-DPONG` 恒 0），是漏抄。

## 5b. 在线检索交叉验证（已做）

- [Capture logs and automate boot tests | UniXNU](https://unixnu.com/porting/log-capture) 开头逐字：**「Set up log capture as you bring up the board. Start with firmware logs, collect kernel evidence at handoff, then add persistent logs and automated reboot cycles.」** —— 与本次结论完全一致：先固件日志，再交棒处的内核证据，最后才是持久日志与自动重启；我们过去把「持久日志」当第一件事，顺序错了。
- [Debugging and logs | UniXNU](https://unixnu.com/guide/debugging) 的 Procedure 第一条：记录失败的**命令**或**最后一个完成的启动检查点**，并带上设备/固件/镜像版本；日志来源按可用性选（USB terminal 只在板子实现协议时可用，否则用 UART、帧缓冲诊断或 QEMU 日志）。
- [Boot arguments | UniXNU](https://unixnu.com/xnu/boot-arguments) 是启动参数的总表（`-v`、`serial=`、`debug=` 等），应作为 `BOOT-ARGS.md` 的上游依据。
- [package/BootLog.c](https://github.com/UniXNU/UniXNU-sheng/blob/5ae8b4876a378a5104330a5ae514ec9d6deae373/package/BootLog.c) 是「小分区日志」那件套的官方实现，与我们 `log-carrier` 报告的 5 份先例一致。
- [scripts/xnu-panic-screen.c](https://github.com/UniXNU/UniXNU/blob/f61fd6c1/scripts/xnu-panic-screen.c) 是官方 panic 屏实现，对应 `0560` 的同名目标。

## 6. 尚未完成的三项

| 项 | 状态 |
| --- | --- |
| `docs/devices/**` 纳入 `OFFICIAL-REQUIREMENTS.toml` | 待做（266 页） |
| 用 `web_search` 交叉验证上面 1/2 两条 | 待做 |
| `.kb` 共享库的 `kb_root` 已可用（`E:\iOS Port\Work\kb`，6,194 文档） | ✅ 本次已用 |

## 复跑命令

```
python3 scripts/k60-docsearch.py --lang both --limit 6 "framebuffer console text console"
python3 scripts/k60-docsearch.py --page /zh/guide/debugging --fetch
python3 -c "..."   # kb_search(kb_root='E:\\iOS Port\\Work\\kb', query='framebuffer console text console')
```
