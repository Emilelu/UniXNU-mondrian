# 上机卡：GPU Metal 硬件加速 · `gpu-scanout2-20261116`

写入时间：2026-11-16 23:47 +08:00（**上机之前**）
分支：`feat/gpu-metal-hw`（HEAD 含 `7ee283f0`）
镜像：`E:/k60-work/artifacts/gpu-scanout2-20261116/boot.img`

## 1. 本飞唯一目的

判定「把 `pong_gpu_scanout=1` 打开后，用户态能不能真的拿到 Metal 设备并出帧」。
上一飞（`gpu-scanout-20261116`，`5ace1a97…`）在同一配置下被我们自己的
`K60POPEN … path=%s` 诊断打断（内核 data abort），因此该问题**从未被验证过**。

## 2. 本飞带入的改动（每项都有证据）

| 改动 | 提交 | 静态 | 单元 | 产物 |
| --- | --- | --- | --- | --- |
| 打开扫描输出闸门 | `1b8eaf47` | `board.toml:203` 含 `pong_gpu_scanout=1` | — | `image-arg-audit: OK (30 arguments, 594 bytes)` |
| 平台名/类名按 personality 命名 | `3524eb7f`、`1a47f11b` | `check-patch-apply.py` ✅ | — | series 229 |
| open trace 不再解引用已回收的 namei 指针 | `0589a33a` | `check-patch-apply.py` ✅（P-162） | `scripts/tests/test-open-trace-no-name-deref.py` 4/4 ✅，改回旧写法时 3 条转红 | 内核重新构建、manifest 记录 |
| Metal 插件按当前源码重编 | 无（产物替换） | 新二进制含 `mismatch` 字符串（旧的无） | — | `metal-plugin-20261116` 95,552 B，stage 6 文件 51,279,xxx B |

## 3. 已知未闭合项（逐条判定与本飞的关系）

| 项 | 状态 | 是否阻碍本飞 |
| --- | --- | --- |
| `pong_metal=1` 历史 backboardd 崩 16 次 | 未解释 | 不阻碍：这正是本飞要观测的现象，判据已写明 |
| `k60_skip_iosurface=1` 仍必需（P-98） | 已知约束 | 不阻碍：0332 的行为不变，且已证明 IOSurface 客户端能建 |
| selector 7 `WrapClientMemory` 未实现 | 已知缺口 | 不阻碍：仅当用户态真的打开加速器客户端后才会被调用；本飞先看是否发生 |
| `IOConnectTrap` index ≥ 6 假成功 | 已知缺口 | 不阻碍：同上，属下一层 |
| `IOSurfaceRoot::start()` 注册前提 | 均已满足（各有独立日志） | 不阻碍 |
| 内核 8 MiB `io_submap` 预算 | 已由 `0621` 抬到 32 MiB | 不阻碍 |

结论：**没有被判定为「会带未知上机」的项**；上表每一项要么有证据闭合，要么已被本飞判据覆盖。

## 4. 判据（先写死，事后不得改）

成功需同时满足 S1–S5：

- **S1** `console.log` 中 `K60KEXC` 与 `K60PANIC` 均 0 次
- **S2** 出现 `present #` 探针行 ≥ 1 次（upstream 侧该行是「真的出帧」的唯一直接证据）
- **S3** `software renderer fallback installed` 计数 == 0
- **S4** `crashed: backboardd` 计数 == 0
- **S5** `SpringBoard` 出现次数 ≥ 100

失败分级：

- **F1** 出现 `K60KEXC`/`K60PANIC` ⇒ 立即停止后续上机，符号化 pc/lr/far 并定位到具体驱动代码；在修好并补齐静态/单元证据之前不再飞。
- **F2** 无 panic 但 S2 或 S3 不满足 ⇒ 记为 FAIL(F2)，下一步固定为「在 `IOService::newUserClient` 打印 provider 的 `getMetaClass()->getClassName()` 与 `getName()`」，以区分「用户态没找加速器」与「找了但失败」。
- **F3** 无 panic、S2/S3 满足但 S4/S5 不满足 ⇒ 记为 FAIL(F3)，下一步取崩溃栈与 `K60UF` 直方图，不再新增 boot-arg。

## 5. 结果登记（上机后填写，不得回改判据）

- 镜像：`dbb93478107fa55adee61a9759e48b7339882b8b5a59e5b5403eacb1ca95a45e`（30 args / 594 B）
- 内核：`ce1f37298b86772d3b00dfec25b030aece4f7e25cbcd0b2e351f412cc264fce3`
- 证据目录：`E:/k60-work/evidence/usblog-20261117-000745`（206,291 B / 3,206 行，抓取完整，未因 panic/复位中断）
- S1 ✅：`K60KEXC` 0 次；`K60PANIC` 唯一 1 次是 `:474 K60PANIC: restart windows ready` banner（P-204：banner 不是失败）
- S2 ❌：`present #` 0 次
- S3 ❌：`software renderer fallback installed` 18 次
- S4 ❌：`crashed: backboardd` 13 次
- S5 ❌：`SpringBoard` 13 次
- 判决：**FAIL(F2)**

### 旁证（本飞顺带拿到的两条真机事实）

1. `:182/:183 PONG SCANOUT: actual framebuffer handoff available sequence=0 status=0x0`
   —— 扫描输出闸门打开后，presenter 真的拿到了固件帧缓冲的物理范围（`pong_scanout_initialize`
   跑到了真正的 handoff 分支，而不是被 gate 提前 return）。此前从未有过这一行。
2. `:1284/:1285/:1717/:1718 K60POPEN err=13 uid=501/25 ruid=… namelen=26/5 mode=0 type=0`
   —— `0589a33a` 的修复在真机成立：同一处诊断现在打印长度，**没有 panic**（上一飞同一位置内核 data abort）。

### 结论与下一步（按 F2 固定动作执行）

断点不在扫描输出，也不在 IOSurface：用户态仍然拿不到 Metal 设备。下一步只做一件事：
在 `iokit/Kernel/IOService.cpp` 的 `newUserClient`（`~:7904`）里，对
`IOSurfaceRootUserClient`（以及任何 name 含 `Accelerator` 的类）打印 provider 的
`getMetaClass()->getClassName()` 与 `getName()`，以区分「用户态没去找加速器」与
「找了但 `newUserClient` 失败」。该改动必须先补齐静态/单元/产物证据，并另写一张上机卡，
判据提前写死，才允许再飞。

