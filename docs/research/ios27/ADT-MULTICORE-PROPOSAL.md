# ADT 多核拓扑：契约提案草案（未进 series）

> 触发：Lead m01179 ①（授权改、但只作提案草案）；Lead m01022 ②（F1 的 `cpus` = 1）。
> 范围：`scripts/pong_adt_contract.py`、`scripts/make-pong-adt.py` 两处。不进 series、不构建、不动 `k60-gates` 的脚本本体。

> **结论：现在不进 series。** 三条判据：① 它改的是**镜像生成路径**——`scripts/make-pong-adt.py` 是 `build-native-bootimg-local.py` 的出图入口，落地后每一张 27 镜像的 ADT 都换形状，而今天没有任何一张 F1 产物可以对着验（§2）；② 判 SMP 的前提是镜像本身可信，而今天唯一能产出 8 核 ADT 的通路是 `--skip-image-verification`，它同时丢掉 Image4/nonce/manifest 绑定那一段（§1.3），等于用「少一段检查的镜像」去判「核有没有起来」；③ 它和 `board.toml:210 cpus = 8`（iOS 16 残留，Lead 认领）是同一个口径冲突的两面，先改脚本会让「配置说 8、生成器说 1」变成「两边都说 8 但没人跑过」，反而更难判。落地条件见 §7。

## 0. 一句话

Pong 的 ADT 契约把「单核」写死成断言（而不是参数），于是 8 核 ADT 今天**根本产不出来**；草案把核数变成参数，同时把真正该守的不变量（MPIDR 唯一、恰一个 `running`、`cpu0..cpuN-1` 无空洞）写进契约。它改的是出图路径，所以只交草案。

## 1. 锁在哪

### 1.1 三处硬锁

| # | 位置 | 现状 | 后果 |
|---|---|---|---|
| 1 | `scripts/pong_adt_contract.py:158-163` | `if cpu_paths != ['/cpus/cpu0']: raise ValueError('Pong single-core ADT must expose only /cpus/cpu0')` | 任何多核 ADT 在校验处就死 |
| 2 | `scripts/pong_adt_contract.py:189` | 报告字段 `'cpu_count': 1` 硬编码 | 即使节点数变了，报告也撒谎 |
| 3 | `scripts/make-pong-adt.py:290-292` | `if not args.skip_image_verification: audit_adt(tree, require_manifest=…, boot_manifest=…)` | 生成器自审计，调的是同一个 `audit_adt`，所以 1 号锁对生成器自己生效 |

### 1.2 实测

```sh
python3 scripts/make-pong-adt.py --cpus 2 --dram-size 0x300000000 \
  --output E:/k60-work/scratch/platform27/adt2.macho.adt
# ValueError: Pong single-core ADT must expose only /cpus/cpu0
#   File ".../scripts/make-pong-adt.py", line 301, in <module>      main()
#   File ".../scripts/make-pong-adt.py", line 291, in main          boot_manifest=…)
#   File ".../scripts/pong_adt_contract.py", line 163, in audit_adt
```

`--cpus 1` 对照：`Pong ADT: 12600 bytes; cpu_count=1`。

### 1.3 唯一通路同时是脏通路

`--cpus 2 --skip-image-verification` 能写出两节点 ADT（`Pong ADT: 12864 bytes; cpu_count=2`），但
`build-native-bootimg-local.py:138-139` 在同一个开关下也跳过第二次稽核（`'skipped by request'`）。
也就是说这条路产出的镜像**同时**少了 Image4 策略、nonce 与 manifest 绑定那一段检查。用它的日志判
SMP，判的是「少了三段检查的镜像里核有没有起来」，结论不可迁移。

`reg` cell 是原始字节：`cpu1` 的 `reg` 打印成 `00010000`，按小端读是 `0x100`（`struct.pack('<I', i << 8)`），
**不是 `0x10000`**。§6 的对账脚本用 `int.from_bytes(…, 'little')` 换算，别拿字符串当数值。

## 2. 为什么现在不能进 series

1. **改的是出图路径。** `make-pong-adt.py` 由 `build-native-bootimg-local.py` 驱动，落地后每张 27 镜像的 ADT 都换形状；而 27 的产物目录 `E:/hackios/UniXNU/out/mondrian/ios-27.0.1-24A446/mondrian_ios27/` 目前只有 `xnu-inputs.json`、`logs/`、`tree/`、`xnu-patches.list`，没有 ADT 可对。
2. **验证必须是「对着真 ADT」。** 9/9 自测证明的是契约逻辑（§5），不证明「SM8475 固件认这 8 个 MPIDR」。后者只有 PSCI `CPU_ON` 的返回码能回答，而那要一张真镜像。
3. **口径冲突没清。** `board.toml:210 cpus = 8` 与 `scripts/make-pong-adt.py:74 --cpus 1` 是同一件事的两面，Lead 认领配置侧。先改脚本会得到「两边都说 8 但没人跑过」，比现在的「配置说 8、生成器说 1」更难判。

## 3. 草案做了什么

- 文件：`patches/proposed/9002-adt-multicore-topology.patch`，`2 files changed, 39 insertions(+), 13 deletions(-)`（`git apply --check --verbose` 在 `feat/platform-27` 上 RC=0）。
- `audit_adt(blob, *, require_manifest=True, boot_manifest=None, expect_cpus=None)`：
  - 核数成为参数；`expect_cpus` 由调用方给（生成器给 `args.cpus`），`None` 表示「任何合法核数」；
  - 拒绝空 `/cpus`、拒绝空洞（`Pong ADT /cpus must be cpu0..cpuN-1 without gaps`）、拒绝 > 8（`exceeds the SM8475 topology (8 CPUs)`）、拒绝与 `expect_cpus` 不符；
  - 校验 MPIDR（`phys_id != index << 8` → `Pong MPIDR affinity of %s must be 0x%x, the DT generator writes Aff1 = index`）；
  - 校验 `state` ∈ {`running`,`stopped`}（未知状态直接拒，不再默默不计入）；
  - 恰一个 `running`（`Pong ADT must mark exactly one running boot CPU`），且必须是 MPIDR 0（`Pong ADT may only mark MPIDR 0 as running`）。
- 报告新增实测字段：`'cpu_count': len(cpu_paths)`、`'cpu_mpidrs': sorted(cpu_phys_ids)`、`'running_cpus': boot_cpus`，`checks` 列表加 `'CPU node count/affinity/state'`。
- `make-pong-adt.py:291` 的自审计传入 `expect_cpus=args.cpus`。

## 4. 不变量（草案守的是这四条，不是「核数」）

| # | 不变量 | 为什么 |
|---|---|---|
| 1 | `/cpus` 子节点是 `cpu0..cpuN-1`，无空洞 | 次核的 `cpu_data` 索引与 `log_id` 由名字顺序决定，缺号会让 `ml_processor_register` 的 `log_id` 与 MPIDR 表错位 |
| 2 | 每个节点 MPIDR 唯一，且等于 `index << 8` | `start.s` 的 reset vector 按 Aff1 选 `cpu_data`（`armcpu_smp_fail[1]` 就是这条不符） |
| 3 | `state` 里恰有一个 `running` | 多于一个 → 两个核抢 boot 路径；零个 → 没人跑 `initCPU(true)` |
| 4 | `running` 的必须是 MPIDR 0 | boot CPU 的 affinity 在 `psci_smp_init()` 与 `armcpu_boot_mpidr` 里都用 0 做基线 |

外加一条**判据**（写进 `SMP-STEP-DECODE.md` §6.2）：`--skip-image-verification` 产出的镜像不得用于判 SMP。

## 5. 验证账

| 项 | 结果 | 证据 |
|---|---|---|
| 补丁本身能打 | ✅ | `git apply --check --verbose` 在 `feat/platform-27` RC=0 |
| 打上后逻辑对 | ✅ 9/9 | `E:/k60-work/scratch/platform27/adt-multicore-selftest.py` → `SELFTEST OK: 9/9 cases` |
| 打的是「干净副本」而不是我的工作区 | ✅ | 两次：`…/adtmc-verify` 与 `…/adtmc-verify2`（真实脚本 `git init` 提交后 `git apply` 草案文件，再跑自测 9/9） |
| 1 / 2 / 8 核都被接受 | ✅ | `mpidrs=['0x0']` / `['0x0','0x100']` / `['0x0'..'0x700']` |
| 五种拒绝 | ✅ | 核数不符、两个 `running`、MPIDR 重复、`cpu0` 非 running、`state=offline` |
| 生成器不开 `--skip-image-verification` 也能出 2 核 | ✅ | 自测 case 9：`adt-2cpu.macho.adt (12864 bytes)` |
| 真 8 核 ADT 上固件认不认 | ❌ 未验 | 需要一张真镜像 + PSCI `CPU_ON` 返回码；这就是 §7 的落地条件 |
| 编译（`-fsyntax-only`） | ❌ 不需要 | 两个文件都是纯 Python 生成器，无 C 参与 |

## 6. 未动的第四处

`scripts/build-native-bootimg-local.py:139` 的第二次稽核**不传** `expect_cpus`（`None` → 任何合法核数都过）。
补一行 `expect_cpus=args.cpus` 就对齐，但那属于改构建驱动的归属，不在本草案范围。在它对齐之前，
「生成器说 N 核」与「构建驱动只要求合法」是两句话——`SMP-STEP-DECODE.md` §6.2 的对账脚本读的是 manifest 的 `boot_args cpus=`
与 ADT 的实测节点数，不依赖这一行。

**回滚**：草案是独立文件，`git rm patches/proposed/9002-adt-multicore-topology.patch` 即完全回滚（未进 series、未被任何脚本引用）。

## 7. 何时能进 series

满足任一条即可重开评审：

1. F1 出了镜像，`docs/research/ios27/SMP-STEP-DECODE.md` §6.2 的对账结果是 `AGREE` 且核数 = 1 —— 那么这条只是「为 8 核留门」，可以等真开 SMP 时再进；
2. 对账结果 `DISAGREE`，或 manifest 说 8、ADT 只有 1 —— 这条立刻升级为阻塞项，因为那意味着配置与产物已经分叉；
3. 有人真的要用 8 核跑一次 `CPU_ON` —— 那时它必须先于 0543（`cpu_start` 回写）落地，否则次核连 reset vector 都选不到正确的 `cpu_data`。

## 8. 复现清单

```sh
# 锁（应打出 3 条：契约 2 处 + 生成器 1 处）
grep -n "single-core ADT\|'cpu_count': 1\|audit_adt(tree" \
  scripts/pong_adt_contract.py scripts/make-pong-adt.py

# 现状：2 核产出被拒
python3 scripts/make-pong-adt.py --cpus 2 --dram-size 0x300000000 \
  --output E:/k60-work/scratch/platform27/adt2.macho.adt        # ValueError

# 草案本身
git apply --check --verbose patches/proposed/9002-adt-multicore-topology.patch

# 草案逻辑（对一个已打上草案的干净副本）
python3 E:/k60-work/scratch/platform27/adt-multicore-selftest.py \
  E:/k60-work/scratch/platform27/adtmc-verify                   # SELFTEST OK: 9/9 cases
```
