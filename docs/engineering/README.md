# 工程文档索引

本目录是从开发工作区同步过来的工程实践记录，按主题分类。

## 核心文档

| 文件 | 内容 |
|---|---|
| [HARD-RULES.md](HARD-RULES.md) | 铁则 ★1–★32（从踩过的坑提炼的可执行规则） |
| [PITFALLS.md](PITFALLS.md) | 坑记录 P-01–P-127，每条含症状、根因、判据、教训 |
| [PITFALL-TO-RULE-INDEX.md](PITFALL-TO-RULE-INDEX.md) | 坑 → 铁则反查表 |
| [TOOLBOX.md](TOOLBOX.md) | 可复用工具与脚本清单 |
| [PLAYBOOKS.md](PLAYBOOKS.md) | 操作手册 PB-1–PB-10 |

## 硬件真值

| 文件 | 内容 |
|---|---|
| [ANDROID-HW-TRUTH.md](ANDROID-HW-TRUTH.md) | Android 实机实测的硬件真值表（协议、寄存器、固件路径） |
| [K60-TOUCH-DT-EVIDENCE.md](K60-TOUCH-DT-EVIDENCE.md) | K60 触摸节点的 DT 权威数据 |
| [K60-TOUCH-CHECKLIST.md](K60-TOUCH-CHECKLIST.md) | 触摸八步核对清单 |
| [TOUCH-STATEMACHINE.md](TOUCH-STATEMACHINE.md) | 官方 Goodix 驱动的状态机提取 |

## 环境与资产

| 文件 | 内容 |
|---|---|
| [ENVIRONMENT.md](ENVIRONMENT.md) | 构建环境、工具链路径 |
| [LOCAL-ASSETS.md](LOCAL-ASSETS.md) | 本地资源索引（参考仓库、固件、镜像） |
| [REPO-INVENTORY.md](REPO-INVENTORY.md) | 全部 git 仓库清单与用途 |

## 为什么公开这些

这些文档记录的是**具体的失败与修正**，不是教科书式的通用建议。
每条坑都带 `文件:行号` 或日志原文作为依据，目的是让后来者不必重复同样的错误。

如果你在做同类移植（高通 SoC + iOS/iPadOS），以下几条最省时间：

- `PITFALLS.md` 的 **P-117**：嵌入式 init 二进制 `__TEXT` 超过 1 页就开不了机
- `PITFALLS.md` 的 **P-118**：boot-args 缺 `debug=0x140` 时日志为 0 字节（看起来像死机）
- `PITFALLS.md` 的 **P-126**：用脚本生成补丁时 `\n` 会被解释成真换行，补丁静默损坏
- `HARD-RULES.md` 的 **★32**：跟进上游必须覆盖全部分支，单分支 refspec 会漏掉关键修复
