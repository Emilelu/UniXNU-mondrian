# K60 iOS 移植 — 动手前必读清单（READING-LIST）

> **进场入口已收敛到 [INDEX.md](../INDEX.md)**（状态/卡点/下一步/交接检查单）；本清单是书目索引，作为 INDEX §4 的补充。

> **不确定就去查这些，不要猜。**
> 按层读：第一层决定「现在干什么」，第二层回答「这事以前干过没有」，第三层回答「上游怎么干的」。

---

## 第一层：项目内（开工前 30 分钟读完）

| 顺序 | 读什么 | 为什么 |
|---|---|---|
| 1 | `E:\k60-work\HANDOFF-2026-11-02.md` | **当前主交接**：目标、硬件路线、已验证事实、卡点、下一步。**注意 INDEX 已标注其 §4 两处过时**（「内核未重编」已被 20:42 构建 `64ae6488…` 推翻；STR 行指旧地址扫描版，现为 kcdata 版） |
| 2 | `E:\k60-work\docs\INDEX.md` | 全量文档地图；哪些文档过时、为什么过时，都标在这里 |
| 3 | `E:\k60-work\docs\ISSUES.md` | 未解决问题的当前形态（崩溃签名、根因未定）；已解决问题的防复发判定 |
| 4 | `E:\k60-work\docs\DECISIONS.md` | 已做决定 + 镜像身份链（引用 sha 的唯一权威表） |
| 5 | `E:\k60-work\docs\PITFALLS.md` | 六个已实证的坑（pagezero、mcopy、探针转义、计数断言、旧 sha） |
| 6 | `UniXNU-mondrian/docs/`（WSL，设备仓）三份当日文档：`MEASURED-HIGH-WINDOW-2026-11-02.md`、`REFERENCE-WALL-AUDIT-2026-11-02.md`、`USERLAND-ROUTES-2026-11-02.md` | 内存窗口定案、显示前提全具备的逐条证据、三条用户态路线为什么不能互相照抄 |
| 7 | `D:\Android\k60-ios\ios-sweet-k60\docs\LOCKSCREEN-2026-10-28.md` | 参考项目进锁屏的四个显示前提（同 SoC，墙体清单源头） |

**挑着读的背景仓**（用到哪个域读哪个，不要通读）：
- `ios-sweet-k60\NOTES.md` —— ⚠️ 是 sweet（SM7150）的笔记不是 K60 的；当「墙体字典」查，不当状态读。
- `ios-sweet-k60\PORT-STATUS-K60.md` —— K60 硬件常量表（GIC/UFS/面板/触摸地址）；**「XNU 未开始」「2 GB 上限」等叙述已过时**。
- `ios-sweet-k60\docs\GPU-PORT-NOTES.md` —— GPU 开工前再读。

## 第二层：历史（动手改任何东西之前先搜）

> 目的：这个症状/这个文件，以前有没有人碰过、结论是什么。**只读，绝不 checkout/reset/clean。**

1. **WSL 构建树 xnu-work 的 git log**（detached HEAD + 脏改动，108 文件未提交）：
   ```bash
   cd /tmp/k60build/out/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work
   git log --oneline --all -- <path>          # 按文件搜
   git log --oneline --all --grep='<症状关键词>'  # 按 commit message 搜
   git diff HEAD -- <path>                     # 看当前脏改动
   ```
   ⚠️ **禁止** `git checkout` / `git reset --hard` / `git clean`——会丢掉全部未提交诊断改动（HANDOFF §6.1）。
2. **设备仓/固件仓的 git log**：`~/hackios/UniXNU-mondrian`、`~/hackios/uefi-mondrian`（分支 `fix/k60-measured-high-window`），同样按症状关键词搜 commit message。
3. **`D:\Android\k60-ios\AGENT-COORDINATION.md` 尾部**：消息板按时间追加，最新结论在文件尾（文件头快照停在 2026-10-27，别从头读）。全文大（368 KB），用关键词搜。
4. **`E:\k60-work\logs\`**：每次构建/打包/上机的原始日志，按时间戳对上候选目录。
5. **旧交接链**（已被取代，只在追历史时读）：`docs/HANDOFF-2026-10-3*`、`HANDOFF-PROMPT-*`、`PROGRESS-2026-10-30-PM.md`、`docs/BOOT-STALL-2026-10-31.md`、`docs/DATA-SPACE-2026-10-31.md`。

## 第三层：上游（改官方代码、借路线之前先查）

| 查什么 | 在哪 |
|---|---|
| UniXNU 官方文档（概念/指南/设备页） | `~/hackios/UniXNU/docs/`：`concepts/`（prelink、payload、boot-chain、security）、`guide/`（boot、build-kernel、debugging、userdata）、`devices/`（**同 SoC 的 pong 等已登记设备最有参考价值**） |
| ios-sweet-k60（hackios 路线，同硬件） | `D:\Android\k60-ios\ios-sweet-k60\` 及其 GitHub 提交记录；**注意它依赖可写 root，tweaks 不可照抄**（USERLAND-ROUTES 逐条解释） |
| UniXNU-pong（pong 路线，Darwin 24） | `~/hackios/UniXNU-pong/`：`userland/init.c`（运行时准备范式）、`drivers/*/README.md`、`migration/ipados18/`（方法论可借，ABI 不可搬） |
| UniXNU-sheng / 其他上游设备仓 | 经 UniXNU 官方 `docs/devices/` 登记的设备仓库跳转（官方索引是权威入口，不凭印象找仓） |
| 上游固件（edk2/uefi-mondrian） | `~/hackios/uefi-mondrian/` 的 `README.md`、`docs/K60-CHANGES.md`、`docs/QR-ADVLOGGER.md` |

**纪律**：改任何官方/上游代码前，先按第三层查它原本的行为与意图；改动必登记（见 `COLLABORATION-RULES.md`）。

---

## 常见场景的直查路径

| 我要…… | 直接去 |
|---|---|
| 引用任何 sha256 | `candidates/<目录>/build-verification.json`（不凭记忆） |
| 重编内核/payload/打包 | `E:\k60-work\tools\`：`build-kernel-summary.sh` → `build-payload-sandbox.sh` → `package-textonly.py`；验证 `handoff-probes.py` |
| 上机 | `~/hackios/UniXNU-mondrian/scripts/k60-device.sh {state\|boot}`；只 `fastboot boot`，绝不 flash |
| 搞清崩溃根因 | ISSUES I-20261102-01 → 等 kcdata STR（`64ae6488…`）上机 |
| 搞清内存窗口为什么 4 GiB | `MEASURED-HIGH-WINDOW-2026-11-02.md` + DECISIONS D-2026-11-02-04 |
| 判断某文档还能不能信 | `INDEX.md` 状态档 |
