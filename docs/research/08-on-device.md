# 触摸 ⑧ 真机验证记录

| 轮次 | 镜像 sha256 | 内核 sha256 | 结果 | 证据 |
|---|---|---|---|---|
| 1 | — | — | ADT 无节点 → `missing/incompatible Pong DT` | `usblog-20261108-180257` |
| 2 | — | — | ADT 有节点 → `Pong touch: ...` 消失（gate 拦截） | `usblog-20261108-182056` |
| 3 | — | — | 触摸启用 + ADT → `kmem_alloc(458752) failed`（GCC 448 KB） | `usblog-20261108-192302` |
| 4 | — | `a2ea0f2e` | 触摸关闭 → 无 kmem 失败、进 SpringBoard | `usblog-20261108-193525` |
| 5 | — | `49245760` | **新 libpong-ui 生效**：`Pong UI: ... entered SpringBoard`；用户态 `real touch device unavailable (Operation timed out)` | `usblog-20261108-210018` |
| 6 | 待填 | 待填 | gate 修复后：期望 `Pong touch: ...` + `/dev/pong-touch` 出现 + `Pong touch HID: display-integrated digitizer opened` | 待测 |
