# 上机卡 2026-11-17b：确认插件是否真正被注入 backboardd

- 镜像标签：`gpu-dualroot3-20261117`（`K60_METAL_PLUGIN_SRC` = 2026-11-16 从当前源码重编的 bundle，含 `mismatch` 探针字符串）
- 分支/提交：`feat/gpu-metal-hw` @ `532c5d62`
- 目的：验证 `0610` 的第二个部署根（`/private/var/pong`）是否让 `init-v24dp`
  真正把 `PongAdrenoMetal.bundle` 注入 backboardd。
- 本轮**只**改部署根；不改内核状态机、不改 boot-arg、不改 blob 生成器。

## 1. 前提证据（上机前必须已具备）

| 类别 | 证据 |
| --- | --- |
| 静态 | `scripts/check-patch-apply.py` ✅（series 229 条逐 hunk 可应用） |
| 单元 | `scripts/tests/test-metal-dual-root.py` 11 例全过，含「注入路径与 init-v24dp.c:366 一致」「模式满足 `!(st_mode & 022)`」 |
| 产物 | 构建日志出现 `K60METAL deploy files=6/6 inject=6 error=0`（pending，构建后填） |

## 2. 成功判据（全部满足才算通过）

- **S1** 内核无异常：`K60KEXC` 出现 0 次（`K60PANIC: restart windows ready` banner 不计）。
- **S2** 部署双根完成：console 出现 `K60METAL deploy files=6/6 inject=6 error=0`。
- **S3** **插件被加载**：用户态日志出现至少一行 `Pong Metal:`（`PongMetalPlugin.mm` 的 `report()` NSLog）。
  这是本轮的最小可验证跃迁；没有它，后面一切都无从谈起。
- **S4** 出帧：出现至少一行 `present #`。

## 3. 失败判据（任一命中即 FAIL，并写明哪一条）

- **F1** 出现 panic / `K60KEXC`（除 banner）。
- **F2** 没有 `K60METAL deploy ... inject=6`：注入根没写成，或计数器没打。
- **F3** 有 `S2` 但**没有** `Pong Metal:` 行：说明路径对了但插件仍未被加载/未被调用，需要往
  `dlopen`/`LaunchServices` 方向继续查，而不是再改路径。
- **F4** `crashed: backboardd` 计数 ≥1 且伴随回退 `software renderer fallback installed`：崩溃回路仍在。

## 4. 抓取

- 复用 `scripts/flash.sh <boot.img> 240`，证据落 `E:/k60-work/evidence/usblog-<ts>/`。
- 判读必须引用 `console.log` 行号；计数用 `grep -c`，不得用「看起来没有」。

## 5. 结果登记

（上机后填写：判决 S1–S4 / F1–F4 命中情况、关键行号、下一步。）
