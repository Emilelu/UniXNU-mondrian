# 外设电源投票记账（官网 §5 要求）

状态：**纯逻辑记账模块 + host 58 项断言，无消费者、未上机**。官网
`https://unixnu.com/zh/porting/power` §5 要求「为外设电源投票明确所有权和引用计数。
停止依赖的 DMA 和中断后再释放资源」（快照 `E:/k60-work/scratch/power-page-20261117.txt:109-110`）。
本仓库没有任何外设电源投票实现：`K60PmicRail.h` 只是只读采样，HR-01 又禁止写 RSC/TCS，
所以先把「谁持有、持有几次、什么时候可以释放」做成可测试的纯逻辑。

## 1. 模型

`drivers/PongPower/K60PowerVotePlan.h` + `.c`：

- 16 个资源槽、32 个 owner（位图 + 16 位计数）。
- 每个资源有一个模式：`Free` / `Shared` / `Exclusive`。第一个 owner 决定模式：
  shared 资源可被多个 owner 同时持有；exclusive 资源在最后一个释放前拒绝其他人。
- 同一 owner 对同一资源只能持有一份（重复申请返回 `-3`），因此
  `count == owner 位图的人数`，不需要每 owner 计数。
- 返回值：`0` 成功；`-1` 空指针/越界/无效模式；`-2` 模式冲突；
  `-3` 重复申请。释放返回 `1` 表示这是最后一次（可以下电）、`0` 仍有人持有、
  `-1` 没有这份 claim。
- 释放顺序由 `k60_vote_release_steps()` 固定为：`stop-dma` → `mask-irq` → `drop-vote`。
  模块无法检查前两步，只把顺序写成调用方与 host 测试共同的契约。

## 2. 为什么不是 rail 驱动

- HR-01（`docs/ops/HARD-RULES.md`）规定 `0x17a00000` RSC 绝对禁止映射；
  `0x17a20000` DRV-2 仅在四个条件同时满足时允许一次只读采样；TCS 写与
  `CONTROL_TRIGGER` 禁止。
- 因此这里的 vote 只是驱动侧的引用计数声明，不发送 RPMh 请求、不写 TCS、
  不改变任何电压。真正下电仍要等 rail 所有权问题解决后另行实现。
- 当前没有消费者：显示、USB、PCIe 等外设各自持有自己的电源路径，尚未接入本模块。

## 3. Host 验证

`scripts/tests/test-k60-power-vote-plan.c`，58 项断言：

- shared 两个 owner 共存、exclusive 拒绝第三人、exclusive 首个 owner 期间 shared 被拒；
- 重复申请返回 `-3`（优先于模式冲突）、释放后位图/计数/模式正确回落；
- 最后一次释放返回 `1`，未持有的释放返回 `-1`；
- owner 0/31 边界、资源 15/16 边界、空指针与无效模式；
- 释放顺序三步、容量不足不写、步骤名与未知步骤文本。

运行：

```sh
cc -Wall -Wextra -Werror -std=c11 -o /tmp/tk60vote \
  scripts/tests/test-k60-power-vote-plan.c drivers/PongPower/K60PowerVotePlan.c
/tmp/tk60vote
```

结果：`TESTS OK 58 checks (0 failures)`。

## 4. 边界与下一步

- 未上机，也没有任何真实 rail 名称、consumer 列表或下电时序证据。
- 下一步（需要设备/其他线配合）：把实际消费者列出来（显示、USB、PCIe、ADSP rail），
  在各自驱动里登记 owner，确认释放前的 DMA/中断停止点，再讨论 rail 写路径。
- 不要把本模块当成 §5 完成：GPU 调频、外设 rail 实际供电、平台睡眠的 ArmCpu 路径都还没有。

## 5. 参考

- 官网快照：`E:/k60-work/scratch/power-page-20261117.txt:109-110`。
- 规则：`docs/ops/HARD-RULES.md` HR-01；只读采样：`drivers/PongPower/K60PmicRail.h`。
- 官方参考实现：`UniXNU-sheng` 的 `package/QcomRpmh.c`/`QcomQmp.c` 与
  `ShengPlatformPower.cpp`（后者只做 PMGR ABI 资格验证，未实现槽位会 panic）。
