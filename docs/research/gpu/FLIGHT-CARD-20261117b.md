# 上机卡 2026-11-17b：确认插件是否真正被注入 backboardd

- 镜像标签：`gpu-dualroot3-20261117`
- 分支/提交：`feat/gpu-metal-hw` @ `532c5d62`
- 插件来源：`K60_METAL_PLUGIN_SRC` = 2026-11-16 从当前源码重编的 bundle（含 `mismatch` 探针字符串）

## 1. 目的

验证 `0610` 的第二个部署根（`/private/var/pong`）是否让 `init-v24dp` 真正把
`PongAdrenoMetal.bundle` 注入 backboardd。本轮**只**改部署根：不改内核状态机、
不改 boot-arg、不改 blob 生成器。

## 2. 前提证据（上机前已具备）

| 类别 | 证据 |
| --- | --- |
| 静态 | `scripts/check-patch-apply.py` ✅（series 229 条逐 hunk 可应用） |
| 单元 | `scripts/tests/test-metal-dual-root.py` 11 例全过，含「注入路径与 init-v24dp.c:366 一致」「模式满足 `!(st_mode & 022)`」 |
| 产物 | `verify-boot-image: OK`；`image-arg-audit: OK (30 arguments, 594 bytes)`；kernel `21f9e87f…`；boot.img `ae25a659…` |

## 3. 抓取

- 复用 `scripts/flash.sh <boot.img> 240`，证据落 `E:/k60-work/evidence/usblog-<ts>/`。
- 判读必须引用 `console.log` 行号；计数用 `grep -c`，不得用「看起来没有」。

## 4. 判据

### 成功判据（全部满足才算通过）

- **S1** 内核无异常：`K60KEXC` 出现 0 次（`K60PANIC: restart windows ready` banner 不计）。
- **S2** 部署双根完成：console 出现 `K60METAL deploy files=6/6 inject=6 error=0`。
- **S3** **插件被加载**：用户态日志出现至少一行 `Pong Metal:`（`PongMetalPlugin.mm` 的 `report()` NSLog）。
  这是本轮最小可验证跃迁；没有它，后面一切都无从谈起。
- **S4** 出帧：出现至少一行 `present #`。

### 失败判据（任一命中即 FAIL，并写明哪一条）

- **F1** 出现 panic / `K60KEXC`（除 banner）。
- **F2** 没有 `K60METAL deploy ... inject=6`：注入根没写成，或计数器没打。
- **F3** 有 `S2` 但**没有** `Pong Metal:` 行：路径对了但插件仍未被加载/未被调用，
  下一步往 `dlopen`/`LaunchServices`/注入时机查，而不是再改路径。
- **F4** `crashed: backboardd` ≥1 且伴随 `software renderer fallback installed`：崩溃回路仍在。

## 5. 结果登记

**判决：FAIL(F3)** — 2026-11-17 01:46:04 上机，证据 `E:/k60-work/evidence/usblog-20261117-014604`
（`console.log` 184,769 B，抓取完整、未因 panic/复位中断，supervisor rc=0）。

| 判据 | 实测 | 结论 |
| --- | --- | --- |
| S1 | `K60KEXC` = 0 | ✅ |
| S2 | `:480 K60METAL deploy files=6/6 inject=6 error=0` | ✅ 双 root 写入成立 |
| S3 | `Pong Metal:` = 0 | ❌ |
| S4 | `present #` = 0 | ❌ |
| F1 | 无 panic | 未命中 |
| F2 | `inject=6` 已出现 | 未命中 |
| F3 | 有 S2、无 `Pong Metal:` | **命中** |
| F4 | `crashed: backboardd` = 0；`software renderer fallback installed` = 1 | 未命中（大幅改善：崩溃 15→0、回退 18→1） |

**本轮确定的事实**：内核侧把 bundle 与两个 marker 写进 `/private/var/pong` 成功
（`inject=6`），且 backboardd 不再崩循环。但插件仍未被执行。

**下一步方向（F3 指定）**：查注入时机与判据，而不是再改路径。首要嫌疑：
`init-v24dp.c` 的 metal 分支用 `sysctlbyname("kern.bootargs")` 读命令行再匹配
`pong_metal=1`，而 P-175 已证明 `PE_boot_args()` 返回的是**内核内嵌默认串**，
不等于固件实际传入的命令行。若该串里没有 `pong_metal=1`，init 会静默跳过注入。

### 判据自身的缺陷（必须记下）

`PongMetalPlugin.mm:36-43` 的 `report()` 只走两条通道：`write(2, …)` 和
`kern.pong_diagnostic` 这个 sysctl。后者在本内核里**没有实现**（全树只有三个调用点，
没有注册点），守护进程的 stderr 也不进 console。因此 **`Pong Metal:` 行在当前内核上
根本不可能出现**，S3 是一个不可观测的判据 —— 这条和「日志里没有就等于没执行」是
同一种错误（P-204 家族）。本轮据此撤回「插件从未被加载」的结论：它可能是被加载了，
只是它的自述无处可去。

**真正的下一件事**：给内核加 `kern.pong_diagnostic`（把字符串打到 console），
让插件的每条 `report()` 可见；否则后续每一次 GPU 上机都测不到东西。
现有旁证支持「插件可能已在跑」：`software renderer fallback installed` 从 18 降到 1，
`crashed: backboardd` 从 15 降到 0。

### 追加核查（2026-11-17 02:12）

**注入确实发生了。** `console.log:530` 有
`Pong init: native Metal entry enabled for backboardd` —— 这行只在
`init-v24dp.c:381`（`memcpy(conf+strlen(base),metal,…)` 成功之后）打印，
而 `strings init-v24dp.bin | grep -c 'native Metal entry enabled'` = 1，确认真机跑的
helper 就是这份源码。之前的 `grep 'Pong Metal'` 没命中是因为该行写作
「native Metal entry」，不是「Pong Metal」（P-204 形状：判据字符串抄错）。

因此缺口下移一层：**launchd 配置里已插入插件，但插件没有被加载**
（全日志 `PongAdrenoMetal` 命中 0，也没有任何 `dyld` 报错点名它）。
下一步应检查：插件 dylib 的 install name / 依赖（`PongMetalBridge.dylib`、
`libvulkan_freedreno.dylib` 是否用 `@rpath` 且注入进程有没有对应 rpath）、
以及注入机制对这一行的确切语义（`; <path> backboardd` 是给哪个字段用的）。


### 追加核查（2026-11-17 02:05）

- 内核 `kernel.macho` 里**确实嵌入了**完整命令行：`pong_metal=1`、`pong_init_path`、
  `k60_skip_iosurface`、`pong_software_keybag` 各命中 1 次 ⇒ `kern.bootargs` 大概率含
  `pong_metal=1`，init 的 metal 分支条件应当成立。
- 日志 `:531 Pong init: UI library configuration result=0 errno=0` ⇒
  `configure_ui_library()` 正常返回，`stat()` 前置检查也通过。
- `:532 Pong init: exec original 20G81 launchd; … stderr -> /dev/console` ⇒ backboardd
  的 stderr 是进 console 的，所以 `report()` 一旦执行就能看见。
- 剩下的唯一缺口：**无法确认 init 是否真的把 metal 那一行拼进了 launchd 配置**。
  该分支成功时没有任何输出。下一步应给 init 的该分支加一行可观测输出（需重建 init
  helper 并更新 `K60_INIT_LEGACY_LEN`），或在 `:531` 前后打印配置串哈希。



