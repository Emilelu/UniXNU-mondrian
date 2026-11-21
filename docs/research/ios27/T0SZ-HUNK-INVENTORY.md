# T0SZ 只读清单：已有 hunk + 待验点

> 这份文档是**清单**，不是实施计划。T0SZ 整组按 Lead 2026-11-21 的裁决（m00836）暂不进
> `patches/xnu-12377/series`；本文只记录「sheng 的补丁里已经有哪些 hunk、各自解决什么、
> 在 27 图上靠什么判据才叫验过」，以及这批 hunk 里哪些根本不属于 T0SZ。
>
> 证据基线：`E:/hackios/xnu-12377` @ `ac9718f`（xnu-12377.121.6），补丁
> `E:/hackios/UniXNU-sheng/patches/xnu-12377/zzzz-sheng-ipados27-bringup.patch`（1974 行）。
> 下方「27 上的判据」一列里，`粗` 表示判据只能粗到「启动即死/不即死」，`无观察点` 表示今天
> 没有任何日志或门禁能看见它——这两种都要单独说清，不能算验过。

## 1. 分组：13 个几何 hunk，6 个搭车 hunk

`sheng` 的补丁把 T0SZ 改动和三类无关改动混在同一批文件里，逐 hunk 过一遍才能分开。分组按
「删掉它 T0SZ 还成不成立」定，不按文件。

### 1.1 T0SZ 几何组（13 个 hunk）

| # | 文件:旧侧行 | hunk 头 | 补丁行 | 它解决什么 |
|---|---|---|---|---|
| 1 | `osfmk/arm64/proc_reg.h:1103` | `@@ -1103,6 +1103,17 @@` | 1199 | 定义 `T0SZ_USER`：`#if defined(BCM2837) && !defined(__ARM_16K_PG__) && defined(__arm64e__)` → `17ULL`，否则等于 `T0SZ_BOOT` |
| 2 | `osfmk/arm64/proc_reg.h:1182` | `@@ -1182,6 +1193,17 @@` | 1217 | `TCR_EPD0_DISABLE (1ULL<<7)` 与 `TCR_EL1_KVA_ENTRY`：进内核地址后 TTBR0 尺寸已定稿、walk 关着 |
| 3 | `osfmk/arm/pmap/pmap_pt_geometry.h:168` | `@@ -168,8 +168,14 @@` | 1071 | `native_user_pt_attr` + 按 `pmap->type` 选属性表的 `pmap_get_pt_attr()` |
| 4 | `osfmk/arm/pmap/pmap.c:335` | `@@ -335,6 +335,50 @@` | 838 | `pmap_pt_attr_4k_user`（`pta_root_level = (T0SZ_USER-16)/9` = 0，即 L0 根、47 位）+ `_Static_assert` 根表放得下 + `pmap_user_tcr()` + `pmap_apply_user_tcr()` |
| 5 | `osfmk/arm/pmap/pmap.c:2277` | `@@ -2277,6 +2321,8 @@` | 889 | `pmap_bootstrap()` 里先写 `kernel_pmap->type = PMAP_TYPE_KERNEL`，再做按类型选属性表 |
| 6 | `osfmk/arm/pmap/pmap.c:7962` | `@@ -7962,6 +8014,12 @@` | 929 | `pmap_switch_user_ttb()`：TCR 不是用户形态时先把 TTBR0 指向非法表，再 `pmap_apply_user_tcr()` |
| 7 | `osfmk/arm/pmap/pmap.c:7972` | `@@ -7972,6 +8030,9 @@` | 942 | `pmap_clear_user_ttb_internal()` 清 TTBR0 后同样应用用户 TCR（walk 关回去） |
| 8 | `osfmk/arm/pmap/pmap.c:12965` | `@@ -12965,7 +13034,7 @@` | 967 | `pmap_user_va_bits()` 的 `#else` 分支由 `64 - T0SZ_BOOT` 改 `64 - T0SZ_USER` |
| 9 | `osfmk/arm/arm_init.c:357` | `@@ -357,6 +357,12 @@ arm_init(` | 775 | **C 载体**：`set_tcr(TCR_EL1_KVA_ENTRY); flush_core_tlb();`，位置在 `arm_slide_rebase_and_sign_image()` 之前 |
| 10 | `osfmk/arm64/start.s:879` | `@@ -879,6 +879,15 @@ arm_init_tramp:` | 1289 | **汇编载体**：`MOV64 x1, TCR_EL1_KVA_ENTRY; MSR_TCR_EL1_X1; isb; tlbi vmalle1; dsb ish; isb` |
| 11 | `osfmk/arm64/arm_vm_init.c:2182` | `@@ -2182,6 +2182,9 @@` | 1090 | `set_mmu_ttb(invalid_ttep & TTBR_BADDR_MASK)` 之后、`flush_mmu_tlb()` 之前应用用户 TCR |
| 12 | `osfmk/arm64/sleh.c:1663` | `@@ -1663,7 +1663,7 @@` | 1252 | PAC 故障归类用 `64 - T0SZ_USER` 而不是 `64 - T0SZ_BOOT`（非规范位才是 poison 位） |
| 13 | `osfmk/mach/arm/vm_param.h:293` | `@@ -293,7 +293,7 @@` | 1563 | `VM_USER_STRIP_MASK` 由 `-1ULL >> T0SZ_BOOT` 改 `>> T0SZ_USER` |

### 1.2 搭车组（6 个 hunk，不属于 T0SZ）

| # | 文件:旧侧行 | 补丁行 | 它是什么 | 处置 |
|---|---|---|---|---|
| a | `osfmk/arm64/proc_reg.h:1807` | 1235 | `CACHE_ATTRINDX_RT` 在 BCM2837 上取 `CACHE_ATTRINDX_WRITECOMB`（实时内存按 Normal 非缓存映射，免得用户态非对齐/矢量访问在 Device 映射上取对齐异常） | 与 T0SZ 无关，单独决定 |
| b | `osfmk/arm/pmap/pmap.c:2314` | 898 | `#if HAS_16BIT_ASID` 下加 `ID_AA64MMFR0_EL1` 位域检查，不匹配就 panic | **在 K60 上是死代码**：`HAS_16BIT_ASID` 只在 `pexpert/pexpert/arm64/H16.h:55`、`H17.h:52` 定义，`BCM2837.h` 没有 |
| c | `osfmk/arm/pmap/pmap.c:6000` | 909 | `wimg_to_pte()` 的 `VM_WIMG_POSTED` 分支：`is_dram_addr(pa)` 放宽成 `is_dram_addr(pa) \|\| pa_valid(pa)` | SoC 物理内存窗口形状，不是 T0SZ |
| d | `osfmk/arm/pmap/pmap.c:6040` | 919 | 同上，`VM_WIMG_WTHRU` 分支 | 同上 |
| e | `osfmk/arm/pmap/pmap.c:10949` | 952 | `pmap_batch_set_cache_attributes_internal()`：属性变更时 `pmap_sync_wimg()` 清脏行 | 缓存一致性，不是 T0SZ |
| f | `osfmk/arm/pmap/pmap.c:15301` | 976 | `native_pmap_user_mappings()`（GPU 线） | 已单独草案：`patches/proposed/9001-…patch` + `PMAP-USER-MAPPINGS-PROPOSAL.md` |
| g | `osfmk/arm64/sleh.c:3002` / `:3013` | 1261 / 1277 | sheng 的 1024 槽采样环 `sheng_prof_ring`，以及把 `sheng_prof_sample()` 调用注释掉 | 不搬；它自带注释「per-interrupt sampling off … the Edge matrix stalled」 |

`osfmk/arm/cpu_common.c`（3 个 hunk）与 `osfmk/arm64/cpu.c`（6 个 hunk）属 SIGP，已按 0542 落地，
不在本文范围。

## 2. 两个载体（C 版与汇编版）：都要，不是二选一

Lead 的问题是对的：`arm_init.c:357` 与 `start.s:879` 是**同一修改的两种载体**，都写
`TCR_EL1_KVA_ENTRY`。判断依据是「谁在哪条路径上执行」，不是「哪份更完整」。

执行路径（`xnu-12377` 原文）：

| 路径 | 汇编 | C |
|---|---|---|
| 冷启动 | `common_start:`（`start.s:645`）无条件写 `TCR_EL1_BOOT`（`:654-655`）→ 末尾 `ret`，返回地址是 `arm_init`（`:520-521` `adrp lr, EXT(arm_init)@page`） | `arm_init()` 跑到 `arm_init.c:357`，C 载体写入并 `flush_core_tlb()` |
| 热复位 | 同一 `common_start` 先写 `TCR_EL1_BOOT`，随后 `cbnz x21, Ltrampoline`（`start.s:800`）→ `Ltrampoline:`（`:821-826` `br x0`）→ `arm_init_tramp:`（`:835`）→ 汇编载体在 `:879` 写入并在原地 `tlbi vmalle1` → `ret`（`:874`）回 `arm_init` | 回来后**仍然**进 `arm_init()`，C 载体再写一次、再 `flush_core_tlb()` 一次 |

结论：**两个都要。** 冷启动只有 C 版会执行；热复位时汇编版先执行、C 版随后再执行。少任何一个，
那条路径上 TTBR0 就停在 `TCR_EL1_BOOT` 的尺寸上。

**两次 TLB 失效的代价与顺序。** 热复位路径上确实有两次本核失效（汇编 `tlbi vmalle1` + C
`flush_core_tlb()`），但：

- 两次写的是同一个值（`TCR_EL1_KVA_ENTRY` 由宏算出，无运行时输入），第二次是幂等的重复，不是
  「改了再改」；
- 两次都在任何用户态代码之前，且 C 版就在 `arm_slide_rebase_and_sign_image()` 前一行——**第一枚
  被签名的指针一定签在最终尺寸的 TCR 下**，这正是要保的顺序；
- 失效是本核的（`tlbi vmalle1`，不带 IS），代价是一次本地 TLB 清空，发生在 boot CPU 早期的
  热复位路径上，不涉及其它核。

所以「重复」是设计上的冗余，不是缺陷；要盯的是**顺序**（汇编在前、C 版在签名前），以及
`#if T0SZ_USER != T0SZ_BOOT` 这条门——宽度相同时两段都不编译，K60 以外不留死代码。

**次级核（SMP 后）。** `common_start` 给次级核写的也是 `TCR_EL1_BOOT`；次级核不跑 `arm_init()`，
本文的两个载体都覆盖不到它。它第一次进用户态时靠 `pmap_switch_user_ttb()`
（`pmap.c:7962` 那个 hunk）应用用户 TCR——这是计数表之外的一条**待验点**：cpus=8 落地时，
必须确认次级核在第一次用户映射 walk 之前确实走过 `pmap_switch_user_ttb()`（`pmap.c:7943`
已有 `set_tcr(pmap_get_pt_attr(pmap)->pta_tcr_value)` 的混合页分支先例）。

## 3. 每个 hunk 在 27 图上怎么验

判据分四类：`编译期`（构建日志就能判）、`启动即死`（错了活不过 bsd_init，粗但真实）、`门禁`
（`git apply --check` 这类，只证「打得进去」）、`无观察点`（今天没有任何日志/门禁能看见它）。

| # | 判据类 | 具体怎么判 |
|---|---|---|
| 1 | 编译期 | `BCM2837.h` 三条同时成立：`:11 #define BCM2837`、`:30 #if defined(__arm64e__)`（triple 带 arm64e）、无 `__ARM_16K_PG__`（文件全文 42 行，`:8-40` 没有 16K 宏）。三者任一不成立 → `T0SZ_USER == T0SZ_BOOT`，**整组 13 个 hunk 全部编译成空**，构建日志里 `pmap_apply_user_tcr` 会从对象里消失。这是最容易假装「已搬」的情况 |
| 2 | 编译期 + 启动即死 | 编译只证宏存在；运行时 TTBR0 walk 关着，若 `TCR_EPD0_DISABLE` 写错位置，第一次用户映射 walk 就 fault，活不过 bsd_init |
| 3 | 编译期 | `ARM_PARAMETERIZED_PMAP` 只在 `pexpert/pexpert/arm64/H13.h:74`、`H14.h:90`、`H15.h:96` 定义，`BCM2837.h` 没有 → 本 hunk 落在**生效**的 `#else` 分支（`pmap_pt_geometry.h:170` 那侧）。若哪天有人给 BCM2837 定义它，本 hunk 静默失效 |
| 4 | 编译期（硬） | `_Static_assert((ARM_PTE_REGION_MASK(T0SZ_USER) >> ARM_4K_TT_L0_SHIFT) + 1 == PMAP_ROOT_ALLOC_SIZE / sizeof(tt_entry_t), "the user L0 root must fit the root allocation size")`。宽度不是 47 位就直接编不过——这是整组里唯一自带硬断言的 hunk |
| 5 | 启动即死 | 漏掉它，`pmap_bootstrap()` 之后 kernel_pmap 会拿到 `native_user_pt_attr`（4K/47 位），内核映射立刻错 |
| 6 | 启动即死 | 用户态第一次上下文切换就会 walk TTBR0；顺序错了就是 PAC 故障或立即 panic |
| 7 | 粗 | 只有「进程退出/换 TTBR0」路径才走到，stage-0 单核、无 fork 压力时可能根本不被执行 → 今天判不了 |
| 8 | **无观察点** | 消费方只有 `bsd/kern/kern_core.c:292` 与 `osfmk/kdp/user_core.c:257`（core 文件的 `addressing_bits`）以及 `pmap.c:12959-12962` 的 `pmap_user_va_size()`。**没有启动日志打印它**。要让它可观测，得在 F1 镜像上产出一次 core（不可行）或在阶段里加一行 `kprintf`——后者属改动，不在本清单范围。今天这条只能靠 #4 的断言间接兜住 |
| 9 | 门禁 + 启动即死 | `git apply --check` 1/1 通过（对 pristine）；真正生效看冷启动是否过 bsd_init |
| 10 | 门禁 + 启动即死 | 1/1 通过；只有热复位能触发，**stage-0 没有睡眠路径，今天不执行**（`platform-sleep` 未进 kernel_args，见 `FORK-DECISION.md` §5） |
| 11 | 门禁（有前提） | 对 pristine `xnu-12377` **打不进**（0/1），对 27 构建树 `.cache/xnu-work` 打进（1/1）。必须对构建树生成，别对 pristine 生成 |
| 12 | 启动即死 | 只在 arm64e 用户体发生 PAC 故障时才走到；走错分支的表现是「把合法故障当 poison 吞掉」或反之 |
| 13 | 编译期 | `VM_USER_STRIP_MASK` 参与 `_VM_KERNEL_STRIP_PTR` 的常量折叠，宽度不一致时用户指针剥离错位；无独立日志 |

**门禁读数（2026-11-21，逐文件 `git apply --check`）**：`proc_reg.h` 3/3、`pmap_pt_geometry.h` 1/1、
`pmap.c` 9/10（第 10 个是 #f 的 GPU 导出，单独草案）、`arm_init.c` 1/1、`start.s` 1/1、
`sleh.c` 2/3（失败的那条是搭车组 g 的注释 hunk）、`arm_vm_init.c` 0/1（pristine）/ 1/1（构建树）。

## 4. 结论：能不能原样搬

| 文件 | 判读 |
|---|---|
| `proc_reg.h` | 可原样搬（3/3），但**先证 `T0SZ_USER == 17` 的门真的成立**；否则搬进来等于没搬 |
| `pmap_pt_geometry.h` | 可原样搬（1/1） |
| `pmap.c` | **不能整包**。9/10 里 4 个是几何（#4/#5/#6/#8），3 个是搭车（b/c/d/e），第 10 个属 GPU 线。搬的时候按组切，且 b 在 K60 上是死代码、c/d/e 不是本线的事 |
| `arm_init.c` | 可原样搬（1/1） |
| `start.s` | 可原样搬（1/1），**必须与 `arm_init.c` 同批**（§2） |
| `arm_vm_init.c` | 内容可搬，**但要对构建树生成**（对 pristine 打不进） |
| `sleh.c` | 只搬 #12（1/3），另两条是 sheng 采样，不搬 |
| `vm_param.h` | 可原样搬（1/1） |

## 5. 待验点（今天判不了，需要什么才能判）

1. **`CONFIG_SPTM` 是否关着。** 若开，`osfmk/arm/pmap/pmap.c` 不是活的 pmap（活的是
   `osfmk/arm64/sptm/pmap/`），sheng 也没改那一份，整组 13 个 hunk 全部白搭。今天的证据：
   `config/MASTER:322` 只是把 `CONFIG_SPTM` 声明成可选 option，`config/MASTER.arm64.iPhoneOS`
   里只有 `MASTER_CONFIG_ENABLE_SPTM` 的条件分支，`configs/mondrian_ios27_defconfig`（26 行）没有
   任何 SPTM 键 → 倾向「关」。**settle 它需要 F1 构建日志里 `osfmk/arm/pmap/pmap.c` 的编译行**
   （或对象目录里没有 `osfmk/arm64/sptm/pmap/*.o`）。在这条落定之前，本组一律记 `unknown`。
2. **次级核的用户 TCR 路径**（§2 末）：需要 cpus=8 的镜像 + 一次多线程用户态负载。
3. **#8 的可观测性**：需要一个不属本线改动的观察点，否则永远只能靠 #4 的静态断言兜。
4. **`__ARM64_PMAP_SUBPAGE_L1__ 1`（`BCM2837.h:19`）与 `pmap_table_level_info_4k` 的交互**：
   本组新增的 `pmap_pt_attr_4k_user` 直接引用 `pmap_table_level_info_4k`，没有验证该 subpage
   配置下 4K 层的表结构是否与 47 位根相容。判据：F1 编译通过 + 启动不立即 fault（粗）。

### 5.1 库内旁证（共享 RAG 库，2026-11-22 查）

Lead 广播的三档纪律（库 → 联网 → 未证）在本组上的实况：

- 库根 `E:\k60-work\kb\kb.sqlite` 可达（`kb_stats` 报 6,194 文档 / 142,260 块 / 142,260 向量，与广播一致）。
- 查「T0SZ_USER arm64e 47 位用户地址空间 PAC」→ Top-1 命中 `arm64e.md §指针认证`：讲的是
  arm64e 镜像的认证指针是链式修复、dyld 在加载时为用户指针签名、PAC 算法不必与 Apple 相同（它证实了
  「用户态指针确实带 PAC 位」这一前提，**没有**给出 T0SZ 的值）；Top-2/3 是 `PITFALLS.md §P-01` 的
  4 GiB pagezero，与本题无关。
- 结论：**库内没有 T0SZ_USER = 17 直接证据**。本文所有 T0SZ 结论的出处仍是源码
  （`proc_reg.h` 的宏、`pmap.c` 的断言、`BCM2837.h` 的板级宏），按三档纪律属「源码证据」，不冒充库证；
  库只提供 PAC 前提的旁证。

## 6. 复现
```sh
# 逐文件试打（pristine）
cd /e/hackios/xnu-12377
for f in osfmk/arm64/proc_reg.h osfmk/arm/pmap/pmap_pt_geometry.h osfmk/arm/pmap/pmap.c \
         osfmk/arm/arm_init.c osfmk/arm64/start.s osfmk/arm64/arm_vm_init.c \
         osfmk/arm64/sleh.c osfmk/mach/arm/vm_param.h; do
  git apply --check --include="$f" \
    /e/hackios/UniXNU-sheng/patches/xnu-12377/zzzz-sheng-ipados27-bringup.patch \
    && echo "OK   $f" || echo "FAIL $f"
done

# 当前 27 构建树里的板级宏（决定第 1 组是否生效）
T=/e/hackios/UniXNU/out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/.cache/xnu-work
grep -n "BCM2837$\|__arm64e__\|ARM_16K_PG__\|PARAMETERIZED\|HAS_16BIT_ASID" \
  $T/pexpert/pexpert/arm64/BCM2837.h
```
