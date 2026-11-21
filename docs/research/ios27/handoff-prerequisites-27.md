# 前置补丁移交单（一页）：userland-abi 与 pong-hackios-ui-foundation

发出方 input27（输入线） · 测量日期 2026-11-21 · 只交接「谁修、锚在哪、怎么判」，不含任何实现建议，也不含 gates 改动

## 为什么输入线要交这一单

输入层两个补丁在 27 装配树副本上**零冲突**（touch 排除下面两条前置路径后 `rc=0`，keys 排除 `bsd/conf/files` 后 `rc=0`），
剩下 3 个 hunk 全部依赖下面两条前置补丁先落地；这 3 个 hunk **不属于输入线的改动范围**。

## 一、待移交的两条

| # | 补丁 | 归属 | 27 上的失败锚（实测） | 输入线对它的依赖 |
| --- | --- | --- | --- | --- |
| A | `zzzzzzz-pong-hackios-userland-abi.patch` | 用户态 ABI 线 | `bsd/conf/files:383`、`libkern/conf/files:109`（`git apply --check` 报上下文不匹配） | 它把 `bsd/kern/pong_userland.c` 这一行写进 `bsd/conf/files`，而 touch 的 `bsd/conf/files` hunk 正是以该行为锚（touch patch 的 conf hunk 失败于 `bsd/conf/files:385`） |
| B | `zzzzzzzzzzzzzzzzzzz-pong-hackios-ui-foundation.patch` | 显示线 | `iokit/conf/files:79`、`bsd/kern/bsd_init.c:1305`、`bsd/kern/kern_memorystatus.c:222` | 它以 `--- /dev/null` 形式**创建** `iokit/Kernel/MiniIOMobileFramebuffer.cpp`；touch 的 MFB hunk 只往该文件插 3 行 console 打印（`PE_initialize_console(NULL, kPEReleaseScreen)`），文件不存在就报 `No such file or directory` |

补充事实：`0210-k60-display-native-canvas.patch` 只**修改** MFB，所以它在 27 上报的是同一个 missing-file 错误，不是新问题。

## 二、什么时候要（时间口径）

- **不是 stage-0 的前置**：27 现在卡在更早的位置（stage-0 进不了 SpringBoard），这 3 个 hunk 的解冻不改变 stage-0 结论。
- **是输入层「一次整链应用」的前置**：只要 27 想用「一条 series 从头 apply 到尾」的方式装输入层，就必须先有 A、B。
- 输入线这边**不等待、不阻塞**：台账里已记「输入层 0 冲突、整链阻塞在前置层」，A/B 修好之前输入线的 ⑥/⑦ 结论不变。

## 三、失败后怎么判（判据写死，避免各线口径不一）

对每条前置补丁，由归属线在**同一份 27 装配树副本**（`.cache/xnu-work`，HEAD `ac9718f` + soc 层）上跑，报三件事：

| 判据 | PASS | FAIL | 备注 |
| --- | --- | --- | --- |
| ① `git apply --check` | `rc=0`，无 offset 警告或 offset 已解释 | 仍报某个 `文件:行` 上下文不匹配 | 只认 `git apply`（27 链路无 fuzz，`patches.py:56-62`） |
| ② 锚行存在 | A：`bsd/conf/files` 里能 grep 到 `bsd/kern/pong_userland.c`；B：`iokit/Kernel/MiniIOMobileFramebuffer.cpp` 文件存在且非空 | 锚行/文件仍缺 | 这是输入线唯一依赖的东西 |
| ③ 输入线复验 | 在 ① ② 之后，touch 补丁**不加 `--exclude`** 就能 `rc=0`（keys 仍只需排除它自己的 conf hunk，或也随之通过） | touch 仍失败在 `bsd/conf/files:385` 或 MFB | 这一条由输入线跑，归属线只需给出 ① ② |

判定口径：①②PASS + ③PASS → 输入层整链可应用，台账把「阻塞在前置层」改写为「整链 rc=0」；
①②PASS 但 ③FAIL → 判输入线自身的问题，由输入线查；
①②FAIL → 维持现状记账，**不算输入层 FAIL**（输入层在 27 上是零冲突的）。

## 四、若归属线选择「不修」

两条替代路径都需要 **Lead 决策**，输入线不自作主张：

- A 不修 → touch 的 `bsd/conf/files` hunk 只能改成不依赖 `pong_userland.c` 的自锚定形式（改的是**输入线**补丁），或该 hunk 永久排除。
- B 不修（27 上不创建 MFB）→ touch 的 MFB console 打印 hunk 就该删除（打印可以挪到别处或不要），同样属输入线补丁的改动。

## 五、我不要的东西

不要为了这 3 个 hunk 去改 gates、改 series、或提前解冻构建；这张单只说明「谁、何时、锚在哪、怎么判」。
