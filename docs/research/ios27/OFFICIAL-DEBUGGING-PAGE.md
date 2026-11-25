# 官方调试页与 ramoops 判据（iron-13 证据）

页面：`https://unixnu.com/zh/guide/debugging`（registry 里原为 `unmapped`，本文件是它的第一条审计记录）。
取法：`python3 scripts/k60-docsearch.py --page /zh/guide/debugging --fetch`（站点 VitePress 本地索引，2026-11-21 抓取，正文 821 行落在 `E:/iOS Port/Work/scratch/page-cb826fe0.txt`）。

## 页面给的诊断阶梯（原文要点，逐条对应本板落点）

1. **先确定日志来源**：固件菜单可导出二维码日志；内核入口用 UART 或屏幕诊断；再往上是 panic 屏幕与用户态证据。
   - 本板落点：K60 没有可用串口（`usbser` 只在固件菜单里可用），内核侧 27 线在 2026-11-21 之前**没有任何 sink**（`docs/research/ios27/CONSOLE-GAP.md`），所以 27 的可见性必须自建，不能照 16 线假设。
2. **每次只应用一项诊断修改，重新构建受影响的产物**；「启动参数修改需要 `./unixnu payload` 和 `./unixnu bootimg`」。
   - 本板落点：这正是 `scripts/build-ios27-linux.sh` 的 payload→bootimg 两段，以及 P-159（`--kernel-arg` 必须同时进 payload）。
3. **入口探针**：在内核入口处涂一块可见颜色，表示固件已把控制权交给内核。
   - 本板落点：我们自己的固件里有等价实现，且比页面更细——`Platforms/Xiaomi/DarwinBootPkg/Driver/Entry.S:12-18` 在跳转前把帧缓冲顶上 1/16 涂 `0xFF00FF00` 再清 `SCTLR_EL1` 的 M/C/I。**看到绿条 = 已跳进内核；没有绿条 = 连分支都没走到。**
4. **官方支持一个 USB 终端**：`scripts/debug_terminal.py` + `scripts/debug-terminal.cmd`（移植自 giulia，协议 2：`collect`/`status`/`logs wifi|gpu|panic`/`screen.start`/`shell`/`reboot.fastboot`，115200 8N1 + DTR，`--vid 0x1209 --pid 0x0001`）。
   - 页面明说：**改 USB ID 本身不提供协议兼容性**；基础内核可能只支持 `help`/`ping`/`status`/`replay`。
   - 本板落点：这是 27 的长期日志通道（对应 16 线的 `0300` usblog EP0）。在它落地之前，唯一可用的读数器是固件侧的 `RamoopsDumpDxe`（`uefi-mondrian` `c52a080`）。

## 对本次飞行的判据意义

页面把「有没有日志」放在阶梯第一格，而不是最后。我们先前把「0 字节控制台」当成「内核死了」，正是跳过了这一格（P-300 的第四条教训）。因此本次飞行的判据不是「串口有没有字」，而是：

- **第 1 次启动**：固件应当打印 `RAMOOPS: no signature ... the window is empty` —— 证明读数器自己被调度到了、窗口可读、而窗口里没有上一轮内核留下的痕迹（符合「内核从未写到这里」）。
- **第 2 次启动（不复位，直接再 boot）**：应当打印 `RAMOOPS: sig ok` 与环形缓冲首尾的内容 —— 证明上一轮内核真的执行到了 `pong_ramoops_console_init()` 并写了字。
- 若第 2 次仍是 `no signature`，结论只能是「内核没有跑到 console init」，不能是「钩子没编进去」（后者已由 `scripts/check-kernel-console.py` 与镜像内符号单独证明）。
