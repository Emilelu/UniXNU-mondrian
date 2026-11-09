# 触摸 ⑦ 核验结论

> 状态：◐ 部分核验。证据等级逐条标注。

| # | 结论 | 等级 | 核验方式 | 结果 |
|---|---|---|---|---|
| 1 | `GOODIX-TOUCH-PORT.md §3.1` 称补丁断言 14400/32000 | **文档** | `grep 'max_x==' patches/xnu/zzzz…pong-touch-console.patch` → 第 65 行 `max_x==1080 && max_y==2412` | ❌ **文档错误**，已记录待更正 |
| 2 | K60 触摸节点在 live FDT 中存在且属性如上 | **实测** | `K60-TOUCH-PARAMS.md` 解析 + sha256 `95c02052…` | ✅ |
| 3 | pong 驱动 `configuration()` 在 ADT 有节点时通过 | **实测** | ADT 15,304 B 含 `pong-touch@13296`；boot 日志不再报 `missing/incompatible` | ✅（但驱动仍被 gate 拦住） |
| 4 | `PE_parse_boot_argn` 缺参数返回 FALSE 导致 return | **实测** | 代码 `if (!PE_parse_boot_argn(...)) return;` + 日志无任何 `Pong touch:` 输出 | ✅ 根因确认 |
| 5 | 修复 gate 后 `/dev/pong-touch` 会出现 | **推断** | 待真机验证（见 09） | ⏳ |

## 待更正文档

- `docs/plans/GOODIX-TOUCH-PORT.md §3.1` 第 1 点：断言值应为 **1080/2412**（不是 14400/32000）。已在本目录 07 记录。
