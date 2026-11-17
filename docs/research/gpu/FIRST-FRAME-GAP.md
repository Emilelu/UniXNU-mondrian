# 首帧缺口：Metal 设备发布后 backboardd 没有任何提交

日期：2026-11-18（01:14 修订）

## 实测对照

| 镜像 | pong_metal | MiniIOSurface 行 | first frame presented | Pong Metal: S |
|---|---|---|---|---|
| usblog-20261116-164726 | 2（软件） | 1（2 个大 surface，8901 us 每个） | 1（swap 2, 1440x3200 canvas） | 无插件 |
| usblog-20261116-224736 | 1 | 0 | 0 | x6 |
| usblog-20261116-230446 | 1 | 0 | 0 | x6 |
| usblog-20261118-003847 | 1 | 0 | 0 | x3 |
| usblog-20261117-130912 | 1 | 0 | 0 | x6 |

## 能证明什么

- `MiniIOSurface` 是**软件**帧缓冲实现；一旦发布了真正的 Metal 设备，backboardd 走 Metal
  路径而不是它，所以「没有 MiniIOSurface 行」是**预期现象**，不能据此说表面管线没启动。
- 三张 `pong_metal=1` 镜像都出现 `Pong Metal: real GPU scanout worker ready status=0x0`
  （例如 003847 的 :1402），说明 presenter/扫描输出线程已建立。
- 但它们全部 `p0`（零 present）、零 `present #`，且 SpringBoard 主线程 `turns=0`。
  => 缺口在 **Metal 路径内**：backboardd 发布了设备并起了扫描输出，但没有任何
  CA drawable / transaction 被提交给 presenter。

## 下一步（离线可查）

1. `GpuScanoutPresenter.h` / `PongMetalScanout.h`（yibiya 版 5455/5013 B）里
   `pongscanout::start()` 等待的是什么事件；若等的是 backboardd 的 offer，谁负责 offer。
2. `PongMetalPlugin.mm` 的 `startPresentation()` 只在 `getprogname()=="backboardd"` 时启动，
   确认 backboardd 的 CA 渲染线程是否因设备替换而改走另一条未被 hook 的路径。
3. SpringBoard 的同步 Mach 调用（BackBoardServices -> FrontBoard）在等哪一条回复；
   用 `dyld-index-20G81.json` 继续符号化该线程帧。

## 01:15 追加：上游也只注入 backboardd

- 上游 `userland/init.c:388` 同样只有 `"; /private/var/pong/PongAdrenoMetal.bundle/PongAdrenoMetal backboardd"`，
  所以「SpringBoard 没设备」不是我们的差异，他那侧也只有 backboardd 有设备。
- 我们的 clients 种子（122 B）已包含 `backboardd/SpringBoard/CollectionsPoster/WidgetRenderer_Default/PosterBoard/Weather/WeatherPoster/GradientPosterExtension`，与上游一致。
- 因此差异只能落在 **backboardd 自己的合成路径**：他出 `present #` 说明 backboardd 仍在产出帧并交给
  presenter；我们的 metal 飞连 `MiniIOSurface` 都没有，说明 backboardd 换到 GPU 设备后没有走
  「软件合成 + GPU blit」这条路，也没有任何别的路径送帧。
- 下一步定死：在 `PongMetalPlugin.mm` 的 `startPresentation()` 里打印 backboardd 的
  `CARenderServerStart` 之后的帧来源判定（把 `PongScanoutWire.h` 的 wait 超时也计数），
  用一张只加日志的镜像区分「backboardd 没产帧」与「产了但没送到 scanout 服务」。
