# HANDOFF — 当前状态（滚动覆盖，只写「现在」）

## 最新状态（2026-11-06 02:25，覆盖下面的旧记录）

### 0334-0339 全部失败的根因：已找到并修复（pitfall #74）

`/tmp/k60build/profiles/os/ipados-16.6.1-20G81/profile.toml` 的 `extra_args` 残留
`--keep-personalities com.apple.driver.AppleMobileFileIntegrity` ⇒ 真 AMFI 的
IOKitPersonalities 被保留并 auto-register ⇒ IOAVFamily/AppleImage4 `start()+0x44`
`ldr wzr` 探静态区 → panic（IOKit kext start 在 bsd_init 之前，串口来不及枚举）。
已撤掉该旗标；**0340 验收通过**（补丁集=0333，行为与 0333 完全一致，日志
`evidence/usblog-20261106-020630`）。铁证：撤旗标后 `--apply` 打印
`patched: mov w0,#1 ; ret`，之前全是 `already patched`。
**pitfall #70/#73 的归因已由 #74 更正：探针全程无辜。**

### 主线卡点不变：`No service cache`

机制（§19.4/§19.6/§19.9 已反汇编确认）：launchd 只 fstat 拿尺寸、`vm_allocate` 全零、
`_xpc_shmem_create` 共享、只注册 1 个端口给 loader；loader memcpy 后 launchd 用
`xpc_create_from_plist(同一块内存, st_size)` 解析，非字典即
`abort_with_reason(7,1,"No service cache")`。
唯一嫌疑：loader 的 `mach_vm_map(copy=FALSE)` 写入没有落到 launchd 的 VM object。

### 探针现状（0342 已就绪，等待上机）

三文件安全形态（vm_user.c 零 printf / kern_exec.c 心跳 t=15s 置位 / kern_exit.c 报告）。
0341 实测发现"置位太晚"（打印 `K60MV not-seen`），已改为心跳置位。
**0342** sha `C684032864F9CEEBBF8174185270D5EBAA2DB543842E524ED8E610E91CB16F37`
（`patched: mov w0,#1 ; ret` = 全新产物）。设备在 0341 后挂死，**需手动断电进 fastboot**，
然后 `fastboot boot usb-a-stage/out/boot-amfi0342-20261106.img`。
看 `K60MV head=`：`bplist00` ⇒ 数据已进 object；`00000000` ⇒ 共享写没落地（查
`vm_map_enter_mem_object` / pmap）。

### 关键产物

| 用途 | 路径 |
|---|---|
| 已知可用镜像 | `usb-a-stage/out/boot-amfi0333-20261105.img`（`D926AABA…`） |
| 修复后基线 | `usb-a-stage/out/boot-amfi0340-20261106.img`（`9814333D…`） |
| 探针镜像 | `usb-a-stage/out/boot-amfi0342-20261106.img`（`C6840328…`） |
| profile 备份 | `/tmp/profile.toml.bak-0340` |
| launchd 逆向 | `deliverables/launchd.bin` + `launchd-config.bin` + `scratch/launchd.dis` |
| 完整分析 | `docs/references/USB-SERIAL-AND-AMFI-CHANNEL-20261105.md` §18–§19.12 |

---


## 当前状态（2026-11-06 01:2x 起，覆盖下面的旧记录）

### 已打通（都有实测日志）

1. **USB CDC-ACM 串口日志通道** — COM5，Windows 免驱 `usbser.sys`。
2. **AMFI** — pong 配方：`amfi == NULL`（0318 门控 `k60_miniamfi`，默认关）+ `amfi->` 守卫 +
   `accelerate_entitlement_queries()` 硬绕过。
3. **mount-phase-1/2** — `k60_skip_firmware_mount=1`（0320）。
4. **kern_exit boot task 容错** — 0314（rv=0 + `os_reason_free` + `OS_REASON_NULL`）。
5. **`launchd_cache_loader` 成功** — boot-arg **`launchd_unsecure_cache=1`**（必须是数字 1）：
   `Using unsecure cache:` → `Sending validated cache to launchd` →
   `Cache sent to launchd successfully` → `clean exit (was 0x0)`。
6. **plist + sig 已恢复** 并逐字节校验（之前被 TWRP 误清零）。

### 当前唯一卡点：`No service cache`

launchd（20G81，`/sbin/launchd` 541,600 B）的服务缓存机制已完全反汇编清楚：

```
read_cache_file():  open("/System/Library/xpc/launchd.plist")
                    fstat 拿 st_size          ← 只用尺寸，不读内容
                    vm_allocate(round_up(st_size,page))   ← 全零
                    dispatch_data_create + xpc_data_create_with_dispatch_data
_xpc_shmem_create(ptr, round_up(len,page))   ← 成功（失败是 crash 尾块 0x100040538）
posix_spawnattr_set_registered_ports_np(attr, &port, 1)   ← 只注册 1 个端口
spawn /usr/libexec/launchd_cache_loader 并等它结束
apply_cache(x19)  ← 唯一调用点 0x100040474
    xpc_create_from_plist(同一块内存, st_size)
    结果不是字典 → 0x100019de8 abort_with_reason(7 /*LIBXPC*/, 1, "No service cache")
```

**结论（§19.9）**：缓存内容、AMFI、boot-args、launchd 配置全部已排除
（stock 507 作业版与 pong 风格 23 作业版实测逐行相同；ramdisk hint 也无效）。
唯一剩下的解释是 **loader 通过 `mach_vm_map(..., copy=FALSE, RW, RW)` 的写入
没有反映到 launchd 所在的 VM object**，即内核跨任务共享写路径。

### 已排除的对照（别再重复）

- pong 的 iOS16 **不用原版 launchd**（`compile_init(... overlay/'sbin/launchd')`），
  不走服务缓存路径，不能作为参考；其 patch 集也没有 VM/memory_object 修复。
- ios-sweet 的 XNU patch 只碰 `pmap.c`/`pmap_misc.c`/`vm_kern.c`（PAC / kext 缺口），
  同样没有共享语义改动。
- 唯一跑通过「stock launchd + `launchd_unsecure_cache=1`」的是 ios-sweet（20H392 真机）。

### 下一步（按顺序）

1. 修 Data 卷读取：`/dev/block/sda38` 开头是自研 `SHNGROOT` 头，
   `BASE_LBA=2494976 + NXSB@32` 的旧假设不成立，需扫出真实 NXSB 偏移。
2. 加**最小风险**内核探针（严守 pitfalls #70）到 `mach_vm_map_external` /
   `mach_vm_deallocate`，确认 loader 那次映射的 `copy`、以及 munmap 前该映射前 16 字节
   是不是 `bplist00`。
3. 若 `copy=FALSE` 且数据在 loader 侧可见、launchd 侧不可见 ⇒ 定位到
   `vm_map_enter_mem_object` / pmap 的共享写实现。

### 镜像与证据

| 用途 | 路径 |
|---|---|
| 已知可用镜像（034 之前基线） | `usb-a-stage/out/boot-amfi0333-20261105.img`（sha `D926AABA…`） |
| 裁剪版缓存 | `deliverables/trimmed-cache/launchd.plist.trimmed`（1,384,579 B，sha `58804F45…`） |
| launchd 二进制 | `deliverables/launchd.bin`（541,600 B）/ `launchd-config.bin`（8,278 B） |
| 反汇编 | `scratch/launchd.dis`（77,754 行）/ `scratch/lcl.dis` |
| 完整分析 | `docs/references/USB-SERIAL-AND-AMFI-CHANNEL-20261105.md` §18–§19.10 |

### 设备状态

`6033dbec` — 0336 boot 后 panic 挂住（PSCI 复位未生效），**需要手动断电**回 fastboot。

---

## 当前状态（2026-11-06 00:40，覆盖下面的旧记录）

### 已打通（有实测日志）

1. **USB CDC-ACM 串口日志通道** — VID_1209&PID_0001，Windows 免驱 `usbser.sys`，COM5，实时抓内核日志。
2. **AMFI** — 走 pong 配方：`amfi == NULL`（0318 把 miniamfi 门控在 `k60_miniamfi=1`，默认关）
   + `amfi->` 全部守卫 + `accelerate_entitlement_queries()` 硬绕过。
3. **mount-phase-1 / mount-phase-2** — 0320 的 `k60_skip_firmware_mount=1` 生效。
4. **kern_exit boot task 容错** — 0314（合并 0314+0316）：`rv = 0` + `os_reason_free(p_exit_reason)`
   + `OS_REASON_NULL`，`k60_tolerate_cache_loader=1` 门控。launchd 不再因 boot task 失败 panic。
5. **`launchd_cache_loader` 成功**（本次最大突破）— boot-arg **`launchd_unsecure_cache=1`**，
   日志实证 `Using unsecure cache:` → `Cache sent to launchd successfully` → `clean exit (was 0x0)`。
   ⚠️ 值必须是数字 `1`；写路径会被 `strtoul(...,10)` 解析成 0（详见 pitfalls #68）。
6. **plist + sig 已恢复**（之前 TWRP 误清零）— 设备读回 sha256 与原件逐字节一致（pitfalls #69）。

### 当前唯一卡点

`launchd_cache_loader` 已 exit 0，但 **PID 1 (launchd) 仍 abort**：

```
KX! 5 1 launchd exit=0 sig=6 r=1 ns=7 code=0x1 rf=0x206 jf=0x0
KXP 1 /private/var/pong/init
pid 1 exited -- exit reason namespace 7 subcode 0x1, description No service cache
```

`rf=0x206` = `OS_REASON_FLAG_ABORT|FROM_USERSPACE|GENERATE_CRASH_REPORT`，即 launchd 自己 `xpc_abort`。

**已排除**：AMFI 服务、签名、plist 内容非法、loader 读不到 plist、launchd 分配的 memory object 太小
（太小会导致 `mach_vm_map` 失败并打印 `Unable to map launchd memory`，日志里没有）。

### 下一步（按优先级）

1. **给 XNU 加 k60 探针：`mach_ports_register`（`osfmk/kern/ipc_tt.c`）**
   打印注册方 pid / port 数 / 每个 port 若是 vm_object 则打印 size。
   一次判定「`ports[0]` 是不是那个 1388544 字节的缓存对象」，以及 launchd 到底分配了多大。
2. 若 size 正确 ⇒ 问题在 launchd 读取/解析侧，改为对 `mach_vm_map`（`osfmk/vm/vm_user.c`）加探针，
   看 loader 的 `copy=0` 映射是否真的共享。
3. 对照实验（可并行准备）：把 `launchd.plist` 换成 pong 风格的**裁剪版 Version 7 缓存**
   （参考 `references/UniXNU-pong/userland/mkjobs.py` 的 CORE/DENY），体积压到 < 4 KiB。

### 关键文件

| 用途 | 路径 |
|---|---|
| 最新镜像 | `E:\k60-work\usb-a-stage\out\boot-amfi0333-20261105.img`（sha `D926AABA…`） |
| 突破日志 | `E:\k60-work\evidence\usblog-20261106-002647\console.log`（sha `5C7DD213…`） |
| boot-arg 改写 | `E:\k60-work\scratch\rewrite-toml-0333.py` |
| 打包 | `/tmp/payload-0333.img` + `scratch/splice-generic.py` |
| plist/sig 恢复 | `E:\k60-work\usb-a-stage\scripts\restore-plist-twrp.ps1` |
| loader 反汇编 | `E:\k60-work\scratch\lcl.dis`（`llvm-objdump --macho -d`） |
| 完整分析 | `docs/references/USB-SERIAL-AND-AMFI-CHANNEL-20261105.md` §18 |

### 设备状态

`6033dbec` — 0333 boot 后 panic 挂住（PSCI 复位未生效），**需要手动断电**才能回 fastboot。

---

> **用法**：新会话/新 agent 进场，读完 `D:\Android\AGENTS.md` 与本页，就等于接上了上一轮的脑子。
> **写法规矩**：本文件**滚动覆盖**，只写「现在正在发生什么」——不写历史、不写定案、不写踩坑细节。
> - 定案 → [DECISIONS.md](DECISIONS.md)
> - 待解问题 → [ISSUES.md](ISSUES.md)
> - 坑 → [PITFALLS.md](PITFALLS.md) / [PITFALLS-FROM-HISTORY.md](PITFALLS-FROM-HISTORY.md)
> - commit / 里程碑 → [HISTORY-LEDGER.md](HISTORY-LEDGER.md)
> - 资产在哪 → [MASTER-INDEX.md](MASTER-INDEX.md)
> **每次状态变化（开一路活、收到一路结果、用户拍板一次）必须回来改本页**，并更新下面的「最后更新」时间。这是铁律 1 的延伸：状态不落盘 = 下个 agent 失忆。

**最后更新：2026-11-05（Asia/Shanghai）**

> **构建环境已恢复（2026-11-05 11:26）**：用户授权后启用 `Microsoft-Hyper-V-Hypervisor`+`HypervisorPlatform` 并重启；`HypervisorPresent=True`，WSL/clang-24/`/tmp/usb-cdc-mainline`/`/tmp/k60build` 全部可用（I-20261105-02 已关闭，坑 #58 已补后续）。

> **WSL 空间线（2026-11-04 晚，A 组已执行）**：apt 缓存清零 + os-dd.bin 删除 + consolecap 归档后删除（日志在 `archive\wsl-consolecap-logs-20261104\`，MANIFEST 校验通过）；df Used −13.2G，vhdx 物理 66.9G 未缩。**待办：compact/fstrim 轮**——前置条件 = USBM 线审计收工 + `~/k60-data-build` 空闲（可 wsl --shutdown）。详见 [references/WSL-RECLAIM-AUDIT.md](references/WSL-RECLAIM-AUDIT.md)。

> **当前生效铁律 5**（用户 2026-11-04）：「后续所有工作以调研文档驱动进行，而不是做一点猜一点。调研结果必须审阅确保万无一失。没得到充分可行结论不要操作。」
> 含义：本页「下一步第一动作」只有在对应**调研文档已审阅**时才可执行；否则第一动作是**补调研**，不是动手。

---

## 1. 现在卡在哪

- **主线（唯一）**：iOS 16.6.1 / 20G81，`fastboot boot` 起 XNU，pong 用户态前置层。
- **里程碑（2026-11-04 定稿，经种子自带排除复核）：pong 用户态适配已越过关键一步**——init 全链路跑通并 exec launchd；**launchd 起到 installd/keybag/偏好系统层，SpringBoard 写 prefs、设置助理标记 Setup 完成**。以下全部为 **mtime/内容归因（盘侧实读），不是推断**；且已与基线镜像（20354 pristine）逐项对照，**除注明剔除者外均为运行时新写（基线无）**：
  - `/codes`、`/containers/{Bundle,Data/System,Shared/SystemGroup,Temp}`、`/installd/Library` mtime = epoch+35s——**`/containers` 骨架属 installd 级产物，非 init 可造**（init 源码无任何创建这些路径的调用）；
  - `/db/com.apple.xpc.launchd/disabled.plist`、`/keybags/systembag.kb`、`/mobile/Library/Preferences/com.apple.{springboard,purplebuddy}.plist` mtime = epoch+36s（基线均无此四件）；init trace `/pong/status.txt` create = epoch+44s（token 全链 `A0…E1`）；
  - 内容验证：`disabled.plist={'com.apple.watchdogd': True}`；`com.apple.springboard.plist={'BKNoWatchdogs':1,'FBLaunchWatchdogExceptions':{purplebuddy:100}}`；**`com.apple.purplebuddy.plist={'SetupDone':1,'SetupFinishedAllSteps':1,'SetupVersion':11}`**；`systembag.kb={'KeyBagKeys':b'SWEET'}`（占位，判移植侧 stub 写）。
  - **剔除项**：`/mobile/Library/Preferences/.GlobalPreferences.plist`（89 B）**基线已有且 sha 相同（`633dfefd…`）= 种子自带，不作运行时证据**。
  - **独立复核（2026-11-04，本 agent 经 adb+KernelSU 只读 dd + 项目 apfs.py 重跑，容器 xid=16）**：`/codes` 仅空目录本身；`/containers = {Bundle, Data, Data/System, Shared, Shared/SystemGroup, Temp}` 全为空目录；**`/containers/Data/Application` 不存在、无 UUID 容器、无 Bundle 内容、无 metadata.plist** → 判定「无真实 app 容器入驻，仅空骨架」，与上条里程碑一致。设备=基线镜像 + 运行时增量（+15 目录 / +6 文件，零删除）；读取 240 块 ×4 KiB、12 次 dd、零写入。报告 `E:\k60-work\tmp\codes-containers-{device,local}.json`。
- **当前卡点（2026-11-05 深夜）——AMFI 已解决，mount 全通，剩 `launchd_cache_loader` 签名验证**：
  0318 按 pong `ios16` 配方让 `amfi` 表保持 NULL（`AMFI interface left NULL` + `accelerate_entitlement_queries` bypass 分支命中），AMFI 查找问题解决（`Unable to find AMFI` **0 次**）。0320 补丁让 mount-phase-1/2 的 firmware/factorydata bind mount 在 union 模式下放行（`k60_skip_firmware_mount=1`）。launchd 跑完全部 boot task 直到 task 22 `launchd_cache_loader`。
  **新卡点**：cache loader 读 plist+sig 后需要通过 Security.framework 验证签名 → plist+sig 已被我们从 TWRP 清零 → `errSecCSSignatureInvalid` → abort → launchd panic。**注意**：AMFI 查找那关已经过了（错误从 `Unable to find AMFI` 变为 `errSecCSSignatureInvalid`），说明 `amfi==NULL` bypass 生效。
  **下一步（二选一）**：① 从 TWRP 恢复 plist+sig 原始数据（脚本 `restore-plist-twrp.ps1` 已备），让 loader 正常验证签名 → 可能因 `amfi==NULL` bypass 而通过；② 按 pong `userland/build.py:464` 从 OS 卷**删除** `launchd.plist + .sig`，让 cache loader 根本不 spawn。
  详见 `references/USB-SERIAL-AND-AMFI-CHANNEL-20261105.md` §12-§17（坑 #64-#67，铁律第 8 条）。
- **自动复位进 fastboot**：PMIC SDAM7100 写入**成功**（串口确认 `PMIC restart reason primed for fastboot`），但 PSCI SMC 在此板不生效（调用返回、设备停panic）。**power-cycle 后 ABL 读 PMIC → 进 fastboot ✓**。dev loop = power-cycle → fastboot → boot → panic → power-cycle → fastboot。全自动复位需硬件看门狗（APSS WDT `0x17C10000`）。
- **设备当前状态**：卡在 0331 panic 画面，COM5 枚举但不可通信。守望脚本 `pwsh-2fee8569b0c94faf` 等待 fastboot（到 00:37）。**需人工 power-cycle**。
- **init 写入状态不变**：v12union init 35,160 B 在 sda38 LBA 2501111..2501119，备份在 `rollback\pong-init-20261105-011015\`。
- **不要再去查窗内容有没有坏**——三窗内容从未受损（PITFALLS 第 19 条）。
- **不要再去查窗内容有没有坏**——三窗内容从未受损（PITFALLS 第 19 条）。

## 2. 正在跑的几路（并行，互不冲突）

| 路线 | 会话 | 当前进度 |
|---|---|---|
| 全局资产索引（D 限 `D:\Android` / E / F / WSL） | `e626b3393773a2c7ad91ef17` | **已完成**：`MASTER-INDEX.md`（29.7 KB）+ `master-index.json`（258 条）+ `master-index-wsl-sha256.txt`（WSL 侧 207 条关键资产哈希）；D 盘 0 条越界 |
| 到 SpringBoard 差距评估 | `bf327214dc1a8cd77d0afc76` | **已完成**：`references/GAP-TO-SPRINGBOARD.md`（26 KB：8 级进度表、12 环依赖链、16 行硬件缺口表、19 项未调研清单、审阅记录 12 条） |
| `unixnu.com` 官网全站程序化索引 | `65e4603067d46f893d704c29` | **已完成**：664 页全量 / 0 失败 / 370.7s / 存档 10.6 MB / `devices-map.json` 234 条 / 增量 0.3s 验证通过；产物 `UNIXNU-SITE-INDEX.md` + `unixnu-site-index.json` + `tools\unixnu-site\`；每日 07:00 定时增量已挂 |
| 上游同步机制（UniXNU org + devices 页 + 同 SoC 仓） | `84c1751be1d956093c2084f3` | 产出 `DEVICE-REPOS.md` + `devices.py list/find` + `push-check.py` + `UPSTREAM-SYNC.md` |
| console 全量落盘（内核环形区 → Data 卷文件） | `195c52805ef0d3aca0863a7e` | **2026-11-05 单变量 boot 已完成，盘侧判读：未打通，I-20261105-01**。v11drain init 34,912 B / `12b9df42…` 写入 sda38 前先备份完整 LBA 2501111..2501119（36,864 B，sha `ED6C3BF1…`）；写后 extent 和 34,912 B bare-prefix 回读 sha 均过。镜像 `boot-usb-console-export-20261104.img` / `a246507b…` 只 `fastboot boot` 成功。用户报告屏显 `Pong init: var: stat root`，之后 Android ADB 回连；屏行不作死点。完整 APFS OwnerData xid=18 盘侧解析：新 `/pong/console.log` inode 249 root:wheel 0644，size=0 B；旧 `/pong/status.txt` 39 B；没有轮转文件。由新 inode + init 源码执行顺序，确认 init 已 fork drainer 且跑到 mkdir/open。**源码接口缺陷已确认，运行时 errno 未直接记录**：drainer 传 cursor `newp`，0243 OID 仅 `CTLFLAG_RD`；实际 XNU `kern_newsysctl.c:1709-1714` 对这种请求形态会在 handler 前返回 EPERM，handler 不可达；这与 APFS 空日志相符。修复前置 = 评审启用 `CTLFLAG_WR` 的权限/安全边界，或另定 cursor 协议；本轮未改代码/重构建。完整取证 sidecar `E:\k60-work\evidence\console-drain-20261105\SIDECAR.json`；原始 dd dump sha `35E496AB…`，精确 APFS image sha `257AEC0B…`。**当前不要再次 boot**；下一步先离线核对 0243 sysctl ABI、header 大小、libmini 返回长度和 payload args，再出新验证单等批准。写前备份和闸门记录 `E:\k60-work\rollback\pong-init-20261105-011015\`。 |
| USB 内核日志通道 | `0a3dfab398a69b8f463bfa96` | **按用户优先级暂停**：cdc4 镜像仍仅为离线构建件，未用本轮 boot 窗口测试；console-export 首轮问题定位期间不再启动 USB 线。已有 cdc3 B 决策证据留档：`:921` 指纹为 0；B 决策载体 `d881352`、0301–0305 `1c0f468`。 |

## 3. 拍板状态

**已拍板（2026-11-04）**

- **USB 那一版要动代码，但必须一步到位**：动代码**前**先完成「实施级研审闭环」（调研文档逐条证据 + 缺失项判定实验 + 落点/失败形态/回滚 + 复审签名），**审不过不许改**。方案仍是单点 `k60_usblog.c`（≈450 行）+ `k60_usblog=2` 一档到底，不做 v1/v2/v3 分档。
- **用户态顺序：先补全所有缺失文件**（不是先加 `status.txt`）。缺件全量 = `/pong/etc/var.skel`、var-seed 内容树、boot-jobs、empty-hal、`/private/var/pong/Wallpaper`、`libpong-ui.dylib` 等（以 `references/USERLAND-PONG-GAP-AUDIT.md` 的缺件表为准）。`status.txt` 旁路日志降为「补全后仍判不出卡点」时的备选。
- **前置风险（必须先证）**：现有写入手法是「同长度覆盖已存在文件的 extent」，**新增文件要修改 APFS 元数据**——这条路径在无 macOS/hdiutil 的环境下必须先有实测或明确风险分级，不允许直接当覆盖写。
- **日志要全量且限容（2026-11-04）**：光 `status.txt` 抓不到内核前缀（内核 printf 早在 init 之前）。要做「内核 console 环形区（`0xA7000000` / 2 MiB / `DBGC`）→ Data 卷文件」的排水器，抓全部 XNU 输出；**总配额 64 MiB（4×16 MiB 轮转）、剩余 <500 MiB 停写**，绝不无限追加。

**仍待拍板**

3. `k60build` 5 个未推 commit（`cafab71` + 本轮 4 个）是否 push。
4. `references/pong-usb` 工作区未提交改动（`AGENTS.md`、`Dwc3Registers.h` 为 M）——责任方查清与恢复。

## 4. 下一步第一动作

- **下一步第一动作 = init drainer 加固的可行性判定（离线）**：通道已打通，下一目标是把 `console.log` 权限从 0644 收到 0600，并落地配额/floor/fsync/轮转/STOP 语义。硬约束：init 当前 34,912 B，inode.size 上限 35,160 B，只剩 248 B。先做一次离线尺寸实验（host 编译 + `size` 断言），确认这些加固能否装入；装不下则先立项“扩大 init inode 或外置 helper”，不在未证实情况下改设备 init。
- **设备状态**：本轮 boot 后设备停在 **TWRP recovery**（`twrp_mondrian-eng`，root 可读块设备）。init extent 未动，备份仍在 `rollback\pong-init-20261105-011015\`。任何后续写分区/boot 仍需用户明确批准。
- **第二列（显示交接：判据 3 落地 → 转查 GUI 进程）**：gfx 镜像（`65D8F295…`）15:41:02 下发，屏仍停 Pong init 文字帧 ⇒ **交接未触发，无进程提交过第一帧**。T3 盘侧取证（xid 15→16）：崩溃证据全空（DiagnosticLogs/cores/log/diagnostics 全 0 项）；Caches 空、containers 骨架空；**`disabled.plist`/`purplebuddy.plist`/`springboard.plist` mtime 39s→45s 被同内容重写** ⇒ **判定②：SpringBoard/purplebuddy/launchd 活着但没提交帧**（非显示驱动问题）。下一步：查 swap 调用方（backboardd/WindowServer 的 IOMobileFramebuffer 打开/提交路径）——盘侧无直接证据，候选通道 `fbtrace=N` 或内核日志出口（drainer/USB）。
- **后续按序**：① 用户批准新短单 → 单变量 boot 0306 镜像；② 盘侧判读新 console.log 是否含 marker/payload，判定 sysctl 通道是否打通；③ 若打通再评估 init drainer 加固（0600/配额/floor/fsync/STOP，受 35,160 B inode.size 上限约束）与 USB reader 实测。USB CDC 暂停。
- **显示侧（帧缓冲映射重建/滚屏区）**：另开平行线，**不在当前关键路径**（I-20261104-07 分节）。
- **init/设备写入闸门**：当前 v11drain 34,912 B（≤35,160 B inode.size 硬上限）；本轮已有完整 9-block 备份。不得再写 init 或加 probe，除非先落审阅调研文档并另获用户明确批准。
- **纯只读可立即做（无需拍板，来自 GAP 体检 U1–U3）**：U2 在 WSL 只读核对 A 树 `kern_minimac.c` 是 376 行 ios16 版还是 482 行 Darwin24 版（M1 前提）；U3 clone 精读 zizhan（同 SoC、A730 已上屏）；U4 clone 精读 udon（同 SoC 117 进程 + dyld 缓存入容器）。

## 5. 不要重复尝试（已证死，别再花时间）

| 别再试 | 为什么 | 出处 |
|---|---|---|
| ramoops 读 XNU 日志 | 结构性不可用：内核重启即失内存；TWRP 未编 `CONFIG_DEVMEM`/`CONFIG_DEVKMEM`/`CONFIG_KCORE`，`mknod` 绕不开 | PITFALLS 第 16 条、D-2026-11-04-01 |
| `fastboot flash` 任何分区 | 硬边界，违反即事故 | AGENTS.md 硬边界 |
| 按 v2 清单几何读设备（OS@`0x1000`、SystemOS@`0x180100000`） | 会读出「三窗全毁」的假灾情，21:43 已误判一次 | PITFALLS 第 19 条 |
| v1/v2/v3 分档试探 | 用户明确否决，要一步到位取成功率最高的方案 | 本次对话 |
| PowerShell 5 `New-Object byte[]` 拼块 | 段长漂移（36576≠36864），`gate3` 假报"整段 sha 不符" | PITFALLS 第 17 条 |
| `Start-Process -RedirectStandardError` 跑 adb | adb daemon 重启时死锁 | PITFALLS 第 18 条 |
| 在 XNU 阶段等 USB / 看屏以外的手段取日志 | XNU 接管后 USB 全断，屏摄 + Data 卷旁路日志是唯一证据 | D-2026-11-04-01 |
| 同卷混用「手工 dd extent」与 apfs.ko 写 | apfs.ko spaceman 把手工 extent 的块当 free 复用，会吃掉手工放的文件（init 被覆盖成 var.skel） | PITFALLS 第 24 条、I-20261104-02 |
| 在「无 `/pong`」的镜像上注入 | 镜像代际误判：pristine 20352 无 `/pong`/init，20354 才有；注入前必须先核对基底含目标文件，否则成功也部署不到设备 | PITFALLS 第 25 条 |
| 用写死长度算零填充 | 段长漂移（36872≠36864）→ Gate3 假失败假回滚；填充必须 `ExtentBytes - (Get-Item <file>).Length` + 断言总长 | PITFALLS 第 28 条 |
| 按「屏上最后可见行」定死点 | console 会静默死亡（write 返回成功但不上屏），进程实际跑到 execve；死点判定必须带外通道互证 | PITFALLS 第 44 条、I-20261104-06 |
| 采样扫描断言「文件不存在」 | APFS 新分配在高块（扩容容器 omap 在 5128782），覆盖不全即假象；「不存在」只接受目录树解析/全盘扫描 | PITFALLS 第 45 条 |
| 把程序自报成功当落盘证据 | 自报只证明返回码，不证明持久化；前提类结论必须独立通道回读 | PITFALLS 第 43 条 |
| init 超 35160 B 只 dd 覆写 | raw extent 覆写不更新 inode.size（残留 35160），超限会被 exec 截断 | PITFALLS 第 46 条 |
| 再往 init 里加用户态探针 | init 链路已证全通（token 链到 E1），问题域移到 console/launchd；用户态探针不再产出新信息、只烧上机次数；要观测走盘侧通道 | I-20261104-06/07 |

## 6. 一句话交接

> 里程碑：**pong 用户态适配已越过关键一步**（init 全链路通并 exec launchd；mtime/内容归因 launchd→installd→SpringBoard prefs→Setup 完成，见 §1）。当前唯一卡点 = **观测通道**（console 静默死亡 + 无日志出口）；下一步第一动作 = **USB 通道上机验证**；显示侧另开平行线不占关键路径；init 禁改（35,160 B 上限余量 280 B）；判读只信盘痕迹（BOOT-PROGRESS-MARKERS）。
