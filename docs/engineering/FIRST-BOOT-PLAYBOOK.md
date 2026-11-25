# K60 首启判读手册（First Boot Playbook）

> 面向 A1（运行时/首启线）与后续接手人。所有值均为本仓实测，不要凭记忆改。

## 0. 物料与校验和

| 物件 | 路径 | 大小 | sha256 |
|---|---|---|---|
| payload（`fastboot boot` 用） | `D:\Android\k60-ios\payload\payload.img` | 201,326,592 B (192 MiB) | `7C03ED4194B938E72DCFB8DA2505C9F2570E1F48892C2F32B03F92CA1F7AE834` |
| SHNGROOT（刷 `unixnu` 分区） | `D:\Android\k60-ios\shngroot\userdata-root.img` | 7.3 GB | 需在使用前 `Get-FileHash` 记录 |
| payload 元数据 | `D:\Android\k60-ios\payload\payload.json` | 588 B | — |

payload 内已核实：
- `EFI/UniXNU/unixnu.toml` → `args = "-v native-ufs=1"`，`path = "Payloads/kernel.macho"`
- `Payloads/kernel.macho` = 54,460,416 B（真 prelink 镜像）
- `Payloads/kernel.macho.adt` = 14,284 B，含 `C5DAF029-2070-4F68-B3CC-1D1320344CF0`
- prelink 组件 39 个，含 `IOStorageFamily` / `apfs` / `corecrypto` / `CoreTrust` / `AppleImage4` /
  `AppleEffaceableStorage` / `kec.pthread` / `IOHIDFamily` / `IOGPUFamily`

## 1. 刷机（只允许这两步）

```powershell
# 手机在 Android：
D:\Android\platform-tools\adb.exe reboot bootloader
D:\Android\platform-tools\fastboot.exe devices          # 期望 6033dbec  fastboot

# 1) SHNGROOT → unixnu 分区（32 GiB，LBA 53342976..61731583）
D:\Android\platform-tools\fastboot.exe flash unixnu D:\Android\k60-ios\shngroot\userdata-root.img

# 2) 只 boot，不 flash boot
D:\Android\platform-tools\fastboot.exe boot D:\Android\k60-ios\payload\payload.img
```

**红线**：绝不 `flash` 任何 Android 分区（`persist` / `modemst*` / `userdata` / `boot` / `vbmeta`…）；
`unixnu` 是唯一允许写的分区。绝不 `fastboot flash boot`。

## 2. 期望的启动序列（按顺序出现才算正常）

| 阶段 | 期望现象 | 失败含义 |
|---|---|---|
| UEFI | 屏幕出现 UniXNU 菜单（标题 `UniXNU`，条目 xnu/Reset/Power off/Tools），`-v` 已带 | UEFI 未起 → 检查 payload FAT / DarwinBoot |
| DarwinBoot | 内核开始输出 `-v` 日志（Apple 风格 `AppleARMPE` / `Darwin Kernel Version`） | 卡在黑屏 → 内核未解压/入口错 |
| XNU 早期 | `vm_page_bootstrap` / `pmap` / `PE_init` / `IOKit` 初始化 | panic 在 pmap → 内存窗/dram-size 错 |
| UFS 控制器 | 我们的驱动日志（`PONG_UFS:` / `NativeUfs` / SHNGROOT 窗口） | 无输出 → DTS 节点未匹配（`qcom,sm8475-ufshc`）或 SMMU |
| 块设备发布 | `IOBlockStorageDevice` 注册、`IOMedia` 出现（disk0…） | 有 UFS 无 media → 窗口/manifest 解析 |
| APFS | `apfs_vfsop_mountroot` / 挂载 OS 卷（UUID `C5DAF029…`） | 挂载失败 → root_match UUID / 认证（AppleImage4/CoreTrust）|
| bsd_init | `bsd_init` 完成、`launchd` 被 exec，`execve` 返回 0 | `exec of /sbin/launchd failed, errno 2` → 根卷没有 userspace（挂错卷）|

## 3. 需要采集的证据

1. **屏幕照片**（每阶段至少一张，含 panic 全文）。手机无串口，照片是唯一直接证据。
2. **QR / Advanced Logger**：只能读 **unixnu 固件/loader 侧**日志（RAMDISK 识别、DARWINBOOT 窗口、storage 枚举）；**XNU 内核 panic 读不到**。内核 panic 只能靠屏幕照片或 UART。
3. **pstore / ramoops**：内核起来后 `/private/var` 或 ramoops 区若有落盘，优先拉取。
4. **UART**（若 Type-C SBU 调试线已到）：`qup_uart@99c000` @115200，把 `serial=3` 加回 boot-args。

## 4. 已知失败签名 → 处置

| 签名 | 含义 | 处置 |
|---|---|---|
| `panic: Process 1 exec of /sbin/launchd failed, errno 2` | 根卷挂上了但没有 userspace（早期 seed/rd=md0 实验就是这个） | 确认 SHNGROOT 的 OS 卷被选中（UUID 匹配），而不是 Data 卷 |
| 卡在 UFS 寄存器读、无 panic | SMMU/时钟/电源域未开 | 对照 `PongUfsTransport.cpp` 的 GDSC/AXI/AHB 序列；确认 DT 窗口 |
| `IOBlockStorageDevice` 未定义符号（链接期） | bindings 未生效 | 不该再出现；若出现查 `interface-audit.json` 的 `fixed_prelink_base` |
| 一写 RSC `0x17a00000` 整机死 | XPU/电源域硬墙 | 用 `k60rpmhoff=1` 绕行（触摸线 A3 负责） |
| 内存相关 panic（页数不足/pmap） | ADT `dram-size` / 内存窗不对 | 见 `MEMORY-PLAN.md`；`ram-notches` 补丁需先进内核 |

## 5. 迭代闭环

```
改 device 仓 board.toml / dts / 启动参数
  → GHA: kernel payload（pre_build=k60-macos-preflight.sh, upload_kernel=true）
  → 下载 payload artifact → 覆盖 D:\Android\k60-ios\payload\payload.img
  → 跑 integration-gate.py 确认 fixed_prelink_base / 表地址仍自洽
  → fastboot boot 复验
```

**每次改动都必须**追加到 `AGENT-COORDINATION.md`（append-only，带时间戳与 sha256）。

