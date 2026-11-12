# Boot 流程（唯一入口）

> 铁则 8：**没有串口日志的 boot 是盲实验。** 每一次 `fastboot boot` 都必须带着
> CDC-ACM 控制台抓取一起跑，并且必须在 boot **之前**挂上。

## 为什么有这一页

2026-11-12 有一次 boot 挂死在早启动，控制台一次都没出现，却没有任何日志留存 ——
当时是靠"人记得先开一个窗口跑 `capture-k60-usblog.ps1`"，忘了就整轮只能猜。
那一轮的结论甚至是从"是不是找不到 unixnu 分区"这种猜测出发的。

同一天晚上又踩到第二个形态：`flash.sh` 自己起了一个抓取进程，`boot-and-capture.ps1`
里面又起了一个，**两个 PowerShell 进程抢同一个 COM 口**，各自写一个时间戳目录。
主判据读的是第一个目录里的 `console.log`，那个文件 0 字节 —— 于是把一轮"Data 已经
挂上、launchd 已经 Early boot complete、SpringBoard 已经在跑"的正常启动，误判成
"内核在 USB gadget init 之前就死了"。真正的日志躺在隔壁目录里，91 KB，1405 行。

结论：**能被忘掉的流程不是流程；能被两个进程同时写的东西不是证据。**
现在结构是单一 supervisor + 单一 collector + 单一证据目录 + 可离线测试的判据函数。

## 一条命令

```bash
bash /mnt/e/hackios/UniXNU-mondrian/scripts/flash.sh /mnt/e/k60-work/usb-a-stage/out/<img> <秒数>
```

补丁集与上次成功启动的不同时，门禁 S 项要求显式声明：

```bash
K60_FORCE_NEW=1 bash /mnt/e/hackios/UniXNU-mondrian/scripts/flash.sh <img> <秒数>
```

`K60_FORCE_NEW=1` 不是绕过门禁：其余每一项照旧检查，只是不再因为"补丁集变了"而失败。

脚本在仓库里（`scripts/flash.sh`），不再放在 `/mnt/e/k60-work/scripts/` —— 放仓库外
的文件不会被提交、不会被复查、也不会被门禁看见，那是铁则 1 的违反。

## 三个角色，互不越界

| 文件 | 角色 | 边界 |
| --- | --- | --- |
| `scripts/flash.sh` | 门禁 + 设备状态 + 调用 supervisor | **只调用 `boot-and-capture.ps1`，自己不开串口** |
| `scripts/boot-and-capture.ps1` | 唯一 supervisor | 不含任何 `SerialPort`；只负责武装抓取、`fastboot boot`、回收 |
| `scripts/capture-k60-usblog.ps1` | 唯一 collector | 唯一打开 COM 口的进程，持命名互斥体 `Local\K60-CDC-ACM-Capture` |
| `scripts/k60-capture-state.ps1` | 判据函数 | 纯函数，可离线测试（`scripts/tests/test-k60-capture-verdict.ps1`） |

争抢的处理是明确的：第二个 collector 拿不到互斥体就以 `capture-busy` 退出（rc=3），
不会写出第二份证据。

## flash.sh 内部顺序

1. `porting-gate.py --quick`（文档 / porting / patch 结构 / 序列指纹）
2. `eight-step-gate.py --flash`（①~⑦ 全绿 + ⑧ 的成功/失败预测）
3. `check-boot-procedure.py`（本页要求的自检）
4. `research-gate.py`
5. 设备状态检测 → 需要时 `adb reboot bootloader`，等 fastboot（150 s）
6. `boot-and-capture.ps1`：**先**起 collector 并等 `capture.ready` 出现，**再** `fastboot boot`
7. 按 supervisor 退出码判读，证据目录路径直接打印出来

## 证据目录里有什么

`E:\k60-work\evidence\usblog-<yyyyMMdd-HHmmss>\`

- `console.log` —— 串口原始字节，唯一正文
- `capture.json` —— 结构化判据：`state`、`complete`、`stopReason`、字节数、
  是否见过 panic 标记 / 复位标记、端口什么时候出现/打开
- `capture-events.jsonl` —— 逐事件时间线（port-observed / port-opened / open-error /
  read-error / panic-marker / reset-marker / stop-reason）
- `boot.json` —— supervisor 的账：镜像路径、sha256、抓取是否武装、`Booting OKAY`
  是否收到、设备是否自己回了 fastboot
- `collector.stdout.log` / `collector.stderr.log`

## 判据：不是"文件存在吗"

`k60-capture-state.ps1` 把结果分成七个状态，`complete` 只对 `captured` 为真：

- `captured` —— 拿到了字节，正常结束
- `captured-truncated` —— 拿到字节但预算耗尽/断线，**日志仍可用**，只是尾部缺失
- `captured-disconnected` —— 设备自己回了 fastboot 且没有 panic 标记
- `captured-error` —— collector 自己报错，但已有字节
- `opened-no-data` —— 端口打开了，一个字节都没有
- `port-open-failed` —— 端口出现过但打开失败
- `port-not-observed` —— 从头到尾没看到端口

supervisor 退出码：0 完整，1 监督/启动失败，2 零字节，3 串口被占用，4 截断，5 自己回了 fastboot。
**0 字节的日志不是"内核没跑"的证据** —— `port-not-observed` 只说明 USB gadget 没枚举成功，
可能原因从"内核死在 gadget init 之前"到"根本没 boot 成功"都有，必须结合 `boot.json`
里的 `bootAccepted` 一起看。

## 串口控制台长什么样

- 内核 gadget 枚举成 `USB\VID_1209&PID_0001`，自动绑 `usbser.sys`
- COM 号**不在** FriendlyName 里，只能在
  `HKLM\HARDWARE\DEVICEMAP\SERIALCOMM` 里找 `\Device\USBSER000`
  （按 FriendlyName 挑会选中蓝牙猫 COM3/COM4，那是错的）
- 必须 `DtrEnable = $true`，否则内核不排空 console ring

## 控制台真的没出现时怎么查

按早启动路径查，不要猜 UI 层现象：

1. 这次 boot 与上次**能跑**的镜像差了什么（内核提交、`board.toml` kernel_args、
   payload 变体、DTB、**固件卷**）
2. 差异里有没有新加的 boot-arg（例如 `pong_adreno_start=1` / `pong_metal=1`）
3. 二分：`bootimg --fd <已知能跑的 FD>` / `--kernel-arg <name>=0`，一次只回退一个变量
4. 固件卷本身可能是变量：`scripts/extract_fd.py` 把 `_FVH` 之前的 shim 之后的 FD 抽出来比 sha256

## unixnu 分区：不要整体覆写

`scripts/build-k60-root-image.py` 生成的 `unixnu-root.img` 是**全新安装**用的三窗口镜像，
Data 窗口只有 32 MiB 的种子。设备上 `/dev/block/sda38` 已经是正确布局，而且 Data 是
19.87 GiB 的真实卷：

- OS / SystemOS 的 sha256 与新建镜像逐字节一致 → 没有理由重写
- Data 一旦被 7.8 GB 的镜像覆盖，就退回 32 MiB 种子，等于销毁用户数据

所以 partition 维持现状，只有 `boot.img` 需要更新，而且用 `fastboot boot` 从内存启动，
不写任何分区。

## 硬约束

- 只允许 `fastboot boot`。**永不** `fastboot flash` 任何 Android 分区，**永不**碰 `persist`
- 每次 boot 前确认 `git status --porcelain` 为空（铁则 2）与 `snap-*` 标签已推（铁则 7）
- 没有日志的"看起来好了"不算 ⑧ 上机通过
- 同一时刻只允许一个 collector；不要手工再开一个窗口抓同一个口
