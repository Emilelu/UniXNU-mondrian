# 交接 Prompt（可直接复制发给新 agent）

```markdown
你是 K60（Redmi K60 / mondrian / SM8475）iOS 移植项目的主 agent，接手一台已经**把 /private/var 挂起来（只读）**的内核移植工作。

## 第一件事：按顺序读这三份文档，不要跳过

1. `D:\Android\k60-ios\HANDOFF-2026-10-30-EVENING.md` ← **当前交接全文，最重要**
2. `D:\Android\k60-ios\PROGRESS-2026-10-30-PM.md` ← 信任缓存打通后的完整推进记录 + pong 对标
3. `D:\Android\k60-ios\deliverables\ZCODE-RESEARCH-REPORT.md` ← 10 章 149 条调研结论

（前两份也已在 device 仓 `docs/` 内，已 push 到 `Emilelu/UniXNU-mondrian` main，HEAD `cd61b51`）

读完再动手。

## 当前状态（一句话）

XNU 已启动到 launchd，**`/private/var` 第一次真正挂上了，来自真实 UFS Data 窗口，只读**。
唯一硬阻塞：**APFS 读写挂载在空间管理器扫描后卡死**，所以 keybag（`/private/var/keybags/systembag.kb`）写不进去。

## 立即要做的唯一动作

上一棒最后提交（`aa7a1f1`）给 UFS 驱动加了写路径标记，但**还没编译**（内核仍是旧的 17:37 版本，二进制里没有 `K60UFS write#`）。所以：

```bash
# 1) 重编内核（把 K60UFS write# 标记编进去）
wsl -d Ubuntu-24.04 -- bash /mnt/d/Android/k60-ios/local-kernel-build12.sh

# 2) 出「读写探测」payload（pong_data_mount=1 + pong_data_rw=1）
wsl -d Ubuntu-24.04 -- bash /mnt/d/Android/k60-ios/handoff-ufsdata-rw-payload.sh

# 3) 上机（脚本会自动切 fastboot；只 boot，绝不 flash）
wsl -d Ubuntu-24.04 -- bash /mnt/d/Android/k60-ios/handoff-boot-image.sh /mnt/d/Android/k60-ios/boot-ufsdata-rw.img
```

### 判据（屏幕最后一行，无串口，只能看屏）

| 看到什么 | 结论 | 下一步 |
|---|---|---|
| `K60UFS write#0 blk=… hcs=0 hcsfatal=0 ready=1 poison=0` 后卡住 | UFS **写命令本身卡死** | 查 `hostWrite4kLocked` / SCSI WRITE(10) 提交与完成等待 |
| `write#0` 里 `hcs` 非 0 或 `poison=1` | 命令未完成就判 busy → host 被永久 poison | 修 `hostIdle()` 的完成判定 |
| `write#0 -> result=<非0>` | 写返回错误 | 按 result 码定位（NotReady / IOError）|
| 多条 `write#N -> result=0` 后卡在别处 | **UFS 写没问题**，是 APFS RW 阶段卡 | 换 APFS 容器（见 EVENING §4.3）|
| `K60DATA mounted ro=0` | **读写挂载成功** | 立刻验证 keybag 能否写入、MKB 是否还 FATAL |

若仍无进展，按 §4.3 第二个候选原因走：**种子是 macOS 26 hdiutil 造的 APFS，版本比 iOS 16.6.1 的 apfs-2142 新；只读不需要日志/空间事务，读写要**。
需要在**本地 WSL** 找办法造兼容容器（含 `apfsprogs`/`mkfs.apfs` 方向）；**大文件不要走 GHA**。

## 硬约束（违反会变砖）

- **只 `fastboot boot`，绝不 `fastboot flash`**
- 允许写 `unixnu` 分区（Data 窗口就在这里，符合红线）；禁止碰 `persist` / `modemst*` / Android `userdata` / `boot` / `vbmeta`
- 手机 serial `6033dbec`
- **长按电源重启不是温重启 → DRAM 掉电 → ramoops 日志必然丢失**
  ⇒ 不要指望 `adb shell cat /sys/fs/pstore/*` 拿日志；**屏幕是唯一可靠日志**（panic 永远在最后一行）

## 必读的技术陷阱（省你几小时）

1. **PowerShell 会吃掉 `$VAR`、把 `|` 当管道、把 `[0-9]` 当索引**
   → 凡含变量/管道/方括号的命令，**一律写进 `.sh` 文件再 `wsl bash xxx.sh`**

2. **Windows 的 `adb.exe` / `fastboot.exe` 不认 WSL 路径**
   → 传文件或镜像前必须 `wslpath -w` 转换（现有脚本已处理，自己写新脚本时注意）

3. **`local-kernel-build12.sh` 开头会 `git reset --hard origin/main`**
   → 改 defconfig / board.toml / 驱动后，**必须先 commit + push**，否则改动被静默丢弃（已因此浪费多轮）

4. **Data 窗口必须是 GPT 包裹的**：`PongUfsTransport` 校验 Data 窗口 offset 512 处是 `EFI PART`；裸 APFS 会被拒

5. **窗口可写性由 boot-arg `pong_ufs_readwrite=1` 决定**（驱动所有写都过这个门）；没有它连 Data 窗口都是只读

6. **挂载顺序**：必须先 union SystemOS 到 `/`，再挂 Data；反过来 union 会遮住 `/private/var`

7. **`#if XNU_PONG_UFS_DATA`** 由 defconfig 里 `CONFIG_XNU_OWNER_DATA_UFS=y` **精确行**推导；
   且构建脚本强制 `DATA_UFS=1` 时必须 `NATIVE_RAM_BLOCK=0`

8. **`unixnu bootimg` 内置校验对 v4 镜像会误报**（比较 v4 恒为 0 的 `page_size`）
   → 用 `handoff-verify-bootimg.sh` 做独立校验

9. **改 CFLAGS 不会触发 make 重编** → 必要时删对应 `.o`；但**别删 `mach.*.unstripped`**
   （会连带破坏 `EXPORT_HDRS`，导致 `kern_exec.o` 编译失败且**无任何 clang 诊断**）

10. **同一个 `.o` 的 `CFLAGS_ADD` 只能有一行** → 第二行会**替换**第一行，静默丢掉所有 `XNU_OWNER_*` 开关

11. **`panic()` 是 noreturn** → 其后的代码会被当死代码优化掉，曾长期掩盖真实链接问题

12. **`set -u` 下变量必须先定义后使用** → 加 `-D` 开关时曾把使用行放在定义行之前

## 汇报要求

每次上机后给出：① 改动（commit hash）② 屏幕原文（最后几行 / panic 全文，OCR 错误请标注）③ 判据对照（预期 vs 实际）④ 下一步
**没有实测不写「已修复」。**

## 你的权限

- 可自由 commit / push：`Emilelu/UniXNU`（`k60` 分支）、`Emilelu/UniXNU-mondrian`（`main`）
- 可 spawn 子 agent，但每个领域一个 owner、禁止重复劳动
- **大文件产物一律本地 WSL 构建，不要走 GHA**

## 已备好的工具（直接用，别重写）

| 脚本 | 用途 |
|---|---|
| `local-kernel-build12.sh` | 内核构建（含 defconfig 重生成）|
| `handoff-ufsdata-payload.sh` | payload：Data 只读 |
| `handoff-ufsdata-rw-payload.sh` | payload：Data **读写**（`pong_data_rw=1`）|
| `handoff-boot-image.sh <img>` | 自动切 fastboot 并 boot |
| `handoff-verify-bootimg.sh` | boot.img 独立 v4 校验 |
| `handoff-enter-recovery.sh` | 任意状态 → recovery 并等 adb |
| `handoff-state-final.sh` | 设备/仓库/产物状态速查 |
| `tools/make-gpt-data-image.py` | 裸 APFS → GPT 磁盘镜像 |
| `install-k60-ufs-data.py` | 向 unixnu SHNGROOT 装 Data 窗口（支持 `--dry-run`）|
| `smp/patch_armcpu_validate.py` | AppleARMCPU 校验补丁（8 核 ADT 必需，漏了必 panic）|

## 参考资产

- pong 参考仓：`D:\Android\k60-ios\refs\UniXNU-pong`（分支 `latest`，`64ddf28`）
- **强烈推荐读** `refs/UniXNU-pong/migration/ipados18/services.md`（59→73 轮迭代史，很多坑它对岸已经踩过）

现在开始：先读那三份文档，然后执行上面「立即要做的唯一动作」。
```

---

## 收尾状态

| 项 | 状态 |
|---|---|
| 交接文档 | ✅ `HANDOFF-2026-10-30-EVENING.md`（12 节，含全部根因、判据、11 条踩坑）|
| 交接 Prompt | ✅ 本文件，可直接复制 |
| 进展文档 | ✅ `PROGRESS-2026-10-30-PM.md`（已写入内存盘废弃结论）|
| 索引更新 | ✅ `READING-INDEX.md` 顶部新增「最新交接」，并标注旧结论已被取代 |
| 代码状态 | ✅ 已全部 push（device `cd61b51` / core `5d8ed7f`）|
| 未完成 | **写路径标记已提交但未编译** → 新 agent 第一件事就是重编 + 上机 |
| 子 agent | 均无运行中任务 |

**核心资产已固化**：从 trust cache 到 launchd 的 10 个阻塞，加 `/private/var` 从无到有的完整路线
（GPT 包裹 → 分区写入 → 开关联动 → 挂载顺序），每一项都有症状→根因→修复→提交号。新 agent 不需要重新踩。
