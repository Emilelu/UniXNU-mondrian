# 仓库与目录登记表

> 为什么有这张表：上下文压缩会丢掉会话里记住的路径，然后就会去错的地方找文件、
> 改错的副本、或者对着一个不是 git 仓库的目录做"版本管理"。
> 这张表是地址簿，不依赖任何一次对话的记忆。
>
> 最后核对：2026-11-12

---

## 一、三个组件仓库（我们自己维护）

| 组件 | 仓库路径 | 远端 | 构建时用的路径 |
|---|---|---|---|
| 设备仓库 | `E:\hackios\UniXNU-mondrian` | `Emilelu/UniXNU-mondrian` | 源码；`/opt/k60/trees/usb-cdc-mainline/device` 是它的镜像 |
| 框架 / `unixnu` CLI | `E:\hackios\UniXNU` | `UniXNU/UniXNU` | **`/opt/k60/trees/k60build`** 是运行时副本（**不是** git 仓库）|
| UEFI 固件 | `E:\hackios\uefi-mondrian` | `Emilelu/uefi-mondrian` | 同一路径，直接构建 |

**关键区别**：`/opt/k60/trees/k60build` 是 `E:\hackios\UniXNU` 的**副本**，没有 `.git`。
所有 `./unixnu ...` 命令都在这个副本里跑，但它不是版本控制的真源。
改了副本不改仓库 = 漂移（见铁则 5、P-148）。

---

## 二、yibiya 的参考镜像（只读，自动跟随）

| 镜像 | 对应的远端 | 分支数 |
|---|---|---|
| `/mnt/e/k60-work/references/yibiya-upstream` | `yibiya/UniXNU-mondrian` | 8 |
| `/mnt/e/k60-work/references/yibiya-unixnu-upstream` | `yibiya/UniXNU` | 4 |
| `/mnt/e/k60-work/references/yibiya-uefi-upstream` | `yibiya/uefi-mondrian` | 1 |

这三个由 `scripts/track-upstream-branches.py` 每小时跟随全部分支，
状态存 `/mnt/e/k60-work/.upstream-branches.json`。

---

## 三、构建输入与工作区

| 用途 | 路径 | 说明 |
|---|---|---|
| 构建输入（device）| `/opt/k60/trees/usb-cdc-mainline/device` | `E:\hackios\UniXNU-mondrian` 的镜像，由 `scripts/sync-device-input.py` 单向同步 |
| 构建树（框架副本）| `/opt/k60/trees/k60build` | `E:\hackios\UniXNU` 的副本，**无 .git** |
| 构建输出 | `/opt/k60/trees/k60build/out-baseline/mondrian/ipados-16.6.1-20G81/mondrian` | kernel / payload / device-tree 都在这里 |
| 镜像产物 | `/mnt/e/k60-work/usb-a-stage/out` | `boot-*.img`、`keep-*.img` |
| 串口日志证据 | `/mnt/e/k60-work/evidence/usblog-*` | 每次 `boot-and-capture.ps1` 一个目录 |
| 草稿 | `/mnt/e/k60-work/scratch` | **只放草稿**，跑通的东西同一轮搬进仓库 |
| 上游镜像根 | `/mnt/e/k60-work/references` | 所有 `*-upstream` 参考镜像 |

---

## 四、打镜像必须用哪个 DTB

```
✅ 内核 DTB（我们的）：
   /opt/k60/trees/k60build/out-baseline/mondrian/ipados-16.6.1-20G81/mondrian/device-tree/hardware.dtb
   ~2,925 B

❌ 不要用（UEFI 的全量 DTB，480 KB，会让镜像起不来）：
   E:\hackios\uefi-mondrian\Platforms\Xiaomi\mondrianPkg\FdtBlob\sm8475-xiaomi-mondrian.dtb
```

**判据**：`./unixnu bootimg --dtb` 传进去的 DTB，打进 boot.img 后是 kernel 区的尾部。
把两个镜像的 kernel 区解 gzip 后比尾部长度，差几百 KB 就是传错了文件（P-149）。

---

## 五、固件卷

```
E:\hackios\uefi-mondrian\Build\mondrianPkg\DEBUG_CLANGPDB\FV\SILICIUM_UEFI.fd
3,145,728 B（固定 3 MiB，board.toml 的 [uefi_fd] size 强制校验）
最后构建：2026-11-02 18:04
```

`unixnu build firmware` 会校验它必须正好 `size` 字节，否则报错。

---

## 六、刷机与抓日志

```powershell
# 刷并抓（官方脚本，会重开串口接 panic）
E:\k60-work\usb-a-stage\scripts\boot-and-capture.ps1 -Image <img> -Seconds 140 -ReopenSeconds 100

# 进 fastboot
wsl -u root -e bash -c "cd /mnt/e/hackios/UniXNU-mondrian && bash scripts/k60-device.sh bootloader"

# 只刷不抓
wsl -u root -e bash -c "cd /mnt/e/hackios/UniXNU-mondrian && bash scripts/k60-device.sh boot <img>"
```

串口是 **COM5**（USB CDC-ACM，VID_1209）。复位回 fastboot = panic（`k60_panic_reset=1`）。
