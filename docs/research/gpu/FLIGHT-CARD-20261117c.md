# 上机卡 2026-11-17c：给插件补上 `LC_RPATH`，验证它能否被 backboardd 加载

- 镜像标签：`gpu-rpath-20261117`
- 分支/提交：`feat/gpu-metal-hw` @ 本卡提交之后的第一笔代码提交
- 插件来源：`K60_METAL_PLUGIN_SRC` = `/mnt/e/k60-work/impl/gpu-mac-build/out/metal-plugin-20261117`
  （2026-11-17 用当前 `scripts/build-pong-metal-plugin.py` 从当前源码重编）

## 1. 目的

上一飞（`gpu-dualroot3-20261117`）已经证明：`K60METAL deploy files=6/6 inject=6 error=0`
而且 `console.log:530` 出现 `Pong init: native Metal entry enabled for backboardd`，
即**插件路径确实被拼进了 launchd 配置**；但全日志 `PongAdrenoMetal` 命中 0，
说明插件**没有被加载**。

离线检查发现一个确凿缺陷：那份插件二进制**没有任何 `LC_RPATH`**，而它依赖
`@rpath/PongMetalBridge.dylib`。`@rpath` 只能由加载它的进程或它自身的 `LC_RPATH` 解析，
backboardd 不会提供 `/private/var/pong/PongAdrenoMetal.bundle` 这条路径 ⇒
即使被 dlopen，`PongMetalBridge.dylib` 也解析不到。

本轮**只**换插件二进制（新构建带 `LC_RPATH @loader_path`），不改内核、不改
boot-arg、不改 `0610` 的部署逻辑、不改 init helper。

## 2. 前提证据（上机前已具备）

| 类别 | 证据 |
| --- | --- |
| 静态 | `llvm-objdump-18 --macho --all-headers` 对新二进制：`LC_RPATH` 计数 **1**，`path @loader_path`；`strings -a | grep -c mismatch` = **1**（证明是当前源码，不是 11-09 旧产物） |
| 静态 | `scripts/check-patch-apply.py` ✅；`scripts/tests/test-metal-dual-root.py` 11 例全过 |
| 产物 | `verify-boot-image: OK`；`image-arg-audit: OK (30 arguments, 594 bytes)`；`K60METAL deploy files=6/6 inject=6`（沿用上一飞的部署逻辑） |

## 3. 抓取

- 复用 `scripts/flash.sh <boot.img> 240`，证据落 `E:/k60-work/evidence/usblog-<ts>/`。
- 判读必须引用 `console.log` 行号；计数用 `grep -c`，不得用「看起来没有」。

## 4. 判据

### 成功判据（全部满足才算通过）

- **S1** 内核无异常：`K60KEXC` 出现 0 次（`K60PANIC: restart windows ready` banner 不计）。
- **S2** 部署双根完成：console 出现 `K60METAL deploy files=6/6 inject=6 error=0`。
- **S3** **插件真的跑起来了**：用户态日志出现至少一行 `Pong Metal:`。
- **S4** 出帧：出现至少一行 `present #`。

### 失败判据（任一命中即 FAIL，并写明哪一条）

- **F1** 出现 panic / `K60KEXC`（除 banner）。
- **F2** 没有 `K60METAL deploy ... inject=6`。
- **F3** 有 `S2` 但**没有** `Pong Metal:` 行：说明 `LC_RPATH` 不是（唯一）原因，
  需要改用「插件被 dlopen 的确切位置」继续查（例如 `dyld` 的 image 列表、
  `_dyld_image_count` 计数、或注入机制的实现是否真的会 `dlopen`）。
- **F4** 有 `Pong Metal:` 但没有 `present #`：插件在跑，但没走到 present 路径。

### 判定口径

- `crashed: backboardd` 与 `software renderer fallback installed` 作为**旁证**记录，
  不单独决定判决（上一飞已从 15/18 降到 0/1，无 `Pong Metal:` 也发生了）。

## 5. 结果登记

（上机后填写：判决、引用行号、与判据逐条对照、以及新增的未决问题。）
