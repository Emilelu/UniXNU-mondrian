# iOS 27 移植审计 — 2026-11-23（冻结期只读/仅文档）

## 结论

`PRECEDENT-MANIFEST.toml` 的 672 条先例全部判定：**have 347 / not-applicable 319 / copied 6 / deliberately-different 0 / missing-must-copy 0**。
门禁：`OK goal constraints: precedent parity is complete and every active item has eight resolvable steps`。

## 实际抄入的七个补丁（series `patches/xnu-12377/series`）

| 补丁 | 内容 | 来源 |
| --- | --- | --- |
| `0561` | 4 KiB 内核栈位移（`unixnu_kernel_stack_shift`） | uke |
| `0562` | Darwin 26 `posix_spawnattr` 0x100 字节布局转换 | uke |
| `0564` | 伞形补丁 26 段：T0SZ_USER/pmap 4K、`sheng_sigp_recover`、bindfs `vfs_vget`、OSSymbol 家族、`iokit_rpc` kobject grant、`vm_dyld_pager`、bootargs | sheng |
| `0565` | `sleh.c` PAC 掩码改 `T0SZ_USER` | sheng |
| `0566` | `pmap_apply_user_tcr()` 定义 | sheng |
| `0567` | `arm_vm_init` 调 `pmap_apply_user_tcr()` | sheng |
| `0571` | `native_adreno_connect_granted()` 定义（补 0564 链接缺口） | sheng（移位到 bsd/dev） |

## 四项验证

1. **能否应用**：在 27 base feed（`ac9718f`）的 `git clone --shared` 副本上按 series 顺序应用，7/7 全过。
2. **是否重复**：新增行集合两两比对，无重复。原先 `0561`/`0563`（vermeer）/`0564` 里的 `osfmk/kern/stack.c` 段是**同一处改动的三份拷贝**，已删 `0563`、从 `0564` 剥掉该段（27→26 段），只留 `0561`。
3. **被调符号是否有定义**：`0564` 的 `iokit_rpc.c` 调 `native_adreno_connect_granted()`，我们树里没有 → 新增 `0571` 在 `bsd/dev/k60_adreno_grant.c` 定义并加入 `conf-files.txt`。
4. **开关/宏是否真的生效**：`0558`/`0559` 依赖 `-uketextconsole`/`-ukedeferredconsole`，而 `board.toml` 曾把它们冲掉 → 已补回（10 项参数）；`T0SZ_USER` 由 `0564` 定义（4 KiB 下 = 17，与 `T0SZ_BOOT` 不等），`0565`–`0567` 的条件成立。

## 判为不抄的，及证据

| 条目 | 判定 | 证据 |
| --- | --- | --- |
| sheng `osfmk/vm/vm_shared_region_pager.c` 段 | not-applicable | 唯一新增是 `sheng_srpart_logged` + 一行 `printf("sheng-sr-part: …")`，纯日志 |
| sheng `bsd/kern/bsd_init.c` 段 | not-applicable | 唯一新增是按 `sheng-log=1` 等 `boot_log_rounds` 最多 30 秒，依赖 sheng 专有符号 |
| sheng `bsd/kern/kern_exec.c` 段 | not-applicable | 仅 2/11 hunk 可应用，且与已落地的 `0562` 完全相同；其余 hunk 依赖我们树里命中 0 的 sheng 支架函数 |
| `pexpert/pexpert/arm64/BCM2837.h` | not-applicable | 我们 feed 里连该目录都没有 |
| `uke-systemos-root-identity` / `uke-owner-boot-set-recheck` | deferred | 需要 `CONFIG_XNU_OWNER_*`，我们 27 defconfig 未开，搬进来是死代码（P-208） |

## 尚未完成的验证（解冻后第一件事）

构建一次，判据：`0561`–`0571` 全部编过、`check-kernel-console.py` 与 `check-kprintf-enabled.py` 仍绿、`llvm-nm` 里 `_native_adreno_connect_granted` / `_pong_ramoops_console_write` 都在。这是对"抄得对不对"的最终检验。
