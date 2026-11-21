# 拟议补丁（未进入系列）

`patches/proposed/` 放**还没有被纳入任何 series 的草案**。和 `patches/xnu/`
不同，这里的东西不会被构建脚本读取，`patches/xnu/series` 也不引用这个目录；
它的唯一作用是让一条独立缺陷有独立的 diff，不和文档改动混在一起。

命名：`NNNN-<scope>-<slug>.patch`，正文用 `Subject: [PATCH] …` + 为什么 +
影响面，末尾 `---` 之后才是 diff（`git apply --check` 必须能过）。

| 草案 | 状态 | 说明 |
| --- | --- | --- |
| `0001-k60-backlight-log-requested-level.patch` | **等真机判据**（Lead 2026-11-21T16:58 + 18:26） | `K60Backlight.cpp:416-417` 把 `goal` 打了两次，日志无法区分请求值与等级；27 的证据行要读这个字段。进系列的条件是预写判据 `docs/research/display/BACKLIGHT-LOG-CRITERIA.md` 在真机上通过（看到 B 形行两字段分开），飞行由 Lead 排期，本线不等 |
| `0002-k60-backlight-let-the-backend-decide.patch` | **等会签后同批**（Lead 2026-11-21T18:26，**仅 27 分支**） | 把 `:339` 的默认从 1 翻 0，`k60_backlight_control=1` 仍可覆盖；判据与理由见 `docs/research/display/DISPLAY-27-DELTA.md` §6。**这是行为改变不是优化**，16.6.1 的封闭系列不得取此补丁。不单独进系列：等 27 显示契约会签完成，与 wire v2 同批提交 |
| `0003-k60-backlight-probe-the-clamp.patch` | **等字节裁决**（Lead 2026-11-21T19:12 批准探针，参数本身超预算） | `publishFirst()` 末尾（`K60Backlight.cpp:382` 后）在 `k60_backlight_probe=1` 时自走一次 `{brightness: 4095}`，让 `0001` 的判据 C3 从「等 OS 发越界值」变成「自己问一次」；**必须叠在 0001 上**，单独打只会把 2047 打两次。判据见 `docs/research/display/BACKLIGHT-LOG-CRITERIA.md` §8，字节账见 §8.5（21 B 字符 + 1 空格 = 22 B，603 → 625 超 18 B；压到 `k60bl_probe=1` 仍超 12 B）。进系列前先定字节来源 |
| —（原本的 R4 草案） | **撤回** | 原以为 `setProperties()` 落空分支会用未初始化 `goal` 去 `publish()`；复核 HEAD 后不成立，`:402-404` 已经是 `return kIOReturnSuccess`。详见 `docs/research/display/DISPLAY-27-DELTA.md` §10 R4 |

提交一个草案时：不要顺手改 `patches/xnu/series`，那是 `xnu` 线的文件；
显示线只提供 diff 与判据。
