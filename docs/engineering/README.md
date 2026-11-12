# 工程文档索引

本目录是 K60 移植的核心工程文档，按主题分类。

> 最后更新：2026-11-12。本文件由 `scripts/check-docs.py` 校验：
> 目录下每个 `.md` 都必须在此登记。

---

## 一、现状与流程

| 文件 | 内容 |
|---|---|
| [STATUS.md](STATUS.md) | **当前硬件状态明细** + 2026-11-11/11-12 变更记录（README 的详细版） |
- [`BOOT-ARGS.md`](BOOT-ARGS.md) —— 每个 boot 参数的接受值、默认与陷阱；608 字节预算；三个 GPU 开关的串行依赖。
| [EIGHT-STEP-SPEC.md](EIGHT-STEP-SPEC.md) | **八步流程规范**：① 同型 ② 官方 ③ 反编译 ④ 广域 ⑤ 方案 ⑥ 深挖 ⑦ 核验 ⑧ 上机。每步含目的/必做/证据格式/通过条件/反模式 |

## 二、规则与坑

| 文件 | 内容 |
|---|---|
| [HARD-RULES.md](HARD-RULES.md) | 铁则 ★1–★35，每条含来源、硬规则、判别方法 |
| [PITFALLS.md](PITFALLS.md) | 坑记录 P-01–P-130：症状 → 真因 → 判别 → 教训 |
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
| [LOCAL-ASSETS.md](LOCAL-ASSETS.md) | 本地资源索引（参考仓库、固件、镜像） |
| [REPO-INVENTORY.md](REPO-INVENTORY.md) | 全部 git 仓库清单与用途 |

## 五、本目录

| 文件 | 内容 |
|---|---|
| `README.md` | 本索引 |
| [`REPO-MAP.md`](REPO-MAP.md) | 仓库与目录登记表：三个组件仓库路径、构建副本、yibiya 镜像、打镜像该用哪个 DTB |
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
