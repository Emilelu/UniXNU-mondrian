# iOS 27 的 PAC 对音频接缝的影响

这份笔记只回答两件事：PAC 打开后，音频代码里哪些行为会变；sheng 的 addon-mount 补丁是不是要先有 PAC。
结论先行，证据按「谁在做什么」列在后面。它不含任何构建或上机读数，理由见最后一节。

## 结论

- 音频代码在 PAC 下没有新的硬件准入要求。它不执行 `smc`，不读写密钥寄存器，不做 `msr`/`mrs`/`tlbi`，也不把指针值写进设备寄存器；它做的是 `ml_io_map()` 之后的 volatile MMIO 读写、`dsb sy`、`delay_for_interval()`、`PE_parse_boot_argn()` 和 `printf()`。
- PAC 唯一会改写音频执行面的地方是四处 io 表和 0531 的弱符号调用点。io 表按类型拷贝，签名与验证成对；弱调用点在链接期生成 `$auth_ptr$ia` 存根，缺定义是链接错误，不是运行时认证失败。
- 五组密钥可写、PACIA/AUTIA 不陷入，是**启动前置**：任一条不成立，内核到不了 `bsd_init`，音频行根本不会出现。所以「出现音频行」只能弱地说明这两条在已经走过的路径上成立，不能反推 PAC 整条链完整。
- 这棵 27 树目前只换 `-arch arm64e`，没有编译器 ptrauth 插桩（全树 `fptrauth` 零命中），所以 PAC 现在影响的是启动期密钥与链接 ABI，而不是 C 代码里的指针签名。
- sheng 的 `zzyd-sheng-audio-addon-mount.patch` 不依赖 PAC：它只传 proc、scratch、整数、字符串和两个 `volatile int` 的地址。它真正的依赖是 `native_gpu_addon_mount()` 与 addon2/addon3 链。

## 一、PAC 在这棵树上是怎么开的

`UniXNU/profiles/arch/arm64e/patches/xnu/series` 列出 `UniXNU/patches/xnu-12377/native-pac-keys.patch`，那份补丁做三件事：

1. `pexpert/pexpert/arm64/BCM2837.h` 在 `__arm64e__` 下定义 `HAS_APPLE_PAC` 与 `HAS_NATIVE_PAC`，把架构密钥寄存器接进公开 XNU 的 PAC 路径。
2. `osfmk/arm64/pac_asm.h` 的 `PAC_INIT_KEY_STATE` 增加原生分支：第一个进到这里的 CPU 用 `CNTPCT_EL0` 经 splitmix64 派生十个数写进 `native_pac_keys`，之后每核（含热复位）从那块内存读回，再用 `msr` 写 APIA/APIB/APDA/APDB/APGA 的 Lo/Hi 并 `isb sy`。这段在 MMU 关闭时执行，所以写出去的值确实落到内存。
3. `osfmk/arm64/start.s` 在 `__DATA` 里保留 `native_pac_keys` 与就绪字；`osfmk/arm64/machine_routines_asm.s` 里 `ml_enable_user_jop_key`/`ml_disable_user_jop_key` 在 `HAS_NATIVE_PAC` 下直接返回 0 或 `ret`——注释写得很直白：内核与每个进程共用一组密钥，没有可切换的东西。

三条对音频有用的推论：

- 密钥每个启动一组、所有核共用。任何「在 A 核签名、在 B 核验证」的指针都成立——音频 io 表正是这种形状：启动时填一次，之后哪个核跑 I2C 都读它。
- 密钥在 C 代码之前就绪；`pong_audio_amp_start()` 填表时，排在它前面的只有启动期本身。
- EL0 与 EL1 共用同一组密钥，所以用户态把指针交给内核不会因密钥不同而验证失败；反过来，共用密钥也意味着 PAC 在这里提供的是完整性，不是隔离边界。

## 二、音频代码的 EL1 特权面

| 位置 | 做的事 | PAC 是否参与 |
| --- | --- | --- |
| `drivers/PongAudio/PongAudioAmp.c:81-82` | `extern ml_io_map()` / `ml_io_map_wcomb()` | 否：映射返回普通内核指针 |
| `PongAudioAmp.c:136`、`:265-268`、`:479` | `ml_io_map()` 打开 pad/GCC/SE15 窗口 | 否 |
| `PongAudioAmp.c:98`、`:104` | `*(volatile uint32_t *)address` 读/写 | 否：普通 load/store |
| `PongAudioAmp.c:105` | `dsb sy` | 否 |
| `PongAudioAmp.c:111` | `delay_for_interval(us, NSEC_PER_USEC)` | 否 |
| `PongAudioAmp.c:951` | `PE_parse_boot_argn("pong_audio_probe", …)` | 否 |
| `PongAudioGeniI2c.c:11-12` | `g->io.read(…)` / `g->io.write(…)` | 是：间接调用，见 §三.2 |
| `PongAudioGeniI2c.c:17-18` | 逐字节清零后 `g->io = *io` | 类型化赋值，签名随类型走 |
| `PongAudioGeniI2c.c:25` | `wrp(g, PONG_GENI_DMA_MODE, 0)` | 显式关掉 Geni DMA |

两个源文件里 `smc`/`msr`/`mrs`/`tlbi` 的命中数为 0，也没有出现「把指针当数据写进寄存器」的写法。

## 三、逐类影响

### 1. MMIO、屏障与延时

认证指令只出现在编译器插入的位置：函数返回、间接调用、以及带 `__ptrauth` 的取地址。一次 volatile 读写、一条 `dsb`、一次 `delay_for_interval` 里没有指针被签名或验证，PAC 开关不改变它们的行为。

唯一会把 MMIO 弄复杂的情形是「把指针值当数据写进设备寄存器，之后硬件按 DMA 读它」：签名位会跟着地址一起进硬件，硬件拿到的不是原地址。这里没有这种写法——Geni 的 DMA 模式被 `PongAudioGeniI2c.c:25` 显式清零，音频 I2C/AMP 的寄存器窗口只按偏移访问；PCM 缓冲走的是另一条租约/SCM 路径，不经过这两个源文件。

### 2. io 函数指针表

四处同形结构：`PongAudioGeniI2c.h:67-70` 的 `PongGeniIo`（`:80` 内嵌进 `PongGeniI2c`）、`PongCodecLpi.c:16-17`、`PongCodecMacro.c:40-45` 的 `va`/`tx` 两组、`PongCodecSwr.c:15`。调用点集中在 `PongAudioGeniI2c.c:11-12`、`PongCodecLpi.c:47`/`:50`、`PongCodecMacro.c:73-76`、`PongCodecSwr.c:21`。

三种情况：

- **没有插桩（现在这棵树）**：`g->io.read` 编成 `BLR`，与 arm64 相同，PAC 不参与。
- **全树 `-fptrauth-calls`**：表里存签名指针，索引里带类型判别。生产者与消费者是同一个声明、同一个类型时，`g->io = *io` 按目标地址重新签名，调用点按同一判别验证。这张表满足条件：它是 typedef，不经 `void *` 中转，也不用 `memcpy` 落进异型存储。
- **混合 TU**：一个 TU 开插桩、另一个不开，签名与验证的判别不一致，间接调用会认证失败。这是打开插桩时最常见的坑。

### 3. 0531 的弱符号调用

`bsd_init` 对 `pong_audio_amp_probe` 的弱引用在 arm64e 下要先把函数地址取进寄存器再判空，链接器因此生成 `l_pong_audio_amp_probe$auth_ptr$ia$…` 存根。它给出的约束是**定义必须存在**（否则 `Undefined symbols`），而不是运行期认证失败：存根用 IA 密钥签名，调用点用同一判别验证，两者成对生成。所以 0531 的顺序仍然是「先让 `PongAudioAmp.o` 强制加载，再列 0531」，与 PAC 无关。

### 4. 跨核与跨 EL

见 §一的两条推论：一组密钥、EL0/EL1 共用。io 表跨核读、以及任何用户态→内核的指针传递，都不会因为密钥不同而认证失败；代价是 PAC 在这里不能当作隔离边界——密钥对本机所有代码都是一样的。

## 四、sheng 的 addon-mount 补丁

`UniXNU/patches/xnu-12377/zzyd-sheng-audio-addon-mount.patch` 在 addon3 之后插一段：定义 `audio_source[] = "/private/var/ngpu/audio"`、`audio_point[] = "/System/Library/Audio/Plug-Ins/HAL"`，然后调用

```
native_gpu_addon_mount(p, scratch, 0xa00, audio_source, sizeof(audio_source),
    audio_point, sizeof(audio_point), ".../BuiltinAudioPlugin.driver",
    ".../ShengAudio.driver/Info.plist",
    &native_gpu_addon4_stage, &native_gpu_addon4_status);
```

传参形态：`proc_t`、栈上的 scratch、整数、两个字符串字面量、两个 `volatile int` 全局的地址。没有函数指针、没有 `__ptrauth`、没有指针↔整数往返、没有 JOP 密钥切换（那条路径在 `HAS_NATIVE_PAC` 下本来就是空操作）。

⇒ **它不依赖 PAC 前置**。它真正的依赖是 `native_gpu_addon_mount()` 和 addon2/addon3 链；27 树里 `native_gpu_addon` 零命中，那是补丁顺序问题，不是 PAC 问题。

## 五、如果以后打开 ptrauth 插桩

三条约束，评审时看 diff 就能判断：

1. 表的类型只有一处定义，生产者和消费者包含同一个头；不要 `void *` 中转。
2. 不要用 `memcpy` 或逐字节拷贝把签名指针搬进另一个类型的存储。`PongAudioGeniI2c.c:17-18` 是安全形状：清零发生在写之前，`g->io = *io` 是类型化赋值。
3. `-fptrauth-calls` 必须全树一致（内核、kext、以及任何链接进内核的 `.o`），否则判别不匹配。

## 六、复现（只读）

```sh
grep -rn fptrauth <xnu-27-tree> | wc -l                     # 0：没有插桩旗标
sed -n 373p <xnu-27-tree>/makedefs/MakeInc.def               # arm64e 只换 -arch
grep -c 'smc\|msr\|mrs\|tlbi' drivers/PongAudio/PongAudioAmp.c drivers/PongAudio/PongAudioGeniI2c.c
sed -n 40,110p UniXNU/patches/xnu-12377/native-pac-keys.patch       # 十词密钥与五组 msr
```

## 七、这两句现在由代码保证

§三.2 与 §三.3 不再只是读代码得出的判断：音频线自己的预检里多了两条断言，量的是同一批文件。

- `python3 scripts/check-audio27-fptrs.py --repo .` 把四处 io 表按类型签名解析回来：每一对 `read`/`write` 的参数与返回值成对（`write` 多一个 `value`）、首参是 `void *`、每对有自己的 `ctx` 字段，并且每张表除成对的 read/write 与各自的 ctx 外没有别的成员（多一个回调、多一个 `void *` 或其他字段都会点名失败）、每个成员至少被调用一次、调用点的首参就是「接收者 + 该对的 ctx」；多出来的函数指针表与裸 `void *` 跨层传递也都失败。读数 `FPTRS OK: 4 tables, 10 callbacks in 5 pairs, 12 calls pass their own context, no other table under drivers/PongAudio, and the weak call is int (void) on both sides`，反例由 `python3 scripts/tests/test-audio27-fptrs.py` 的十九个用例逐个打红；其中一个真的把 `void *opaque` 加进表并在 `PongAudioGeniI2c.c` 里跨层赋值，门禁按字段名打红。
- `python3 scripts/check-audio27-weak-link.py --tree <k60-gates>` 读**有效**系列判断 0531 是否被选中：只在未选中时打印 `NOTE audio: switch off, the call site is not linked`；选中时要求链接清单里有 `PongAudioAmp.o`、符号表里真有定义，源码里的 `__attribute__((weak))` 与理由只算 policy note，不放行。今天 gates 的系列是 HOLD，读数就是那行 NOTE；换成音频仓自己那份列出 0531 的系列则退 1，并点名 `0531 is unconditional (#if 1)` 与缺哪份链接证据。选中却没人定义时，它还打印 `an undefined weak reference is a link error ... not a silent run-time fallback`：这是链接错误，不是运行时静默。

两条只挂在 `scripts/check-audio27-preflight.sh` 里（`PAC IO signatures`、`PAC IO negative cases`、`PAC weak-link cases`、`PAC weak-link selection` 四行），不进全局 blockers：stage 0 按设计没有音频 lane 对象，把它们挂到全局，一次本不该带音频的构建就会看起来像回归。只想跑这四行时用 `sh scripts/check-audio27-preflight.sh --pac-only`。

## 八、这篇不证明什么

- 没有实机证据：没有验证 EL1 真能写五组密钥、PACIA/AUTIA 真不陷入、SoC 的 FEAT_PAuth 真打开。这些只能在有串口的上机上区分；失败时内核到不了 `bsd_init`，音频行不会给出额外信息。
- `native-pac-keys.patch` 只是被 profile 引用。它有没有应用到某次构建、那次构建有没有过，本文不判。
- 音频源没有插桩，所以「插桩后仍然成立」是从类型形状推的，不是编出来的读数；真要确认，得等一条打开 `-fptrauth-calls` 的构建，那时本文 §五 的三条就是判据。
- P-282 是同一类推理错误：产物里读不到某个标签，可能只是本地工具链发不出这个值。不要把「我们的产物看着没问题」当成消费方判错的证据；这里每一次「没有 `fptrauth`」也要先确认 clang 能表达那个旗标，再谈产物。
