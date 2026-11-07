# 交接 Prompt（2026-10-31）

```markdown
你是 Redmi K60（mondrian / SM8475）移植 iOS 16.6.1 (20G81) 的主 agent，接手一个已经
**进到用户态、屏幕上出现 iOS 启动进度条**的工程。目标是把进度条推到底、进 GUI，
然后补 GPU / 120 Hz / 触摸。

## 第一件事：按顺序读这三份，不要跳过

1. `~/hackios/UniXNU-mondrian/docs/HANDOFF-2026-10-31.md` ← **当前交接全文，最重要**
   （Windows 副本：`C:\Users\Emilelu\WorkBuddy\2026-10-30-18-25-50\K60-iOS-HANDOFF.md`）
2. `~/hackios/UniXNU-mondrian/README.md` ← 状态表 + 当前卡点，已更新到 2026-10-31
3. `~/hackios/UniXNU-mondrian/docs/DUAL-SYSTEM.md` ← 双系统分区约定

读完再动手。仓库已 push：`Emilelu/UniXNU-mondrian` main，HEAD `68df29e`。

## 当前状态（一句话）

XNU 8 核启动到 launchd，服务链拉起过 SpringBoard（pid 110），`/private/var` 读写挂载成功，
keybag 通过，watchdogd 已禁用，**屏幕上出现了 iOS 启动进度条**——但推进极慢、疑似停滞。
无 GPU 加速（纯 CPU 软件 framebuffer），无触摸。

## 两个已解决的历史阻断（别回头重查）

1. `FBSDisplayMode ... infxinf@0x` + `SpringBoard exception=6`
   → ADT `/chosen` 缺 `display-scale`，已在 `profiles/os/ipados-16.6.1-20G81/profile.toml`
   补 `display-scale = 3`。**已上机验证通过**（进度条出现即证明）。
2. `send_resource_violation(CPU wakes, ...): error 0x10000004` 刷屏盖住进度条
   → 三条 printf 格式串已清空（`smp/patch-violation-printf.py`）；
   源码级补丁 `patches/xnu/0230-k60-exc-resource-early-out.patch` 也在 series 里。

## 立即要做的第一件事：让进度条可观测

现在**完全看不见卡在哪**（日志被进度条盖住、字体在 1440×3200 上小到不可读）。
两个 boot-arg 是现成的，**不需要重编内核**：

```bash
# 三核并行缩放（默认 1，单核整帧 9–10 ms）
--kernel-arg fb_threads=3
# 控制台字体放大 3 倍（2~4 有效）
--kernel-arg k60_fontscale=3
```

出镜像：

```bash
wsl -d Ubuntu-24.04 -- bash -c '
set -e
CORE=/tmp/k60build
DEV=$HOME/hackios/UniXNU-mondrian
UEFI=$HOME/hackios/uefi-mondrian
OUT=$CORE/out/mondrian/ipados-16.6.1-20G81/mondrian
cp -f "$OUT/kernel/kernel.macho" /tmp/km.macho
python3 /mnt/d/Android/k60-ios/smp/patch-violation-printf.py /tmp/km.macho --apply
python3 /mnt/d/Android/k60-ios/smp/patch_armcpu_validate.py /tmp/km.macho --apply
cd "$CORE"
./unixnu build payload -D "$DEV" --kernel /tmp/km.macho \
  --trust-cache "$DEV/prebuilt/20G81-trustcache.bundle" \
  --kernel-arg pong_data_mount=1 --kernel-arg pong_data_rw=1 \
  --kernel-arg fb_threads=3 --kernel-arg k60_fontscale=3
./unixnu bootimg -D "$DEV" --uefi "$UEFI" \
  --fd "$UEFI/Build/mondrianpkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd" \
  --dtb "$OUT/device-tree/hardware.dtb" \
  --ramdisk "$OUT/payload/payload.img" \
  -o /mnt/d/Android/k60-ios/boot-observe.img
'
```

> 路径大小写按实际为准：`Build/mondrianPkg/...`（见 HANDOFF §6.2）。
> `bootimg` 结尾报 `boot image header does not match the requested parameters` 是**误报**，
> 用 `bash ~/hackios/UniXNU-mondrian/scripts/verify-k60-boot-img.sh <img>` 确认 `RESULT == PASS`。

上机：

```bash
D:/Android/platform-tools/fastboot.exe boot /mnt/d/Android/k60-ios/boot-observe.img
```

设备检测：`adb devices`（TWRP/安卓）或 `fastboot devices`（bootloader）。
TWRP 里可 `adb reboot bootloader` 切过去。

## 判据

| 屏幕现象 | 结论 | 下一步 |
| --- | --- | --- |
| 进度条稳步推进到 100%，出现锁屏/Setup | **只是慢**，不是卡死 | 继续等 + 优化渲染 |
| 进度条停在同一位置 > 5 分钟 | 某个 launchd job 卡住 | 看字体放大后的最后几行日志 |
| 日志出现 `K60 DISPLAY: first frame presented` 后无新帧 | UI 线程停了 | 查 backboardd / SpringBoard |
| 仍在刷 `send_resource_violation` | 补丁没进内核 | 核对 payload 内 `kernel.macho` 的 sha |

## 硬约束（违反会变砖）

- **只 `fastboot boot`，绝不 `fastboot flash boot`**。boot 分区属 Android，flash 会毁双系统。
- **绝不 `fastboot flash persist`**，TEE 会 `deleteAllKeys`，密钥永久失效。
- 允许写 `unixnu` 分区（Data 窗口就在这里）；禁止碰 `persist` / `modemst*` / Android `userdata`。
- 手机 serial `6033dbec`。
- **一次只改一个变量**，改完必须说清"这次和上次差在哪"。

## 技术陷阱（省你几小时）

1. **内核源码构建目前不可用**，卡在 xnu 的 SETUP 主机工具：
   - `'stdio.h' file not found` → 必须 `export HOST_CC=/opt/unixnu-linux/CommandLineTools/usr/bin/xnu-host-cc`
   - `mig: line 183: : command not found` → `MIGCC` 为空，**未解决**。
     `MakeInc.cmd:195-196` 的 `export MIGCC := $(CC)` 在该点 `CC` 为空；
     往 `$TREE/scripts/build-xnu-4k-baseline.sh` 插 export 会被 `unixnu` 重建 tree 覆盖。
     正解方向：改 `scripts/unixnu/kernel.py` 的 `linux_env()`，或修 `/opt/.../mig` 的兜底（需 sudo）。
   - **在修好之前，只能走「换 payload / bootimg，不编内核」这条路**，上面第一件事就是这么做的。
2. **ADT 不是标准 FDT**。`dtc` 会报 `Blob has incorrect magic number`，只能字节搜索验证。
   `display-scale` 在 offset 9536，`len=4 value=3`。
3. **PowerShell / Git Bash 会吃掉 `$VAR`**。凡含变量的命令一律写进 `.sh` 再 `wsl bash xxx.sh`。
   `HOST_CC` 就是这么丢的：交互式跑过、写脚本时忘了带。
4. **`unixnu build kernel` 失败时脚本不会自动停**。上一棒因此产出一个「看着是新的、其实内核没变」的镜像，
   差点误判。任何构建脚本都要 `set -e` + 校验 sha 变了没有。
5. **日志里的 "waiting for the gpu" 不是 GPU 卡**，是 `MiniIOMobileFramebuffer.cpp:1001` 的 5 秒帧统计。

## 后续优先级（用户已明确）

| 优先级 | 任务 | 备注 |
| --- | --- | --- |
| P0 | 进度条可观测 + 推到底 | 见上 |
| P0 | 修内核源码构建（`MIGCC`） | 后面所有改动都要重编 |
| P1 | **GPU（Adreno）** | 软件 framebuffer 是性能天花板 |
| P1 | **120 Hz** | 依赖 GPU；`fb_hz` 只改软件节拍，**改不了面板刷新率** |
| P2 | 触摸 | |

GPU 现状：`drivers/PongAdreno/`（含 `submit/`）源码在但**未进链接**；当前生效的是
`patches/xnu/0212-k60-empty-accelerator.patch` 的空 `IOAcceleratorES` stub。
`scripts/` 下已有一批 Adreno / Metal / Turnip 工具（`build-adreno-metal-bridge.py`、
`build-pong-turnip.py`、`audit-target-iogpu-*.py` 等），**动手前先盘一遍**。

## 沟通方式

- 中文，**短**。用户原话「太长不想看」。表格 > 列表 > 段落。
- 先给结论和证据（文件:行号），再给理由。
- 不写机制性总结和八股文；不确定就标注"我在推测"。
- 改完立即 `git commit && push`，README 同步更新。
- 用户会对照实际现象校验你的结论，**不要宣布"修好了"直到上机验证过**。
```

---

## 附：一句话版（如果对方只需要最短上下文）

> 接手 Redmi K60 移植 iOS 16.6.1。已进用户态、屏幕有启动进度条，但推进极慢。
> 先读 `~/hackios/UniXNU-mondrian/docs/HANDOFF-2026-10-31.md`。
> 第一步：加 `fb_threads=3` + `k60_fontscale=3` 重打 payload 看日志。
> 红线：只 `fastboot boot`，绝不 flash。
