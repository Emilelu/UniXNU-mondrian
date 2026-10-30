# K60 移植进展与 pong 对标（2026-10-30 下午）

> 承接 `HANDOFF-2026-10-30.md`。本文记录 **信任缓存打通之后** 的推进过程、已排掉的阻塞、
> 以及和 pong 官方参考仓（`Chengdong-Yu/UniXNU-pong` @ `64ddf28`）的对标结论。

---

## 一、本轮已排掉的阻塞（每项都有实测证据）

| # | 阻塞 | 根因 | 修复 | 提交 |
|---|---|---|---|---|
| 1 | CoreTrust 拒 launchd（`unsuitable CT policy 0`）| TC 未注入 | payload 带 `--trust-cache`（20G81 束，sha256 `344ae644…`）| `8b82eb3` |
| 2 | TC 装载时 `Kernel data abort` @ `__PLK_TEXT_EXEC` | `trust_cache_runtime_init()` 因 `img4if==NULL` 提前 return，`trust_cache_rt` 全零，AMFI `loadModule` 撞 NULL `mutableRT` | 照常初始化运行时，img4 传 NULL，只挡动态加载路径 | `df99f2e` |
| 3 | 模块 1（System TC）被当 engineering 跳过 | `MASTER.arm64.pong` 无 `CONFIG_SECOND_STATIC_TRUST_CACHE` | 新增补丁打开该选项 | `df99f2e` |
| 4 | owner 挂载块从不执行（`K60CACHE` 从未出现）| 补丁 hunk 被 rebase 到 `if (scratch_result != KERN_SUCCESS) { panic(...); }` 之内，且重复声明 `init_envp` 遮蔽外层 | 把块移出失败分支，删重复声明 | `4ffd2ad` |
| 5 | bootstrap 轮链接失败（`_native_pong_ufs_volume_device` 等未定义）| 驱动 archive 在 bootstrap 轮被故意跳过，而这轮必须链接成功才能产出编译记录 | 给两个驱动入口加 **weak 定义** | `a3cef50` |
| 6 | `mount[3]` 退出 66（`failed to get boot manifest hash`）| `/chosen/boot-manifest-hash` 不存在 | ADT 注入 48 字节 `boot-manifest-hash`（与 `crypto-hash-method=sha2-384` 对齐）| 本机 profile.toml |
| 7 | dyld 找不到 `libSystem`（`no dyld cache`）| 缓存真名是 **`dyld_shared_cache_arm64`**（不是 arm64e）| union 挂载已生效，探针确认 p1=0 | `e3a9540` |

**当前状态**：launchd 已跑起来，一路推进到 **`watchdogd`（pid 95）**，比卡在 launchd 前进了一大截。

---

## 二、当前唯一阻塞：`/private/var` 无可用卷

实测日志：

```
MKB_INIT: Could not open /private/var/keybags/systembag.kb: No such file or directory
coredump (watchdogd, pid 95): Failed to open core dump file /private/var/codes/watchdogd.core: error 2
```

`mkbinit` 的第一个动作就是打开 `/private/var/keybags/systembag.kb`，没有「无 keybag 继续」的分支。

**已做的两件事**：
1. `pong_software_keybag=1` 已加（软 keybag 生效，`failed to load system bag` 消失）
2. Data seed 已接进 payload（`seed/k60-data-seed.dbr`，APFS 卷 `OwnerData`，UUID `6DCCF70A-…`，32 MiB，含 `keybags/` 目录）

**还差的**：`native_ram_block_volume_seed()` 没找到卷 ⇒ `/private/var` 未挂载。
已把 defconfig 的 `XNU_OWNER_DATA_VOLUME_UUID` 从 pong 常量 `576A2203-…` 改成种子实际的 `6DCCF70A-…`（`f0b4d9e`）。

> **本段已被后续工作取代 —— 见下方「二·续」与 `HANDOFF-2026-10-30-EVENING.md`。**

### 二·续：内存盘路线废弃，改用真实 UFS Data 窗口（最终结论）

内存盘路线实测**死路**：

```
K60DATA mount enter path=/private/var dev=/dev/disk1s1
（此后永久卡死，无 panic）
```

卷已发布（`/dev/disk1s1` 说明种子与 UUID 都正确），卡点在 `mount()` 内部。

改为对齐 pong 的**真实 UFS Data 窗口**路线后成功：

| 步骤 | 结果 |
|---|---|
| 把 32 MiB 裸 APFS 用 `make-gpt-data-image.py` 包进 GPT | `EFI PART@512` ✓，分区内 `NXSB@32` ✓，GPT 主备 CRC ✓ |
| 用 `install-k60-ufs-data.py --dry-run` 校验几何 | unixnu=`/dev/block/sda38`，32 GiB，起始扇区 426743808 ✓ |
| 实际写入 offset `7,780,433,920`（7420 MiB）| manifest count=3，Data 条目正确，manifest sha256 ✓ |
| 内核改走 `DATA_UFS` 路径 + `pong_ufs_readwrite=1` | — |
| 上机（只读）| **`K60DATA mounted ro=1 fstype=apfs`** ← `/private/var` 首次挂上 |

**遗留卡点**：读写挂载（`pong_data_rw=1`）在 `disk3 scan ... (no trim)` 之后卡死。
已给 UFS 驱动加 `K60UFS write#N` 标记（commit `aa7a1f1`，**尚未编译进内核**），
下一步重编后上机即可定位是「UFS 写命令卡死」还是「APFS 读写阶段卡死」。

---

## 三、ramoops 取证（重要基础设施）

**已确认对齐**（TWRP 内实测）：

```
ramoops@0xa7000000 :  reg = 0xa7000000, 0x400000
  console_size = 2097152   (2 MiB)
  pmsg_size    = 2097152   (2 MiB)
  mem_address  = 0xA7000000
  mem_size     = 4194304
# /proc/iomem: a7000000-a73fffff : reserved
```

与 `zzzzz-pong-ramoops-minimal.patch` 的布局**逐字节一致**，且 `CONFIG_XNU_PONG_RAMOOPS_CONSOLE=y`
已生效（内核符号 `_pong_ramoops_console_write` 存在）。

**已纠正的误判**：一度以为魔数应为 `PRZ`，实际 Linux
`drivers/staging/android/persistent_ram.h` 定义为：

```c
#define PERSISTENT_RAM_SIG (0x43474244) /* CGBD */
```

即 `CGBD` **本来就是对的**，已回滚。

**关键修正（2026-10-30 16:00）**：**ramoops 在 DRAM 里，长按电源重启 = 掉电 = DRAM 归零，
日志必然丢失。** 之前在「重启进 TWRP 后看到 pstore 为空」上做的推断全部无效，
不能据此判断 XNU 有没有写。

pong 能在 REC 读到 281 KB console，说明它的重启路径**不断电**（或在掉电前把内容转到持久介质）。
我们目前只能用 `fastboot boot` + 长按重启，这条取证链走不通。

**结论**：ramoops 方案在本机的可用前提是「断电前把内容取走」，
否则必须改用**屏幕上的 panic 输出**作为唯一判据。

`Failed to get pstore mem` 来自 `minidump.ko`，与 ramoops 无关。

---

## 四、与 pong 官方参考仓的对标（`64ddf28`）

### 4.1 官方设备页状态

| 部分 | pong | mondrian |
|---|---|---|
| 配置 | implemented | implemented |
| 固件与启动 | implemented | planned |
| CPU 与中断 | implemented | planned |
| 内存与 DMA | implemented | planned |
| 存储与根卷 | implemented | planned |
| 显示 | implemented | planned |
| 输入 | implemented | planned |
| GPU | implemented | planned |
| 网络 | implemented | planned |
| 音频 | implemented | planned |
| 电源 | implemented | planned |
| 镜像组装 | implemented | host-verified |
| 诊断 | implemented | planned |

### 4.2 关键差异

| 项 | pong `64ddf28` | 我们 |
|---|---|---|
| OS profile | `ipados-18.7.10-22H374`（Darwin **24**）| `ipados-16.6.1-20G81`（Darwin **22**）|
| 组件 | `PongPlatform24` 单一聚合 | ArmDTPlatform / ArmCpu / XnuPrelink / PongUfs 分散 |
| 补丁系列 | 4 段（format2/arch-darwin24、soc、os、xnu-ipados18）| 1 段（`device:patches/xnu/series`）|
| 存储 | **UFS 三窗口 OS/SystemOS/Data**，Data 8 GiB，UUID `952D79E9-…` | SHNGROOT 仅 OS+SystemOS，**无 Data** |
| Data 卷 | 真实 UFS 窗口 + `install-ipados18-ufs.py` 写入 | 尝试内存盘（NativeRamBlock）+ seed |
| pstore | `patches/xnu-ipados18` 内「控制台与 pstore」 | `zzzzz-pong-ramoops-minimal.patch`（已生效）|

### 4.3 补丁覆盖度（按文件名比对）

- pong 有 **103** 个 patch 文件，我们仓里**一个不缺**（差集 0）
- 我们另有 **22** 个 patch **未进 series**，其中值得逐条评估的：
  - `zzzzzz-pong-writable-data.patch`、`pong-ufs-data.patch`、`pong-union-lower-directory.patch`、`pong-container-path.patch`
  - `pong-touch-console.patch`、`pong-physical-keys.patch`、`pong-goodix-resume.patch`
  - `pong-settings-pmsg.patch`、`zzy-native-gpu-addon-mount.patch`

### 4.4 pong 踩过的同一个坑（可直接借鉴）

> 后续因 kern_exec 残留 iOS 16 根卷 UUID 而跳过 SystemOS/Data，导致 helper ENOENT；
> 现已将三个卷的 UUID 统一配置化。

——这与我们 `576A2203`（pong 常量）vs `6DCCF70A`（本地 seed）的问题**完全同构**。

### 4.5 pong 的 keybag 方案

> 静态 init 在已有 Data 创建缺失的 root-owned `/private/var/keybags`（0700）及 `/private/var/logs`（0755）；
> 初次 Data 生成也加入同样目录。已有目录及文件不重置。

即：**keybag 目录由用户态 init 创建，内核只负责挂载 Data 卷**。

---

## 五、下一步（优先级）

1. **确认 ramoops 是否真在写**（`K60SELF` 自检，本轮已构建）
2. **让 `/private/var` 挂上**，二选一：
   - A. 追真实 UFS Data 窗口（对齐 pong，但需恢复模式写入 SHNGROOT，有风险）
   - B. 继续修内存盘路线（`native_ram_block_volume_seed` 返回 0 的具体位置）
3. Data 通了之后，回到 launchd 后续服务（`logd`、`containermanagerd`、`securityd` 等）

---

## 六、本轮踩到的工程陷阱（补充到踩坑清单）

1. **`local-kernel-build12.sh` 开头会 `git reset --hard origin/main`**
   → 任何未提交的 defconfig / board.toml 改动都会被丢弃。改配置后**必须先 commit+push**。
2. **`payload.py` 的 `--trust-cache` 白名单读 `[payload]` 段**，不是 `[payload."adt"]`
   → 放错段落等于白名单失效（不报错，但也不校验）。
3. **`board.toml` 的 `data_ramdisk` 键不会被读取**
   → 只有 CLI 的 `--data-ramdisk FILE` 有效。
4. **`unixnu bootimg` 内置校验对 v4 镜像会误报**
   → 它比较 v4 header 里的 `page_size` 字段（v4 恒为 0）；需用自己的 v4 布局校验。
5. **`panic()` 是 noreturn，死代码会被优化掉**
   → 曾因整个 owner 块在 `panic()` 之后而从未链接真正符号，问题被掩盖很久。
6. **Mach-O 里 weak *声明* 仍是强引用**
   → 未定义符号要用 weak *定义*（返回 0 的桩），archive 的强定义会覆盖它。
7. **`disable_exc_resource` 挡不住 `OS_REASON_SIGNAL`**
   → `namespace 2` 是信号退出（SIGTRAP=5），与资源监控无关。
