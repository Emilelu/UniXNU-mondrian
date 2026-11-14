# 触摸 ⑧ 真机验证记录

| 轮次 | 镜像 sha256 | 内核 sha256 | 结果 | 证据 |
|---|---|---|---|---|
| 1 | — | — | ADT 无节点 → `missing/incompatible Pong DT` | `usblog-20261108-180257` |
| 2 | — | — | ADT 有节点 → `Pong touch: ...` 消失（gate 拦截） | `usblog-20261108-182056` |
| 3 | — | — | 触摸启用 + ADT → `kmem_alloc(458752) failed`（GCC 448 KB） | `usblog-20261108-192302` |
| 4 | — | `a2ea0f2e` | 触摸关闭 → 无 kmem 失败、进 SpringBoard | `usblog-20261108-193525` |
| 5 | — | `49245760` | **新 libpong-ui 生效**：`Pong UI: ... entered SpringBoard`；用户态 `real touch device unavailable (Operation timed out)` | `usblog-20261108-210018` |
| 6 | 待填 | 待填 | gate 修复后：期望 `Pong touch: ...` + `/dev/pong-touch` 出现 + `Pong touch HID: display-integrated digitizer opened` | 未单独记录 |
| 7 | `0b2003f4…` | `c78a5cc9…` | **单指触摸通过**：COORD-ON ack=80、八条真实触点、四条 HID 派发 | `usblog-20261114-150931` |

## 第 7 轮（2026-11-14 15:09）— 单指触摸通过

- **镜像**：`touch-20261114a`，`boot.img` sha256
  `0b2003f45603449b28194e29def3302d84f1de508895581c0cd0417dcf9d88e9`（201,887,744 B）；
  `kernel.macho` sha256
  `c78a5cc93c3ec6e24de34a4a31e1b7639607fb45c2b024cb78b32753b8451b09`（105,476,096 B）。
- **日志**：`E:\k60-work\evidence\usblog-20261114-150931\console.log`，268,137 B / 3,870 行；
  `capture.json` `complete=true`、`panicMarker=null`、`resetMarker=null`、`portSeen=true`。
- **命令**：`bash scripts/flash.sh /mnt/e/k60-work/artifacts/touch-20261114a/boot.img 240`
  （经 `boot-and-capture.ps1` 监督，单串口写者）。
- **判据**：SpringBoard 254 行；`K60PANIC: ring kept` / `initproc exited` / `panic(` /
  `Debugger called` 各 0 次。用户在场，屏幕出现真实触点响应。

### 决定性日志行

```
681  goodix: CFG-EXIT completed state=80 ack=80
682  goodix: RAW-OFF ack=80
683  goodix: COORD-ON ack=80
684  goodix: chip "BERLIN", firmware "9916R" 05.80.02.63, sensor 255
685  goodix: active config=0x640fdf7d version=70 fw-state=0x10218/92 fw-buffer=0x1205c/4200
686  goodix: IC-info length=193 misc=49 touch=0x10308 command=0x10174 head=8 point=8 raw axes=14400x32000
687  Pong touch: Berlin-D ready, SPI 0x990000 reset=20 irq=21 raw axes=14400x32000 transport=GPIO SPI
1425 Pong touch HID: display-integrated digitizer opened
2490 goodix: type=1 finger=0 raw=6185,17320 normalized=28148,35470
2491 Pong touch HID: type=1 finger=0 xy=28148,35470
2492 Pong touch HID: type=3 finger=0 xy=28148,35470
```

八条触点（行号 → raw → normalized）：
2490 `6185,17320 → 28148,35470`；2493 `5105,18406 → 23233,37694`；
2503 `5881,18943 → 26764,38794`；2506 `5837,18798 → 26564,38497`；
2507 `6129,18425 → 27893,37733`；2518 `10740,12021 → 48878,24618`；
2574 `11085,17879 → 50448,36615`；2601 `12541,4303 → 57074,8812`。

### 真因（这一轮才被找到）

旧代码只发 `0x90/0x00`（关 raw 帧），**从未发本机 Android `goodix_htc_enable(false)` 的
第二条命令 `0x91/0x01`（坐标上报使能）**；且配置完成只检查 `ack[1]`，不等
`reply[0] == 0x80`（`cmd_ack.state`），所以没写完的配置看起来已经完成。两处都已在
`patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch` 修正。

### 本轮尚未验收

- 两点同时按下的触点 ID 稳定性与各自独立的 release。
- 屏幕边缘手势（系统级返回/多任务）。
- 手指移动时的持续帧率。
- `tap-to-wake`：日志有 `Pong touch HID: touch detection mode 0xff/0xfe/0x1/0`，
  但未在息屏状态验证唤醒。
- `0x10308` 头部长度取自 `misc+48`，保留模块只证明了 `misc+44`（触点数据地址）与
  `misc+50`（点结构长度），`misc+48` 仍是推断。
