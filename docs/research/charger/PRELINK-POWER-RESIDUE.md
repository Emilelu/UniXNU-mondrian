# Prelink 电源残留：PMGR / Watchdog / ARMPlatform 的 26 个地址

日期：2026-11-21

范围：iOS 27.0.1（24A446）的 kernel.json 中，com.apple.driver.ApplePMGR、com.apple.driver.AppleARMWatchdogTimer、com.apple.driver.AppleARMPlatform 三个 bundle 的 unresolved 引用。本文只回答三件事：每个地址属于哪类调用、stage-0 是否必须实现、现有 K60PmicRail/0614/0619 能否填。本文不改代码，不改 gate，不把 4 字节 ret 占位当作实现。

## 1 结论

- 三个 bundle 一共 30 条引用，去重后 26 个地址：PMGR 7、Watchdog 6 个 stubbed 加 1 个 missing、ARMPlatform 17。重复地址是跨 bundle 的同一目标，不是 30 个独立函数。
- 真正接近 PMGR 硬件语义的只有 6 个：0xfffffff00ab86b04（时钟/计时读）、0xfffffff00abff7fc 与 0xfffffff00abffae8（cluster powerdown）、0xfffffff00ad45084（PMGR 系统寄存器写）、0xfffffff00b351bd8 与 0xfffffff00b351d7c（PMGR 中断控制器）。其余是 CPU 编号/状态、IOReporter、IOService、IOCPU、panic/console 等通用内核依赖。
- 没有任何一个地址属于电压（voltage）类。电池/充电的 PMIC 电压路径不在这三个 bundle 里；不要拿 K60PmicRail 的 rail 账本去补 PMGR 的时钟、复位或中断函数。
- 26 个地址没有一个能由 K60PmicRail、0614 或 0619 填。K60PmicRail 是只读 PMIC rail 账本，0614/0619 是 ADSP PAS 交接；它们都不提供 PMGR 时钟/复位/系统寄存器/中断控制器的实现。
- stage-0 停在 bsd_init 不等于这些符号可以不管。prelink 的 loadable 条件是闭包完整；只要这 26 个引用还在，mapping_complete 就是 false，loadable 就是 false。stage-0 不可达的项也需要一个 native 映射，只是不需要在 bsd_init 之前执行其行为。
- 0xfffffff007044478 是 missing，不在 native 的代码段，原始 kernelcache 在该偏移是零；本文不能凭地址猜它的函数名。它需要从 Watchdog bundle 的重定位/符号表取得名字，或由 native 侧提供同地址对象；不能用一个 ret 占位糊过去。

## 2 证据口径

分析对象：

- kernel.json：/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.json
- 原始 kernelcache：/opt/k60/trees/ios27-out/ipsw/24A446/kernelcache.decompressed
- 输出 kernel.macho：/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.macho
- 地址到名字：kernel.map.json；native 符号：tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped.noctf

kernel.json 的计数是 25 个 bundle、203 条 stubbed、131 个唯一 stubbed 地址、3 条 missing。三个目标 bundle 的条目是：

~~~text
ApplePMGR              stubbed 7   missing 0
AppleARMWatchdogTimer  stubbed 6   missing 1
AppleARMPlatform       stubbed 17  missing 0
~~~

### 2.1 4 字节 ret 是占位，不是函数

kernel.json 里的 stubbed 地址是原始函数入口地址。输出 kernel.macho 在这些地址上写一条 4 字节 ret，再把原函数整体后移 4 字节。以 0xfffffff00ab86b04 为例：

~~~text
original kernelcache @ 0xfffffff00ab86b04:
  bti c
  mrs x0, S3_4_C15_C10_6
  ret

output kernel.macho @ 0xfffffff00ab86b04:
  ret
  0xfffffff00ab86b08: bti c
  0xfffffff00ab86b0c: mrs x0, S3_4_C15_C10_6
~~~

因此判断一个 stubbed 地址时必须读原始 kernelcache 的同一地址；读输出 kernel.macho 的同一地址只会看到 ret。这个 ret 让 prelink 能继续，但它也让被引用的函数永远返回，不能作为“已经实现”的证据。

### 2.2 原始 kernelcache 没有符号表

原始 kernelcache 是 MH_FILESET，318 条 load command：305 条 LC_FILESET_ENTRY、9 条 LC_SEGMENT_64、1 条 LC_DYLD_CHAINED_FIXUPS。305 个子 Mach-O 的 LC_SYMTAB 都是 symoff=77496320、nsyms=0、stroff=77970320、strsize=1，也就是全部被 strip。函数名只能来自 kernel.map.json 的“最近全局符号”，或 native 文件的符号表。

地址换算：

~~~text
__TEXT_EXEC:      0x1430000 + (addr - 0xfffffff008434000)
__TEXT_BOOT_EXEC: 0x4428000 + (addr - 0xfffffff00b42c000)
__PRELINK_TEXT:   0x8000    + (addr - 0xfffffff00700c000)
~~~

### 2.3 missing 0xfffffff007044478

该地址在 native 的 __TEXT（0xfffffff007004000..0xfffffff0071a4000），不在 native 的 __TEXT_EXEC（从 0xfffffff0072c0000 开始）。llvm-nm 在该地址没有符号；最近的符号是 const 数据（例如 0xfffffff007044dd8 的 _t_fl）。原始 kernelcache 的 0x40478 是零，反汇编为 udf #0。结论只能是“非代码段/未知数据引用”，不能从指令体判类。它必须从 Watchdog bundle 的未解析重定位或链接映射取得真实名字；在那之前，任何“这是一个 watchdog 函数”的说法都是猜测。

## 3 逐地址判断

列说明：

- 引用：本任务三个 bundle 中引用该地址的 bundle；同一地址在其他 bundle 也出现时不影响本判断。
- 首几条：原始 kernelcache 的入口指令，已去掉 4 字节 ret 的干扰。
- 最近全局：kernel.map.json 中最近的全局函数名；带 +0x 表示该地址是一个未命名的局部函数，落在全局函数的范围内。
- (a) 类：PMGR 五类（clock/voltage/reset/watchdog/PMGR interrupt）或“非 PMGR 硬件”的通用类。
- (b) stage-0：必须实现 = bsd_init 之前的行为需要；stage-0 不可达 = 行为不在 bsd_init 前执行，但 prelink 仍需要一个符号映射；未知 = 无法判。
- (c) K60 现有物：K60PmicRail、0614、0619 能否填；全部为否，原因见 §5。

| 地址 | 引用 | 首几条 | 最近全局 | (a) 类 | (b) stage-0 | (c) K60 现有物 |
|---|---|---|---|---|---|---|
| 0xfffffff00ab86b04 | PMGR, Watchdog | bti c; mrs x0,S3_4_C15_C10_6; ret | _clock_absolutetime_interval_to_deadline+0x54 | clock（计时读） | 必须实现 | 否 |
| 0xfffffff00abff7fc | PMGR | pacibsp; sub sp,#96; 读 global+612；88 字节数组循环 | _sched_perfcontrol_check_oncore_thread_preemption+0xb4 | reset（cluster powerdown） | 必须实现 | 否 |
| 0xfffffff00abffae8 | PMGR | pacibsp; sub sp,#80; 读 global+612/640、TPIDR_EL1、DAIF | _sched_perfcontrol_check_oncore_thread_preemption+0x3a0 | reset（cluster powerdown） | 必须实现 | 否 |
| 0xfffffff00ad44a38 | PMGR | bti c; adrp; str x0,[global,#440]; ret | _gpu_set_fceiling_cb_default+0xc | 非 PMGR 硬件：GPU 频率上限回调 | stage-0 不可达（GPU 不启动） | 否 |
| 0xfffffff00ad468ec | PMGR | bti c; mrs x9,MPIDR_EL1; 24 字节数组查表 | _ml_get_boot_cpu_number+0xec | 非 PMGR 硬件：CPU 编号 | 必须实现 | 否 |
| 0xfffffff00ad46948 | PMGR | 同 0xad468ec，MPIDR_EL1 + global+604/632 | _ml_get_boot_cpu_number+0x148 | 非 PMGR 硬件：CPU 编号 | 必须实现 | 否 |
| 0xfffffff00b36e788 | PMGR | pacibsp; sub sp,#128; 保存 x19-x28；IOReporter 方法 | IOReporter::configureReport+0xe0 | 非 PMGR 硬件：IOReporter 上报 | stage-0 不可达（reporting） | 否 |
| 0xfffffff00abe3554 | Watchdog, ARMPlatform | pacibsp; sub sp,#32; bl #20; 返回 0 | _cons_putc_locked+0x2c | watchdog（console/panic 日志） | 必须实现（console 早路径） | 否 |
| 0xfffffff00ad3d804 | Watchdog, ARMPlatform | bti c; mrs x8,TPIDR_EL1; ldrh w0,[x8,#432]; ret | _cpu_to_processor+0x38 | 非 PMGR 硬件：CPU 状态 | 必须实现 | 否 |
| 0xfffffff00ad46814 | Watchdog, ARMPlatform | bti c; MPIDR_EL1 + 24 字节数组查表 | _ml_get_boot_cpu_number+0x14 | 非 PMGR 硬件：CPU 编号 | 必须实现 | 否 |
| 0xfffffff00b4320d8 | Watchdog | bti c; 两个 adrp/ldr；sub；b #4 到 pacibsp 函数 | _get_arm_cpu_version+0x168 | watchdog（CPU 启动版本） | 必须实现 | 否 |
| 0xfffffff00b432308 | Watchdog | pacibsp; sub sp,#208; 保存 x19-x26；45 个直接调用者 | _get_arm_cpu_version+0x398 | watchdog（machine timeout/CPU 启动） | 必须实现 | 否 |
| 0xfffffff00ab8e798 | ARMPlatform | pacibsp; 保存 x19/x20；bl __zalloc_permanent；str x20,[x0,#8] | _Debugger+0x3f4 | 非 PMGR 硬件：panic/debug 缓冲 | 必须实现（panic 路径） | 否 |
| 0xfffffff00ad3c5b8 | ARMPlatform | pacibsp; TPIDR_EL1；ldr x19,[x8,#440]；与 global 比较 | _cpu_cluster_id+0x14 | 非 PMGR 硬件：CPU cluster id | 必须实现 | 否 |
| 0xfffffff00ad3d814 | ARMPlatform | bti c; adrp/ldr x0,[global,#1200]; ret | _cpu_to_processor+0x48 | 非 PMGR 硬件：CPU 状态 | 必须实现 | 否 |
| 0xfffffff00ad45084 | ARMPlatform | bti c; mrs MPIDR_EL1；msr S3_5_C15_C0_0 / _1；isb；ret | _machine_init+0x114 | PMGR 系统寄存器写（CPU machine init） | 必须实现 | 否 |
| 0xfffffff00ad46870 | ARMPlatform | bti c; MPIDR_EL1 + 24 字节数组查表 | _ml_get_boot_cpu_number+0x70 | 非 PMGR 硬件：CPU 编号 | 必须实现 | 否 |
| 0xfffffff00b2ab224 | ARMPlatform | pacibsp; sub sp,#224; 清栈块；IOService SetProperties block tail-call | IOService::StateNotificationItemCopy+0x1b8 | 非 PMGR 硬件：IOService 状态通知 | stage-0 不可达 | 否 |
| 0xfffffff00b2e7034 | ARMPlatform | pacibsp; 保存 x19/x20；applyToProviders 形状 | IOService::systemPowerChange+0xf4 | 非 PMGR 硬件：IOService 电源变更 | stage-0 不可达 | 否 |
| 0xfffffff00b33eed4 | ARMPlatform | IOCPU 方法；保存 x19/x20；读 vtable 槽 0x150 | IOCPU::setProperties+0x130 | 非 PMGR 硬件：IOCPU 策略 | 必须实现 | 否 |
| 0xfffffff00b33ef90 | ARMPlatform | cbz x1; b ...; mov x0,#0; ret | IOCPU::setProperties+0x1ec | 非 PMGR 硬件：IOCPU 策略 thunk | 必须实现 | 否 |
| 0xfffffff00b33efa4 | ARMPlatform | cbz x1; b ...; mov w0,#0; ret | IOCPU::setProperties+0x200 | 非 PMGR 硬件：IOCPU 策略 thunk | 必须实现 | 否 |
| 0xfffffff00b351bd8 | ARMPlatform | IOInterruptController 方法；x1+128 + w2*16 取 handler | IOInterruptController::causeInterrupt+0x90 | PMGR interrupt | 必须实现 | 否 |
| 0xfffffff00b351d7c | ARMPlatform | IOInterruptController 方法；cbz x3；同样的索引/handler | IOInterruptController::enableInterrupt+0xf8 | PMGR interrupt | 必须实现 | 否 |
| 0xfffffff00b36ea1c | ARMPlatform | pacibsp; sub sp,#96; 加锁；IOService::updateReport 调用 | IOReporter::configureReport+0x374 | 非 PMGR 硬件：IOReporter 上报 | stage-0 不可达（reporting） | 否 |
| 0xfffffff007044478 | Watchdog (missing) | 原始 kernelcache 0x40478 为零/udf #0；native __TEXT 无符号 | 无（不在 native 代码段） | 未知（非代码段/数据引用） | 未知 | 否（先取得符号名） |

## 4 归类汇总

| 类 | 地址 | 数量 |
|---|---|---|
| clock | 0xab86b04 | 1 |
| reset（cluster powerdown） | 0xabff7fc, 0xabffae8 | 2 |
| PMGR 系统寄存器写 | 0xad45084 | 1 |
| PMGR interrupt | 0xb351bd8, 0xb351d7c | 2 |
| CPU 编号/状态/topology | 0xad468ec, 0xad46948, 0xad3d804, 0xad46814, 0xad3d814, 0xad46870, 0xad3c5b8 | 7 |
| IOReporter | 0xb36e788, 0xb36ea1c | 2 |
| IOService | 0xb2ab224, 0xb2e7034 | 2 |
| IOCPU | 0xb33eed4, 0xb33ef90, 0xb33efa4 | 3 |
| panic/console | 0xab8e798, 0xabe3554 | 2 |
| watchdog/CPU 启动与超时 | 0xb4320d8, 0xb432308 | 2 |
| GPU 频率上限回调 | 0xad44a38 | 1 |
| 未知 | 0x7044478 | 1 |

0xad44a38 是 GPU 频率上限回调，不是 PMGR register，因此单独归入 GPU 类。真正属于 PMGR 硬件语义的地址是 6 个：clock 一个（0xab86b04）、reset 两个（0xabff7fc、0xabffae8）、系统寄存器写一个（0xad45084）、PMGR interrupt 两个（0xb351bd8、0xb351d7c）。

## 5 为什么 K60PmicRail / 0614 / 0619 一个也填不了

K60PmicRail 做的是：读已有的 PMIC rail 账本，记录 complete/valid，不写 PMIC、不写 SPMI、不写 PMGR 系统寄存器。它没有时钟源、没有 CPU cluster 复位、没有中断控制器注册、没有 IOService/IOCPU 生命周期。它不能把 0xab86b04 的计时读、0xabff7fc/0xabffae8 的 cluster powerdown、0xad45084 的 msr 写成任何东西。

0614/0619 做的是 ADSP PAS 的交接（handoff、认证、发布），不是 CPU/PMGR。它们的输入是 ADSP 固件和 SMEM，不是 PMGR 的时钟/复位寄存器；它们不能提供这些符号，也不能替代这些函数。

唯一容易误判的是 0xad45084：它确实是 msr S3_5_C15_C0_0/_1，但这是 CPU machine init 的系统寄存器写，不是 PMIC rail 读数。K60PmicRail 的只读账本不能填它；0614/0619 也不碰它。对 0xabff7fc/0xabffae8 同理：cluster powerdown 不是 ADSP 电源交接。

因此表中 (c) 全部为否。不是“暂时没有接线”，而是这些现有物的职责范围不包含 PMGR 时钟/复位/中断/CPU 生命周期。

## 6 对 stage-0 的处理建议

1. 先把 26 个地址分成“native 可映射”和“必须新实现”两组。CPU 编号/状态、IOReporter、IOService、IOCPU、IOInterruptController 这些通用目标，优先在 native 符号表里找同名/同语义实现，建立映射；不要为它们写 K60 硬件代码。
2. 对 clock、cluster powerdown、PMGR 系统寄存器写、PMGR interrupt 这 7 个地址，逐个要求“原始函数体 + 调用者 + 硬件寄存器”三件证据；没有三件证据就不写实现。0xad45084 需要先确定 S3_5_C15_C0_0/_1 在 PMGR 里的含义，不能凭 msr 就说是电压。
3. 0x7044478 先解决“它是什么”，再谈“怎么填”。从 Watchdog bundle 的未解析重定位/链接映射取符号名；如果确实是数据/const 引用，就在 native 侧提供同地址对象，而不是造一个函数。
4. 处理完后重新跑 prelink，目标不是“stubbed 数变小”，而是 mapping_complete=true、loadable=true；如果仍有缺失，必须在记录里写清楚“哪一条、为什么可以缺席”，不能只报一个总数。
5. 这 26 个是电源三 bundle 的子集；F1 的 150 个地址里其余项按同一张表处理，不要把“非 PMGR 硬件”误记成 PMGR 残留。

## 7 引用

- kernel.json 的 stubbed/missing 字段；本文的计数来自该文件。
- kernelcache.decompressed 的 __TEXT_EXEC/__TEXT_BOOT_EXEC 反汇编；每个地址的首几条已在表中列出。
- kernel.map.json 的最近全局函数名；带 +0x 的地址是未命名局部函数，名字只表示它落在哪个全局函数范围内，不是它的真实符号。
- native 文件 mach.development.bcm2837.unstripped.noctf 的符号表；0x7044478 不在其代码段。
