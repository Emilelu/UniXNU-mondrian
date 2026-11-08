# K60 iOS 移植 — ZCode 调研任务书

> 交给 ZCode agent 的完整任务说明。请做**源码级、寄存器级**调研，不要给通用建议。

## 一、项目背景

在 **Qualcomm SM8475（Redmi K60，代号 mondrian）** 上运行 **XNU 8796.141.3（Darwin 22.6.0，iOS 16.6.1，profile 20G81）** 原生内核。

启动链：`ABL → fastboot boot → BootShim → UEFI(Mu-Silicium/mondrianPkg) → UniXNU → DarwinBoot → XNU`

内核是**自己编的**（apple-oss-distributions/xnu + 我们的 89 条补丁），但用 **prelink** 把原厂 kernelcache 里的部分 Apple kext 一起链进来（APFS、IOStorageFamily、AMFI、AppleARMPlatform 等）。

## 二、已打通的部分（实测日志，不必再验证）

```
ArmCpu: CPU registered, install interrupt controller
cache: 1 CPU(s), 64 bytes CPU cache line size
K60 DISPLAY: panel 1440x3200 DSC video mode, canvas 1440x3200 native, stride 5760, 60 Hz
K60 DISPLAY: TimingElements 1440x3200 at 60 Hz / ColorElements 到位
K60 ACCEL: empty IOAcceleratorES published (no backend)
apfs_module_start:3058: Load: com.apple.filesystems.apfs v2142.140.9
ArmDTPlatform: registered platform cpus=1 arm-io=1 devices=2 nvram-proxy=1
PONG_UFS: transport ready LUN=0 block=4096 blocks=61731840
```

UFS 驱动（自研 `IOBlockStorageDevice` 子类）已能发布 IOMedia，**APFS 已成功挂载只读 OS 卷**。

## 三、当前阻塞（最高优先级）

```
panic(cpu 0 caller 0xfffffff0079fac18): rootvp not authenticated after mounting @bsd_init.c:1087
```

已有补丁 `zzzzzzzzz-pong-development-root-policy.patch` 实现了 boot-arg 放行：

```c
PE_parse_boot_argn("pong_allow_unauthenticated_root", &pong_development_root, ...);
pong_development_root = (pong_development_root == 1) &&
    PE_i_can_has_debugger(NULL) &&
    (vfs_flags(vnode_mount(rootvnode)) & MNT_RDONLY);
if (autherr && pong_development_root)
    printf("PONG DEVELOPMENT: allow unsealed read-only root; APFS rootauth error=%d\n", autherr);
if (autherr && !owner_authorized && !pong_development_root)
    panic("rootvp not authenticated after mounting");
```

下一个待验证版本已加 `pong_allow_unauthenticated_root=1`。

## 四、本地文件位置

工作根目录：`D:\Android\k60-ios\`

| 内容 | 路径 |
|---|---|
| 协作看板（全部历史与实测日志） | `AGENT-COORDINATION.md` |
| 首启判读手册 | `FIRST-BOOT-PLAYBOOK.md` |
| 120Hz 显示调研 | `deliverables\K60-120HZ-PLAN.md` |
| 触摸交接（含寄存器判据） | `deliverables\A1-touch\HANDOFF.md` |
| 触摸驱动源码 | `ios-sweet-k60\drivers\k60-goodix-touch\` |
| 触摸补丁 0240–0252 | `ios-sweet-k60\xnu\patches\` |
| SMP/多核方案（8 核 ADT 属性表、启动顺序） | `smp\K60-SMP-MULTICORE.md` |
| AppleARMCPU 补丁工具 | `smp\patch_armcpu_validate.py` |
| 原厂参考仓（只读） | `refs\UniXNU-pong`、`refs\UniXNU-sheng`、`refs\ios-sweet-k60` |

WSL 侧仓库：

| 仓 | 路径 | GitHub |
|---|---|---|
| 设备仓 | `~/hackios/UniXNU-mondrian` | `Emilelu/UniXNU-mondrian` |
| 内核仓（k60 分支） | `~/hackios/UniXNU` | `Emilelu/UniXNU` |
| UEFI 固件仓 | `~/hackios/uefi-mondrian` | `Emilelu/uefi-mondrian` |

关键文件：

- `~/hackios/UniXNU-mondrian/board.toml` — 板级配置（`[payload] cpus/kernel_args`、`[userdata]` 窗口、`[payload.adt] root_match_volume_uuid`）
- `~/hackios/UniXNU-mondrian/dts/mondrian.dts` — K60 板级设备树（UFS 节点、`unixnu,adt-name`）
- `~/hackios/UniXNU-mondrian/configs/mondrian_defconfig` — 内核开关
- `~/hackios/UniXNU-mondrian/patches/xnu/series` — 补丁序列（89 条）
- `~/hackios/UniXNU-mondrian/drivers/NativeUfs/` — UFS 驱动（`PongUfsTransport.cpp`、`RootLayout.h`）
- `~/hackios/UniXNU/profiles/os/ipados-16.6.1-20G81/profile.toml` — OS profile（prelink roots、ADT 表）
- `~/hackios/UniXNU/scripts/unixnu/devicetree.py` — ADT 生成器

## 五、调研题目

### 题目 1（最高优先）：根卷认证与 launchd 执行链

1. `rootvp not authenticated after mounting` 在 XNU 8796 的确切触发条件（哪个函数、哪个返回值、`autherr` 各错误码含义）
2. 放行之后 `load_init_program()` → `execve("/sbin/launchd")` 还会撞哪些检查？逐项列（代码签名、AMFI policy、trust cache、entitlements、MACF/sandbox）
3. 每项的最小放行条件（boot-arg / 补丁点 / plist）
4. iOS 16 launchd 需要哪些 entitlement？无 trust cache 时 `cs_enforcement_disable=1` 覆盖到哪一层
5. 社区先例（checkra1n / palera1n / unc0ver / XTOM ios-sweet）分别怎么绕过，哪些适用于「自己编的内核 + 原厂 APFS 卷」

### 题目 2：AppleARMPE vs 自研 ArmDTPlatform

我们 prelink 带进了 `com.apple.driver.AppleARMPlatform`（含 AppleARMCPU 类），已用字节补丁跳过其 `_validateConfiguration`；CPU 实际由自研 `ArmCpu` 驱动接管（`IOProbeScore 2000`）。

1. AppleARMPE 在非 Apple 硬件上还有哪些初始化路径会踩雷（NVRAM / PMGR / watchdog / IIS / M2Scaler / 中断映射）
2. 哪些是「必须工作否则 panic」，哪些「失败可继续」
3. 若要让自研 ArmDTPlatform 独占平台专家、排除 AppleARMPlatform：依赖闭包（AMFI → ApplePMGR → AppleARMPlatform）怎么断？有无 stub ApplePMGR 之类的优雅做法
4. 若保留 AppleARMPE，需补哪些 DT 属性（对照真实 Apple 设备 ADT）
5. 两种方案对后续 GPU / 显示 / 电源管理的长期代价

### 题目 3：APFS 只读未签名根卷的挂载语义

1. 非 sealed / 非 signed 状态下挂载后哪些元数据缺失（sealed volume、root hash、auth root、snapshot）
2. `autherr` 具体错误码与含义
3. 不重新签名的前提下能否让卷被认作 authenticated（原厂 trust cache bundle / 伪造 auth root / snapshot）
4. 原厂 IPSW 的 trust cache 能否直接给自编内核用？前置条件（芯片 ID / ECID / nonce）
5. 只能走「未认证放行」时，userspace 会缺什么（keychain / sandbox / AMFI 服务）

### 题目 4：Goodix 触摸 + 无 RSC 的 GENI-SPI

硬件：Goodix（Berlin 或 GT9xx），GENI-SPI SE4 @ `0x990000`，GPIO16-19(SPI) / 20(reset) / 21(IRQ) / 71(AVDD)，坐标 14400×32000。
硬阻断：RSC `0x17a00000` 不可访问，IOVDD = `pm8350c ldo2` 需经 RSC。

1. Berlin 读 chip ID 的寄存器与返回格式（期望 `0x10014` 头 4 字节 = `"911\0"`）
2. GT9xx 对应寄存器（`0x8140` = `"9111"`）
3. Berlin 触点包格式（8 字节 stride 字段布局）
4. 无 RSC/RPMh 时 GENI-SPI 的最小初始化序列：GCC 时钟投票能否直接写寄存器绕过 RPMh？SE4 fw/status 判据
5. `pm8350c ldo2` 有无不经 RSC 的旁路（ABL/UEFI 配置、直接写 SPMI）
6. postmarketOS / mainline Linux `geni-spi` 驱动如何处理 RSC 依赖

### 题目 5：120Hz 显示栈

面板 Sharp QHD AMOLED 1440×3200（LTPS，非 LTPO），DSC video mode，dtbo 原生两档 timing：120Hz / 60Hz（phy-timings 不同，切档写寄存器 `0xC6` = `0x1244`(120) / `0x1288`(60)）。我们自研 AppleCLCD 目前硬编码 60Hz。

1. XNU `IOFramebuffer` / `IODisplay` 如何表达刷新率（`IOFBCurrentPixelClock`、vsync 周期在哪设置）
2. iOS 16 ProMotion 在非 Apple 硬件上如何被 userspace 识别（IORegistry 属性？MobileGestalt？）
3. 伪装成 ProMotion 机型（如 `iPhone13,2`）需改哪些 ADT/product 属性
4. `CADisplayLink` / CoreAnimation 帧率上限由什么决定
5. 120Hz 下 DSC slice 参数是否需变（我们 `slice-height=8` 两档相同，但 pixel rate 翻倍）

## 六、输出要求

- 每个题目给「结论 + 依据（源码位置 / 寄存器 / 社区项目链接）+ 可执行动作」
- 明确区分「确定事实」与「推断」，推断标注依据强度
- **题目 1 请给到能直接改代码的粒度**（函数名 + 补丁点 + boot-arg 名称）
- 不确定的地方直接说「需要实测验证」，不要编造
