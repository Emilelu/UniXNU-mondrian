# docs/ops —— 2026-11-12 上游快照，不是本项目权威

本目录的两份文件是 **2026-11-12 从 `yibiya/UniXNU-mondrian` pick 88 个提交（`97b84eb7`）时一起带进来的上游文档**，
不是本项目自己维护的清单，也不在本项目的编号体系里。

| 文件 | 实际是什么 | 权威版本在哪 |
|---|---|---|
| [HARD-RULES.md](HARD-RULES.md) | 上游 12 条「HR-NN」规则（467 行）。其中 HR-01「默认禁止访问 RSC」已被 `docs/engineering/HARD-RULES.md` 的 ★7 推翻 | [`docs/engineering/HARD-RULES.md`](../engineering/HARD-RULES.md)（★1–★37） |
| [PITFALLS.md](PITFALLS.md) | 上游坑台账（1,169 行），编号只到 **P-76**，与本地 P 编号空间冲突 | [`docs/engineering/PITFALLS.md`](../engineering/PITFALLS.md)（P-01–P-230） |

**为什么留着**：它们是上游同一时期的原始记录，对比两边可以看出一件事在本仓被重新判断过没有；
删掉就失去了对照。**为什么不能拿它当依据**：同一编号在两份文件里指的不是同一个坑，照抄会引错结论。

第三份同源副本是 [`docs/reference/PITFALLS.md`](../reference/PITFALLS.md)（148 行）。

历史与判据见 [`docs/audits/PORTING-GAP-AUDIT-2026-11-16.md`](../audits/PORTING-GAP-AUDIT-2026-11-16.md) 的 §3。
