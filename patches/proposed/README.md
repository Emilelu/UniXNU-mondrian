# 拟议补丁（未进入系列）

`patches/proposed/` 放**还没有被纳入任何 series 的草案**。和 `patches/xnu/`
不同，这里的东西不会被构建脚本读取，`patches/xnu/series` 也不引用这个目录；
它的唯一作用是让一条独立缺陷有独立的 diff，不和文档改动混在一起。

命名：`NNNN-<scope>-<slug>.patch`，正文用 `Subject: [PATCH] …` + 为什么 +
影响面，末尾 `---` 之后才是 diff（`git apply --check` 必须能过）。

| 草案 | 状态 | 说明 |
| --- | --- | --- |
| `0001-k60-backlight-log-requested-level.patch` | 待裁 | `K60Backlight.cpp:416-417` 把 `goal` 打了两次，日志无法区分请求值与等级；27 的证据行要读这个字段 |
| —（原本的 R4 草案） | **撤回** | 原以为 `setProperties()` 落空分支会用未初始化 `goal` 去 `publish()`；复核 HEAD 后不成立，`:402-404` 已经是 `return kIOReturnSuccess`。详见 `docs/research/display/DISPLAY-27-DELTA.md` §10 R4 |

提交一个草案时：不要顺手改 `patches/xnu/series`，那是 `xnu` 线的文件；
显示线只提供 diff 与判据。
