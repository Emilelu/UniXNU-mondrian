# SMP 进度判读表：`armcpu_smp_step` / `psci_smp_cpu_stage`

> 适用范围：CPU 线（官方 `porting/platform` 第 1 行）。这份表把「次核起来到哪一步」的每个可观测值
> 映射成结论与下一步，供 F1 之后的 SMP 轮次直接查。Lead 2026-11-21 裁决：F1 前先交这张表。
>
> 行号约定：`drivers/ArmCpu/ArmCpu.cpp`、`E:/hackios/xnu-12377` 的行号是**源码行**；
> `0540-k60-psci-smp.patch` 的行号是**补丁文件内行**（该补丁新建 `osfmk/arm64/psci_smp.c`，
> 补丁行与新建文件内的行号不同，定位时用符号名 `grep`，别用行号互推）。
>
> §6.2 是产物到手后的**可粘贴对账块**（manifest `cpus=` × ADT `/cpus` 子节点数，两路都自测过），
> §6.3 是「若产物是 8 核」的后续分支，其中含一条本轮实测的新前提：ADT 生成器与契约本身单核锁死。

## 0. 先分清楚两条路径

| 路径 | 谁在跑 | 观测手段 | 表格 |
| --- | --- | --- | --- |
| **A. 本轮编译的**：device fork `ArmCpu.cpp`（779 行）+ `0540` 的 `psci_smp.c` | 27 镜像 | 只有 **log 行** + 少量导出符号 | §2、§3 |
| **B. catalog `UniXNU/ArmCpu` 93a5030c**（sheng、xnekom 在用） | 别家的镜像 | **不打印任何东西**，只能读符号 `armcpu_smp_step[]` 等 | §4 |

27 的 `board.toml:14` `include` / `:21` `archives` 指向 `component:ArmCpu`，但 `components.toml:3-19` 把
`revision` 钉在 `93a5030c`，它是 catalog 版本；fork 之所以生效是设备仓自带 `drivers/ArmCpu/ArmCpu.cpp`
遮蔽了组件（见 `FORK-DECISION.md` §2）。所以**这一轮**：A 路径，指令集里没有 `armcpu_smp_step`
（`grep -c armcpu_smp_step drivers/ArmCpu/ArmCpu.cpp` = 0）。§4 的表是为「哪天换回 catalog」和
「读 sheng/xnekom 的日志」准备的，不是本轮产物。

## 1. 本轮实际存在的两个状态字

| 状态 | 定义位置 | 写入者 | 读取者 |
| --- | --- | --- | --- |
| `psci_smp_cpu_stage[MAX_CPUS]`（按 cpu number） | `0540-k60-psci-smp.patch:84` | `psci_smp_cpu_reached()`（`:132`）、`start_cpu`（`:196`、`:199`）、`cpu_running`（`:141`）、`cpu_off`（`:242`） | `psci_smp_start_cpu()` 的等待循环与结局判定（`:208-232`） |
| `psci_smp_start_fault`（64 字节，一条 cache line） | 同补丁 `:79-82` | **没有写入者**（见 §3.2） | `:213-228` |
| `psci_smp_started`（每核一位） | 同补丁 `:85` | `:204`、`:228` | **没有读取者**（见 §3.3） |

## 2. 表 A：fork + 0540 的 log 行 → 判读 → 下一步

| # | 日志（原样字符串） | 出现位置 | 含义 | 结论与下一步 |
| --- | --- | --- | --- | --- |
| A1 | `ArmCpu: CPU %u MPIDR=%#x registered` | `ArmCpu.cpp:526` | 该次核的 nub 已被 `ml_processor_register()` 收下 | 正常；**只说明注册成功，不说明它跑起来了** |
| A2 | `ArmCpu: CPU %u registration failed %d` | `ArmCpu.cpp:518` | `ml_processor_register()` 返回非 0，该 nub 被放弃 | 后续 `armcpu_registered != ml_get_cpu_count()` 会在 `:550` panic；先查 ADT `/cpus` 与拓扑是否一致 |
| A3 | `ArmCpu: incomplete CPU registry (%u/%u)`（panic） | `ArmCpu.cpp:550` | 拓扑说有 N 个 CPU，实际注册到 M 个 | 27 上最常见成因：ADT `/cpus` 节点数与 `ml_get_topology_info()->num_cpus` 不一致（`cpus=` boot arg 会砍拓扑，见 §6） |
| A4 | `ArmCpu: CPU %u PSCI start PASS result=0` | `ArmCpu.cpp:575` | `psci_smp_start_cpu()` 在 5 s 内看到 stage ≥ `RUNNING`(3) | 该核已进调度器，无需动作 |
| A5 | `ArmCpu: CPU %u PSCI start FAIL (offline) result=…` | `ArmCpu.cpp:575` | 未在 5 s 内进调度器；**紧挨着的 `psci:` 行才是原因** | 往下读 A6–A10 中实际出现的那一条 |
| A6 | `psci: no cpu data for cpu %d, not started` | `0540:168` | `cpu_datap(cpu)` 为 NULL：该 CPU 没有 `cpu_data_t`，根本没问固件 | 说明注册链断了（A2/A3），不是 PSCI 问题 |
| A7 | `psci: cpu %d (MPIDR 0x%x) was not started: the firmware answers %lld (%s)` | `:200-201`，错误名表 `:113-120` | SMC 的 `CPU_ON` 返回负数 | 按 `%s` 判：`denied`(-3)=固件策略拒绝；`already on`(-4)=该核已在运行（固件视角），此时不是失败，是重复请求；`invalid parameters`(-2)=entry/affinity 形态错；`not present`(-7)=affinity 不在固件表里 |
| A8 | `psci: cpu %d (MPIDR 0x%x) was started %d seconds ago and has not joined: no sign of it since the firmware took the request` | `:230-232` | `CPU_ON` 返回 0，但该核连 C 代码都没到 | 三个已知方向：`LowResetVectorBase` 的 `ml_static_vtop()` 物理地址错；`CleanPoC_DcacheRegion` 没覆盖到它读的字（`ResetHandlerData`/`const_boot_args`/`cpu_ttep` 在 `cpu_start()` 里回写，27 series 尚未带这一段，见 §7）；ADT 的 `reg` 值不在固件的 MPIDR 表里 |
| A9 | `… has not joined: it got as far as arm_init_cpu()` | `:232` 的另一个分支 | **在 0540 上永不出现**：没有任何代码写 stage 2 | 见 §3.1；真出现说明有人补了 `arm_init_cpu()` 钩子 |
| A10 | `psci: cpu %d (MPIDR 0x%llx) took an exception on its way in and has switched itself off: ESR … ELR … FAR …` | `:225-228` | **在 0540 上永不出现**：`psci_smp_start_fault.valid` 只会被清零 | 见 §3.2；这条能给出 ESR/ELR，是 SMP 最有价值的一条，但需要 `start.s` 的 `Lsecondary_early_exception` |
| A11 | `PSCI: CPU_OFF returned on cpu %d`（panic） | `:243` | `CPU_OFF` 返回了，固件没把核关掉 | 固件违约；该核已 mask DAIF 在自旋，只能整机重启 |
| A12 | `ArmCpu: boot CPU running with GICv3/CNTV ctl=%#llx cval=%#llx now=%#llx freq=%#llx daif=%#llx irq=%llu` | `ArmCpu.cpp:591` | 启动 CPU 的收尾快照，**SMP 轮次里这是基线行** | `freq` 必须等于 ADT `timebase-frequency`（SM8475 为 24 MHz）；`ctl` bit0=1 表示 CNTV 已开；`daif` 里若 `0x200`(A) 或 `0x100`(I) 仍置位，中断没开；`irq` 为 0 说明定时器一次都没进来 |
| A13 | `ArmCpu: CPU %u redistributor did not wake`（panic） | `ArmCpu.cpp:600` | 次核自己的 GICR 没醒 | 先看 A10 是否本可给出原因；否则查 GICR 帧步长（`redistributor-stride`）与该核 affinity 的匹配 |
| A14 | `ArmCpu: unowned SPI %u`（panic） | `ArmCpu.cpp:637` | 收到 32..1019 的 SPI 但没有 owner | 与 CPU 无关，属中断线：检查 `armcpu_spi_attach()` 是否被调用过 |

`ArmCpu.cpp:305`（sleep report）、`:371`（`preserve firmware GICD_CTLR`）、`:428`（resume gate）、
`:463-468`（GIC 映射/初始化预备行）、`:480`（`platform sleep enabled`）、`:496`（`start boot CPU`）
是启动期的上下文行，SMP 判读不用它们。

## 3. 0540 的三个死字段（实测，不是推测）

### 3.1 stage 2（`PSCI_SMP_CPU_IN_KERNEL`）永远不被写

- 定义在 `0540:265`，唯一的**读**在 `:232`（`stage >= PSCI_SMP_CPU_IN_KERNEL` 选措辞）。
- 全仓 `grep -n 'PSCI_SMP_CPU_IN_KERNEL' patches/xnu-12377/0540-k60-psci-smp.patch` 只有 `:232`、`:265` 两处。
- iOS 16 祖先有写入点：`patches/xnu/zzzzzzzzzzzzzzzzzzzzz-pong-psci-smp.patch:69-70`
  （`psci_smp_cpu_reached(2); /* PSCI_SMP_CPU_IN_KERNEL */` 插在 `arm_init_cpu()`），0540 重写时没带过来。
- 后果：次核死在 `arm_init_cpu()` 里，log 会说是「没有它的任何迹象」，误导排查方向。

### 3.2 `psci_smp_start_fault` 永远不会被填充

- `:183` `psci_smp_start_fault.valid = 0;` 清零；`grep -c 'start_fault.valid = 1'` = 0。
- 设计上由 `start.s` 的 `Lsecondary_early_exception` 写入，0540 明确没装它：注释 `:23-25`
  「None of that is here: psci_smp_start_fault stays zero, so start_cpu() reports "has not joined"
  instead of a register dump」。
- 后果：A10 分支不可达；次核在 MMU 打开前取异常，本可以拿到 ESR/ELR/FAR，现在拿不到。

### 3.3 `psci_smp_started` 只写不读

- `grep -n psci_smp_started` 命中 3 处：`:85` 定义、`:204` 置位、`:228` 清位；**没有读取点**。
- 结论：它原本是给「停止所有已启动次核」用的，0540 里没有那样的路径。别把它当成「次核已启动」的证据。

## 4. 表 B：catalog `armcpu_smp_step` 1–7（sheng / xnekom 路径）

catalog 版**不打印**（`grep -c 'printf\|IOLog\|kprintf' ArmCpu-93a5030c.cpp` = 0），这些值只能由
调试器或符号转储读出。行号是 `E:/k60-work/scratch/platform27/ArmCpu-93a5030c.cpp`（= catalog rev
`93a5030c` 的 `ArmCpu.cpp`）。

| 值 | 写入点 | 含义 | 停在这一点说明 |
| --- | --- | --- | --- |
| 1 | `:414` | 次核 nub 被接受并挂进 `gPending`（`IOCPU::start()` 之后、注册之前） | 卡在 `IOCPU::start()` 或 `ipc_kobject` 匹配，`ml_processor_register()` 没被调用 |
| 2 | `:493` | `ml_processor_register()` 返回 `KERN_SUCCESS`，已有 `machProcessor` | 卡在 `startSecondary()`/`kernel_thread_start`（`psci_rc` 会是 -1000） |
| 3 | `:533` | 辅助线程已建，即将调 `processor_start()`；**此时 `CPU_ON` 未必发出** | 卡在调度器给辅助线程排班 |
| 4 | `:824` | `CPU_ON` 发出前一刻；返回码写进 `armcpu_smp_psci_rc[]`（`:826`） | `4` 且 `psci_rc==0` = 固件收下了、核没回来；`psci_rc<0` = 固件拒绝 |
| 5 | `:560` | 次核在核自己的 `initCPU()` 里（已在核页表上跑 C 代码） | 卡在 MPIDR 校验或 redistributor 唤醒（看 `fail`） |
| 6 | `:567` | MPIDR 低位匹配（`:565` 未触发）+ 本地 GICR 已醒（`:566` 未触发） | 卡在 `enableGic()` |
| 7 | `:575` | 已进调度器，`armcpu_smp_running++` | 终态 |

`armcpu_smp_fail[]`：`1`=`MPIDR` 低位与请求的 affinity 不符（`:565`，reset vector 选错 `cpu_data`）；
`2`=本地 redistributor 没醒（`:566`）；`3`=注册前远程 redistributor 没醒（`:482`）；
`4`=`ml_processor_register()` 失败（`:491`）。前两个走 `parkCore()`（核继续自旋，不再前进）。

`armcpu_smp_psci_rc[]`：`-1000`=`kernel_thread_start()` 失败（`:550`）；`-1001`=`psciConduit()`
失败，通常是 ADT 里**没有 `/psci` 节点**（`:816`），catalog 版从 IORegistry `/psci` 的 `method`
取 conduit、**不设默认值**（`:501-514`）；其余为 PSCI 原始返回（`:826`），`0`=接受。

`armcpu_smp_conduit`：`1`=smc、`2`=hvc（`:817`）。K60 的 `/chosen` 写 `psci-method = "smc"`
（`scripts/make-pong-adt.py:174`），且 ADT 没有 `/psci` 节点（`:235-269`），所以换成 catalog 版会先得到
`-1001`。

`armcpu_smp_sys[8][5]` / `armcpu_boot_sys[5]`：`:47` 只有声明，**93a5030c 全文件没有写入点**
（`grep -n 'armcpu_smp_sys\|boot_sys'` 只命中 `:47`）。读到全 0 不代表「没有信息」，代表这个字段在本
revision 里不存在。

## 5. 表 C：同一件事在两条路径上的样子

| 事件 | A 路径（fork + 0540） | B 路径（catalog） |
| --- | --- | --- |
| 固件接受 `CPU_ON` | log 无输出；stage 内部变 1（`ASKED`），不可见 | `step = 4`，`psci_rc = 0` |
| 次核开始跑 C 代码 | **不可见**（stage 2 无写入者） | `step = 5` |
| 次核进调度器 | `ArmCpu: CPU %u PSCI start PASS` | `step = 7` + `armcpu_smp_running` |
| 固件拒绝 | `psci: cpu %d … was not started: … (%s)` | `step = 4`，`psci_rc < 0` |
| 次核没回来 | `psci: … has not joined: no sign of it …` | `step = 4`（`psci_rc = 0`） |
| 次核取异常 | **不可见**（fault 记录无写入者） | 同样不可见（catalog 没有 fault 记录） |

## 6. 27 stage-0 上这些值会是什么

两个独立的上限：

1. **ADT `/cpus` 节点数**：`scripts/make-pong-adt.py:74` 的 `--cpus` 默认 `1`（`choices=range(1,9)`），
   设备仓 `board.toml:210` 写 `cpus = 8`，注释 `:206-209` 说明「八个 CPU 全要，靠 kext 补丁绕过
   AppleARMCPU 的单 CPU 校验」。
2. **XNU 的 `cpus=` boot arg**：`osfmk/arm64/machine_routines.c:1154`
   `PE_parse_boot_argn("cpus", …)` 会在 `ml_parse_cpu_topology()` 里砍掉多出的核，并置
   `cpu_config_modified = true`；`scripts/build-native-bootimg-local.py:108` 就是把它拼进
   boot_args 的地方（`keepsyms=1 cpus={--cpus}`）。缺省（manifest 里没有 `cpus=`）时不砍，拓扑
   回到 DT 的 `/cpus` 子节点数。

所以这一轮到底是单核还是八核，取决于 F1 那次构建传的 `--cpus`：

- `--cpus 1`：拓扑 1 个核 → `ArmCpu.cpp:543` 的 `number < 0` 分支跳过其余七个 nub（不 panic，
  `:550` 也不会触发，因为 `armcpu_registered == ml_get_cpu_count()`）→ 一次 `processor_start` 都没有
  → §2 的 A4–A11 全部不出现，0542 的 SIGP 路径休眠。
- `--cpus 8`：拓扑 8 个核 → 注册 8 个 → 7 次 `processor_start` → 7 条 `ArmCpu: CPU %u PSCI start …`
  逐一出现，`psci:` 解释失败者。这就是「SMP 下 UFS 根起不来」的场景本身。

### 6.1 定案：F1 = 1 核，但这是口径不是读数

**Lead 已定案（2026-11-21T18:26）：F1 的 `cpus` = 1。** 真值是 `scripts/make-pong-adt.py:74` 的
`--cpus 1`；设备仓 `board.toml:210` 的 `cpus = 8` 是 iOS 16 残留，由 Lead 修（这条口径冲突归他）。
所以适用的是上面第一列：一次 `processor_start` 都没有，§2 的 A4–A11 不出现，0542 的 SIGP 路径在
stage-0 休眠；等 F1 通过后按 8 核重评，再决定 0543 与这张表的第二列。

`cpus = 1` 来自 Lead 的口径，**不是**从产物读出来的：本轮
`E:/hackios/UniXNU/out/mondrian/ios-27.0.1-24A446/mondrian_ios27/` 里只有 `xnu-inputs.json`
（内核阶段）与 `logs/`、`tree/`、`xnu-patches.list`，没有 `stage/EFI/UniXNU/`。产物一到先按 §6.2
对账，对不上以产物为准。

### 6.2 对账块（可粘贴，已在同形合成产物上自测）

产物路径由 `scripts/build-native-bootimg-local.py` 决定：`:90` `payload = out / 'stage/EFI/UniXNU'`，
`:123-124` 写 `pong-boot-manifest.json`，`:128` 写同目录的 `kernel.macho.adt`。所以两处读数都在
同一目录里：

```sh
OUT=<F1 的 --output-dir>     # 例 /mnt/e/hackios/UniXNU/out/mondrian/ios-27.0.1-24A446/mondrian_ios27
PAYLOAD=$OUT/stage/EFI/UniXNU
```

**块 1：manifest 的 `cpus=`**

```sh
MANIFEST=$PAYLOAD/pong-boot-manifest.json
python3 - "$MANIFEST" <<'PY'
import json, re, sys
manifest = json.load(open(sys.argv[1], encoding='utf-8'))
boot_args = manifest['boot_args']
match = re.search(r'(?:^|\s)cpus=(\d+)(?:\s|$)', boot_args)
print('boot_args:', boot_args)
print('manifest cpus =', match.group(1) if match else 'ABSENT (XNU falls back to the DT topology)')
PY
```

**块 2：ADT 的 `/cpus` 子节点数，并与块 1 对账**

```sh
ADT=$PAYLOAD/kernel.macho.adt
python3 - "$ADT" "$MANIFEST" <<'PY'
import json, re, sys
sys.path.insert(0, 'scripts')
from pong_adt_contract import parse_adt

nodes = parse_adt(open(sys.argv[1], 'rb').read())
children = sorted(p for p in nodes
                  if p.rsplit('/', 1)[0] == '/cpus'
                  and p.rsplit('/', 1)[-1].startswith('cpu')
                  and p.rsplit('/', 1)[-1] != 'cpu-map')
print('ADT /cpus children:', len(children), children)
for path in children:
    print(' ', path, 'MPIDR =', hex(int.from_bytes(nodes[path]['reg'], 'little')),
          'state =', (nodes[path].get('state', b'<absent>').rstrip(b'\0').decode() or '<empty>'))

manifest_cpus = json.load(open(sys.argv[2], encoding='utf-8'))['boot_args']
match = re.search(r'(?:^|\s)cpus=(\d+)(?:\s|$)', manifest_cpus)
print('VERDICT:',
      'AGREE on %s core(s)' % match.group(1)
      if match and int(match.group(1)) == len(children)
      else 'DISAGREE - the manifest and the ADT must be reconciled before anything is read from them')
PY
```

自测（2026-11-21，脚本 `E:/k60-work/scratch/platform27/reconcile-repro.sh`，两个块都在 1 核 ADT +
同形 manifest 上原样跑过）：一致时打 `manifest cpus = 1` / `ADT /cpus children: 1 ['/cpus/cpu0']` /
`VERDICT: AGREE on 1 core(s)`；把 manifest 改成 `cpus=8` 再跑同一块，打
`VERDICT: DISAGREE - …`，不抛异常。所以判读只有一句话：**两处必须相等，不等先对账、别读表**。

### 6.3 若产物是 8 核：后续分支

**0542 立刻有用。** 8 核拓扑 ⇒ 注册 8 个核 ⇒ 7 次 `processor_start`，§2 的 A4–A11 全部打开，
`psci:` 那几行开始解释谁没起来；SIGP 的 `cpu_signal` 残留位正是「调度停摆 / UFS 根挂不上」那条路径，
本条补丁从「备着」转为「在用」。

**0543 仍然不写。** 依据是 Lead 2026-11-21T18:26 的口径「等 F1 通过后按 8 核重评」：8 核产物只证明
核数，不证明 SMP 是下一阶段目标，也不证明 §7 的两条前提该由本线现在补。判据是 F1 通过 + Lead 明确
把 SMP 排进阶段，两者缺一不写。

**新增的第三方前提（本轮实测，之前没有任何文档列过）：ADT 生成器与契约本身是单核锁死的。**

```sh
python3 scripts/make-pong-adt.py --cpus 2 --dram-size 0x300000000 --output E:/k60-work/scratch/platform27/adt2.macho.adt
#   File "…/scripts/make-pong-adt.py", line 291, in main
#   File "…/scripts/pong_adt_contract.py", line 163, in audit_adt
#     raise ValueError('Pong single-core ADT must expose only /cpus/cpu0')
# ValueError: Pong single-core ADT must expose only /cpus/cpu0   ← 生成器自审计（:290-292）直接拒绝
```

即 8 核 ADT 今天产不出来，唯一通路是加 `--skip-image-verification`（`make-pong-adt.py:290` 的
`if not args.skip_image_verification` 跳过自审计；`build-native-bootimg-local.py:138-139` 的第二次审计
同样被 `'skipped by request'` 跳过）。实测这条通路能写出两个节点：

```sh
python3 scripts/make-pong-adt.py --cpus 2 --dram-size 0x300000000 --skip-image-verification \
  --output E:/k60-work/scratch/platform27/adt2skip.macho.adt
# Pong ADT: 12864 bytes; cpu_count=2; …
# children: ['/cpus/cpu0', '/cpus/cpu1']   regs: ['00000000', '00010000']   ← Aff1 逐核 +1
```

所以 8 核路线要动三处，且必须一起动，否则「跳过图像验证」会成为唯一通路，而那条通路同时丢掉
Image4 / nonce / manifest 绑定那一段检查：

1. `scripts/pong_adt_contract.py:158-163`：放开「只许 `/cpus/cpu0`」，改成「节点数 == 期望核数 + MPIDR
   唯一 + `state` 里恰有一个 `running`（boot CPU 必须是 MPIDR 0）」；
2. `scripts/pong_adt_contract.py:189`：`'cpu_count': 1` 改成实测值（现在是硬编码常量，报告会撒谎）；
3. `scripts/make-pong-adt.py:291` 的自审计随契约一起放开（它调的就是同一个 `audit_adt`）。

推论：**只有「8 核 + 跳过图像验证」才产出的镜像，其日志不能用来判 SMP 是否修好**——它少掉的正是
nonce/manifest 绑定那一段。要用它判 SMP，得先把上面三处改完再重出。

## 7. 真开 SMP 之前必须先补的两件事

1. **`cpu_start()` 的回写**（sheng `cpu.c` 的 `:934` hunk，0542 未搬）：次核在 MMU 关闭、无 cache 的
   状态下从 DRAM 读 `ResetHandlerData`、`const_boot_args`、`cpu_ttep`；不把这三处写回 PoC，A8 的
   「没有它的任何迹象」就是预期结果。按 Lead 的顺排规则，这条应作为下一条 `0543-*`。
2. **stage 2 的钩子**：在 `arm_init_cpu()` 里加 `psci_smp_cpu_reached(2)`（iOS 16 祖先的做法，
   `patches/xnu/zzzzzzzzzzzzzzzzzzzzz-pong-psci-smp.patch:69-70`），否则 A8/A9 这两条判读永远二选一
   到错的那一边。可以和第 1 条同一条补丁，也可以紧跟其后。

（`Lsecondary_early_exception` + fault 记录是第三件，成本高、只在「次核取异常」这一种失败上有收益，
按需再排。）

另有一条**在 SMP 之前**就要解决的前提（§6.3 实测）：ADT 契约与生成器都按单核写死
（`scripts/pong_adt_contract.py:158-163`、`:189`，`scripts/make-pong-adt.py:290-292`），所以今天连
8 核 ADT 都产不出来——这条不属于 0542/0543，属于生成器那一侧，要先有人认领。

## 8. 复现清单

```sh
# A 路径：本轮编译的 log 行（应输出上表所有 A 行，行号一致）
grep -n 'IOLog(\|panic(' drivers/ArmCpu/ArmCpu.cpp

# 0540 的 stage 值、fault 记录、started 位
grep -n 'PSCI_SMP_CPU_\|psci_smp_start_fault\|psci_smp_started' \
  patches/xnu-12377/0540-k60-psci-smp.patch

# 三个死字段：期望输出分别是 2 / 0 / 3 行
grep -c 'PSCI_SMP_CPU_IN_KERNEL' patches/xnu-12377/0540-k60-psci-smp.patch
grep -c 'start_fault.valid = 1' patches/xnu-12377/0540-k60-psci-smp.patch
grep -c 'psci_smp_started' patches/xnu-12377/0540-k60-psci-smp.patch

# B 路径：catalog 的写入点与「不打印」事实
grep -n 'armcpu_smp_step\|armcpu_smp_fail\|armcpu_smp_psci_rc\|armcpu_smp_conduit' \
  /e/k60-work/scratch/platform27/ArmCpu-93a5030c.cpp
grep -c 'printf\|IOLog\|kprintf' /e/k60-work/scratch/platform27/ArmCpu-93a5030c.cpp   # 0

# 8 核/单核的两个上限
sed -n '74p' scripts/make-pong-adt.py; sed -n '206,210p' board.toml
grep -n 'PE_parse_boot_argn("cpus"' /e/hackios/xnu-12377/osfmk/arm64/machine_routines.c

# 单核锁死在哪三行（期望：163 的 raise、189 的常量、291 的调用）
sed -n '158,163p;189p' scripts/pong_adt_contract.py
sed -n '290,292p' scripts/make-pong-adt.py

# 8 核 ADT 今天产不出来（期望：ValueError … must expose only /cpus/cpu0）
python3 scripts/make-pong-adt.py --cpus 2 --dram-size 0x300000000 \
  --output E:/k60-work/scratch/platform27/adt2.macho.adt

# 唯一通路：跳过图像验证才能写多核（期望 cpu_count=2、两个子节点）
python3 scripts/make-pong-adt.py --cpus 2 --dram-size 0x300000000 --skip-image-verification \
  --output E:/k60-work/scratch/platform27/adt2skip.macho.adt
python3 -c "import sys; sys.path.insert(0,'scripts'); from pong_adt_contract import parse_adt; \
n=parse_adt(open('E:/k60-work/scratch/platform27/adt2skip.macho.adt','rb').read()); \
print(sorted(p for p in n if p.rsplit('/',1)[0]=='/cpus' and p.split('/')[-1].startswith('cpu') and p.split('/')[-1]!='cpu-map'))"

# 产物对账两段（§6.2）的自测：全流程一次跑完，期望 AGREE on 1 core(s)
bash /e/k60-work/scratch/platform27/reconcile-repro.sh
```
