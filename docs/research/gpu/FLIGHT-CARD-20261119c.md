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
- `P3` 内核里能 `strings` 到 `completed wait n=%llu`、`commit-to-complete n=%llu`、
  `vkpipe n=%llu`、`Q timing v2:`（证表明明进了镜像，不是插件没编进）。
- `P4` 插件二进制里能 `strings` 到 `streamTelemetry` 无关（静态函数无符号），所以改查
  `native_bridge_metal_telemetry` 的字符串行 `Q timing v2: per-buffer API counts`。
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
