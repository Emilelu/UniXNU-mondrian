# Boot 流程（唯一入口）

> 铁则 8：**没有串口日志的 boot 是盲实验。** 每一次 `fastboot boot` 都必须带着
> CDC-ACM 控制台抓取一起跑，并且必须在 boot **之前**挂上。

## 为什么有这一页

2026-11-12 有一次 boot 挂死在早启动，控制台一次都没出现，却没有任何日志留存 ——
当时是靠"人记得先开一个窗口跑 `capture-k60-usblog.ps1`"，忘了就整轮只能猜。
那一轮的结论甚至是从"是不是找不到 unixnu 分区"这种猜测出发的。

能被忘掉的流程不是流程。现在抓取由 `flash.sh` 无条件启动，本页把判读方式写死，
`scripts/check-boot-procedure.py` 反过来检查 `flash.sh` 还带着这段，防止被"简化"掉。

## 一条命令

```bash
bash /mnt/e/k60-work/scripts/flash.sh /mnt/e/k60-work/usb-a-stage/out/<img> <秒数>
```

补丁集与上次成功启动的不同时，门禁 S 项要求显式声明：

```bash
K60_FORCE_NEW=1 bash /mnt/e/k60-work/scripts/flash.sh <img> <秒数>
```

`K60_FORCE_NEW=1` 不是绕过门禁：其余每一项照旧检查，只是不再因为"补丁集变了"而失败。

## flash.sh 内部顺序

1. `porting-gate.py --quick`（文档/porting/patch 结构/序列指纹）
2. `eight-step-gate.py --flash`（①~⑦ 全绿 + ⑧ 的成功/失败预测）
3. `research-gate.py`
4. 设备状态检测 → 需要时 `adb reboot bootloader`，等 fastboot（120 × 2 s）
5. **启动串口抓取**（`capture-k60-usblog.ps1`，后台）
6. `boot-and-capture.ps1` → `fastboot boot <img>`
7. 串口判定 + 证据目录路径

## 串口控制台长什么样

- 内核 gadget 枚举成 `USB\VID_1209&PID_0001`，自动绑 `usbser.sys`
- COM 号**不在** FriendlyName 里，只能在
  `HKLM\HARDWARE\DEVICEMAP\SERIALCOMM` 里找 `\Device\USBSER000`
  （按 FriendlyName 挑会选中蓝牙猫 COM3/COM4，那是错的）
- 必须 `DtrEnable = $true`，否则内核不排空 console ring
- 证据目录：`E:\k60-work\evidence\usblog-<yyyyMMdd-HHmmss>\console.log`

## 判读：控制台没出现意味着什么

`K60 console never appeared` 不是"日志脚本坏了"，是**内核没走到 USB gadget init**。
这句话本身就是早启动挂死的硬证据：UEFI 之后的代码在执行到 gadget 之前就停了。
此时不要再猜 UI 层现象（"好像找不到 unixnu 分区"），要按早启动路径查：

1. 这次 boot 与上次**能跑**的镜像差了什么（内核提交、`board.toml` kernel_args、payload 变体、DTB）
2. 差异里有没有新加的 boot-arg（例如 `pong_adreno_start=1` / `pong_metal=1`）
3. 二分：用 `--kernel-arg <name>=0` 重新出 payload + bootimg，一次只回退一个变量

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
