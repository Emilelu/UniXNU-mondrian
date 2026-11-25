# 可借用机制清单（zizhan 27 线的两条）

来源：`/mnt/e/iOS Port/Work/references/latest/UniXNU-zizhan` @ `a7f8ae2`（2026-11-23 导出）。
两条都判 `DEFERRED`：机制本身可用，但我们 stage-0 用不上。**没有经过我们的构建或上机验证**，借用前必须先在 27 树上重放并证明。

---

## 1. `0035-zizhan-chosen-boot-args` — 把启动参数扩到 1024 字节命令行之上的 `/chosen`

**它解决什么**：DarwinBoot 只传 1023 字节命令行（`BOOT_LINE_LENGTH`），日常参数 + 一轮测试开关放不下。
它让额外参数通过 `/chosen` 属性 `zizhan-boot-args` 传入，`PE_boot_args()` 返回「命令行（空格补到 1024）+ 额外参数」，而 `kern.bootargs` 仍然是原始命令行。

**改动点**（三个文件）：
- `pexpert/arm/pe_bootargs.c`：新增 `static char zizhan_boot_args_all[2048]` 与 `zizhan_boot_args_extend()`；`PE_init_platform` 在设备树就绪后调用它。
- `bsd/kern/kern_sysctl.c`：`sysctl_sysctl_bootargs` 改用 `PE_boot_args_cmdline()`（保持 `kern.bootargs` 是原始命令行），另加只读 `kern.zizhan_bootargs` 暴露完整参数。
- `pexpert/arm/pe_init.c`：调用点。

**必须记住的坑（他们实测）**：把额外参数**追加进 `kern.bootargs`** 会让 `launchd_cache_loader` 看不到 `launchd_unsecure_cache=1`，随后的代码签名检查失败。所以两个视图必须分开。

**对我们的适用性**：我们 27 的命令行是 **132 字节**（8 个参数），离 1023 很远 ⇒ 现在不需要。真正会需要它的是「一轮测试要同时开五六个开关」的时候。

---

## 2. `0031-zizhan-inject-extra` — `pong_inj=<library>:<program>` 免重建 init 的注入

**它解决什么**：`exec_inject_conf` 是 init 配置的注入表；改一次就要重建 init。这个 boot-arg 在 sysctl 写入时把 `; <library> <program>` 追加到配置里，`<program>` 支持逗号分隔多个，于是**一个实验 dylib 可以进另一个程序而不碰 init**。

**改动点**：只有 `bsd/kern/kern_exec.c` 的 `exec_inject_conf` sysctl 处理分支（17 行）。它用 `PE_parse_boot_argn("pong_inj", …)`，要求值以 `/` 开头且含 `:<program>`。

**对我们的适用性**：GPU/用户态阶段（往 `launchd`、`backboardd` 注入实验库）会用得上；stage-0 到不了用户态，且我们的 27 树是否有同形态的 `exec_inject_conf` 路径**尚未核实**（借用前先 grep 确认，不要假设）。

---

## 借用规则

1. 先 `git apply --check` 在四层叠好的 27 架上试；不通过就按 P-155 用 `diff -u` 重切，不手写 hunk。
2. 任何 `-D`/boot-arg 开关，判据必须是对象记录（`.o.json`）或最终符号表，不是脚本字面量（P-301）。
3. 借来的机制必须进 `PRECEDENT-MANIFEST.toml` 的 `copied`，并在 `PRECEDENT-PARITY.md` 写明对应行。
4. 上机验证前保持 `DEFERRED` 的定性，不许写成「已解决」。
