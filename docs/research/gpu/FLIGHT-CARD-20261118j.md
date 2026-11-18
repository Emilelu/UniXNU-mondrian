# 上机卡 · `gpu-import-scope-20261118`：每帧导入 + 计时算术修正 + 完整上报行

## 1. 目的

上一飞（`gpu-stages-20261118`，证据 `usblog-20261118-135714`）把整帧成本定位到
`presenter->present()`：锁页 `prepare` 4–12 µs、交付 `done` 38–55 µs、而 `copy`
16,813–19,833 µs。之后一版试图用「按 `(base, bytes)` 缓存源导入」把这段省掉，但那条
缓存**不安全**：内核每帧 `createMappingInTask(..., kIOMapAnywhere)` 新建映射，并在
`PongScanoutComplete` 之后立刻 `map->release()`；缓存的 `MTLBuffer` 却活到下一帧，所以
「命中」等于让 GPU 从已经释放的映射里取源像素。本轮把它删掉，换成**每帧导入、不跨帧
持有**，并修掉两个让上一轮的判据读不出数的问题：

1. `_k60Us()` 对跨整秒的 `tv_nsec` 差做无符号强转，任何跨秒跨度都会被算成 ~1.8e13 µs
   （17 ms 看起来像几小时）；改为借位后统一相除，逻辑搬到 `PongScanoutTiming.h`，
   由宿主编译器**实际执行**。
2. `report()` 只有 256 字节，`scanout frames=… sum=…` 整行连前缀后缀超过它，尾部字段
   与换行被静默截掉；改为 768 字节并强制以换行结束。

本飞要回答的问题**不是**「能不能更快」，而是「16.8 ms 到底属于谁」——因为上一版把
`import` 排除在 `sum` 之外，账对不上。本飞上报的 `sum` 就是这一侧拥有的四段
（import + encode + submit + gpu），可以直接与内核记账的 `copy` 对账。

**行为改动只有一处**：不再跨帧复用导入。这是把未证伪的风险去掉，不是性能优化。

## 2. 前提证据（都在镜像之前产生）

| 编号 | 事实 | 出处 |
| --- | --- | --- |
| P1 | 上一飞分阶段实测：`copy` 16,813–19,833 µs、`prepare` 4–12 µs、`done` 38–55 µs | `evidence/usblog-20261118-135714/console.log` |
| P2 | 计时算术被编译执行，不是文本匹配 | `scripts/tests/test-scanout-timing.py`：11 例，含 `(1,999999999)→(2,1)` = 0 µs、`(100,999000000)→(101,16000000)` = 17,000 µs、倒序 = 0 |
| P3 | 阶段拆分形状 | `scripts/tests/test-present-stage-split.py` 17 例（四时钟夹住 `commandBuffer`/`endEncoding`/`commit`/`waitUntilCompleted`，四个访问器，`sum` 显式，`char rate[512]`） |
| P4 | 不再跨帧持有导入 | `scripts/tests/test-presenter-import-scope.py` 13 例（无 `imported_`/`reuses_`/`importedBase_`/`importedBytes_`，`present()` 内恰好一次导入，无成员持有，`report()` 768 字节 + 强制换行） |
| P5 | 既有阶段守卫仍过 | `scripts/tests/test-frame-stage-timing.py` 7 例（`lastWait/lastCopy/lastDone` 走 `span()`，`stamped()` 为假时不上报） |
| P6 | 内核侧未改 | 本轮 `git diff` 只含 `drivers/PongMetal/` 下四个文件与三个测试 |
| P7 | 插件由当前源码重编 | 构建日志 `BUILD_EXIT=0`，`strings … \| grep -c "sum=%llu us"` = 1 且 `-c "imports=%llu import="` = 1 |
| P8 | 风险已记录且未升级为「已确认」 | `drivers/PongMetal/README.md:6` 仍写 "remain unconfirmed"；`porting.toml` 的 gpu 条目状态不变 |

## 3. 抓取

- 镜像：`gpu-import-scope-20261118`
- 命令：`scripts/flash.sh <boot.img> 240`，证据落 `E:/k60-work/evidence/usblog-<ts>/`
- 只看 `console.log`；`capture.json` 的 `complete` 必须为真
- 报告行每 60 帧一条，取**末条**为准；`scanout frames=` 的首末两条用于算帧率

## 4. 判据

**S1** `K60KEXC` 命中 0（内核没有异常）。
**S2** 至少 1 行含 `imports=`、`import=`、`encode=`、`submit=`、`gpu=`、`sum=` 六个字段
（带新计时的插件真的上了机）。
**S3** 该行以 `sum=<n> us` 结尾且换行后紧跟下一条记录（`report()` 的截断已修好；
用 `grep -a "sum=[0-9]* us$"` 命中至少 1 次来判）。
**S4** 每条报告行都满足 `imports` == `frames`（没有跨帧复用导入；这是本飞唯一的行为改动
真的生效的直接证据）。
**S5** 末条 `import=` 占 `copy` 的比例 ≤ 25%（导入不是帧成本；同时说明删掉那条不安全
缓存没有付出可见代价）。
**S6** 末条 `sum` 与同段 `copy` 相差 ≤ 30%（这一侧四段与内核记账对得上；差太多说明
`done` 里混了 `PongScanoutComplete` 的往返，账要重记）。
**S7** `scanout frames=` 仍在增长，`crashed: backboardd` 为 0，且首末两条算出的帧率
≥ 5 fps（删除缓存没有让帧率塌掉）。
**S8** `scanout frames=` 出现 ≥ 2 条（只有一条样本无法定案，按 F8 处理）。

**F1** `K60KEXC` > 0 ⇒ 每帧导入改坏了内核路径，回退到上一张可启动镜像并重新审计。
**F2** 没有任何一行含 `sum=` ⇒ 新插件没上机（查 bundle sha256、`stage-metal-plugin.sh`
日志与 `K60METAL deploy files=` 计数），本飞无结论。
**F3** 有 `sum=` 但行尾缺 `us` 或与下一条记录连成一行 ⇒ `report()` 的缓冲区/换行修复
没进镜像，报告仍不可读；先修再飞。
**F4** 任意一行 `imports` < `frames` ⇒ 导入被跨帧复用（缓存被加回或镜像不是本轮源码），
按未证伪的 use-after-unmap 风险立即停飞。
**F5** `sum` 与 `copy` 稳定偏差 > 30% ⇒ 两侧记的不是同一段，**不得**据此归因；下一步是
把 `done` 拆成「交给内核」与「内核返回」，而不是继续改 blit。
**F6** 末条 `gpu` ≥ 0.8 × `sum` ⇒ 成本就是 GPU 搬运本身（18.4 MB / 16.8 ms ≈ 1.1 GB/s，
远低于 A730 blit 的预期带宽）。下一步转向 Turnip 的渲染模式（官方默认 `gmem,nocb`，
本机被 `PongMetalPlugin.mm` 的 `setenv("TU_DEBUG","sysmem,nocb",0)` 强制成 sysmem）
与 blit 路径，而不是显示管线。
**F7** 末条 `encode` + `submit` ≥ 0.6 × `sum` ⇒ 成本在每帧一次的命令提交固定开销上；
下一步是命令缓冲的批量/复用策略，而不是搬运带宽。
**F8** `capture.json` 的 `complete` 为假、`scanout frames=` 少于 2 条、或 `crashed:
backboardd` > 0 ⇒ 抓取或运行无效，本轮结论作废，重飞同一张镜像。

## 5. 结果登记

（判决在出帧后填写，不在镜像之前填。）
