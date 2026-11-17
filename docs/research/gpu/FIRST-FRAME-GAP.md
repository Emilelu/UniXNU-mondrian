# 首帧缺口：Metal 设备出现后 UI 表面管线整条不再启动

日期：2026-11-18

对照两飞（同一内核族，唯一变量是 `pong_metal` 与插件注入）：

| 镜像 | pong_metal | `MiniIOSurface` 行 | `first frame presented` | `Pong Metal: S` |
|---|---|---|---|---|
| `usblog-20261116-164726` | 2（软件） | 1（2 个大 surface，8901 us 每个） | 1（`swap 2, 1440x3200 canvas`） | 无插件 |
| `usblog-20261118-003847` | 1（插件注入 backboardd） | **0** | **0** | `c0/0 d0 p0 x3` |

结论：插件注入 backboardd 之后，`MiniIOSurface` 一个都没创建、`show()` 也没出过帧。
所以 `p0` 不是「GPU 提交失败」，而是**上游的 UI 表面管线根本没启动**；SpringBoard
主线程 `turns=0` 也与此一致（它在等一个永远不会来的首帧握手）。

下一步（离线可查）：
1. 看 `iokit/Kernel/MiniIOSurface.cpp` 的 `MiniIOSurfaceStart()` 在什么条件下被调用，
   以及 `native_pong_ui_services_start()` 是否与插件注入路径互斥。
2. 查 `PongMetalPlugin.mm` 的 `selectedClient()` 与 `startPresentation()` 是否在
   backboardd 里提前接管了 `CARenderServerStart` 相关初始化。
3. 对照 yibiya 的 `GPU-ENABLE-PLAN.md:101/113/133`（`MiniIOSurface.cpp` 启动门、
   `surfacesReady` 帧判定）——他的工作路径里 MiniIOSurface 必须在插件之前完成初始化。
