# Pitfall number allocation

Three lanes claimed `P-283` on 2026-11-20 (wifi registered it in its own
`RULES.toml`, cellular and audio wrote it into their documents). None of them
could see the others: each works in its own worktree and `scripts/next-pitfall-id.py`
reads only `origin/main` of *that* worktree, where the largest number is still
`P-282`. That is a coordination gap, not a lane error, so from now on the Lead
allocates numbers in this file and the lanes read it before writing one.

| id | owner | subject |
| --- | --- | --- |
| P-281 | lead | a counter is named after what it is summed from |
| P-282 | lead | a label the toolchain cannot emit is not the loader's fault |
| P-283 | wifi | an archive that passes arch/provenance can still be a stub container |
| P-284 | cellular | a preflight that must stay pending cannot borrow the flight ledger's verdict |
| P-285 | audio | a bare `void *` across an io boundary compiles and links; only a type pair does not |
| P-288 | 官方页审计覆盖率 | lead | 2026-11-21 |
| P-289 | 门禁自身语义 | lead | 2026-11-21 |
| P-290 | 门禁自身语义 | lead | 2026-11-21 |
| P-291 | 流程（先读参考源） | lead | 2026-11-21 |
| P-292 | 基线（残留计数） | lead | 2026-11-21 |
| P-293 | 流程（官网页出处） | lead | 2026-11-21 |
| P-294 | 证据（候选哈希≠产物哈希） | lead | 2026-11-21 |
| P-295 | 度量（量错一组=量错全部） | lead | 2026-11-21 |
| P-296 | 语义（缺席值落在合法值域内） | gpu27 | 2026-11-21 |
| P-301 | 构建（开关未到编译器） | lead | 2026-11-21 |

Rules:

1. Ask for the number in the message you report to the Lead; do not take one from
   `next-pitfall-id.py` while `main`'s maximum is behind another lane's work.
2. The number is reserved here first, then landed in `RULES.toml` and
   `PITFALLS.md` by whoever owns the lane, on the lane's own branch.
3. This file is the only place that records a reservation; a number that appears
   nowhere here is not allocated, and `scripts/check-pitfall-numbers.py` treats a
   duplicate as a failure.
| P-303 | 门禁（不可 import 的死代码） | lead | 2026-11-21 |
| P-302 | 门禁（账本选错操作系统） | lead | 2026-11-21 |
| P-304 | 门禁（路径锚点） | lead | 2026-11-21 |
| P-305 | 预链接 / 合规对照 | lead | 2026-11-22 |
| P-306 | 预链接（root 列表） | lead | 2026-11-22 |
