# 工程文档索引

本目录是 K60 移植的核心工程文档，按主题分类。

> 最后更新：2026-11-16。本文件由 `scripts/check-docs.py` 校验：
> 目录下每个 `.md` 都必须在此登记。
>
> 当前决策先读[2026-11-16 重新审视](../audits/REASSESSMENT-2026-11-16.md)：历史通过、当前实验与门禁实际覆盖必须分别核对。

---

## 一、现状与流程

| 文件 | 内容 |
|---|---|
| [STATUS.md](STATUS.md) | **当前硬件状态明细** + 重新审视结论 + 历史变更记录（README 的详细版） |
| [IOS27.md](IOS27.md) | **iOS 27.0.1 线**：iPhone 16 Pro Max（iPhone17,2）、arm64e 4 KiB、xnu-12377 + Darwin 26、F0–F4 阶段门、IPSW 与 kernelcache 哈希 |
| [BOOT-FREEZE.md](BOOT-FREEZE.md) | **上机冻结**：`state = "frozen"` 时任何 `fastboot boot` 被拦；解冻要同时满足五条件，环境变量不可绕过 |
| [OFFICIAL-STEPS.toml](OFFICIAL-STEPS.toml) | **铁则 17 的步骤账本**：每条流水线命令对应的官方页与锚点，由 scripts/check-official-steps.py 校验 |
| [IOS27-REFERENCE-FIRST.toml](IOS27-REFERENCE-FIRST.toml) | **铁则 16 的读数账本**：每个仍 open 的飞行阻塞至少两条参考源读数（仓/文件/行/它怎么解决/我们的处置），由 `scripts/check-reference-first.py` 校验路径与行号能否当场解析 |
| [LANE-CONTRACT-ios27.md](LANE-CONTRACT-ios27.md) | 七条车道的统一约定：参考源先行（iron-16）、官网页锚点（iron-17）、八步①②–⑦、禁构建/禁上机/禁写共享树。 |
| [IOS27-DRIVER-ARCH.md](IOS27-DRIVER-ARCH.md) | 27 每个硬件层的架构归属：官方 sheng/官文优先，只有硬件不同导致抄不了的才参考同 SoC；pong 谱系不作架构来源。 |
- [`BOOT-ARGS.md`](BOOT-ARGS.md) —— 每个 boot 参数的接受值、默认与陷阱；608 字节预算；三个 GPU 开关的串行依赖。
| [EIGHT-STEP-SPEC.md](EIGHT-STEP-SPEC.md) | **八步流程规范**：① 同型 ② 官方 ③ 反编译 ④ 广域 ⑤ 方案 ⑥ 深挖 ⑦ 核验 ⑧ 上机。每步含目的/必做/证据格式/通过条件/反模式 |
| [FIRMWARE-REBUILD.md](FIRMWARE-REBUILD.md) | **固件卷重建手册**：构建入口、为什么同一个 pin 三次重建得三个哈希（P-216）、`Mu_Basecore` 必须停在记录的 pin 上（P-217）、现场四个卷、P-154 已关闭、下次重建的五步实验协议、DarwinBoot 只认固定属性名的硬约束 |
| [BOOT-PROCEDURE.md](BOOT-PROCEDURE.md) | **启动流程唯一入口**（铁则 8）：门禁 → 先挂 CDC-ACM 串口抓取 → `fastboot boot`；"控制台没出现"= 早启动挂死的硬证据；含二分回退配方 |
| [IOS-SCOPE.md](IOS-SCOPE.md) | **iOS 迁移边界**（用户 2026-11-19 决定）：只保留可转移的活。本机四棵 SM8475 树里只有我们在 iOS 16，参考栈在 17.7.11–18.7.10；含可转移/停止清单、判据三条、迁移面统计 |

## 二、规则与坑

| 文件 | 内容 |
|---|---|
| [HARD-RULES.md](HARD-RULES.md) | 铁则 ★1–★37，每条含来源、硬规则、判别方法 |
| [PITFALLS.md](PITFALLS.md) | 坑记录 P-01–P-254：症状 → 真因 → 判别 → 教训 |
| [PITFALL-IDS.md](PITFALL-IDS.md) | 坑号分配表：号码由 Lead 统一分配；各线只看得到自己 worktree 的 `origin/main`，2026-11-20 三条线各写了一个 P-283 |
| [`LINE-MAP.md`](LINE-MAP.md) | 逐行的“谁在做什么”地图：每条 bring-up 线的源码、补丁、证据与负责人 |
| [GPU-IOSURFACE-ROOT-CAUSE.md](GPU-IOSURFACE-ROOT-CAUSE.md) | GPU Metal 根因：用户态按注册名找 `IOSurfaceRoot`，mini 实现注册成 `IOCoreSurfaceRoot` |
| [PITFALL-TO-RULE-INDEX.md](PITFALL-TO-RULE-INDEX.md) | 坑 → 铁则反查表 |
| [TOOLBOX.md](TOOLBOX.md) | 可复用工具与脚本清单 |
| [PLAYBOOKS.md](PLAYBOOKS.md) | 操作手册 PB-1–PB-10 |

## 三、硬件真值

| 文件 | 内容 |
|---|---|
| [ANDROID-HW-TRUTH.md](ANDROID-HW-TRUTH.md) | Android 实机实测的硬件真值（协议、寄存器、固件路径）。**注意 GTP 结论已被 P-129 推翻** |
| [K60-TOUCH-DT-EVIDENCE.md](K60-TOUCH-DT-EVIDENCE.md) | K60 触摸节点的 DT 权威数据 |
| [K60-TOUCH-CHECKLIST.md](K60-TOUCH-CHECKLIST.md) | 触摸八步核对清单 |
| [TOUCH-STATEMACHINE.md](TOUCH-STATEMACHINE.md) | 官方 Goodix 驱动状态机逐段提取（481 行） |

## 四、环境与资产

| 文件 | 内容 |
|---|---|
| [ENVIRONMENT.md](ENVIRONMENT.md) | 构建环境、工具链路径、SSH 主机 |
| [DISK-HYGIENE.md](DISK-HYGIENE.md) | 磁盘卫生：空间门禁判据（hard-41）、回收顺序、WSL 虚拟盘压缩（需管理员） |
| [AGENT-BUS.md](AGENT-BUS.md) | 协作通道：`scripts/k60-bus.py` 消息总线、游标、与 reply md 的分工 |
| [BRANCH-INVENTORY-20261119.md](BRANCH-INVENTORY-20261119.md) | **分支全量盘点**（2026-11-19）：49 条未合入 main 的分支逐条编号，含 ahead/behind、文件数、内容、证据、被谁包含（git 祖先实测）与建议动作；用户逐条确认后按「先合 → 门禁全绿 → 删已合并」执行 |
| [LOCAL-ASSETS.md](LOCAL-ASSETS.md) | 本地资源索引（参考仓库、固件、镜像） |
| [REPO-INVENTORY.md](REPO-INVENTORY.md) | 全部 git 仓库清单与用途 |

## 五、本目录

| 文件 | 内容 |
|---|---|
| `README.md` | 本索引 |
| [`REPO-MAP.md`](REPO-MAP.md) | 仓库与目录登记表：三个组件仓库路径、构建副本、yibiya 镜像、打镜像该用哪个 DTB |
| [`../research/SUBAGENT-DELIVERABLES.md`](../research/SUBAGENT-DELIVERABLES.md) | Subagent 交付物台账：每条调研必须有落库文件 + 产出断言 + 提交（铁则 8）|
| [`BATTERY-INTEGRATION.md`](BATTERY-INTEGRATION.md) | 电池栈编译集成：构建脚本 4 处改动、defconfig 开关、宏链路、归档构建时机、无 PAS1 时的运行时行为 |
| [`TAGS.md`](TAGS.md) | tag 策略：只允许 boot-proven / main 基线 / 版本里程碑三种 tag，每轮时间戳 tag 被门禁拒绝 |
| [`DIVISION-OF-LABOR.md`](DIVISION-OF-LABOR.md) | 上下游分工 + 仓库覆盖：23 个跟踪 / 48 个同步 / 3 个 pick，以及为什么 fork 与参考实现处理方式不同 |
| `../scripts/check-build-freshness.py` | 构建新鲜度门禁：框架副本一致 / 固件不旧 / 产物齐备；`--manifest` 记录各组件 sha256 |
| `../scripts/check-snapshot-tag.py` | 快照门禁：启动相关改动前必须有已推送的 snap-* tag（铁则 7）|

---

## 阅读顺序

**新接手**：STATUS.md → EIGHT-STEP-SPEC.md → HARD-RULES.md → PITFALLS.md

**要做触摸/GPU**：先读 `../research/EIGHT-STEPS.toml` 对应章节（⑦ 未通过不得刷机），
再读本目录的 K60-TOUCH-*.md / TOUCH-STATEMACHINE.md。

## 最省时间的几条

如果你在做同类移植（高通 SoC + iOS/iPadOS），以下几条能直接省掉几天：

- **P-117**：嵌入式 init 二进制 `__TEXT` 超过 1 页（16,384 B）就开不了机，症状是日志 0 字节 + 自动复位
- **P-118**：boot-args 缺 `debug=0x140` / `applog=1` 时日志为 0 字节，看起来像死机
- **P-126**：用脚本生成补丁时 `\n` 会被解释成真换行，补丁静默损坏，`git apply` 只报 `git failed (128)`
- **P-129**：不能从驱动文件名/模块名推断协议，只能实测寄存器
- **P-130**：手工搬运 fork 里的代码会丢失 GitHub contributors 署名
- **★32**：跟进上游必须覆盖全部分支，单分支 refspec 会漏掉关键修复
- **★34**：同 SoC 兄弟移植的记录优先于官方通用驱动
- [OFFICIAL-REQUIREMENTS.toml](OFFICIAL-REQUIREMENTS.toml) — 官网每页一条要求（铁则 13）
- [UPSTREAM-REPOS.toml](UPSTREAM-REPOS.toml) — 参考仓库与同步基线（铁则 15）
