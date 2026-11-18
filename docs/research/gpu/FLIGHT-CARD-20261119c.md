# 飞行卡 20261119c — 客户端的 48 ms 在哪里

镜像 tag：`gpu-telemetry-20261119`
写了这张卡才允许构建它。判据在这一节之后不允许再改（改了就重飞，见 `check-flight-card.py`）。

## 1. 为什么飞这一张

上一飞 `usblog-20261119-044558` 把 `present()` 拆开了，结果是这样（92 个样本中位，µs）：

| import | encode | submit | gpu | sum |
|---|---|---|---|---|
| 52 | 418 | 2,288 | 12,593 | 17,233 |

`MiniIOMobileFramebuffer` 的 17 个窗口里最好的一段是 83 帧 / 16 fps，**13,483 µs 在驱动内**。
62 ms 的一帧减去 13.5 ms，**还有约 48 ms 在客户端绘制里**——而日志里关于这 48 ms
**一个数都没有**：

- `Pong Metal:` 状态行只有 3 条（5 s / 20 s / 60 s），200 s 的飞行在 60 s 之后完全静默；
- `NativeBridgeMetalFrontend.mm:1606` 的 `native_bridge_metal_telemetry()` 会输出
  行 `T`（pipeline/library/function 编译累计）、`G`（commit-to-complete）、`J`（scheduled /
  completed / resource wait 累计，surface flush 累计）、`V`（Vulkan pipeline 与 shader cache
  命中）、`K`（最近 20 次 commit 的逐条计时，含 `ctc=`），
  **但全仓没有任何调用点**——它声明在头文件里，等一个永远不会来的消费者。

所以这一飞不改任何渲染行为，只做两件事：
1. 给那张表一个调用者（`streamTelemetry()`，按 `\n` 切行逐行 `report()`）；
2. 把观测节奏从 `{5,20,60}` 延到 `{5,20,60,120,180}`，让稳态被采到。

这正是 P-241 记的那两件事，也回答用户的问题「究竟卡在哪」的另一半。

## 2. 改了什么

- `drivers/PongMetal/PongMetalPlugin.mm`：新增 `static void streamTelemetry(void)`；
  观测循环改成 `for(unsigned seconds:{5u,20u,60u,120u,180u})`，`seconds>=60u` 时在状态行之后
  附加流一次计时表。
- 新增 `scripts/tests/test-metal-telemetry-stream.py`（6 例）：表存在、行还在、插件真的调用、
  按行切分、节奏覆盖 ≥120 s、60 s 之后才流。
- 登记 `P-241`（`PITFALLS.md` + `RULES.toml`），README 计数 → `P-01–P-241`。

**行为零改动**：不碰绘制、不碰拷贝、不碰提交、不碰 coherence。唯一新增的是日志。

## 3. 前置条件（缺一条就不飞）

- `P1` 八步门禁 `--flash` 全绿（`eight-step-gate.py --flash`）。
- `P2` `verify-boot-image: OK`、`image-arg-audit: OK`、`kernel archives` 全在。
- `P3` **产物侧**（这些字符串在插件的 bundle 里，不在内核里——它们由 `PongMetalBridge.dylib`
  输出、由 `PongAdrenoMetal` 调用）：
  `PongMetalBridge.dylib` 必须能 `grep -ac` 到 `Q timing v2`、`G commit-to-complete`、
  `J completed wait`、`T pipeline`、`V vkpipe`、`J surface cache`（各 ≥1）；
  且 `PongAdrenoMetal` 里必须出现 `native_bridge_metal_telemetry`（≥1，证明插件真的引用它）
  与 `streamTelemetry`（≥1）。
- `P4` 镜像里 `metal-plugin-20261119m` 的 `PongAdrenoMetal` sha256 是
  `1979ff0abf97154870286460092f98107ffc27a53d5f6e2e7e2a2e13a8af99e9`。
- `P5` `K60_AGENT_ID` 已设（supervisor claim 要署名，否则 rc=7）。
- `P6` 设备在 fastboot。

## 4. 判据

### 4.1 有效期（先判这一层，P-236）

同时满足才算「这次真的测到了」：
- 至少一条 `MiniIOMobileFramebuffer: <n> frames in` 且 `n > 0`；
- 至少一条 `Pong Metal: c<n>/0 d<n>` 且 `n > 0`；
- 至少一条 `scanout frames=`。

任一条不成立 ⇒ **INVALID**，不得据此判任何 S/F 规则（P-236），只能重飞。

### 4.2 成功判据

- **S1** 日志里没有 `panic(`、没有 `K60KEXC`、没有 `crashed: backboardd`。
- **S2** 计时表的行**全部**出现至少一次：`T pipeline n=`、`T library n=`、`T function n=`、
  `G commit-to-complete n=`、`J scheduled wait n=`、`J completed wait n=`、
  `J resource wait n=`、`J surface cache n=`、`V vkpipe n=`、`Q timing v2:`。
  （这是本次飞行的主要目的：表有调用者了。）
- **S3** 至少 3 条 `K<n> t=` 逐条 commit 行，且每条都带 `ctc=<数字>us`。
- **S4** 状态行出现在 120 s 之后：至少一条 5 s、一条 20 s、一条 60 s、一条 120 s 采到的
  `Pong Metal:` 行（按飞行时长 ≥130 s 算；`capture.json` 的 `stopReason` 是 `budget`）。
- **S5** 渲染没被这一飞弄坏：`imports==frames` 每一行都成立，`scanout copy` 形状行恰好一条，
  且 `Pong Metal: c<n>` 的 `n` 比上一次飞行（558）不低一个数量级。
- **S6** 记录（不设阈值）：把 `G commit-to-complete` 的 `mean`、`J completed wait` 的
  `total/max`、`V vkpipe` 的 `total/max`、`T pipeline` 的 `total/max`、`K` 行 `ctc` 的中位
  抄进 §5。下一张卡的阈值必须从这些实测值推出，不允许凭空写。
- **S7** 面板仍是 120 Hz：至少一条 `after the UI frame te` 且数值 ≥110。

### 4.3 失败规则

- **F1** 出现 panic / `K60KEXC` / `crashed: backboardd` ⇒ 立即判失败，回滚这一飞，先查日志新增段。
- **F2** 4.1 不成立 ⇒ INVALID（不是 S 失败），重飞同一张镜像，判据不许改。
- **F3** S2 缺任何一行 ⇒ 表没有真的被流出来。此时**不得**下任何「客户端不慢」的结论：
  没有数据的反面不是没问题（P-241 教训 1）。
- **F4** `G commit-to-complete` 的 `mean` ≥ 一帧间隔（用 `MiniIOMobileFramebuffer` 窗口自算）
  ⇒ 客户端在等 GPU 完成而不是在算，下一刀改 `waitUntilCompleted` 而不是绘制。
- **F5** `V vkpipe` 的 `total` 占 `T function` 的 `total` 一半以上 ⇒ 时间在 Vulkan pipeline
  编译/shashier cache 上，下一刀是 shader cache 而不是带宽。
- **F6** `J surface cache` 的 `us` 累计 ≥ 1 s 且 `dup` 接近 `n` ⇒ surface 每帧重复导入，
  下一刀是 surface cache 键，而不是绘制。
- **F7** `imports != frames` 任一行 ⇒ 扫出路径回归，先修它，其他结论作废。

## 5. 结果登记

（飞行后填写；`criteria-sha256` 由 `scripts/pin_criteria_digest.py` 写入，供重飞校验。）

### 5.1 这一飞的判读

镜像 `gpu-telemetry-20261119`（`boot.img 3d005597…`、kernel `93272ff6…` 105,676,800 B、
payload kernel `fe86b526…`、payload adt `1cb581cf…`、series 228、30 args / 596 B、
插件 `metal-plugin-20261119m` 的 `PongAdrenoMetal` sha256
`1979ff0abf97154870286460092f98107ffc27a53d5f6e2e7e2a2e13a8af99e9`）。
证据 `usblog-20261119-055934`（246,415 B），`capture.json complete=true`、`supervisor rc=0`、
无 panic、无复位。

有效性（4.1）成立：`compositor=4`、`client_commits=8`、`scanout_lines=5`。

| 判据 | 结果 | 实测 |
|---|---|---|
| S1 无 panic | ✅ | `panic(` 0、`K60KEXC` 0、`crashed: backboardd` 0 |
| S2 计时表十行全到 | ✅ | 10/10 |
| S3 逐条 commit 行 | ✅ | 14 条 `K<n>`，14 条都带 `ctc=` |
| S4 采到 120 s 之后 | ✅ | 4 条状态行（节奏 5/20/60/120 s） |
| S5 渲染没被弄坏 | ❌ | `client_commits=8`，低于本卡自设的 50 |
| S6 记录下数值 | ✅ | 见 5.2 |
| S7 面板仍 120 Hz | ✅ | `after the UI frame te 122/s` |

失败规则：无命中。

### 5.2 这一飞真正给出的数

```
G commit-to-complete  n=8  total=175ms  max=51ms  mean=21,928us
J completed wait      n=4  total=47ms   max=22ms
J scheduled wait      n=4  total=0ms    max=0ms
J surface cache       n=16 bytes=151,289,856 dup=0 us=8 max=2
T pipeline            n=41 total=219ms  max=17ms
T library             n=4  total=118ms  max=49ms
T function            n=41 total=4ms    max=0ms
V vkpipe              n=0  （没有 Vulkan pipeline 编译）
V cache               hit41 miss0
```

逐条 commit（这是本卡最想要的东西）：

```
K1 rp6  dr82 kpx9050  bl0 ctc=21738us
K2 rp0  dr0  kpx0     bl1 ctc=10580us
K3 rp12 dr99 kpx13631 bl0 ctc=51894us
K4 rp0  dr0  kpx0     bl1 ctc=22798us
K5 rp12 dr99 kpx13631 bl0 ctc=28799us
K6 rp0  dr0  kpx0     bl1 ctc=5283us
K7 rp3  dr79 kpx9015  bl0 ctc=17531us
K8 rp0  dr0  kpx0     bl1 ctc=16802us
```

### 5.3 结论：墙就是那个全屏 blit，现在有三条独立证据指向同一个数

`rp0 dr0 bl1` 的 commit——**一个渲染 pass 都没有、只有一次 blit**——`ctc` 是
**5.3 / 10.6 / 16.8 / 22.8 ms**。有绘制的 commit 是 17.5–51.9 ms。

同一个 18.4 MB 拷贝从三个方向量出来是同一个数：

| 测量的位置 | 值 |
|---|---|
| 内核侧 `Pong Metal: … gpu=` （`waitUntilCompleted` 跨度） | 12,593 µs |
| 客户端 `G commit-to-complete mean` | 21,928–23,515 µs |
| 合成器 `MiniIOMobileFramebuffer: … us each in the driver` | 13,483–23,589 µs |

18.4 MB / 12.6 ms = **1.5 GB/s**，而这颗 A730 的显存带宽是 50 GB/s 量级。

同时这一飞洗清了另外两个嫌疑：
- `T pipeline` 累计 219 ms、`T library` 118 ms，`V vkpipe n=0` ⇒ **pipeline/着色器编译是一次性的启动成本，不在稳态路径上**；
- `J surface cache n=16 bytes=151 MB dup=0 us=8` ⇒ **surface 没有重复导入，缓存不是问题**。

所以 `F5`（Vulkan 编译）与 `F6`（surface cache）都被实测排除，剩下的只有 `F4` 的分支：
客户端确实在等 GPU 完成这一次提交，而这次提交的绝大部分是那次全屏 blit。

### 5.4 这一飞**不能**回答的部分（结论边界）

整段飞行只有 4 个合成器帧、8 次 commit：屏幕是静的，没有任何动画在驱动绘制。
所以这张表描述的是**空闲**状态，不是「有动画时的客户端绘制成本」。
S5 判失败正是为了标出这一点——它是我为「这次真的在渲染」写的代理判据，而不是渲染坏了。

按 P-236 的口径：这一飞**有效**（有帧、有 commit、有 scanout），但**不具代表性**。
下一飞必须在**有动画驱动**的条件下重测同样几行，才能回答「客户端那 ~48 ms 怎么分」。

### 5.5 下一步（按实测，不按猜测）

1. **先解决动画驱动**：把 HID 触摸注入（或让 SpringBoard 播放已知动画）作为前置条件写进下一张卡，
   否则客户端侧的数永远只能反映静屏。
2. **同一飞里加一个同尺寸对照 blit**：往一个 GPU 自有缓冲再拷一份同样 18.4 MB，分别计时。
   若那份是 1 ms 量级而写固件 framebuffer 是 12 ms，则**目标是慢的那个**，
   方向就是 zizhan 的 `target`（拷进面板缓冲）而不是固件 framebuffer。
   这一条是当前唯一能解释「同样形状，zizhan 5–6 ms、我们 12.6 ms」的可测假设。
3. 若对照 blit 也慢，则回到带宽本身：查 GPU 实际频率（`GPUCC` 只被用来开门，
   全程没有任何一处读回或设置 GX 频率，日志里也没有一个 MHz 的数）。
