# 参考源身份表（谁是我自己的 fork）

日期：2026-11-22
触发：用户 m60074 / m60100 ——「ZxbMsl160918 是 fork 我仓库的啊，K60 所有 unixnu 仓库全都是 fork 我的，每次都不去确认？」

## 用 GitHub API 实测（`GET /repos/<owner>/<repo>` 的 `fork` 与 `parent.full_name`）

| 仓库 | fork | 父仓库 |
| --- | --- | --- |
| `Emilelu/UniXNU-mondrian` | false | — （本仓） |
| `ZxbMsl160918/UniXNU-mondrian` | **true** | `Emilelu/UniXNU-mondrian` |
| `mzyxsl/UniXNU-mondrian` | **true** | `Emilelu/UniXNU-mondrian` |
| `xtom0706/UniXNU-mondrian` | **true** | `Emilelu/UniXNU-mondrian` |
| `xNekom/UniXNU-mondrian` | **true** | `Emilelu/UniXNU-mondrian` |
| `yibiya/UniXNU-mondrian` | **true** | `Emilelu/UniXNU-mondrian` |
| `kmu1757/UniXNU-t970` | false | — （独立作者的 t970 移植） |

| `dddqmmx/UniXNU-sirius` | **true** | `57UU/UniXNU-sirius` |
| `57UU/UniXNU-sirius` | false | —（created 2026-10-23，独立移植线） |

`sirius` 是别人（57UU）的独立移植线，`dddqmmx` 只是它的 fork ⇒ **可作外部参考**；但它跑 17.7.11 不是 27，只能作「机制可行」证据，不能作「27 上可成立」的证据（2026-11-22 input27 实测，记此以免下次又当第三方）。

（`whohusaixing/UniXNU-mondrian` 查询返回空，需要重查；未确认前不得引用。）

## 由此产生的硬规则

1. **自己 fork 的仓库不得作为「第二来源/独立证据」。** 它们能证明的只有「我某个时间点的状态被某个 agent 抄走了一份」，不能证明实现正确。
2. 引用任何 `github.com/<owner>/<repo>` 或 `unixnu.com/devices/mondrian-*` 页之前，先在本表查身份；不在表里就先 `GET /repos/...` 查 `fork` 字段，并把结果补进表里。
3. 「同 SoC 的其他机型」（`UniXNU-t970`、`zizhan`、`UniXNU-sheng`）才是外部参考；其中 sheng 的 27 线是**唯一**与自己同 OS profile 且独立来源的实现。
4. 已在 `docs/research/ios27/OFFICIAL-DEVICE-PAGES.md` 顶部登记 `mzyxsl` 的更正；`ZxbMsl160918` 的引用同样降级为「自身状态记录」。

## 待办

- `scripts/check-source-provenance.py`：扫描 `docs/**` 里出现的仓库/设备页引用，要求命中本表且 `own-fork` 的条目不得带「第二来源/独立/第三方」措辞。
- 把 `whohusaixing` 的查询结果补齐。

## 系列条目数的口径（2026-11-22 input27 提问后定）

我先前写「27 系列 34 条」是把文件里出现的所有 `.patch` 字符串都算上（含注释里提到的）；`input27` 在本仓 HEAD 数到 **30 条非注释行**。两者都不是判据——**以 `python3 scripts/check-series-numbering.py` 的输出为准**，它只数真实生效的条目。以后写这类数字必须注明「用什么命令数的」。
