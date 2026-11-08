# K60 进系统 · 压缩后必读账本

> 这份文件的唯一用途：**上下文被压缩后，第一眼读完它就能回到正确的状态**。
> 只写四类内容：已验证事实、已排除的假设、硬规矩、当前阻塞。
> 不写过程叙事。每轮结束更新。

---

## 一、硬规矩（违反过一次就会重犯旧错）

0. **动手前必须先读这四份，禁止凭记忆开工**
   - `docs/reference/PITFALLS-FROM-HISTORY.md`（1,969 行，坑的完整目录）
   - `docs/reference/ISSUES.md`（487 行，问题+根因+修法）
   - `docs/reference/DECISIONS.md`（357 行，为什么这么选）
   - `docs/plans/APPLY-PIPELINE.md`（381 行，apply() 全流程）
   本次会话 15 个坑里 **14 个早就写在这些文件里**，我却重造了 4 个抓取脚本、
   6 个构建脚本、几十个 scratch 文件——**问题不是没记录，是我没读**。
   配套脚本清单也先查：`ls E:\k60-work\usb-a-stage\scripts\`。

1. **只改 patch 文件，绝不手改 `tree/.cache/xnu-work/`**
   `tree/.cache/xnu-work` 是生成物。直接编辑会在下一次清树重建时丢失。
   我犯过：手改 `kern_exec.c` 补 `init_envp`、手改 `MiniIOSurface.cpp` 换 `reinterpret_cast`、手写 `k60_init_blob.h` —— 全部在重建后丢失并再次报错。

2. **两个仓库必须同步**
   - 构建读：`/tmp/usb-cdc-mainline/device`
   - Git 跟踪：`E:/hackios/UniXNU-mondrian`
   改 E 仓不影响构建；改 D 仓不入库。`0391` 曾来回同步 6 次以上。

3. **一次只改一个变量**，构建后固定输出三个判据再上机：
   - `patches applied` = 192
   - `ArmDTPlatform` 字符串数 = 38
   - `K60INIT` 字符串数 = 1

4. **禁止清 `tree/.cache/fakeroot`**；SDK 头丢失后从
   `/opt/k60/trees/k60build/out/mondrian/.../tree/.cache/fakeroot` 或 out3 复制
   （`Availability.h` 不在 AvailabilityVersions feed 里）。

5. **WSL 直连 GitHub 会被 403 限流**：feed 用本地缓存，DriverKit 用
   `.cache/sources/xnu-driverkit-*.json` 缓存。

6. **Git 提交/推送必须用 Windows git**，WSL 里的 git 永远推不上去。

7. **禁止 `fastboot flash`**，只用 `fastboot boot`。TWRP 已集成在 boot 镜像，用 `fastboot reboot recovery` 进入。

---

## 二、已验证事实（不要再重新推导）

### panic 解码
| 输出 | 含义 | 出处 |
|---|---|---|
| `namespace 9` + `code 0x1` | `OS_REASON_EXEC` + `EXEC_EXIT_REASON_BAD_MACHO` | `bsd/sys/reason.h:96,244` |
| `namespace 3` | `OS_REASON_CODESIGNING`（**不是** 9，我曾误判） | `reason.h:90` |
| `Unable to find driver for this platform: "J120AP"` | `IOPanicPlatform` 兜底，说明 `ArmDTPlatform` 未链入 | `IOPlatformExpert.cpp:2318` |

### 内核写文件的正确写法（照抄 `0340-k60-uilib-deploy.patch:7001-7013`，设备上已验证可用）
```c
ctx = vfs_context_current();
error = vnode_open(path, O_CREAT | O_WRONLY | O_TRUNC, 0644, 0, &vp, ctx);
error = vn_rdwr(UIO_WRITE, vp, (caddr_t)blob, (ssize_t)len, 0,
                UIO_SYSSPACE, IO_SYNC, vfs_context_ucred(ctx), &resid, current_proc());
vnode_close(vp, 0, ctx);          // <-- 必须是 0
```
**`vnode_close(vp, FWRITE, ...)` 会导致 `vnode_rele_ext kusecount 不平衡` panic**
（`vfs_subr.c:2693-2694`）。我曾用 `FWRITE` + `IO_SYNC|IO_NOCACHE` + `NOCRED`，触发 panic。

### init 必须的 Mach-O 形态（XNU `load_machfile` 接受的）
```
MH_EXECUTE, flags=0x1(NOUNDEFS)    不能有 DYLDLINK，不能有 LC_LOAD_DYLINKER
__PAGEZERO vmaddr=0 vmsize=0x100000000      (mach_loader.c:655 硬性要求 4 GiB)
LC_UNIXTHREAD 提供入口（不是 LC_MAIN）
LC_CODE_SIGNATURE 存在
```
参照物：`E:/k60-work/deliverables/pong-init/init`（35,160 B，pong 真实 init）。

### 我们的 stub 为什么曾被 `BAD_MACHO` 拒绝
`init-stub3`（我手工 clang 编的）：`flags=0x200085` = `DYLDLINK|TWOLEVEL|PIE`，
含 `LC_LOAD_DYLINKER`，无 `LC_CODE_SIGNATURE`。
原因：`ld64.lld 18` 的 `-static` **未实现**（`warning: Option '-static' is not yet implemented`），
产物只能是动态链接。**这条路走不通，不要再用手工编译的 stub。**

### 构建配方（唯一验证成功的组合）
```
cd /tmp/k60build
./unixnu build kernel -D /tmp/usb-cdc-mainline/device \
  --out /opt/k60/trees/k60build/out-baseline \
  --kernelcache /mnt/e/hackios/UniXNU/out/ipsw/20G81/kernelcache.decompressed
```
- patch 顺序 = 黄金 `xnu-patches.list`（191 条）+ `0391` 追加（共 192）
  不可用文件名字母序：`offline-owner-systemos-mount` 必须在
  `zzzzzz-pong-init-scratch-allocation` / `zzzzzzz-pong-hackios-userland-abi` 之后
- `.config`：`CONFIG_XNU_ARM_DT_PLATFORM=y`、`CONFIG_XNU_ARMCPU=y`、
  `CONFIG_XNU_PONG_ADRENO_PLATFORM=y`（与黄金完全一致，**不要改**）
- 构建脚本中**必须存在**两行（我曾误删，导致 `ArmDTPlatform` 不链接）：
  ```bash
  EXTRA_MAKE_ARGS+=("LD_KERNEL_ARCHIVES=$KERNEL_EXTRA_ARCHIVES")
  EXTRA_MAKE_ARGS+=("LD_KERNEL_ARCHIVES=$PLATFORM_ARCHIVES")
  ```

### boot args（**必须与 `boot-0461` 完整 29 项一致**；我曾只用 20 项，漏了 9 项）

**黄金 payload 原件在磁盘上，不要重新打包**：
```
/mnt/e/k60-work/scratch/payload-0461.img   201326592 B  2026-11-07 21:25:57  tol=YES initblob=no
/mnt/e/k60-work/scratch/payload-0461c.img  201326592 B  2026-11-07 21:25:58  tol=YES initblob=no
```
（`payload-0461` 与 `boot-0461-20261107.img` 只差 2 秒，是打进那个 boot 镜像的原始 payload）
同日迭代链：`payload-0441` → `selfreset` 系列 → `0444`/`0445c`/`0447` … → **`0461`（进 SpringBoard）**。
带 `selfreset` 名字的版本对应 0311 自动复位验证。

从 `payload-0461.img` 的 `unixnu.toml` 实读（跑到 SpringBoard 那一次）：
```
-v native-ufs=1 pong_allow_unauthenticated_root=1 debug=0x140
cs_enforcement_disable=1 pong_software_keybag=1 disable_exc_resource=1
pong_ufs_readwrite=1 k60_console_export=1 k60_usblog=2
pong_data_mount=1 pong_data_rw=1 fb_threads=3 k60_textonly=1
amfi_get_out_of_my_way=1 pong_init_path=/private/var/pong/init
epoch=1793709100 k60_fontscale=3
k60_skip_firmware_mount=1        ← 漏了它：launchd mount-phase bind mount 会 EPERM → PID 1 panic
k60_tolerate_cache_loader=1      ← 漏了它：launchd_cache_loader 崩溃被当成致命
launchd_unsecure_cache=1         ← 内核不识别，无害
xpcproxy_idversion=1
applog=1 applog_name=runningboardd,backboardd,lsd
k60_entitlement_allow=1
k60_skip_iosurface=1
k60_panic_reset=1
k60_selftest_reboot=300
```
``**`debug=0x140` 不是 `0x144`**：`0x144` 含 `DB_NMI`，panic 会卡在 NMI 里**不复位**，
必须手动长按电源。`0x140` 才会走 0311 的 `IMEM 0x146AA65C = 0x77665500` 自动回 fastboot。
**缺 `k60_usblog=2` → CDC console 不枚举，设备静默。**
`boot-0461` 的 payload 里**有** `kernel.macho.trustcache`（61,764 B），
所以"B decision 不要 trust-cache"这条对 11-07 那次**不成立**，不要再据此排除。

### boot 镜像格式（`unixnu bootimg` 产出的**不可用**）
```
正确布局（取自 boot-0461，实测能启动）:
  [0,4096)        ANDROID! 头，u32@8 = kernel_size = 548,774，u32@16 = ramdisk_size = 0
  [4096,552960)   kernel 区（BootShim + UEFI FD + dtb）
  payload 放在偏移 552,960 起（header 不声明 ramdisk_size）
```
`unixnu bootimg` 会把 `ksize` 写成 1,027,600，payload 落到 UEFI 找不到的偏移 → 设备静默。
用 `splice4` 方式：保留模板 header/kernel 区，替换 552,960 起的 payload。

---

## 三、已排除的假设（别再试）

| 假设 | 为什么错 |
|---|---|
| "AMFI 拒绝未签名 init"（Round 15） | `namespace 9` 是 `OS_REASON_EXEC`，不是 CODESIGNING |
| "stub 缺 4 GiB pagezero"（Round 17） | 实测 stub **有** `__PAGEZERO vmsize=0x100000000` |
| "把 `PONG_ADRENO_PLATFORM` 从 1 改 0 能修 panic" | 黄金本身 `.config` 里就是 `=y`，ADRENO 不是变量 |
| "改 boot-args 能修 `vnode_rele_ext`" | 那个 panic 已由 `vnode_close(vp,0,ctx)` 修好，与 args 无关 |
| "用 `--trust-cache` 一定错" | `boot-0461` 里就有 trustcache，11-07 那次是带它跑起来的 |
| **"内核里缺 init / 需要内嵌 init blob"** | 实测 `boot-0461` 的 kernel.macho **既没有** `faa38544…` 也**没有**我的补丁版 blob。它直接用设备上 dd 写入的 init |
| **"`0391` 是必要的"** | 黄金没有内嵌 blob 也能进 SpringBoard。`0391` 是自造路线，且**用 `O_TRUNC` 破坏了设备上的正确 init** |
| **"`launchd.ios` 需要我们用字符串替换来修"** | 设备上的 init 是 dd 写入的 v10guard 系列，源码级就已经是 `/sbin/launchd`；我那个二进制替换是多余的，且破坏了签名页哈希 |
| ~~"`68d9bb06…` 不存在"~~ **错！它在 `E:\k60-work\deliverables\pong-init\init-v2`（35,160 B）** | 我按文件名 `init` 搜，漏了 `init-v2`。该件 `flags=0x1`、`__PAGEZERO 0x100000000`、`UNIXTHREAD`、`CODE_SIG`、内含 `/sbin/launchd`（无 `.ios`）——正是需要的形态 |

---

## 四、当前状态与阻塞

### 真正的目标状态（重要：不要再把已成功的当成失败）

`boot-0461-20261107.img`（201,883,648 B，sha256 `b2c612c8…` 的同类件）**已经进系统了**：
```
[SpringBoard] Pong UI: img 323 ...
[SpringBoard] [backboardd] Pong UI: UIApplication -_run hooked
```
之后才崩：`KX! 18 1 launchd exit=0 sig=11` → `initproc exited -- namespace 2 subcode 0xb`，
死前最后一行是 `access(/System/Cryptexes/App/usr/libexec/webbookmarksd, X_OK) failed with errno 2`。
即：**UI 已起来，卡在 launchd(PID 1) 崩溃**，根因是设备 OS 窗从未跑过 `apply()`。

### 已确认可用（有日志证据）
- UEFI → 内核 → APFS：`SystemOS mounted dev=9000006 ro=1 union=1 flags=14809021`、
  `K60CACHE stage=6 err=0 ... p1=0 p2=0 p5=0`（与黄金逐字段一致）、`APFS SystemOS union PASS`
- Data：`K60DATA mount returned error=0 rw=1`、`K60UFS write#0..#7` 全 `result=0`、
  `K60UILIB deploy bytes=111328 resid=0 error=0`、`mkdir ok=1/28`（全 EEXIST，正常）
- init（用设备上 dd 写入的版本）：`Pong init: helper exec result=0` → 全部 boot_stage 通过
- CDC console 枚举（COM5，VID_1209/PID_0001）

### 当前阻塞：launchd(PID 1) 崩溃，不是内核问题
`apply()` 从未运行（需要 macOS `hdiutil`），所以：
- `/pong/LaunchDaemons`、`/pong/boot-jobs` 等 bindfs 源目录不存在 →
  init 打印 5 条 `optional boot view SKIP`
- stock `LaunchDaemons` 未被移到 `/pong/stock-config`，launchd 读到的 job 集与文件系统不一致

**修法**：用 `tools/apfs` 离线在 Data 窗造出 `/pong/LaunchDaemons`（从 20G81 plist 按 `CORE`/`DENY` 筛选），
再让 init 的 `prepare_boot_services()` 去 bindfs —— **不需要改内核，不需要改 init**。
历史证据：`write-pong-init-*.ps1` 的四闸门写盘流程已跑通多次。

### 设备侧重要事实
- `/private/var/pong/init` 是 **11-03 用「手工 dd 写 9 块到 extent (0,36864,6135)」放入 inode 216**，
  extent 未经过 APFS 正常分配，spaceman 位图中块 6135-6143 仍是 free（PITFALLS:230）
- **inode.size 字段残留 35160**：任何 > 35,160 B 的 init 会被按旧 size **截断执行**（PITFALLS:462）
- 历次版本：v6 34,872/`25d23885`、v7probe 34,880/`a00da80e`、v9alias 34,880/`78dcee4c`、
  **v10guard 34,880/`db7e4eee`**（最后写入）；段回读 `ed6c3bf1…`
- 我的 `0391` 用 `O_TRUNC` 覆盖过它，**现值未知**，必须重新核实

**init 全谱系（`E:\k60-work\deliverables\pong-init\`，15 个版本都在）**：
```
init          faa38544  35160  原始（exec /sbin/launchd.ios）
init-v2       68d9bb06  35160  exec→/sbin/launchd  ← 正确形态，有签名，就用它
init-v3~v5    35160            
init-v6       25d23885  34872
init-v7probe  a00da80e  34880
init-v8probe/v8trace  34880
init-v9alias  78dcee4c  34880
init-v10guard db7e4eee  34880   ← 设备上最后一次 dd 写入的版本
init-v11drain 12b9df42  34912   ← 34,912 / 35,160 B，仅剩 248 B 余量（PITFALLS 46）
init-v12union 3703f983  34464
```
每个版本都配 `init.c.<ver>-mondrian-src` 源文件，可追溯。

### 抓取与自动化工具（**用现成的，不要重造**）
```powershell
pwsh E:\k60-work\usb-a-stage\scripts\boot-and-capture.ps1 `
  -Image <img> -Seconds 300 -WaitFastboot 90
```
`E:\k60-work\usb-a-stage\scripts\boot-and-capture.ps1`（11-06，259 行）已实现：
自动 boot、从注册表 `\Device\USBSER000` 找端口、逐块 Flush、
**端口消失后重开**（`-ReopenSeconds`）、**panic 后等静默再收尾**（`-PanicGraceSeconds`）、
**等设备自动回 fastboot**（`-WaitFastboot`，靠 0311）、写 `capture.json` 含 `complete` 判定。

**我今天重写的 `cap.py`/`capwait.py`/`capd.py`/`capd2.py`/`bootcap.ps1`/`bootcap1.ps1`
全是重复轮子，且缺 `-WaitFastboot` 和完整性判定。不要再写新的。**
UI 按钮插件 `@local/k60-console-buttons` 仅作辅助，不替代上面的脚本。

---

## 五、本次会话踩坑清单（每条都要防止复发）

| # | 坑 | 根因 | 防复发 |
|---|---|---|---|
| 1 | `0391` 新增文件段缺 `@@ -0,0 +1,N @@` hunk 头 | `git apply` **静默创建 0 字节文件**，编译报 `use of undeclared identifier` | 生成 patch 后必须 `git apply --check` + **`stat -c%s` 确认新文件非 0 字节** |
| 2 | 删 `LD_KERNEL_ARCHIVES` 两行 | 自造注入方案时"清理"过头，`ArmDTPlatform` 不链接 → `Unable to find driver for this platform: "J120AP"` | 改脚本前先 `diff -u` 黄金脚本（`out3/.../tree/scripts/`），改后复查两行还在 |
| 3 | `0391` 吞掉 `init_envp` 声明 | patch 的 hunk 上下文覆盖了 `load_init_program` 里的声明行 | patch 应用后 `grep -c 'user_addr_t init_envp'` 必须 ≥1 |
| 4 | 用 `cp -a` 盖树后 `unixnu` 跳过补丁 | `tree/` 已存在就不重新解包+打补丁 | 构建日志必须 `grep -c '== kernel: patch'` = **192**（或 191） |
| 5 | 清 `tree/` 连 `fakeroot` 一起删 | SDK 头丢失 → `Availability.h: No such file` | 清树前备份 `.cache/fakeroot` 与 `.cache/sources`，清后立即回填 |
| 6 | GitHub 403（feed / DriverKit） | WSL 直连被限流 | 用 `out3/feeds` 本地副本 + `.cache/sources/xnu-driverkit-*.json` 缓存 |
| 7 | `unixnu bootimg` 产物不可用 | 把 `ksize` 写成 1,027,600，payload 偏移错 | 只用 `splice4` 方式（保留 0461 布局，payload 放 552,960） |
| 8 | `vnode_close(vp, FWRITE, ctx)` | 让 `vnode_rele_internal` 递减未 acquire 的 `v_writecount` → `vnode_rele_ext kusecount` panic | 内核写文件一律照抄 `0340:7001-7013`，`vnode_close(vp, 0, ctx)` |
| 9 | 手工用 `clang` 编 init stub | `ld64.lld 18` 的 `-static` **未实现**，产物带 `DYLDLINK`+`LOAD_DYLINKER` → `EXEC_EXIT_REASON_BAD_MACHO` | **不要自己编 init**。用设备上 dd 写入的现成 init，或用 pong 的静态二进制 |
| 10 | 用 `k60_init_blob` 覆盖设备 init | `O_TRUNC` 破坏 dd 写入的正确文件 | **永不用 `k60_init_blob`**。需要换 init 时走 `write-pong-init-*.ps1` 四闸门 dd |
| 11 | boot args 只用 20 项 | 漏 `k60_skip_firmware_mount=1` → launchd mount-phase EPERM → PID 1 panic | 打包前必须与 `boot-0461` 的 29 项逐字比对 |
| 12 | `debug=0x144` 而非 `0x140` | `0x144` 含 `DB_NMI`，panic 卡在 NMI 不复位，必须手动长按电源 | 固定 `debug=0x140` |
| 13 | 重造抓取/引导脚本 | 没 `ls` 就开工，`boot-and-capture.ps1` 早有全部功能 | **先查 `E:\k60-work\usb-a-stage\scripts\`**，已有就不再写 |
| 14 | 抓取器没启动就 boot | 工具调用被中断，daemon 没起，panic 现场丢失 | 用 `boot-and-capture.ps1`，它一个进程内完成 boot+capture |
| 15 | 改 boot 镜像后设备静默 | 镜像格式/args/或内核早期挂死 | 每次 boot 只用 `boot-and-capture.ps1` 并检查 `capture.json` 的 `complete` |

## 六、下一步（唯一正确的路径）

1. 设备进 fastboot（需人工长按电源 10–15s → 音量下+电源）
2. `boot-and-capture.ps1 -Image E:\k60-work\usb-a-stage\out\boot-0461-20261107.img -Seconds 300 -WaitFastboot 90`
   → 建立基线，同时确认设备上的 init 是否还完好
3. 基线确认后：从 `series` **删除 `0391`**，脚本回退到与黄金脚本逐行一致，
   重建并验证 `diff` 源码树 0 差异（内核对黄金等价）
4. 用 `tools/apfs` 离线在 Data 窗造 `/pong/LaunchDaemons`（按 `CORE`/`DENY` 筛选 20G81 plist），
   解决 launchd(PID 1) 崩溃 —— 这是"进系统并稳住"的最后一步
