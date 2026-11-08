# k60-ios — 参考仓库与协作区（已整理 2026-11-02）

本目录是 K60 iOS 移植的**参考与协作区**：参考仓库克隆、交付文档、研究笔记、取证照片。当前活跃构建/上机流程在 `E:\k60-work`，不在此目录。

## 目录结构

| 目录 | 内容 | 说明 |
|---|---|---|
| `UniXNU\` | UniXNU 主仓库克隆（main，clean） | 源码目录，保留 |
| `UniXNU-fork\` | 自有 fork（k60 分支，clean） | 源码目录，保留 |
| `UniXNU-sheng\`、`UniXNU-liuqin\` | 参考实现克隆 | 源码目录，保留 |
| `uefi-pong\` | uefi-pong 仓库克隆（main，clean） | 源码目录，保留 |
| `ios-sweet-k60\` | ios-sweet-k60 克隆（**31 个未提交改动**） | 有在途修改，勿 clean |
| ~~`refs\`~~ | 已于 2026-11-02 迁往 `E:\k60-work\references\`（7 个干净克隆 + 索引文件） | 已迁移 |
| `deliverables\` | 各阶段交付文档（beta2/delta2/gamma/gamma2 等） | `.md` 全部原地保留 |
| `docs\`、`tools\` | 项目文档/工具 | 保留 |
| `scripts\` | 既有脚本集（191 个） | 保留 |
| `seed\` | 32MB 数据种子 + json | 保留（重复副本已删） |
| `firmware\`、`out\`、`smp\`、`dual_sys\`、`patches\`、`payload\`、`agents\`、`work-display\`、`work-persaudit\`、`shots\` | 固件、输出、研究材料 | 保留 |
| `build-artifacts\` | 构建产物说明文档 | FVMAIN.Fv 已删，`.md` 保留 |
| `gha-logs\` | GHA 抓取的研究 json + issue 文档 | 保留（旧 run 日志已删） |
| `logs\` | （空）旧日志已清理 | 保留目录 |
| `archive\root-scripts-2026-11-02\` | 根目录散落的 1077 个一次性脚本/杂项 | 归档可追溯，未删除 |

## 根目录文件（2026-11-02 归类后）

只剩 7 个文件：`AGENT-COORDINATION.md`（活跃协调板）、`repack.sh`、`boot.json`、`hardware.dtb`（均被脚本/文档硬编码引用，不可移动）、`boot-ios16-hi4g.img` / `boot-ios16-win296.img`（0 字节重解析点，指向 E: 侧镜像）、`README.md`/`INDEX.md`。

其余已全部归类：`.md` → `docs\{handoff,prompts,board,status,research}\`；照片/日志文本 → `evidence\`；配置 → `config\`；`tmp-board.toml` → `cache\`；补丁 → `patches\`；快照 → `archive\snapshots\`。全量映射见 `E:\k60-work\RENAME-MAP.md`，目录说明见 `INDEX.md`。

## 整理记录

见 `archive\MANIFEST-K60-IOS-2026-11-02.md`（含释放空间与完整清单）。
