# AOCI-CODE 评估：能否作为本项目的全局认知索引

调研日期 2026-11-23（冻结期，未构建、未上机）。对象：<https://github.com/aoci-spec/aoci-code>（v0.2.0-rc3）。

## 1 它是什么

AOCI-CODE 是一个 Go 单二进制 + stdio MCP Server，用「模型给每个受管文件写一条 FRAS 语义条目」的方式，产出一份**随仓库保存、可 Git 版本化、可治理**的系统认知索引：

- `aoci.txt`：Root，声明参与当前 CognitionSet 的 Volume；
- `aoci.meta.txt`：标签字典、FRAS 规则、配额、创作约束；
- `aoci.code.txt`：每个受管对象的条目，格式 `file[标签]: F:职责 | R:强关系 | A:公开接口 | S:非显然约束`；
- `.aoci/`：config、baseline、curation、ledger（默认不进 Git）。
- MCP 固定 9 个工具：`aoci_rules`、`aoci_overview`、`aoci_get_entries`、`aoci_search`、`aoci_maintain`、`aoci_update_entry`、`aoci_remove_entry`、`aoci_header`、`aoci_report`。
- 治理：Managed Scope、Baseline、漂移检测（Missing/Orphan/Stale/Unbaselined）、Plan→Stage→Check→Diff→CAS→原子写→Recovery，`aoci verify` / `aoci check` / `aoci index agent guide`，以及只读回环面板 `aoci ui`。

## 2 本机实测（不是读文档得来的）

二进制：`E:\k60-work\tools\aoci\aoci.exe`，`aoci version 0.2.0-rc3 (commit 0a00a2b9…)`，zip sha256 `0a342721…`（与 Release `SHA256SUMS` 一致），exe sha256 `d5e74716…`。

| 实测项 | 结果 |
| --- | --- |
| 下载 + 校验 + 解压 | 通过（`gh release download v0.2.0-rc3`，`SHA256SUMS` 匹配） |
| `aoci --version` | `0.2.0-rc3` |
| MCP stdio 握手 | 成功：`serverInfo {name: aoci-code, version: 0.2.0-rc3}`，`tools/list` 返回 9 个工具，`aoci_rules` 正常返回合同文本 |
| 试点仓（139 文件，仅 docs+2 脚本）`init` | 121 个 index 文件、`estimated_whole_index_tokens=15110`、约 47k 行、4 轮 Maintain |
| 试点仓 `scan` | 127 文件，**175 ms** 建立基线 |
| 真实仓克隆（1,803 个跟踪文件）`init` | `index=1555 / observe=212 / exclude=36 / safety_excluded=22`、`estimated_whole_index_tokens=172850`、38 轮 Maintain |
| 真实仓加排除规则后 `scan` | `index=1058`（排除 `patches/**/*.patch`、`firmware/`、`out/`），**1,048 个条目 / 217,681 行 / 24 轮 Maintain（每轮 ≤50 条）/ 3 路并行约 11 轮** |
| `aoci verify --json` | `structure_valid=true`、`governance_aligned=false`（空索引，1048 条待写）、`layout_mode=volumes-v1` |
| `init` 对现有 `AGENTS.md` | **追加** 104 行 `<!-- aoci:... -->` 区块，原内容未动；另生成 `AGENTS.md.backup.<时间戳>.<sha>` |
| `init` 对仓库其它文件 | 改 `.gitignore`（+4 行）、写 `.gitattributes`（强制 LF）、生成 `aoci.txt`/`aoci.meta.txt`/`aoci.code.txt` |

## 3 与我们的需求对得上吗

需求：把散落在 `docs/research/**`、`docs/engineering/**`、`board.toml`、`patches/*/series`、以及 9 个参考源仓库里的知识，整合成一份**持久、可治理、可版本化**的项目认知地图。

**对得上的：**
- 持久 + 可治理 + 可版本化：索引就是仓库里的明文文件，Git diff/审查/回滚都成立；这正好补上我们现在「文档散、靠人记、靠门禁断言」的短板。
- 漂移检测：`aoci verify` 能列出 Missing/Orphan/Stale/Unbaselined；我们现在的 `check-docs.py` 只查链接和编号，查不出「文档说的和代码不一致」。
- 大规模可交付：Whole-Index 分 Chunk 交付（`chunk_tokens` 4000–24000），不会一次性塞爆上下文；`aoci_search`/`aoci_get_entries` 支持按需取条目。
- 与宿主解耦：stdio MCP 已实测可用，不绑定具体模型厂商。

**对不上的（必须正视）：**
1. **一仓一索引**：AOCI 没有「跨仓库」概念。9 个参考源仓库要各自 `init`，或者把它们的知识以文档形式沉淀进主仓（我们现在的 `docs/research/**` 就是干这个的）。`aoci ui --also` 只是同页查看多个仓库，不合并治理。
2. **没有「外部参考源」原语**：参考源只能写成我们文档里的 FRAS 条目（R 字段写 `repo@commit path:line`），AOCI 不会自己去扫外部仓库。
3. **索引成本**：真实仓全量 1,048 条、217,681 行、24 轮 Maintain；按当前批次预算（每轮 50 条 / 24 KiB）是几小时的活。**必须先划 Scope**，否则 1,555 条里 279 个补丁正文会把 token 全吃光。
4. **许可证**：FSL-1.1-MIT（Fair Source，source-available）。自用没问题，但不能拿它做对外竞争服务；商用分发前要法务确认。
5. **它不能替代我们的门禁**：AOCI 自己说得很清楚——「绿色结果证明已编码的结构和治理条件成立，不证明语义一定正确」。我们的 `check-rules.py`、八步门禁、`check-series-order.py` 仍然是验收真相。

## 4 建议的落地架构（三层）

```
L0  验收真相（保持不变）：check-rules.py / 八步门禁 / check-series-order / check-docs …
L1  AOCI 认知索引（新增）：只覆盖「人读的知识面」
      docs/**  +  scripts/*.py  +  board.toml  +  patches/*/series（只读 series 文件名，不读 .patch 正文）
      exclude: patches/**/*.patch、firmware/**、out/**、*.bin、*.img、*.zip
L2  参考源摘要（已有）：docs/research/{wifi,audio,battery,display,cellular,ios27}/… 每条 FRAS 的 R 字段指向参考源 repo@commit file:line
```

**为什么不把 9 个参考仓各建一份索引**：成本 ×9，而且它们的价值已经被我们抄进 `docs/research/**` 与 `PRECEDENT-MANIFEST.toml`；真正需要索引的是「我们自己的知识面」。等 GPU 线重开、需要逐条判 140 个 mesa/metal2vulkan 补丁时，再单独给 t970/pong 建临时索引。

## 5 分阶段计划与验收

| 阶段 | 动作 | 验收 |
| --- | --- | --- |
| P0（已完成） | 下载/校验/试点 init+scan+MCP 握手 | 本文第 2 节 |
| P1 | 在 k60-gates 的**克隆**上按第 4 节 Scope 跑完整索引（24 轮） | `aoci verify` 的 `governance_aligned=true`；`aoci index score` 的 coverage bad=0 |
| P2 | 评审 `aoci.code.txt` 的前 20 条，确认 FRAS 质量（F/R/A/S 是否真是「非显然」信息） | 人工抽检通过；与 `docs/INDEX.md` 无二义 |
| P3 | 合入仓库（提交 `aoci.*.txt`，`.aoci/` 入 `.gitignore`），`AGENTS.md` 的 aoci 区块与现有铁则并存 | `check-docs.py`、`check-line-endings.py`、`check-rules.py` 全绿 |
| P4 | 接 MCP（dsh 侧配置），每轮任务收尾调 `aoci_maintain` 增量维护 | 连续 3 次任务后 `governance_aligned` 仍为 true |

**回滚**：删 `aoci*.txt`、`.aoci/`、`AGENTS.md` 的 aoci 区块即可；索引是纯文本，无外部状态。

## 6 已知风险与对策

| 风险 | 对策 |
| --- | --- |
| `AGENTS.md` 被追加 104 行规则，可能与铁则冲突 | 先只读 diff；冲突处以铁则为准，必要时在 aoci 区块前写「本区块不得覆盖上方铁则」的说明 |
| `.gitattributes` 强制 LF 改变行尾 | 我们已有 `check-line-endings.py`（P-186 教训），init 后必须跑一次 |
| 索引 token 预算 172,850（全量）过大 | 按第 4 节排除补丁正文；必要时把 `scripts/tests` 设为 observe |
| 首次索引要几小时 | 分批 Maintain，可中断续做；`remaining` 非 0 就继续 |
| 参考源知识没进索引 | 由 `PRECEDENT-COVERAGE.md` 的审计保证：167 个未入账补丁判完后，所有参考知识都在 `docs/research/**` 里有落点 |

## 7 结论

**值得采用，但定位要准确**：AOCI-CODE 适合当「项目认知层」（L1），不适合当「验收层」（L0），也不适合直接当「跨仓参考源索引」（它没有这个概念）。

对我们的直接价值是把现在散在 20+ 个 md 文件里的「为什么这么改、谁依赖谁、什么不能碰」变成一份**每个受管文件一条、带漂移检测、可 Git diff** 的索引，正好回答用户提出的「确保建立软件项目全局认知的索引方法」。

代价是一次性的 24 轮索引创作（约几小时）与每轮任务收尾的增量维护；相比每次新会话重新翻 1527 条账本、40 万行文档，这是划算的。

## 8 待用户决定

1. 是否按第 4 节的 Scope 在克隆上跑 P1（不碰主仓，索引完成后你审 `aoci.code.txt`）；
2. 是否接受 FSL-1.1-MIT 许可证用于本项目；
3. 是否把 `aoci.*.txt` 纳入 Git（这会让每次任务多一个可审查的 diff）。
