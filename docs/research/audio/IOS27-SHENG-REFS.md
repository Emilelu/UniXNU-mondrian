# 27 上的 sheng：内核与驱动参考清单

内核与驱动的研究也必须包含 [UniXNU-sheng](https://github.com/UniXNU/UniXNU-sheng)，不能只在用户态阶段引用它。
本页按同一份上游 main 检出 `c8f92b208068eeaa4cd2b0f592671f04ee70076e` 逐条审查；精确 revision 也记录在 [porting.toml](../../../porting.toml) 的音频证据里。
运行所有 sheng 检查时，把 SHENG_REPO 指向这同一棵树。旧本机分叉只有 17 项，上游清单有 25 项；不能把一棵树的清单和另一棵树的 HAL 契约拼成结论。

## 一、25 项按系列顺序逐条判断

系列第一行是注释，不是补丁。audio 表示新增音频行为；partial 表示包含既有音频路径的上下文、需一起审查；no 表示没有直接新增音频行为，仍可能是进入音频阶段的启动前置。
每行引用的是补丁文件自己的行号，不是应用后的 XNU 行号。

| 补丁 | 判 | 改动与音频关系 | 依据 |
| --- | --- | --- | --- |
| `zzye-sheng-cpu-idle.patch` | no | processor.c 的空闲调度；没有音频端点 | sheng:patches/xnu-12377/zzye-sheng-cpu-idle.patch:1 |
| `zzyf-sheng-amp.patch` | no | sched_clutch.c 的 P/E 核偏好与 BCM2837.h 的 AMP 配置；AMP 是大小核调度 | sheng:patches/xnu-12377/zzyf-sheng-amp.patch:1 |
| `zzyd-sheng-audio-addon-mount.patch` | audio | kern_exec.c 新增音频 HAL 的 addon4 槽 | sheng:patches/xnu-12377/zzyd-sheng-audio-addon-mount.patch:19 |
| `source-storage-runtime.patch` | no | bsd_init.c 启动存储运行时；音频日志之前的基础设施 | sheng:patches/xnu-12377/source-storage-runtime.patch:1 |
| `zzzz-sheng-ipados27-bringup.patch` | partial | 27 平台、pmap、启动参数与日志；音频挂载仅为上下文，不是第二份新增实现 | sheng:patches/xnu-12377/zzzz-sheng-ipados27-bringup.patch:284 |
| `vmwait-dyld-pager-source-release.patch` | no | vm_dyld_pager.c 先释放 busy source/placeholder，避免 APFS UPL 等自己；补丁注明未上机 | sheng:patches/xnu-12377/vmwait-dyld-pager-source-release.patch:18 |
| `zzzzzz-sheng-latency-trace.patch` | no | exception.c 的延迟追踪 | sheng:patches/xnu-12377/zzzzzz-sheng-latency-trace.patch:1 |
| `zzzzzzzz-sheng-exit-latency.patch` | no | kern_exit.c 的退出延迟追踪 | sheng:patches/xnu-12377/zzzzzzzz-sheng-exit-latency.patch:1 |
| `zzzzzzzzz-sheng-unnest-trace.patch` | no | vm_unix.c 的 unnest 追踪 | sheng:patches/xnu-12377/zzzzzzzzz-sheng-unnest-trace.patch:1 |
| `sheng-wifi-launchd-cache.patch` | no | kern_exec.c 的 Wi-Fi launchd 缓存 | sheng:patches/xnu-12377/sheng-wifi-launchd-cache.patch:1 |
| `sheng-bluetooth-runtime.patch` | no | kern_exec.c 的蓝牙运行时挂载 | sheng:patches/xnu-12377/sheng-bluetooth-runtime.patch:1 |
| `sheng-wifi-association-event.patch` | no | kern_event.c 的 Wi-Fi 关联事件 | sheng:patches/xnu-12377/sheng-wifi-association-event.patch:1 |
| `sheng-main-thread-profile.patch` | no | sleh.c / mach_msg.c 的主线程采样 | sheng:patches/xnu-12377/sheng-main-thread-profile.patch:1 |
| `sheng-cache-input-diagnostic.patch` | no | exception.c 的缓存输入诊断 | sheng:patches/xnu-12377/sheng-cache-input-diagnostic.patch:1 |
| `sheng-bluetooth-exit-diagnostic.patch` | no | kern_exit.c / exception.c 的蓝牙退出诊断 | sheng:patches/xnu-12377/sheng-bluetooth-exit-diagnostic.patch:1 |
| `zzzzzzzzzz-sheng-sigp-reinit-assert.patch` | no | cpu_common.c 的 SIGP 重初始化断言 | sheng:patches/xnu-12377/zzzzzzzzzz-sheng-sigp-reinit-assert.patch:1 |
| `sheng-appsync-runtime.patch` | no | kern_exec.c 的 appsync 运行时 | sheng:patches/xnu-12377/sheng-appsync-runtime.patch:1 |
| `sheng-appsync-user-trust.patch` | no | appsync 信任缓存与 UBC 接线 | sheng:patches/xnu-12377/sheng-appsync-user-trust.patch:1 |
| `zzzzzzzzzzz-sheng-edge-matrix.patch` | no | sched_clutch.c 的跨 P/E 集群迁移、窃取与计数；补丁注明未上机 | sheng:patches/xnu-12377/zzzzzzzzzzz-sheng-edge-matrix.patch:31 |
| `zzzzzz-sheng-bsd-checkpoints.patch` | no | bsd_init.c 的 weak_import checkpoint 与逐调用埋点；可判断音频入口是否已到 | sheng:patches/xnu-12377/zzzzzz-sheng-bsd-checkpoints.patch:16 |
| `sheng-bootstrap-checkpoints.patch` | no | startup.c / bsd_init.c 记录 bsd_init 与 pid1 入口、返回 | sheng:patches/xnu-12377/sheng-bootstrap-checkpoints.patch:15 |
| `sheng-headless-startup-checkpoints.patch` | no | 非图形 BootProgress 也记录 startup 阶段 | sheng:patches/xnu-12377/sheng-headless-startup-checkpoints.patch:15 |
| `sheng-startup-failure-log.patch` | no | Data mount、launch policy 与 panic 的结果日志 | sheng:patches/xnu-12377/sheng-startup-failure-log.patch:8 |
| `sheng-process-exit-log.patch` | no | 记录进程退出原因、描述与 csflags | sheng:patches/xnu-12377/sheng-process-exit-log.patch:8 |
| `sheng-platform-sleep.patch` | no | 定义并调用平台睡眠 hook、CPU_OFF 与唤醒路径；不是音频恢复实现 | sheng:patches/xnu-12377/sheng-platform-sleep.patch:15 |

只有 zzyd 新增音频专用挂载。bringup 需要同看，是因为它的上下文依赖这条已有路径；另外 23 项没有直接新增音频行为。
启动埋点和页入修复仍值得启动线参考，不能把 no 读成“与整个移植无关”，也不能把上游的未上机说明读成硬件已验证。

## 二、音频与平台接线的可借鉴内容

### addon4 是增量接线

`sheng:patches/xnu-12377/zzyd-sheng-audio-addon-mount.patch:9` 在 addon2/addon3 后新增 addon4 的 stage/status；
`sheng:patches/xnu-12377/zzyd-sheng-audio-addon-mount.patch:19` 定义源 /private/var/ngpu/audio 与目标 /System/Library/Audio/Plug-Ins/HAL；
`sheng:patches/xnu-12377/zzyd-sheng-audio-addon-mount.patch:20` 用 scratch offset 0xa00 调 native_gpu_addon_mount。
它要求前置 addon 挂载机制，不是对原始 XNU 可独立应用的一条补丁。offset 不同也不足以证明与 K60 蓝牙槽位安全共存，还需检查两边实际写入区间与整条框架序列。

`sheng:patches/xnu-12377/zzzz-sheng-ipados27-bringup.patch:284` 的音频调用行首是空格，属于 unified diff 上下文。
这个补丁新增的是附近 0xe00 的 floating wallpaper 挂载，见 `sheng:patches/xnu-12377/zzzz-sheng-ipados27-bringup.patch:277`。
不能据此声称“不打 zzyd，bringup 也会再添加一次音频挂载”。完整注入契约与冻结边界见 [用户态重接计划](IOS27-USERLAND.md)。

### 用户页表几何与 PAGE_SHIFT 不是同一件事

bringup 的 `sheng:patches/xnu-12377/zzzz-sheng-ipados27-bringup.patch:849` 新建 T0SZ_USER 分叉：
根层级在 `sheng:patches/xnu-12377/zzzz-sheng-ipados27-bringup.patch:853` 取 (T0SZ_USER - 16) / 9，
VA mask 在 `sheng:patches/xnu-12377/zzzz-sheng-ipados27-bringup.patch:866` 使用 ARM_PTE_REGION_MASK(T0SZ_USER)，
根分配静态断言在 `sheng:patches/xnu-12377/zzzz-sheng-ipados27-bringup.patch:869`。
`sheng:patches/xnu-12377/zzzz-sheng-ipados27-bringup.patch:1216` 只在 BCM2837、非 __ARM_16K_PG__ 且 __arm64e__ 的分支定义 17ULL（其余分支为 T0SZ_BOOT），
`sheng:patches/xnu-12377/zzzz-sheng-ipados27-bringup.patch:1236` 给最终 TTBR0 范围设置 TCR，并通过 TCR_EPD0_DISABLE 禁止 TTBR0 walks，直到匹配的页表就绪。

K60 的设备系列没有这段 T0SZ_USER 分叉；这不等于整个有效构建输入没有它，框架与架构系列必须分别检查。
修改 PAGE_SHIFT 的 ABI 补丁不能单独证明根层级、地址范围与指针签名位置也正确。音频线记录这处平台前置，交平台 owner 判断，不自行改 pmap。

### weak_import 写法不是 ld64 链接证据

`sheng:patches/xnu-12377/zzzz-sheng-ipados27-bringup.patch:14` 声明 weak_import 的 boot_log_rounds，
`sheng:patches/xnu-12377/zzzz-sheng-ipados27-bringup.patch:16` 取地址判空并读取 log=1。
这说明源代码怎样防止调用缺席的 provider，不能证明在我们的 ld64、链接形态和输入集合下，未定义弱数据或函数都能链接。
K60 的 armcpu-sleep-hook.patch 恰好记录弱数据也被拒绝，并为函数指针提供真实存储；它没有实现睡眠调用路径。
0531 仍按 [接线清单的 HOLD 条件](IOS27-WIRING.md) 处理：先证明 PongAudioAmp.o 进入链接，再恢复调用点；不加返回成功的空壳。

## 三、K60 设备系列逐组对照

审查输入是 K60 设备系列中 30 个启用项与暂缓的 0531。下表列全这些文件；“未发现对应”仅限所审 sheng 设备系列，不代表全框架没有答案。

| K60 文件或同类组 | sheng 对照与决定 |
| --- | --- |
| ptrauth-string-discriminator.patch | sheng 的 ptrauth strip 诊断与第四个 __ptrauth 字符串参数兼容性不同；未找到可替代项。 |
| armcpu-sleep-hook.patch | sheng-platform-sleep.patch 还实现 hook 调用与唤醒；本地只提供指针存储。是功能差距，不可宣称同一能力已完成。 |
| 0500-k60-bt-qbt-new-files.patch、0502b-k60-bt-qbt-kernel-stubs.patch、0501-k60-bt-qbt-bsd-conf.patch、0502-k60-bt-qbt-bsd-init.patch | K60 蓝牙源与内核入口接线；sheng-bluetooth-runtime.patch 的运行时挂载不能替代它们。 |
| 0507-k60-bt-readonly-probe.patch、0508-k60-bt-s2-smmu-rcg-reset.patch、0509-k60-bt-s3-identity-publish.patch | K60 蓝牙探针、SMMU 与身份；未发现可直接替换的 sheng 补丁。 |
| 0510-k60-bt-firmware-addon.patch、0511-k60-bt-s4-unblock.patch、0512-k60-bt-late-start.patch、0514-k60-bt-boot-observability.patch、0515-k60-bt-tlv-counters.patch | 固件与启动观测有共同需求，但 sheng 的蓝牙运行时与通用埋点不是 K60 控制器实现。 |
| 0516-k60-bt-qbt-uart-clock.patch、0517-k60-bt-power-order.patch、0518-k60-bt-gic-intid.patch、0519-k60-bt-userspace-power-nodes.patch、0520-k60-bt-uart-control-alias.patch | UART、供电、中断与用户态别名为 K60 板级接线；不借另一板的常量与时序。 |
| 0521-k60-bt-blob-stub.patch、0522-k60-bt-vm-kern-xnu.patch、0523-k60-bt-transport-set-rate.patch | 生成载体、12377 内部头与传输调速；未发现对应替代项。 |
| 0525-k60-bt-official-boot-args.patch | 实际是 bluetooth/k60bt 与 log-bluetooth 参数兼容，不是“启动参数入库”。sheng 的 PE_builtin_boot_args 是另一项机制，不能把二者当成重复实现。 |
| 0526-k60-bt-runtime-mount.patch、0527-k60-bt-launchd-cache.patch | 与 sheng-bluetooth-runtime.patch、sheng-wifi-launchd-cache.patch 同属运行时挂载与缓存需求；具体 bundle/路径属于不同 owner，复用机制前需逐段比较。 |
| 0530-k60-spi-availability.patch、0532-k60-cpu-start-completion.patch、0533-k60-v-crypto-syntax.patch | SDK availability、IOCPU completion 与汇编语法适配；本次 sheng 系列没有直接替代项。 |
| 0531-k60-audio-amp-probe-call.patch（HOLD） | weak_import 源码可参考；不能用它证明未定义弱符号链接成功。仍需真实 provider 对象。 |
| 0540-k60-psci-smp.patch | sheng 的记录选择 ArmCpu 与 smp=1 / armcpu-spi-ipi=1，见 sheng:porting.toml:178、sheng:porting.toml:181；这是需与 CPU owner 对照的同类需求，不足以证明两边源码等价。 |
| 0541-k60-virtual-timer-guard.patch | 本地避免 CNTP_CTL 写入；sheng 的 WFE/睡眠策略是另一问题，不能互换。 |

可直接参考的另一项平台机制是内建启动参数：`sheng:patches/xnu-12377/zzzz-sheng-ipados27-bringup.patch:1940` 给出默认定义，
`sheng:patches/xnu-12377/zzzz-sheng-ipados27-bringup.patch:1949` 先查命令行再查内建串；
`sheng:package/BootWatchdogPolicy.c:65` 是板级强定义。若音频参数将来需要内建，应先复用这套机制并保留命令行覆盖。
本次未发现可原样替换 AW88261 探针的 sheng 补丁；也没有足够证据断言所有平行实现都不存在重复。上表的相同需求交对应 owner 继续比较。

## 四、驱动层真正值得借的部分

- GENI I2C：`sheng:package/GeniI2c.c:28` 从 GENI_HW_PARAM_0 读 FIFO 字数，下一行读 RX 深度；
  `sheng:package/GeniI2c.c:38` 的 write_command 用 hold 控制 STOP_STRETCH。需要长缓冲或更完整 FIFO 流控时先读这份 BSD-2-Clause-Patent 实现及其宿主测试，避免重新设计水位逻辑。
- 功放：`sheng:package/ShengCs35l43.c:13` 先读 CS35_DEVID/REVID，再安排 errata 与保护序列。
  sheng 的六颗 CS35L43 与 K60 两颗 AW88261 不同；可借步骤组织和回读方法，寄存器序列、地址与 reset GPIO 必须保持本板依据。
- HAL 与 DSP 路径：package 下的 AudioReach、Service、ABI 和 hal 下的插件同样是参考源；它们不在设备补丁列表中。重接边界与 ABI 判据集中在 [用户态计划](IOS27-USERLAND.md)。

## 五、如何复核

`python3 scripts/check-audio27-sheng-refs.py [repo]` 检查系列每项恰有一行、no 行的目标文件名是否含音频关键词、audio/partial 行是否引用自己的补丁、全部引用的文件与行号是否存在，以及 SOURCES.toml 至少列出三份不同且在同一棵 sheng 检出中存在的音频参考源。
宿主 `scripts/tests/test-audio27-sheng-refs.py` 十例包含重复参考不能凑数和参考文件缺失的反例。
它不验证引文语义、链接成功或硬件行为；diff 的新增/上下文区分与复用决定仍需人工审查。
退出码 0 一致、1 不一致、3 没有检出。预检两行是 sheng refs gate is honest 与 sheng reference sources hold。

[研究清单](../SOURCES.toml) 实际登记五份 sheng 内核/驱动/HAL 参考源；`python3 scripts/research-gate.py` 查文件存在及 examined/finding。
引用的语义与许可证在本页和研究清单中记录，门禁通过不代表已经把这些代码移入 K60。
