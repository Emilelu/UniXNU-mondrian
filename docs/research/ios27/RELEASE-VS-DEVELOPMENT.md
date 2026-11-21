# iOS 27 release 与 development 符号表比较：205 个 stubbed target 的可判定边界

日期：2026-11-21
范围：mondrian iOS 27.0.1 (24A446) 的 build 20 产物；release 与 development 两份未剥离 XNU；E:/k60-work/scratch/stubs 下的 205 个 stubbed stanza。
边界：只读产物与符号表；不构建、不上机、不 fastboot、不改共享仓。

## 0. 结论先行

- 205 个 stubbed item 不能按原计划干净地分成“config 差异 / 真缺符号 / name 已存在但 matcher 没配”三类。能站住的账是 **61 + 5 + 139 = 205**：
  - **61 items（25 个 target）** 的候选名在 release 与 development 两份 nm 里都存在，而且地址都不同；这是 matcher 候选/配对问题，不是 release-only 导出。
  - **5 items（1 个 target）** 只有一个泛称 “device-tree getter (DTGetProperty family)”，没有单一符号名，不能按名字判。
  - **139 items（105 个 target）** 在 target 地址上没有 exact symbol，两份 nm 都没有；这是第四类，需要函数体/形状证据，不能塞进 config 或真缺符号。§6.2 已按固定优先级把这 105 个 target 冻结成 B/R/S/C/G/Z/O 七类（1/13/7/51/8/22/3），每类写明什么证据能让它退出。
- **config 差异：0 个已证明。** 25 个具体候选名全部在 release 与 development 里存在；没有一个是 release-only。把“sheng 开了 12 个键”当作这 205 个 target 的解释，与符号表事实不符；参见 DEFCONFIG-DELTA.md。
- **真缺符号：0 个已证明。** 本次 nm 对比没有给出任何一个 target 在两份产物里都缺名字的证据。另有 3 个 missing 地址不属于这 205 个 stubbed，必须单独计。
- target 是 **输出 collection 地址**，不是 release/development 的 native 地址；collection_slide 为 0，target 又超过两份 nm 的最大地址，所以不能把 target 直接拿到 nm 里查。这是原三类拆分失败的根因，不是 205 个 target 的语义。

## 1. 输入、产物与计数口径

### 1.1 两份未剥离 XNU

| 产物 | 路径 | 大小 | sha256 | llvm-nm-18 行数 / unique names | 最大符号地址 |
|---|---|---:|---|---:|---:|
| release | /opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/build/xnu/fileset-reference/mach.release.bcm2837.unstripped.noctf | 16,296,560 B | 71d351ceaa0d032f9c554195278e58a35ee3983a9876fde39987af225e1ddc05 | 41,040 / 41,011 | 0xfffffff007b46ff0 |
| development | /opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped.noctf | 23,783,640 B | b13875dac33fa66ba4ee3cf2ec6876eb8ffdd1baa10c8e49cda32432006be91f | 67,482 / 64,930 | 0xfffffff007e5c000 |

两份 nm 都没有 t/T 类型；落在 __TEXT_EXEC 的代码符号由 llvm-nm 记为 s/S，因此 s/S 同时包含代码和数据。类型计数：

- release：a 3、s 31,860、S 6,017、b 1,799、d 1,276、D 85。
- development：a 3、s 39,482、S 23,362、b 2,214、d 1,211、D 1,210。

### 1.2 build 20 的 kernel.json

路径：/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.json。

- format = MH_FILESET；entry = com.apple.kernel；matcher_version = 8。
- collection_base = native_link_address = 0xfffffff007004000；collection_slide = 0x0。
- missing_address_space = "output collection"。
- candidate = 93,061,120 B，sha256 = dee01c54a73edf594bbe866ae020cb3331d31afe3edc4616b1a6fc0a34fbaad0。
- kernelcache = /opt/k60/trees/ios27-out/ipsw/24A446/kernelcache.decompressed；reference_sha256 = 71d351ce...；native_sha256 = b13875da...。
- missing 3 items / 3 unique；stubbed 205 items / 131 unique target；mapping_complete = false、loadable = false、allow_missing = true。

### 1.3 205 个 stanza 的来源

路径：/mnt/e/k60-work/scratch/stubs/unreachable.toml。

- 205 个 stanza（item 行）。
- 203 个 distinct (bundle, target) 对；205 行比 distinct 数多 2 行重复。
- 131 个 unique target 地址。
- 25 个 bundle。
- 引用种类：179 个 __auth_got，26 个 __const。
- 205 个 item 按 bundle 分布：15 个只-我们 bundle 121 items；10 个两边都有 bundle 84 items。两数与 DEFCONFIG-DELTA.md 的 §3.1 表一致。

配套的 facts2.json 有 131 条 target 记录，items 合计 205；其中 129 条在 __TEXT_EXEC,__text，2 条在 __TEXT_BOOT_EXEC,__bootcode。facts2 的 prev/next 是输出 image 的邻居，不是 native 邻居；这一点在第 5 节会用到。

计数口径必须分开：

- **205**：stubbed item 行数，也就是 unreachable.toml 的 stanza 数。
- **203**：去重后的 (bundle, target) 对数；prelink.log 末尾的 “stubbed functions: 203” 与它同数，但本文不把这个数字当 205 的替代。
- **131**：unique target 地址数；同一个 target 被多个 bundle 引用时只算一次。
- **3**：missing 地址数，不是 stubbed；与 205 相加得到 208 个 item。不要拿 203 或旧快照的数字去替换 205。

## 2. nm 全表：名字集合与地址集合

对完整 nm 输出按第一列名字去重后比较：

| 关系 | 名字数 | 说明 |
|---|---:|---|
| release-only | 2,926 | 只在 release 出现；development 没有同名 |
| dev-only | 26,845 | 只在 development 出现；release 没有同名 |
| both | 38,085 | 两份都有同名 |
| both，地址集合相同 | 2 | 同名且同址，极少 |
| both，地址不同 | 37,840 | 同名但重定位/布局不同 |
| both，名字多重定义或地址集合不等 | 243 | 同一名字对应多个地址，不能按单地址比较 |

这个表最重要的结论不是 2,926 或 26,845，而是 **38,085 个同名符号里有 37,840 个地址不同**。同一符号名在两份产物里几乎都换了地址；把 release 地址当 development 地址、或把 target 直接减 slide 后查 nm，都会得到错误结果。

## 3. 131 个 target 的四类（含泛称）

按“target 地址上有没有 exact symbol”判，不按“名字是否在 nm 的其他位置出现”判：

| 类别 | target 数 | items | 判定 |
|---|---:|---:|---|
| both，地址相同 | 0 | 0 | 没有 target 在两份 nm 里同址 |
| both，地址不同 | 25 | 61 | 25 个具体候选名两份都有，地址都不同 |
| release-only | 0 | 0 | 没有 target 的候选名只在 release 出现 |
| dev-only | 0 | 0 | 没有 target 的候选名只在 development 出现 |
| neither，target 地址无 exact symbol | 105 | 139 | 两份 nm 都没有该地址的符号；第四类 |
| generic，无单一符号名 | 1 | 5 | device-tree getter (DTGetProperty family) |
| **合计** | **131** | **205** | 与 unreachable.toml / kernel.json 一致 |

这张表就是“必须加总 205”的答案。若强行压成三类：

- name 已存在但 matcher 没配：61；
- config 差异：0（已证明）；
- 真缺符号：0（已证明）；
- 合计 61，不等于 205；剩余 144 必须作为第四类（5 个泛称 + 139 个未命名），不能摊进前两类。

## 4. 25 个具体命名 target

下表 25 行是第 3 节 “both，地址不同” 的 61 items。每行的候选名在 release 与 development 两份 nm 里都存在；release 与 development 的地址列是 nm 里的实际地址，不是 output target 地址。

| target (output) | items | 候选名 | release 地址 | development 地址 |
|---|---:|---|---|---|
| 0xfffffff00abe3554 | 11 | _printf | 0xfffffff00722013c | 0xfffffff0073438cc |
| 0xfffffff00ab86b04 | 7 | _mach_absolute_time | 0xfffffff007365d1c | 0xfffffff00754b108 |
| 0xfffffff00b0de1d8 | 7 | _proc_name | 0xfffffff0076a563c | 0xfffffff00788e318 |
| 0xfffffff00ac20880 | 5 | _task_reference_external | 0xfffffff00725280c | 0xfffffff007379b18 |
| 0xfffffff00b11a998 | 3 | _code_signing_configuration | 0xfffffff0076e3100 | 0xfffffff0078cd95c |
| 0xfffffff00ad3d804 | 2 | _ml_get_max_cpu_number | 0xfffffff007360ef4 | 0xfffffff007544354 |
| 0xfffffff00ad46814 | 2 | _ml_get_cpu_number | 0xfffffff007360d88 | 0xfffffff007544258 |
| 0xfffffff00abe36d4 | 2 | _vprintf | 0xfffffff00722024c | 0xfffffff0073439cc |
| 0xfffffff00b11acd8 | 2 | _restricted_execution_mode_state | 0xfffffff0076e32f8 | 0xfffffff0078cdd20 |
| 0xfffffff00b2a7f90 | 2 | IOService::Start_Invoke | 0xfffffff00785b4a8 | 0xfffffff007a80b1c |
| 0xfffffff00b2a7e74 | 2 | IOService::Stop_Invoke | 0xfffffff00785b5c4 | 0xfffffff007a80bf4 |
| 0xfffffff00ada94d8 | 2 | _vnode_authorize | 0xfffffff0073b1608 | 0xfffffff0075c31dc |
| 0xfffffff00ada1af4 | 2 | _vnode_lookup | 0xfffffff0073a9c6c | 0xfffffff0075b9688 |
| 0xfffffff00abdea40 | 1 | _lck_mtx_gate_close | 0xfffffff00721c198 | 0xfffffff00733a900 |
| 0xfffffff00abde90c | 1 | _lck_mtx_gate_try_close | 0xfffffff00721c18c | 0xfffffff00733a8a8 |
| 0xfffffff00b11a314 | 1 | _check_trust_cache_runtime_for_uuid | 0xfffffff0076e2274 | 0xfffffff0078cc774 |
| 0xfffffff00ad46948 | 1 | _ml_get_cluster_number_local | 0xfffffff007360e84 | 0xfffffff007544360 |
| 0xfffffff00ad468ec | 1 | _ml_get_cpu_number_local | 0xfffffff007360e3c | 0xfffffff0075442f0 |
| 0xfffffff00b0de068 | 1 | _proc_parent | 0xfffffff0076a53e4 | 0xfffffff00788e194 |
| 0xfffffff00abdd25c | 1 | _lck_rw_gate_destroy | 0xfffffff00721acc0 | 0xfffffff0073392b8 |
| 0xfffffff00add41bc | 1 | _vnode_setmountedon | 0xfffffff0073dac44 | 0xfffffff0075e97d8 |
| 0xfffffff00add40f8 | 1 | _vnode_clearmountedon | 0xfffffff0073dad28 | 0xfffffff0075e9844 |
| 0xfffffff00ad05978 | 1 | ___memcpy_chk | 0xfffffff00732a430 | 0xfffffff0074f90c0 |
| 0xfffffff00b416214 | 1 | _pmap_claim_reserved_ppl_page | 0xfffffff00734f0b4 | 0xfffffff007525f24 |
| 0xfffffff00b41624c | 1 | _pmap_free_reserved_ppl_page | 0xfffffff00734f0c0 | 0xfffffff007525f2c |

两个 C++ 名字的 exact nm 名字是：

    __ZN9IOService12Start_InvokeE5IORPCP15OSMetaClassBasePFiS2_PS_E
    __ZN9IOService11Stop_InvokeE5IORPCP15OSMetaClassBasePFiS2_PS_E

两行都同时存在于 release 与 development；不是 dev-only。表中写 demangled 只是为了阅读。

这张表能证明什么、不能证明什么：

- 能证明：25 个候选名都不是 release-only；不能把 61 items 归因于“release 导出、development 没有”。
- 不能证明：output target 一定就是该 native 函数。第 5 节的 pmap 例子会说明，按输出 prev + offset 反推的名字可能是错的；候选名仍要 matcher 或函数体复核。
- 因此这 61 items 的正确标签是“候选名已存在、matcher 未配对”，而不是“符号真缺”。

## 5. 为什么 target 不能直接拿到 nm 里查

### 5.1 target 是输出 collection 地址

kernel.json 明确写 missing_address_space = "output collection"，collection_base = native_link_address = 0xfffffff007004000，collection_slide = 0x0。

- target 0xfffffff00abe3554 大于 release 最大符号地址 0xfffffff007b46ff0。
- 它也大于 development 最大符号地址 0xfffffff007e5c000。
- collection_slide 是 0，target - collection_slide 仍是 target；这不是 native 地址。

因此“拿 target 减 slide，再查 release/development 的 nm”在起点就错了。

### 5.2 段级 old/new 平移不能逐 target 逆映射

kernel.json 的 segment_layout：

| 段 | old | new |
|---|---|---|
| __TEXT | 0xfffffff007004000 | 0xfffffff007184000 |
| __TEXT_EXEC | 0xfffffff0072c0000 | 0xfffffff00ab18000 |
| __DATA | 0xfffffff007c38000 | 0xfffffff00b6b0000 |
| __BOOTDATA | 0xfffffff007d8c000 | 0xfffffff00c7f0000 |

__TEXT_EXEC 的段级差是 0x3858000，但把它套到 __text 的 target 会落错位置：

- 0xfffffff00abe3554 - 0x3858000 = 0xfffffff00738b554，落在 _vfs_removename 的函数体内，不是函数起点。
- 同一 target 按输出邻居 _cons_putc_locked + 44 反推，得到 _printf；这才是能对上函数起点的解释。

输出 collection 把老 __TEXT,__text 重新排进了新 __TEXT_EXEC；段级 old/new 只能描述段边界，不能当作逐函数的地址映射。

### 5.3 prev + offset 也不可靠

facts2 的 prev/next 是输出 image 的邻居，不是 native 邻居。一个反例：

- target 0xfffffff00b416214 的函数体证据指向 _pmap_claim_reserved_ppl_page。
- 输出 prev _pmap_ce_free_acceleration_buffer + 56 却得到 _pmap_flush_noncoherent_page。
- target 0xfffffff00b41624c 同理，prev + 偏移得到 _cpu_data_startup_init。

所以不能把 prev + offset 得到的结果当 native 地址，也不能拿它给 105 个未命名 target 强行命名。

### 5.4 现有索引没有 output→native 全表

- kernel.map.json 只保存已配对目标：functions 16,899 条，另有 data 797 条；stats 里 functions_original 21,692、functions_native 29,012、functions_matched 16,899。
- stubbed target 按定义不在 functions 里；131 个 stubbed target 在 map 的 functions/data 里都没有条目，3 个 missing 地址也不在其中。
- kernel.macho 是 93,061,120 B 的输出；llvm-nm 能看到 67,546 行多 member 符号，但 131 个 target 地址里只有 2 个有 exact symbol（_sustained_pressure_handler 与 IOBigMemoryCursor::MetaClass::alloc），其余 129 个没有；这仍不是 output→native 全表。
- kernelcache.decompressed 没有可用的符号表；原 kernel 的 old.symbols() 为 0，也不能从原 kernel 直接取名。

结论：对 105 个未命名 target，nm 这一层没有可查的名字；要么用函数体/形状证据，要么补一张真正的 output→native 表。继续用名字查只会制造假的“真缺符号”。

## 6. 205 的三类拆分与必须保留的第四类

| 账目 | target | items | 依据 |
|---|---:|---:|---|
| name 已存在但 matcher 没配 | 25 | 61 | 25 个候选名在 release+dev 都有，地址都不同；见 §4 |
| config 差异 | 0 | 0 | 没有 target 的候选名是 release-only；12 个 sheng-only 键也不增删这些源文件 |
| 真缺符号 | 0 | 0 | 本次 nm 对比没有证明任何 target 在两份产物里都缺名字 |
| 第四类：泛称/无单一符号 | 1 | 5 | device-tree getter (DTGetProperty family) |
| 第四类：未命名/无 exact symbol | 105 | 139 | 两份 nm 都没有 target 地址的符号；见 §5 |
| 合计 | 131 | 205 | 与 205 个 stanza 对齐 |

如果报告只允许三类，必须明确写“61 + 0 + 0 = 61，剩余 144 个 item 是第四类，不能分配”。把 144 个摊进 config 或真缺符号，会让数字看起来凑满 205，但证据是假的。

### 6.1 三个 missing 不属于这 205

kernel.json 另有 3 个 missing 地址：

- 0xfffffff007044478（__PRELINK_TEXT 视图里的 leaf，16 个 0，不是函数起点）
- 0xfffffff00b72fce8（__DATA）
- 0xfffffff00b739538（__DATA）

它们分别由 AppleARMWatchdogTimer、IOHIDFamily、security.sandbox 引用；是保留原地址、没有重定向的引用，不是 stubbed。205 + 3 = 208 个 item；不要把 missing 混进 stubbed 的三类账。

### 6.2 第四类 105 个 target 的固定分类

第四类不再是一句「139 items 未命名」。下面按**固定优先级 B → R → S → C → G → Z → O** 分类，先命中先归，保证每个 target 只进一类、总数可复算：

| class | 含义 | targets | items | 现有最强证据 | 什么证据能让它退出第四类 |
|---|---|---:|---:|---|---|
| B | bootcode | 1 | 5 | `__TEXT_BOOT_EXEC,__bootcode`；5 个 bundle 引用；无 body 字符串/callee | 启动阶段符号表，或对 bootcode 调用点做反汇编并给出 native 符号 |
| R | 正分候选 | 13 | 13 | `match.json` 最高候选分 ≥ 1（1..4） | 带 `original_sha256` 与 `native_symbol` 的 reviewed pairing；低分候选本身不算 |
| S | 函数体字符串 | 7 | 13 | 函数体内有可读字面量 | reviewed 的 body-literal pairing（字面量 + 大小 + 起点） |
| C | 调用点字符串 | 51 | 70 | 调用点/调用者带字符串 | reviewed 的调用点哈希 + native 符号；同名不算 |
| G | 只有调用图 | 8 | 12 | 有 callees，无字符串/正分候选 | 反汇编调用序列与 native 函数逐边一致 |
| Z | 零分候选 | 22 | 23 | 有候选列表，但最高分为 0 | 同族、带符号的产物重新打分；或反汇编确认 |
| O | 无候选 | 3 | 3 | 没有候选、字符串、调用者 | 真正的 output→native 表，或逐条反汇编 |
| **合计** | | **105** | **139** | | |

这张表的 105 个地址与 139 个 item 是 `facts2.json` 去掉 25 个具体命名 target 和 1 个 DTGetProperty 泛称后的全集；没有省略、没有把 `unknown` 摊进 B/R。分类脚本只读 `facts2.json` 与 `match.json`，复算命令见 §10。

### 6.3 105 个 target 明细

下表与 §6.2 是同一份数据；`class` 列即固定归属，`bundles` 是引用该 target 的 bundle 数，最后两列只复述现有证据，不把 probable 写成 proven。

| target | size | items | bundles | class | 现有最强证据 |
|---|---:|---:|---:|---|---|
| `0xfffffff00b4320d8` | 28 | 5 | 5 | B | bootcode; no symbol table |
| `0xfffffff00ac061f4` | 80 | 1 | 1 | R | candidate score 1: _smr_leave |
| `0xfffffff00ac11bd8` | 12 | 1 | 1 | R | candidate score 1: _task_is_privileged |
| `0xfffffff00ac4c1dc` | 16 | 1 | 1 | R | candidate score 1: _get_task_pidsuspended |
| `0xfffffff00add2190` | 88 | 1 | 1 | R | candidate score 4: _vfs_vnodecovered |
| `0xfffffff00add2e78` | 80 | 1 | 1 | R | candidate score 3: _vfs_context_ignores_content_protection |
| `0xfffffff00b0a30a8` | 12 | 1 | 1 | R | candidate score 1: _csblob_get_auxiliary_info |
| `0xfffffff00b0a30e0` | 12 | 1 | 1 | R | candidate score 1: _csblob_get_auxiliary_info |
| `0xfffffff00b0a3f48` | 120 | 1 | 1 | R | candidate score 1: _csproc_get_platform_identifier |
| `0xfffffff00b0df0b0` | 288 | 1 | 1 | R | candidate score 1: _proc_getexecutablevnode |
| `0xfffffff00b119a94` | 128 | 1 | 1 | R | candidate score 1: _check_trust_cache_runtime_for_uuid |
| `0xfffffff00b11ab54` | 80 | 1 | 1 | R | candidate score 1: _enable_developer_mode |
| `0xfffffff00b11aba4` | 80 | 1 | 1 | R | candidate score 1: _enable_developer_mode |
| `0xfffffff00b11b604` | 80 | 1 | 1 | R | candidate score 1: _enable_developer_mode |
| `0xfffffff00abff7fc` | 748 | 1 | 1 | S | body string: machine_routines_common.c |
| `0xfffffff00abffae8` | 856 | 1 | 1 | S | body string: machine_routines_common.c |
| `0xfffffff00b0dea00` | 248 | 1 | 1 | S | body string: kern_proc.c |
| `0xfffffff00b250384` | 312 | 1 | 1 | S | body string: array |
| `0xfffffff00b286c90` | 344 | 1 | 1 | S | body string: set |
| `0xfffffff00b36e788` | 660 | 7 | 7 | S | body string: machine_routines_common.c |
| `0xfffffff00b36ea1c` | 304 | 1 | 1 | S | body string: machine_routines_common.c |
| `0xfffffff00ab8e798` | 100 | 1 | 1 | C | caller string: hwtrace |
| `0xfffffff00ac13a78` | 32 | 1 | 1 | C | caller string: AMFI: hook..execve() killing %s (pid %u): Attempt to |
| `0xfffffff00ac2534c` | 16 | 5 | 5 | C | caller string: IOSA |
| `0xfffffff00ac475f4` | 80 | 1 | 1 | C | caller string: raw jhash |
| `0xfffffff00ac48238` | 128 | 2 | 2 | C | caller string: OSEntitlements.cpp |
| `0xfffffff00ac9033c` | 144 | 2 | 2 | C | caller string: virtual IOReturn IOGPUVirtualMemory::wire() |
| `0xfffffff00ac991f8` | 36 | 2 | 2 | C | caller string: alloc_vm_buffer |
| `0xfffffff00ad44a38` | 16 | 1 | 1 | C | caller string: ApplePMGR:  eventID = 0x%x activeTime = 0x%llx
 |
| `0xfffffff00ad46870` | 124 | 1 | 1 | C | caller string: reg |
| `0xfffffff00ad71480` | 56 | 2 | 2 | C | caller string: EFI PART |
| `0xfffffff00ad714b8` | 116 | 3 | 3 | C | caller string: jobj.c |
| `0xfffffff00ad87160` | 120 | 1 | 1 | C | caller string: fake-mount |
| `0xfffffff00adb0fbc` | 16 | 2 | 2 | C | caller string: com.apple.private.security.disk-image-authority |
| `0xfffffff00addd814` | 192 | 1 | 1 | C | caller string: icp_new_crypto |
| `0xfffffff00ade9170` | 20 | 1 | 1 | C | caller string: apfs_vnop_lookup |
| `0xfffffff00adee60c` | 84 | 1 | 1 | C | caller string: jobj_release |
| `0xfffffff00b0a2e6c` | 148 | 2 | 2 | C | caller string: AMFI: vnode_check_signature called with platform %d
 |
| `0xfffffff00b0a30b4` | 44 | 1 | 1 | C | caller string: com.apple.cs-auxiliary-info |
| `0xfffffff00b0a3158` | 108 | 1 | 1 | C | caller string: Error getting XML
 |
| `0xfffffff00b0a31c4` | 120 | 1 | 1 | C | caller string: Error getting XML
 |
| `0xfffffff00b0a323c` | 40 | 1 | 1 | C | caller string: AMFI: vnode_check_signature called with platform %d
 |
| `0xfffffff00b0a34e0` | 164 | 2 | 2 | C | caller string: int _proc_check_map_anon(proc_t, kauth_cred_t, user_ |
| `0xfffffff00b0a3b50` | 272 | 1 | 1 | C | caller string: none |
| `0xfffffff00b0a43fc` | 12 | 1 | 1 | C | caller string: launch-type |
| `0xfffffff00b0dd71c` | 120 | 2 | 2 | C | caller string: AMFI: allowing pid %u to inherit IPC ports (platform |
| `0xfffffff00b0df1d0` | 240 | 1 | 1 | C | caller string: forbidden-sandbox-reinit |
| `0xfffffff00b0e497c` | 12 | 1 | 1 | C | caller string: com.apple.rootless.restricted-block-devices |
| `0xfffffff00b0e4f2c` | 232 | 1 | 1 | C | caller string: driver extensions must be sandboxed |
| `0xfffffff00b0fca08` | 128 | 1 | 1 | C | caller string: com.apple.private.img4.ignition-blob |
| `0xfffffff00b11a1a0` | 184 | 1 | 1 | C | caller string: AMFI: Failed to get trust cache UUID for %s (TCRetur |
| `0xfffffff00b11ac10` | 68 | 1 | 1 | C | caller string: com.apple.rootless.restricted-block-devices |
| `0xfffffff00b11ac54` | 68 | 2 | 2 | C | caller string: loadTrustCacheWithExternalManifest |
| `0xfffffff00b11ac98` | 64 | 1 | 1 | C | caller string: int _check_cdhash_in_trustcache(struct proc *, user_ |
| `0xfffffff00b11ad04` | 72 | 1 | 1 | C | caller string: AMFI: AMFIUpdateDeviceState
 |
| `0xfffffff00b11ad4c` | 100 | 1 | 1 | C | caller string: AMFI: AMFICompleteSecurityBootMode / bootMode: %u
 |
| `0xfffffff00b11adb0` | 8 | 1 | 1 | C | caller string: com.apple.private.amfi.garbage-collect-profiles |
| `0xfffffff00b11b564` | 76 | 1 | 1 | C | caller string: AMFI: disabling local signing due to allow3rdParty = |
| `0xfffffff00b11b5b0` | 84 | 1 | 1 | C | caller string: AMFIGetLocalSigningPublicKey |
| `0xfffffff00b11b6ec` | 236 | 1 | 1 | C | caller string: getOSEntitlementsFromProcSecure |
| `0xfffffff00b11bf90` | 32 | 1 | 1 | C | caller string: static IOReturn Image4UserClient::objectLoad(OSObjec |
| `0xfffffff00b11bfb0` | 24 | 1 | 1 | C | caller string: static IOReturn Image4UserClient::objectLoad(OSObjec |
| `0xfffffff00b13ce5c` | 152 | 1 | 1 | C | caller string: AMFI: providing XNU monitor with auxiliary signature |
| `0xfffffff00b2581dc` | 172 | 4 | 4 | C | caller string: IOAVController |
| `0xfffffff00b28f6d4` | 156 | 1 | 1 | C | caller string: %s:0x%llx serialize

 |
| `0xfffffff00b2ab224` | 480 | 1 | 1 | C | caller string: AppleARMFunctionSymbol |
| `0xfffffff00b2e7034` | 196 | 1 | 1 | C | caller string: reg |
| `0xfffffff00b332404` | 20 | 1 | 1 | C | caller string: allocate |
| `0xfffffff00b332418` | 56 | 2 | 2 | C | caller string: IOReturn IOGPUDevice::new_resource(IOGPUNewResourceA |
| `0xfffffff00b36aa88` | 400 | 1 | 1 | C | caller string: %s:0x%llx IOCircularDataQueueEnqueue:0x%x

 |
| `0xfffffff00b36ae4c` | 68 | 1 | 1 | C | caller string: %s:0x%llx %llu attempts to dequeue before first enqu |
| `0xfffffff00b4182c8` | 16 | 1 | 1 | C | caller string: panic: pmap and kext data length inconsistency: actu |
| `0xfffffff00abd0d50` | 80 | 2 | 2 | G | callees: 1; no other artifact |
| `0xfffffff00b092a0c` | 416 | 1 | 1 | G | callees: 2; no other artifact |
| `0xfffffff00b17aa18` | 304 | 1 | 1 | G | callees: 6; no other artifact |
| `0xfffffff00b24f4b8` | 204 | 1 | 1 | G | callees: 1; no other artifact |
| `0xfffffff00b2869dc` | 80 | 1 | 1 | G | callees: 1; no other artifact |
| `0xfffffff00b32cf8c` | 308 | 1 | 1 | G | callees: 1; no other artifact |
| `0xfffffff00b335fe0` | 104 | 2 | 2 | G | callees: 1; no other artifact |
| `0xfffffff00b369a14` | 368 | 3 | 1 | G | callees: 4; no other artifact |
| `0xfffffff00ac26044` | 84 | 1 | 1 | Z | candidates 6; top score 0 |
| `0xfffffff00ad3d814` | 16 | 1 | 1 | Z | candidates 5; top score 0 |
| `0xfffffff00ad449d0` | 72 | 1 | 1 | Z | candidates 2; top score 0 |
| `0xfffffff00ad45084` | 60 | 1 | 1 | Z | candidates 4; top score 0 |
| `0xfffffff00b11b4d8` | 12 | 1 | 1 | Z | candidates 13; top score 0 |
| `0xfffffff00b11b558` | 12 | 1 | 1 | Z | candidates 13; top score 0 |
| `0xfffffff00b11beac` | 120 | 1 | 1 | Z | candidates 3; top score 0 |
| `0xfffffff00b11bf24` | 108 | 1 | 1 | Z | candidates 2; top score 0 |
| `0xfffffff00b24f1ac` | 68 | 1 | 1 | Z | candidates 3; top score 0 |
| `0xfffffff00b24f250` | 284 | 1 | 1 | Z | candidates 4; top score 0 |
| `0xfffffff00b2502cc` | 168 | 1 | 1 | Z | candidates 2; top score 0 |
| `0xfffffff00b286bd8` | 168 | 1 | 1 | Z | candidates 2; top score 0 |
| `0xfffffff00b315dd8` | 204 | 1 | 1 | Z | candidates 1; top score 0 |
| `0xfffffff00b316084` | 84 | 1 | 1 | Z | candidates 6; top score 0 |
| `0xfffffff00b31a524` | 112 | 1 | 1 | Z | candidates 1; top score 0 |
| `0xfffffff00b31af40` | 160 | 1 | 1 | Z | candidates 1; top score 0 |
| `0xfffffff00b31afe0` | 88 | 1 | 1 | Z | candidates 4; top score 0 |
| `0xfffffff00b3360a8` | 128 | 2 | 2 | Z | candidates 5; top score 0 |
| `0xfffffff00b3361fc` | 84 | 1 | 1 | Z | candidates 6; top score 0 |
| `0xfffffff00b33eed4` | 188 | 1 | 1 | Z | candidates 1; top score 0 |
| `0xfffffff00b33ef90` | 20 | 1 | 1 | Z | candidates 5; top score 0 |
| `0xfffffff00b33efa4` | 20 | 1 | 1 | Z | candidates 5; top score 0 |
| `0xfffffff00ad3c5b8` | 352 | 1 | 1 | O | no candidate; no strings/callers |
| `0xfffffff00b351bd8` | 172 | 1 | 1 | O | no candidate; no strings/callers |
| `0xfffffff00b351d7c` | 180 | 1 | 1 | O | no candidate; no strings/callers |

这张表的作用是**冻结分母**：以后新增证据只能把某一行从第四类移到已命名/已配对，不能改变其余行的地址、item 数或分类口径。若某行被证明是错误 target，必须单独记录并重算总数，不能静默删除。

## 7. 每一类下一步需要什么证据

### 7.1 61 items：matcher 候选/阈值

这 25 个名字已经同时存在于 release 和 development，问题不在“有没有导出”，而在“为什么 matcher 没把 output target 配到它”。需要：

- 对该 target 检查 matcher 的候选生成结果：是候选列表里没有这个名字，还是候选有但分数低于阈值；
- 用函数体/调用点证据确认候选名不是相邻函数的误配（pmap 两行就是必须复核的例子）；
- 若候选名正确，修 matcher 的候选/阈值；若候选名错误，补候选生成，而不是开 config。

### 7.2 0 items：config 差异

目前没有一条能由 nm 证明。要证明 config 差异，至少需要：

- 某个 target 的候选名在 release 与 development 都不存在，且该符号由某个构建输入/源文件在一边定义、另一边不定义；
- 该定义差异能追到具体的 CONFIG_/构建脚本/源文件，而不是“sheng 开了所以我们应该开”。

DEFCONFIG-DELTA.md 已逐键检查 12 个 sheng-only 键：没有一条通过 bsd/conf 或 osfmk/conf 增删源文件；它们产生 native_owner_*、NativeUfs/SourceStorage 或表布局，不是原 kernel 的 134 个 target。因此本文不把任何 item 记到 config 差异。

### 7.3 139 items：未命名 target 的函数体证据

这 105 个 target 在两份 nm 里都没有 exact symbol，已经按 §6.2 的固定优先级分成 B/R/S/C/G/Z/O 七类，逐条地址见 §6.3。下一步不是重新分堆，而是按类取证：

- R/S/C 先用 `match.json` 的候选/字符串/调用点做复核，但只有 `original_sha256 + native_symbol` 齐全才能移出；
- G/Z 用反汇编比较调用序列、常量和段内相对位置；
- B/O 需要启动阶段符号表或真正的 output→native 表；
- 如果仍然无法命名，就保留在原 class，不要为了凑三类编一个名字，也不要改变其余行的分母。

### 7.4 5 items：DTGetProperty 泛称

device-tree getter (DTGetProperty family) 不是一个符号，而是一族调用形态；需要按调用点/属性名/decompile 结果拆分。它不能归入 25 个具体名字，也不能按 nm 名字判 config。

## 8. 被否定的解释

### 8.1 “sheng 开了 12 个键，我们关了，所以多了 205 个 stubbed”

不成立，至少不能解释这 205 个：

- 25 个具体候选名全部在 release 与 development 里存在；0 个 release-only。
- 12 个 sheng-only 键没有一条通过 bsd/conf 或 osfmk/conf 增删原 kernel 源文件；DEFCONFIG-DELTA.md 已逐键给出编译落点。
- 15 个只-我们 bundle 的 owner 仍是 com.apple.kernel，bundle 只是引用者；bundle 数量不是“子系统被关掉”的证据。

### 8.2 “15 个只-我们 bundle 说明我们没编这些子系统”

不成立。build 20 的 kernel.json 里 134 个 unique 未解析/被重定向 target 的 owner 全部是 com.apple.kernel；bundle 只是谁引用了这个 target。15 个只-我们 bundle 与 10 个两边都有 bundle 共享同一批 target，不能按 bundle 名字推断编译开关。

### 8.3 “nm 里有这个名字，所以 target 就是它”

不成立。名字存在只说明候选名在产物里；target 是 output collection 地址，不是 native 地址。pmap 的 prev+offset 反例已经说明，名字存在与 target 指向它是两件事。

## 9. 限制

- nm 只提供符号名、类型和地址；没有 dSYM、源码行、类型签名或调用图。同名多地址有 243 个，不能用单一地址集合比较。
- 原 kernel 的 old.symbols() 为 0；不能从原 kernel 直接取名；__LINKINFO,__symbolsets 只有 9 个 KPI 集合名，不含地址。
- 本文没有构建、没有上机、没有运行期验证；不能判断这 205 个 stub 在运行期是否可达，也不把“结构上可解析”当成“飞行安全”。
- 输出 collection 的布局与 native 不同；段级平移和 prev+offset 都不是可靠映射，105 个未命名 target 需要另行反汇编。
- 205 是 item 行数；203 是 distinct (bundle,target) 对数；131 是 unique target 地址数；3 是 missing。四个数字不能互换。

## 10. 复算命令

以下命令只读产物，不写仓库；输出放在 /mnt/e/k60-work/scratch 下，避免 /tmp。

    R=/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/build/xnu/fileset-reference/mach.release.bcm2837.unstripped.noctf
    D=/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped.noctf
    llvm-nm-18 -P "$R" > /mnt/e/k60-work/scratch/release.nm
    llvm-nm-18 -P "$D" > /mnt/e/k60-work/scratch/development.nm
    awk '{print $1}' /mnt/e/k60-work/scratch/release.nm | sort -u > /mnt/e/k60-work/scratch/release.names
    awk '{print $1}' /mnt/e/k60-work/scratch/development.nm | sort -u > /mnt/e/k60-work/scratch/development.names
    comm -23 /mnt/e/k60-work/scratch/release.names /mnt/e/k60-work/scratch/development.names | wc -l
    comm -13 /mnt/e/k60-work/scratch/release.names /mnt/e/k60-work/scratch/development.names | wc -l
    comm -12 /mnt/e/k60-work/scratch/release.names /mnt/e/k60-work/scratch/development.names | wc -l

本文的 25 个命名 target 与 105 个未命名 target 来自 /mnt/e/k60-work/scratch/stubs/REPORT.md 与 facts2.json；205 个 stanza 来自 /mnt/e/k60-work/scratch/stubs/unreachable.toml；计数用 Python 对 nm 的第一列与第三列做集合/地址比较，逻辑与第 2、3 节一致。

§6.2/§6.3 的固定分类可用仓库脚本复算：

```sh
python3 scripts/fourth-class-table.py \
  --facts /mnt/e/k60-work/scratch/stubs/facts2.json \
  --match /mnt/e/k60-work/scratch/stubs/match.json \
  --markdown /mnt/e/k60-work/scratch/fourth-class-table.md \
  --check
```

`--check` 必须打印 `FOURTH CLASS PASS 105 targets / 139 items, frozen per-class sums`，且七类计数为 `B=1/5 R=13/13 S=7/13 C=51/70 G=8/12 Z=22/23 O=3/3`。少一个 target、改一个 item 或调整优先级都会红，除非同时修改本节的冻结表并说明理由。

## 11. 一句话交接

205 = 61 个“候选名两份都有、matcher 没配” + 5 个泛称 + 139 个“两份 nm 都没有 exact symbol”的未命名 target；config 差异 0、真缺符号 0（本次对比能证明的范围内）。139 个 item 已冻结为 §6.2 的七类，逐条在 §6.3。下一步不是继续扫 nm 名字，而是给 61 个候选做 matcher 复核、按七类给 105 个未命名 target 做函数体/反汇编，或者补一张真正的 output→native 表。
