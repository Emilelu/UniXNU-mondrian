# MASTER-INDEX — K60 iOS 移植全局资产总索引

> **本索引是唯一全局入口。** 它回答"东西放在哪"；项目内部的文档导航、铁律、卡点、定案在
> [INDEX.md](file:///E:/k60-work/docs/INDEX.md)（项目文档地图）。两者关系：**全局资产地图 ↔ 项目文档地图**，互链互补。
> 官网内容索引：[UNIXNU-SITE-INDEX.md](file:///E:/k60-work/docs/UNIXNU-SITE-INDEX.md)（unixnu.com 全站程序化索引，实时优先、缓存仅基线）。分工：**全局资产地图（本地，本文件） ↔ 官网内容索引（动态远端）**。
> 上游同步机制：[UPSTREAM-SYNC.md](file:///E:/k60-work/docs/UPSTREAM-SYNC.md)（devices.py list/find/pull-check、push-check.py、增量落盘）；设备仓登记快照：[DEVICE-REPOS.md](file:///E:/k60-work/docs/DEVICE-REPOS.md)。分工：**资产地图（在哪） ↔ 上游同步机制（怎么跟进） ↔ 设备仓登记（有谁）**。
>
> - 生成时间：2026-11-04（委托会话，只读扫描产出）
> - 机读版：[master-index.json](file:///E:/k60-work/docs/master-index.json)（同目录，每条含 path/kind/size/mtime/sha256 前 16 位/tags/owner_session/status）
> - 扫描性质：**全程只读**，未修改任何被扫描文件，未执行 git/构建/设备操作；唯二新增文件 = 本文件 + master-index.json
> - 哈希口径：仅对镜像/内核/清单/init/证据等不可再生文件计算 sha256 并**只记前 16 位**；`.git` 内部、构建中间产物、`out/`、`.cache/`、>50MB 日志只登记目录级
> - **D 盘扫描范围 = 仅 `D:\Android`；D 盘其它区域不在授权范围内，未读取、未索引。**（用户 2026-11-04 明确）

## 0. 新 agent 五分钟上手

1. **先读本文件**（你在读的就是）：知道四大存储位置各管什么、关键资产在哪、哪些事不要从零做。
2. **再读 [INDEX.md](file:///E:/k60-work/docs/INDEX.md) 顶部铁律 6 条**：遇坑必录 / 先查坑表 / 灾情三关 / 窗≠卷 / 调研驱动 / 实时优先。然后 §1 状态速览。
3. **读当前卡点与下一步**：INDEX.md §1 → [ISSUES.md](file:///E:/k60-work/docs/ISSUES.md) 未解决区 → [DECISIONS.md](file:///E:/k60-work/docs/DECISIONS.md) 顶部 3 条。
4. **知道去哪找东西**（速记）：
   - 文档/坑/决策 → `E:\k60-work\docs\`
   - 可上机 boot 镜像 → `E:\k60-work\bootimg\`（现役 3 个）与 `E:\k60-work\candidates\4g-quiet\`（v2–v5 系列）
   - init-vN 与源码 → `E:\k60-work\deliverables\pong-init\`
   - Data 窗镜像与清单 → `E:\k60-work\candidates\data-20352\`
   - 写盘脚本（四闸门）→ `E:\k60-work\usb-a-stage\scripts\write-pong-init-vN.ps1`
   - 屏摄证据 → `E:\k60-work\evidence\`（新图会自动落入，勿动命名）
   - 回滚镜像 → `E:\k60-work\archive\unixnu-rollback-20261103-0330\`（9.4 GiB 全分区）与 `E:\k60-work\rollback\`（init/manifest 级）
   - 全部工具脚本 → `E:\k60-work\tools\`（133 个，按 build/pack/probe/flash/inspect/patch/record/ci 分组）
   - 上游参考仓（只读）→ `E:\k60-work\references\`（23 仓）；WSL 设备侧工作仓 → `~/hackios/`
   - XNU 构建树 → WSL `/tmp/k60build`（UniXNU fork k60build 分支 worktree；**detached+脏，禁 checkout/reset/clean**）

## 1. 存储位置总览

| 位置 | 用途 | 体量 | 文件数 | 风险与硬约束 |
|---|---|---|---|---|
| `D:\Android`（**仅此目录被授权扫描**） | 历史主工作区 `k60-ios` + WSL 虚拟磁盘 + adb 工具 | k60-ios ≈197 MB / ~7,140 文件；`wsl\Ubuntu-24.04\ext4.vhdx` **60.8 GB**；platform-tools 17.5 MB | ~7,160 | **D 盘余量仅 36.5 GB，禁止在 D 盘生成大文件**；k60-ios 内仓库有未提交改动，禁 clean；两个 0 字节 `=3900`/`=840` 是历史重定向事故残留 |
| `E:\k60-work` | **现役主产物区**（文档/镜像/证据/回滚/工具/参考仓） | ~72.1 GB | ~20,511 | E 盘是唯一大产物区；`archive\` 只增不删；`candidates\4g-quiet*` 与 `bootimg\boot-4g-quiet-snapshot.img` 受保护不动 |
| `E:\k60-archive` | 整盘级冷数据（设备回读、历史 boot、256MB 种子） | ~4.0 GB | 16 | 设备回读唯一副本**禁止清理**（README 明记） |
| `F:\k60-archive` | 早期冷数据（10-27~31：dtb 全集、28 个历史 boot、扩容前备份、uefi-sheng 仓） | ~6.4 GB | ~2,382 | F 盘余量 87 GB；`F:\New folder` 为空目录；另有 7 KB 老日志 |
| WSL `Ubuntu-24.04`（vhdx 在 `D:\Android\wsl\`） | 构建与设备侧操作主场：`~/hackios`（15G，15 仓/目录）、`~/k60-archive`（16G）、`~/k60-data-build`（9.2G）、`/tmp/k60build`（4.1G）、`/tmp/usb-a-stage`（3.3G） | ~47.5 GB | — | **`/tmp` 下内容重启 WSL 即可能丢失**（k60build/usb-a-stage 在其上）；`~/k60-work` 是指向 `E:\k60-work` 的符号链接（同一物，非副本）；`~/hackios/*` 各仓工作区与 .git 绝对禁止改动 |

合计在册资产 ≈ **190 GB**（含 60.8 GB WSL vhdx）。

---

## 2. D:\Android（扫描范围 = 仅此子树）

### 2.1 根级（`D:\Android\`）

| 项 | 说明 |
|---|---|
| `k60-ios\` | 历史主工作区（2026-10-27 起），现为参考与协作区；活跃构建已迁 E:\k60-work |
| `platform-tools\` | Google adb/fastboot 官方工具（14 文件，含 `adb.exe`、`fastboot.exe`、`mke2fs` 等） |
| `wsl\Ubuntu-24.04\ext4.vhdx` | **WSL2 虚拟磁盘 60.8 GB**（全部 WSL 资产的物理载体；压缩需 `wsl --shutdown`，见 [D-DRIVE-WSL.md](file:///E:/k60-work/docs/D-DRIVE-WSL.md)） |
| `.screenshots\` | 空目录 |
| `manifest-v2-backup.bin`（4 KB，sha `5DFC7EA713A3CEE1`） | **= 设备在役 SHNGROOT 清单 v2（几何错误版）的备份**；与 `E:\k60-work\candidates\data-20352\shngroot-v2.bin`、`E:\k60-work\rollback\manifest-20261103-v2-20261103-231955.bin` 逐字节相同 |
| `=3900`、`=840`（各 0 B） | 疑似历史 shell 重定向误产物（如 `> =3900`），无内容无引用 → 建议删除候选 |

### 2.2 `D:\Android\k60-ios\`（≈197 MB / ~7,140 文件）

区定位与分组详见其自带 [INDEX.md](file:///D:/Android/k60-ios/INDEX.md)。根级 7 文件被脚本/文档硬编码引用**不可移动**：`AGENT-COORDINATION.md`（多 agent 协调板）、`repack.sh`（重打 boot 镜像）、`boot.json`（repack.sh 读取）、`hardware.dtb`、`boot-ios16-hi4g.img` / `boot-ios16-win296.img`（**0 字节符号链接 → `E:\k60-work\bootimg\` 同名镜像**）、`README.md`/`INDEX.md`。

| 目录 | 用途 | 文件数/体量 | 关键文件 | 什么时候来 |
|---|---|---|---|---|
| `docs\` | 历史文档库：handoff(6)/prompts(18)/board(16)/status(7)/research(8)+route-a 3 篇 | 58 / 364 KB | `handoff\HANDOFF.md`(52KB 主交接)、`research\K60-MONDRIAN-PORTING-PLAN.md`、`status\K60-IOS-STATUS.md` | 查 10-27~11-01 历史决策与提示词 |
| `evidence\` | 早期屏摄/panic 照片 37 个（含 `shots\` 11 张） | 37 / 57 MB | `panic-full.png`(20MB)、`panic-a/b.png`、`pt-t1..t6` | 查早期 panic 与 boot 证据 |
| `seed\` | 32 MB 数据种子 `k60-data-seed.dbr`（sha `5FD2F3566E989D11`）+ json | 2 / 33.6 MB | — | 需要 32MB 代种子时；与 WSL `/tmp/usb-a-stage/device/seed/` 同一份 |
| `out\dual_sys\` | GPT/f2fs 操作留档 5 代（applied-32/b/c、plan-32 等，各含 gpt-before/after + plan + twrp.sh） | 49 / 5 MB | 各代 `plan.json`、`SHA256SUMS` | 复核 userdata GPT 变更历史 |
| `firmware\` | `k60-gpu\` GPU 固件 5 件（a730_sqe.fw/zap/gmu）+ `history\` 2 件 | 7 / 2.3 MB | `k60-gpu\a730_sqe.fw` | 需要 GPU 固件 blobs |
| `config\` | 板级配置：`core-components.toml`、`k60-seed.yml`、`kc20g81-components.json`、`pong-board.toml` | 4 / 53 KB | — | 查板级/组件配置 |
| `scripts\` | 既有脚本 10 个（`audit_official*.sh`、`flash-unixnu-chunked.ps1`、`boot-*.ps1` 等） | 10 | `flash-unixnu-chunked.ps1` | 早期刷写/审计脚本 |
| `archive\` | `root-scripts-2026-11-02\`（**1,077 个历史脚本归档**）+ `snapshots\` + MANIFEST | 1,081 / 1.4 MB | `MANIFEST-K60-IOS-2026-11-02.md` | 找 11-02 前的一次性脚本 |
| `deliverables\` | 各阶段交付：`beta2\`(1,350 文件/37MB 最大)、`gamma*`、`delta2`、`A1-touch`、`display-k60`、`K60RamoopsLogLib`、`K60RebootFastbootDxe` + 根级 DXE 源码与调研报告 | 1,405 / 38 MB | `ZCODE-RESEARCH-REPORT.md`、`K60-120HZ-PLAN.md`、`RamPartitionDxe.c`、`K60ButtonsDxe.c` | 查 UEFI/DXE 侧交付物 |
| `smp\` | 内存/prelink 专项脚本与 board 记录 | 51 / 66 KB | `adt_dump.py`、`board-prelink-block.toml` | 内存窗历史 |
| `dual_sys\` | 双系统 python 工具（`gpt.py`、`partition.py`、`f2fs-shrink.c`、`test_dual_sys.py`） | 8 / 83 KB | — | GPT/双系统工具源 |
| `work-display\` / `work-persaudit\` / `agents\` | 其他 agent 工作区（勿动） | 42 | `agents\A1/A2/A4/A5.json` | 仅查阅 |
| `gha-logs\` | GHA 抓取研究 json | 6 / 367 KB | — | 查 CI 研究 |
| `logs\` | **空目录** | 0 | — | 无 |
| `payload\`、`cache\`、`build-artifacts\`、`patches\`、`tools\` | 小件：payload.json、tmp-board.toml、macOS/runner 说明、2 补丁、make-gpt-data-image.py | 11 | — | 按需 |
| 6 个源码仓 | 见 §5 仓库表 | ~4,190 | — | 读源码/对照 |

> D:\Android\k60-ios\INDEX.md「敏感文件」节登记了 `D:\` 根的两个凭据文件——**不在本次授权扫描范围**，仅沿用该登记，未读取未验证。

---

## 3. E:\k60-work（现役主产物区，~72.1 GB / ~20,511 文件）

根级 5 文件：`INDEX.md`（项目文档入口）、`README.md`、`DIRECTORY-CONVENTIONS.md`（目录规范，2026-11-02 起生效）、`HANDOFF-2026-11-02.md`、`RENAME-MAP.md`。

| 目录 | 用途 | 文件数/体量 | 关键文件 | 什么时候来 |
|---|---|---|---|---|
| `docs\` | **项目文档核心**（知识库 agent 维护） | 68 / 639 KB | [INDEX.md](file:///E:/k60-work/docs/INDEX.md)、[DECISIONS.md](file:///E:/k60-work/docs/DECISIONS.md)、[ISSUES.md](file:///E:/k60-work/docs/ISSUES.md)、[PITFALLS.md](file:///E:/k60-work/docs/PITFALLS.md)、[PITFALLS-FROM-HISTORY.md](file:///E:/k60-work/docs/PITFALLS-FROM-HISTORY.md)、[HISTORY-LEDGER.md](file:///E:/k60-work/docs/HISTORY-LEDGER.md)、`references\`（40 份上游调研 DIGEST/PORT-ALL-MATRIX）、`archive\` | 任何操作前必读；本文件与 master-index.json 也在这 |
| `bootimg\` | **可上机镜像（现役 3 个）** | 3 / 606 MB | `boot-4g-quiet-snapshot.img`(=`302A001B…` 进度条基线)、`boot-ios16-hi4g.img`、`boot-ios16-win296.img` | fastboot boot 取这里 |
| `candidates\` | 活跃候选构建树 | 72 / **49.4 GB** | `4g-quiet\`（v2–v5+argfix+datafix 13 套 boot+payload）、`4g-quiet-v1-20261102-2003\`（进度条基线）、`4g-diag/sandbox/str\`、`data-20352\`（**Data 窗 2×21.3GB + 3 枚清单**） | 取某一版构建及其 build-verification.json |
| `deliverables\pong-init\` | **init-v1..v6 交付链**（35160/34872 B 各版 + 对应 init.c 源 + entitlements + var.skel.draft + SHA256SUMS） | 15 / 327 KB | `init-v6`(sha `25D23885…`)、`SHA256SUMS.txt` | 改 pong init 时 |
| `rollback\` | init/manifest 级回滚（expected-segment、设备备份、6 个写盘留档目录含 MANIFEST/WRITE-RESULT） | 24 / 385 KB | `rb-manifest.bin`（几何正确底版 `33626441…`）、`manifest-20261103-fix.bin` | init/清单写盘回滚 |
| `evidence\` | **屏摄与取证证据**（11-03 起） | 60 / 1.46 GB | 14 张屏摄、`blocks\`（设备定点 dump，含 scan-gap 805MB）、`crops*\`（分区裁切）、`forensics-20261103\` | 读屏摄/取证；屏摄读数须先列给用户确认 |
| `usb-a-stage\` | USB-A 日志通道攻关区（其他 agent 活跃区） | 66 / 5.1 GB | `BRIEF-A/REPORT-A/VERIFICATION-A.md`、`out\`（boot-a-control/usblog2、chunk.bin 4.1GB）、`scripts\write-pong-init-v3..v6.ps1`（**四闸门写盘脚本**）、`stage-src\bsd\dev\k60_usblog.c` | USB 通道/写盘脚本 |
| `usb-smmu\` | USB SMMU bypass 设计草案 | 3 / 34 KB | `DESIGN.md`、`RISKS.md`、`k60-usb-smmu-bypass.draft.patch` | 做 SMMU 时 |
| `tools\` | **项目工具集 133 个**（build/ci/inspect/patch/probe/record/_archive 子目录 + 根级受保护脚本） | 133 / 334 KB | `package-v2..v5.py`、`make-shngroot-manifest.py`、`verify-init-vN.py`、`apply-init-vN-probes.py`、`refs-pull.py` | 找现成工具，先查这里再写新的 |
| `references\` | **上游参考仓 23 个（只读）** + unixnu 官网存档（2 html + txt + repos.json） | 7,192 / 102 MB | 见 §5 仓库表 | 查上游事实；每天 09:00/21:00 自动 fetch |
| `forks-review\` | fork/patch 审查：`hakios-xnu-kernel`、`ios-sweet`、`UniXNU`(k60/cherrypick 分支) 3 仓 + `diffs\`(4 份对比 diff) + `patches\`(**2 个待 git am 的 CI patch**) | 2,125 / 326 MB | `diffs\xtom-unixnu.diff` 等 | 评审 fork 差异 |
| `git\` | 2026-11-03 仓库收敛大会战留档（~100 个 commit-*/push-*/tag-* 脚本与日志）+ `progress-bar-20261102\`（**XNU 进度条基线源码树 worktree**，5,014 文件，.git 指向 `/tmp/k60build/out/.../​.cache/xnu-work`） | 5,120 / 71 MB | `progress-bar-20261102\`（含 `.upstream_base_commits`） | 复查收敛操作；进度条源码基线 |
| `incoming\` | 他 agent 移交物：`temp-k60-artifacts\`（含 MANIFEST 登记全 sha；kernel.development.sweet.a 136MB、gh-artifact zip、xnu-kernel.zip、k60probe 402MB）+ `workbuddy-sessions-archive\`（sessions 953 文件/1GB、changes-detail 664、file-history 2004） | 4,403 / 2.1 GB | `temp-k60-artifacts\MANIFEST.md` | 接收/溯源移交物 |
| `archive\` | **工作区归档（只增不删）**：`2026-11-02\candidates\`（7g/8g/exit-summary/measured-high4g/textonly 5 套）、`prelink-before-amfi-20261103\`、`rollback-v2-ponginit\`、**`unixnu-rollback-20261103-0330\`（9.4 GiB 全分区回滚 `FCA1FFAA…`）**、build-records、logs、INVENTORY/MANIFEST | 72 / 12.5 GB | `rollback-0-0x24FB00000.bin`(9.9GB)、`MANIFEST-2026-11-02.md`（删除登记） | 回滚/查退役构建 |
| `reports\` | 11-02 内存窗攻坚产物（hi4g 截图、live dtb/iomem、mem-audit、mfb/kern_exit 源码快照） | 23 / 5.4 MB | `MEASURED-HIGH-WINDOW-2026-11-02.md`、`live-6033dbec-*` | 内存窗历史 |
| `logs\` | 近期日志（boot/package/kernel/device-watch + usb-watch 38MB + 8 张 band 截图） | 35 / 86 MB | `usb-watch-20261103-012138.log` | 查近期运行日志 |
| `firmware\` | UEFI FD/EFI 构建输入 | 4 / 9.5 MB | `measured-high-darwin22.fd`、`hi4g-before-repair.fd` | 固件级实验 |
| `tmp\` / `temp\` | 分析脚本与中间输出（sync2-*/survey-*/cmp-blocks*、bootargs/patches 对照） | 84 / 509 KB | — | 查临时分析 |
| `diffs\` | v4/v5 分步 patch 集 | 6 / 25 KB | `v5-step1..4` | 复现 v5 构建 |
| `cache\` | 可再生扫描缓存（`c-drive-files.csv` 68MB、`d-drive-files.csv` 98MB 等） | 6 / 166 MB | — | 可随时清 |

---

## 4. E:\k60-archive（整盘级冷数据，~4.0 GB / 16 文件）

保留策略见其 [README.md](file:///E:/k60-archive/README.md)。

| 目录 | 内容 | 关键文件（sha 前 16） |
|---|---|---|
| `backups\data2g-install-2026-10-31\` | **设备 data 分区 2GB 回读唯一副本（禁止清理）** | `data-window-readback.img` 2.0GB `562D80EC…`（≡ WSL `~/k60-archive/data/k60-data2g-install-20261031/k60-data2g-gpt.img`）、`shngroot-before.bin` `A14709E4…`、`shngroot-with-data.bin` `CB552B2E…`（≡ `E:\k60-work\archive\manifest-cur.bin`） |
| `bootimg-history\` | 历史 boot 8 枚（11-02 已按里程碑收敛过） | `boot-ios16-good1031.img`（里程碑）、`boot-darwin24*` 4 枚、`boot-ios16-quiet/tcguard/win4g` |
| `seed256\` | 256 MB 数据种子 | `k60-data-seed.dbr` `E3163232…` + json（**与 D 盘 32MB 种子不同代**） |

---

## 5. F:\（早期冷数据，~6.4 GB）

| 路径 | 内容 |
|---|---|
| `F:\k60-archive\images\` | **2026-10-29~31 测试矩阵 boot 镜像 28 枚**（boot-baseline/1cpu/8cpu/amfi/gpu/mem/tc/ufs*/wifi/fontfix/quiet…），各 201.9MB，sha 已全部登记进 JSON |
| `F:\k60-archive\dtb\` | dtbo_a.img + 解出的 64 个 dtb（10-27） |
| `F:\k60-archive\backups\data-before-grow-2026-10-31\` | 扩容前 258MB data 窗备份（`20318499…`）+ shngroot `A14709E4…` + recovery-facts/report |
| `F:\k60-archive\uefi-sheng\` | 参考仓（branch `sheng`，UniXNU/uefi-sheng，2,283 文件/297MB 含 .git） |
| `F:\k60-archive\k60-work-scripts-2026-10-31.zip` | 514 KB 脚本快照 |
| `F:\Redmi K60-20190100-000545.log` | 7 KB 出厂/维修日志（2019 文件名，10-31 前落在 F:） |
| `F:\New folder\` | **空目录**（孤儿） |

---

## 6. WSL（Ubuntu-24.04，vhdx 物理文件在 `D:\Android\wsl\`）

### 6.1 `~/hackios/`（15 GB，设备侧工作仓群）

Git 仓 10 个（HEAD/远端见 §7 仓库表）：`UniXNU`、`UniXNU-mondrian`★、`uefi-mondrian`★、`UniXNU-sheng`、`UniXNU-liuqin`、`UniXNU-pong`、`uefi-pong`、`UniXNU-sm8475-common`★、`UniXNU-docs`、`Device-Binaries`（★ = 用户本人仓库/fork）。
非 git 目录：`k60\`（68M，kernel.macho+json）、`artifacts\`（52M，kernel.macho+adt.bin）、`work-display\`（202M，显示攻关，含 UniXNU/xnu/shim/out-patches/verify-xnu）、`xnu-src\`（3M，平铺的 xnu 源码单文件集）、`acpi-mondrian-submodule-backup\`（3.5M）。

> 硬约束：`~/hackios/*` 下任何仓库的工作区与 .git **绝对禁止改动**（脚本写死 `/home/emilelu/hackios/...` 路径）。

### 6.2 `~/k60-data-build/`（9.2 GB，Data 窗构建产地）

| 项 | 说明 |
|---|---|
| `data-20352.apfs.img` | **20352 MiB 纯容器镜像**（sha `388861bd…`，21,340,618,752 B）——比 E 盘窗口版少 2 MiB GPT 包装，内容对应 `data-window-20354.img`（`81A2662F…`，窗口级） |
| `seed-manifest.json` | 种子清单（36 文件 + launchd_sha256 校验依据，`a7056c96…`） |
| `seed-tree\` | 种子文件树（30 目录） |
| `linux-apfs-rw\` | APFS 构建工具仓（linux-apfs/linux-apfs-rw，master） |
| `wsl2-kernel\` | WSL2 内核源码树（带 .git） |
| `t.img` | 512MB 测试镜像（疑似一次性残留） |
| `mnt\` | 挂载点（空） |

### 6.3 `~/k60-archive/`（16 GB，WSL 侧冷数据总仓）

顶层有 `INDEX.md`、`MOVE-MANIFEST.txt`、`README.md`、`DIRECTORY-CONVENTIONS.md`、`RENAME-MAP.md`。

| 子目录 | 体量 | 内容 |
|---|---|---|
| `images\` | 7.5G | `boot\`(3.1G，payload/boot 镜像与 plo-payloads/plq-extract 等提取树)、`cryptex\`(2.5G，`k60-cryptex.dmg` 2.67GB)、`kernel-macho\`(1.9G，**38 个历史内核 macho**，km-*/kernel-* 全系)、`kernelcache\`(63M，kc_full.bin/kc.bin) |
| `probes\` | 3.7G | 探测研究：`aks-research-20261031\`(2.5G，dyld_shared_cache 分片 26 段)、`sideb-analysis-20261031\`(941M，含 lfw .git pack 854MB)、`disasm\`(150M，kern_dis/apfs 反汇编)、`prelink\`(72M)、`fork\`、`dts\`、`fw-dumps\`、`adt\` 等 22 组 |
| `data\` | 4.8G | data512×4 代（raw+gpt 变体）、`k60-data256-gpt.img`、`k60-data2g-install-20261031\`（2.1G×3，含与 E 盘回读同一份 `562D80EC…`）、apfsprogs-20261030、inspection json |
| `docs\` | 3.7M | `DATA-BACKUP-RECOVERY.md`、`DTB-IDENTIFICATION.md`、unixnu-docs/unixnu-web/hakios-docs 存档、notes |
| `logs\` | 11M | 按日期分层（10-27~11-01） |
| `evidence\` | 8.8M | html、k60-forensics-20261031、src-snapshots、txt-dumps |
| `scripts\` | 6.5M | adt/amfi/build/compare/misc/patches/probe 七组 |
| `misc\` | 3.3M | configs、loose |
| `2026-11-03\` | 1.7M | `work-display-device-pw-backup.tar.gz` |

### 6.4 `/tmp` 与杂项（**WSL 重启即可能丢失**）

| 路径 | 体量 | 内容 |
|---|---|---|
| `/tmp/k60build` | 4.1G | **UniXNU fork 的 k60build 分支 worktree**（.git 文件 → `~/hackios/UniXNU/.git/worktrees/k60build`，HEAD `56e1da11…`）；`out\mondrian\ipados-16.6.1-20G81\...\tree\.cache\xnu-work` 即进度条基线源码树本体（E:\k60-work\git\progress-bar-20261102 指过来）；**detached+脏，禁 git 操作** |
| `/tmp/usb-a-stage` | 3.3G | USB 攻关 WSL 侧：`out\...`（boot/payload 系列，**与 E:\k60-work\candidates\4g-quiet 同哈希重复**）、`device\`(140M，含 seed/mac-build kernelcache)、`patchgen\`、k-argfix/k-argfix2/k-usblog2/k-control.macho（**前三个同哈希 `AC896498…`**）、waipio/sm8450 dtsi |
| `~/k60-work` | — | **符号链接 → /mnt/e/k60-work**（与 E:\k60-work 同一物） |
| `~/acpica-local` | 2.7M | ACPICA 本地工具（2023 年老目录） |
| `~/smp-core` | 8.2M | smp 专项 |
| `~/bin/gh-cred` | 8K | gh 凭据辅助 |

---

## 7. 关键资产表（sha256 前 16 位；全量见 master-index.json）

### 7.1 现役 boot 镜像（fastboot boot 候选）

| 镜像 | 路径 | sha16 | 体量 | 状态 |
|---|---|---|---|---|
| 进度条基线（11-02 20:03） | `E:\k60-work\candidates\4g-quiet-v1-20261102-2003\boot-ios16-4g-quiet.img` | `302A001B48FC4A18` | 192.5 MB | active（里程碑基线） |
| ≡ 同物副本 | `E:\k60-work\bootimg\boot-4g-quiet-snapshot.img` | `302A001B48FC4A18` | 192.5 MB | active（受保护） |
| hi4g / win296 | `E:\k60-work\bootimg\boot-ios16-hi4g.img` / `-win296.img` | `350227D1…` / `B979C1C9…` | 192.5 MB | active（D 盘有同名符号链接指过来） |
| v2 / v3 / v4 / v5 | `E:\k60-work\candidates\4g-quiet\boot-ios16-4g-quiet-v{2,3,4,5}.img` | `A9AE831E…`/`D9B9D6FD…`/`1113D1B0…`/`310F7BC1…` | 192.5 MB | v2–v5 已上机（均 panic/止步，见 INDEX §5） |
| argfix/argfix2/datafix/0303/0304/0305/20261103 | 同目录 7 枚 | 见 JSON | 192.5 MB | archived 候选 |
| 4g-diag / 4g-sandbox / 4g-str | `candidates\4g-*\boot-*.img` | `84EC5343…`/`6389F3DD…`/`6C9AE79A…` | 192.5 MB | archived |
| boot-a-control / boot-a-usblog2 | `E:\k60-work\usb-a-stage\out\` | `E8290AFF…` / `47C7BCEE…` | 192.5 MB | USB 通道实验 |

### 7.2 Data 窗与清单（SHNGROOT）

| 资产 | 路径 | sha16 | 说明 |
|---|---|---|---|
| **Data 窗（含 pong init，在役）** | `E:\k60-work\candidates\data-20352\data-window-20354.img` | `81A2662F804488A2` | 20354 MiB 窗口（含 2MiB GPT 包装），11-03 17:09 写入设备 |
| Data 窗（写 pong 前备份） | 同目录 `data-window-20354-pre-ponginit-backup.img` | `ADBBF0DDC4BBBA0D` | 11-03 05:17 写入版 |
| 纯容器构建源 | WSL `~/k60-data-build/data-20352.apfs.img` | `388861bd84d0caff` | 20352 MiB，少 2MiB 包装 |
| **清单·几何正确底版** | `E:\k60-work\candidates\data-20352\shngroot-final-20261103.bin` | `33626441D3A4C9FB` | = `archive\rollback-v2-ponginit\rb-manifest.bin` = `rollback\rb-manifest.bin`（3 副本） |
| 清单·在役（几何错误，待替换） | `E:\k60-work\candidates\data-20352\shngroot-v2.bin` | `5DFC7EA713A3CEE1` | ≡ `D:\Android\manifest-v2-backup.bin` ≡ `rollback\manifest-20261103-v2-20261103-231955.bin` |
| 清单·修复版（待上机） | `E:\k60-work\rollback\manifest-20261103-fix.bin` | `4DE94A07CB6371A7` | 配套 json `5C2B9CC4…` |
| 清单·草案（禁写设备） | `candidates\data-20352\shngroot-draft.bin` | `D443E5415995096B` | digest 占位零 |

### 7.3 pong init 链（`E:\k60-work\deliverables\pong-init\`）

| 版本 | sha16 | 备注 |
|---|---|---|
| init（原始） | `FAA3854458543CAE` | 回退原件 |
| init-v2 | `68D9BB06FA6411B1` | exec→/sbin/launchd |
| init-v3 | `159593D22C017204` | |
| init-v4 | `4E6AEAE08AD542AD` | |
| init-v5 | `1CDADCFC9B8B920A` | 标记串 `[v5]` |
| **init-v6（最新，已写盘）** | `25D23885C9175BEC` | 单行覆盖输出，2026-11-04 07:39 随 v5 镜像 boot |
| 写盘回滚段 | `E:\k60-work\rollback\` 下 expected-segment 与 device-backup（v2 `1069C3BF…`/v3 `9854613E…`/v4 `4464F095…`/v5 `847EDAFE…`） | 每版 36KB |

### 7.4 回滚与种子

| 资产 | 路径 | sha16 |
|---|---|---|
| **全分区回滚（9.4 GiB，11-03 03:40）** | `E:\k60-work\archive\unixnu-rollback-20261103-0330\rollback-0-0x24FB00000.bin` | `FCA1FFAA038174CF` |
| 2GB data 回读（唯一副本） | `E:\k60-archive\backups\data2g-install-2026-10-31\data-window-readback.img` | `562D80EC507672DB` |
| 扩容前 258MB data 备份 | `F:\k60-archive\backups\data-before-grow-2026-10-31\data-window.img` | `203184993CE09BA8` |
| 256MB 种子 | `E:\k60-archive\seed256\k60-data-seed.dbr` | `E31632324E100844` |
| 32MB 种子 | `D:\Android\k60-ios\seed\k60-data-seed.dbr` ≡ WSL `/tmp/usb-a-stage/device/seed/` | `5FD2F3566E989D11` |
| prelink 回退包 | `E:\k60-work\archive\prelink-before-amfi-20261103\`（payload `E722BE51…`+README-ROLLBACK） | — |

### 7.5 内核 macho（构建产物）

现役 extracted：`candidates\*\extracted\kernel.macho`（基线 `65FBE51E…`、4g-diag/7g/8g 同 `1A18C6A2…`、4g-quiet `88C49E85…`、exit-summary `9AA69B35…`、textonly `6AA3FC8E…` 等）。
历史 38 枚：WSL `~/k60-archive/images/kernel-macho\`（km-* 系列全登记进 sidecar）。
USB 实验：`E:\k60-work\usb-a-stage\out\kernel-a-usblog.macho` `2F80BBE2…`；WSL `/tmp/usb-a-stage/k-argfix2.macho` `967b5dc7…`（argfix/usblog2/control 三枚同 `AC896498…`）。

> **WSL 侧全量哈希**：207 条（≥1MB 文件 + 三根级全部文件，含 38 枚历史内核、cryptex、data512 各代）见 sidecar [master-index-wsl-sha256.txt](file:///E:/k60-work/docs/master-index-wsl-sha256.txt)（与本索引同目录，属 master-index.json 附件）。

### 7.6 证据（屏摄，读数须先列给用户确认）

`E:\k60-work\evidence\`：0303 三连拍、heartbeat、A1 panic、datafix、v2/v3/v5 panic 屏摄 + crops/crops-v2/crops-v3 裁切带 + `blocks\` 设备定点 dump（blk-a..d、scan-* 共 1.2GB）+ `forensics-20261103\` 取证脚本与比对清单。
早期：`D:\Android\k60-ios\evidence\`（panic 全系、pt-t1..t6、shots\）。

### 7.7 固件与 DTB

`E:\k60-work\firmware\`（3 FD + 1 EFI）、`F:\k60-archive\dtb\`（dtbo 全集 65 件）、`D:\Android\k60-ios\firmware\k60-gpu\`（a730 系列）、`D:\Android\k60-ios\hardware.dtb`、各 candidates 的 `hardware.dtb`（现役版 `7F840FF3…`）。

## 8. 仓库表（共 45 个 git 仓/worktree；sha 为 HEAD 前 12 位）

### 8.1 用户本人仓库/fork（★ 活跃开发）

| 仓 | 位置 | 分支 | HEAD | 远端 |
|---|---|---|---|---|
| UniXNU-fork ★ | `D:\Android\k60-ios\UniXNU-fork` | k60 | `48331fff72d0` | github.com/Emilelu/UniXNU |
| UniXNU-mondrian ★ | WSL `~/hackios/UniXNU-mondrian` | fix/k60-measured-high-window | `3c1bea360994` | github.com/Emilelu/UniXNU-mondrian |
| uefi-mondrian ★ | WSL `~/hackios/uefi-mondrian` | fix/k60-measured-high-window | `624458224913` | github.com/Emilelu/uefi-mondrian |
| UniXNU-sm8475-common ★ | WSL `~/hackios/UniXNU-sm8475-common` | main | `d0c90f1e2f8d` | github.com/Emilelu/UniXNU-sm8475-common |
| UniXNU（fork，k60build worktree） | WSL `/tmp/k60build` | k60build | `56e1da11739f` | 属于 ~/hackios/UniXNU 的 worktree；**脏树禁 git 操作** |
| UniXNU（cherrypick 副本） | `E:\k60-work\forks-review\UniXNU` | k60/cherrypick-20261102 | — | github.com/Emilelu/UniXNU |
| ios-sweet-k60（fork 自 XTOM0706，含本人 4 提交） | `D:\Android\k60-ios\ios-sweet-k60` | main | `3fbaa5e74c36` | github.com/XTOM0706/ios-sweet-k60 |

### 8.2 上游/参考仓（只读）

D:\Android\k60-ios：`UniXNU`(main `33da8131`)、`UniXNU-sheng`(main `08cde20e`)、`UniXNU-liuqin`(main `907b8e91`)、`uefi-pong`(main `87c10fd7`)。
E:\k60-work\references（23 仓，每天 09:00/21:00 自动 fetch，详见 JSON）：`darwin-xnu-build`、`ios-sweet`、`pong-*`×11、`uefi-pong`、`UniXNU`(feat/ipados27-gpu-parity `c93e9654`)、`UniXNU-pong(-upstream)`、`UniXNU-sheng(-upstream)`、`UniXNU-sm8550-common`、`UniXNU-upstream` 等。
E:\k60-work\forks-review：`hakios-xnu-kernel`(main)、`ios-sweet`(main)。
F:\k60-archive：`uefi-sheng`(sheng)。
WSL ~/hackios：`UniXNU`(main `e3b31338`)、`UniXNU-docs`(detached `066c8d83`)、`UniXNU-pong`(main `64ddf288`)、`UniXNU-sheng`(main `08cde20e`)、`UniXNU-liuqin`(main `907b8e91`)、`uefi-pong`(main `0ab8be59`)、`Device-Binaries`(main `a1501e0c`，Project-Silicium)。
WSL ~/k60-data-build：`linux-apfs-rw`(master)、`wsl2-kernel`（带 .git）。
源码快照（非独立仓）：`E:\k60-work\git\progress-bar-20261102`（XNU worktree，gitdir 在 /tmp/k60build 内）、WSL `~/hackios/xnu-src`。

## 9. 不要再从零做（已闭环事项速查）

| 事项 | 结论/产物位置 |
|---|---|
| APFS 容器从零构建 + 种子写入 | 已闭环（WSL `~/k60-data-build` 全链路 + 四项验收）；调研 [DIGEST-apfs-linux.md](file:///E:/k60-work/docs/references/DIGEST-apfs-linux.md) |
| unixnu 官网地毯式调研 | `E:\k60-work\references\unixnu-*.html/json` + [DIGEST-unixnu-com.md](file:///E:/k60-work/docs/references/DIGEST-unixnu-com.md) |
| 上游 23 仓逐仓调研 | `E:\k60-work\docs\references\DIGEST-*.md`（40 份） |
| pong 用户态移植矩阵 | [PORT-ALL-MATRIX.md](file:///E:/k60-work/docs/references/PORT-ALL-MATRIX.md) |
| USB 日志通道方案 | [USB-LOG-CHANNEL.md](file:///E:/k60-work/docs/USB-LOG-CHANNEL.md) + `references\USBM-LOG-CHANNEL-AUDIT.md` + `usb-smmu\DESIGN.md` |
| 12 GiB 内存可行性 | [DECISION-MEMORY-12GIB-2026-11-02.md](file:///E:/k60-work/docs/DECISION-MEMORY-12GIB-2026-11-02.md)（单窗上限 ~8.65 GiB） |
| ramoops 取证 | **已证伪**（TWRP 无 /dev/mem；I-20261104-01），勿再试 |
| init 注入与写盘四闸门 | `deliverables\pong-init\` + `tools\apply-init-vN-probes.py` + `usb-a-stage\scripts\write-pong-init-vN.ps1` |
| commit 规范 | [COMMIT-CONVENTION.md](file:///E:/k60-work/docs/COMMIT-CONVENTION.md)（feflow 原文在 `docs\references\`） |
| 参考仓每日同步 | 计划任务「参考仓库上游变动检查」+ `tools\refs-pull.py` |
| 屏摄自动取图 | `usb-a-stage\scripts\fetch-latest-photo.ps1`、`wait-and-fetch-photo.ps1`（5 秒轮询目录见项目记忆） |
| C/D 盘文件普查 | `E:\k60-work\cache\*-drive-files.csv`（可再生） |

## 10. 维护规则

- 新资产入库后**当轮更新本索引与 JSON**（加一行/一条，写清 owner_session 与 sha16）。
- 本索引只做"在哪/是什么/多少"；结论与决策一律写回 docs/ 四册（DECISIONS/ISSUES/PITFALLS/HISTORY-LEDGER）。
- 删除/移动任何被登记资产前，先按 `DIRECTORY-CONVENTIONS.md` 走 MANIFEST/RENAME-MAP 登记，再回本索引改状态（`superseded`/`archived`）。
