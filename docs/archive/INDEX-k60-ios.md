# D:\Android\k60-ios INDEX（2026-11-02 归类版）

参考与协作区。当前活跃构建/上机流程在 `E:\k60-work`；本区保存文档、参考仓库、取证材料。

```
D:\Android\k60-ios\
├── docs\            全部文档（handoff/prompts/board/status/research + 原有 3 篇 route-a）
├── evidence\        屏摄照片、panic 照片、UEFI 日志文本（含 shots\）
├── config\          板级配置/清单（toml/yml/json）
├── cache\           可再生临时数据
├── firmware\        固件相关
├── patches\         补丁文件
├── seed\            32MB 数据种子 + json
├── scripts\         既有脚本集（191 个）
├── tools\           项目工具
├── deliverables\    各阶段交付文档（beta2/delta2/gamma/gamma2 等）
├── gha-logs\        GHA 抓取的研究 json
├── logs\            （空）日志位
├── out\             f2fs/GPT 备份类输出（10/29）
├── payload\ / payload 相关 / dual_sys\ / smp\  专项工作区
├── agents\ / work-display\ / work-persaudit\    其他 agent 工作区（勿动）
├── build-artifacts\ 构建产物说明（.md）
├── ios-sweet-k60\   参考仓（31 个未提交改动，勿 clean）
├── UniXNU\ / UniXNU-fork\ / UniXNU-sheng\ / UniXNU-liuqin\ / uefi-pong\   源码仓（相对路径不可变）
├── archive\         归档区（root-scripts-2026-11-02、snapshots、MANIFEST）
└── 根目录 7 文件     见下表
```

## 根目录保留文件（被脚本/文档硬编码引用，不可移动）

| 名称 | 用途 | 状态 | mtime |
|---|---|---|---|
| `AGENT-COORDINATION.md` | 多 agent 协调板（record-*.py 的写入目标） | **活跃**（18:00+ 保护） | 19:11 |
| `repack.sh` | 重打 boot 镜像（被 HANDOFF.md、NEXT-AGENT-PROMPT-14.md 等多处引用） | 活跃 | 13:45 |
| `boot.json` | 打包元数据（被 `repack.sh:13` 读取） | 活跃 | 10/30 |
| `hardware.dtb` | 最小 DT（被 HANDOFF-2026-10-30.md:29 等引用根路径） | 参考 | 10/30 |
| `boot-ios16-hi4g.img` / `boot-ios16-win296.img` | 0 字节重解析点，指向 E: 侧镜像 | 链接 | 13:45 |
| `README.md` / `INDEX.md` | 本区说明与索引 | — | 11/2 |

## docs\ 分组

| 子目录 | 用途 | 数量 |
|---|---|---|
| `docs\handoff\` | 交接文档（HANDOFF 系、A5-HANDOFF） | 6 |
| `docs\prompts\` | agent 提示词（NEXT-AGENT-PROMPT 系、INBOX 等） | 18 |
| `docs\board\` | _board_entry 系记录 | 16 |
| `docs\status\` | 状态/规则/索引（STATUS、REVIEW、SYNC-LOG、COLLABORATION-RULES 等） | 7 |
| `docs\research\` | 研究输入/ playbook / issue 回复 | 8 |
| `docs\`（根） | 原有 route-a 文档 3 篇（未动） | 3 |

## evidence\ 内容

panic 屏摄 9 张、panic2 系列 4 张、bt/p3/p4 照片 7 张、pt-t1..t6 共 6 张、check 2 张、`shots\` 11 张、D 盘根目录迁入的 `AppleARMBootPerf-Error-profile-20261031.txt`、`READY-TO-ENTERUEST-20261102.txt`。

## 状态标记口径

- **活跃**：被现行流程引用（repack.sh/boot.json/AGENT-COORDINATION.md）或 18:00+ 修改；
- **参考**：文档、快照、取证照片（只读价值，不进入构建）；
- **归档**：`archive\` 内一切，只增不删。

## 敏感文件·待用户处置（只登记，不动不复制）

| 文件 | 类型 | 位置 |
|---|---|---|
| `grok 1104.txt` | x.ai OAuth 凭据明文（含 refresh_token） | `D:\` 根目录 |
| `dahl-credentials.txt` | 凭据文件 | `D:\` 根目录 |

**请尽快移出盘根并轮换对应 token/凭据**；本区任何脚本不得读取、复制或引用这两个文件。
