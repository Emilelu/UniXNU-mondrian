# 显示 ⑧ 真机验证记录（背光发布层）

| 轮次 | 镜像 | boot.img sha256 | kernel.macho sha256 | 结果 | 证据 |
|---|---|---|---|---|---|
| 0 | brightness-4 | 30ccafb3… | 488a1d8f… | control=1：发布层生效，但 backboardd 4 次 `sig=11`、SpringBoard 7 行、无 first frame（int-236 形状） | `usblog-20261115-013520` |
| 1 | brightness-13 | `c8c33b9e…` | `bf2df340…` | **PASS（发布层）**：control=0 / conformance=0 / stats[0]=3 / 无 SIGSEGV / first frame / SpringBoard 128 行 | `usblog-20261115-134638` |
| 参照 | brightness-9（旧格式） | `ca992179…` | `7e809dc5…` | 行为同 13：control=0、无 SIGSEGV、SpringBoard 208 行；判定器只能给 INCONCLUSIVE（日志无 `stats=`） | `usblog-20261115-134001` |
| 3 | brightness-15 | `67acb403…` | `513cc329…` | **PASS（发布层）**：control=1 / conformance=1 / 无 sig=11 / first frame / SpringBoard 128；物理可调但两端与 Android 不符 | `usblog-20261117-004800` |
| 4 | brightness-16 | `bfaa3912…` | `845c3c9d…` | **PASS（发布层）**：conformance=1 / 无 sig=11 / first frame / SpringBoard 129；8 位 DBV 两端 0xff 与 0x1 到达，但最低观感仍不够低（8 位底 1/255 ≈ 0.39%，Android 12 位底 1/4095 ≈ 0.024%） | `usblog-20261117-013028-658`、`usblog-20261117-013717-505` |
| 5（预注册） | brightness-17 | 飞后填 | 飞后填 | 待飞：DCS 0x51 改 12 位双字节（0x01…0xfff，与 Android 同域）+ 端点精确映射 | 见文末第 5 轮 |

brightness-11/12 与 brightness-14（都是 c56b507 基线、日志无计数或 control=1）已被裁定作废，不再飞。

## 第 1 轮（2026-11-15 13:46）— brightness-13 默认形态 PASS

- **镜像**：`brightness-13`，`boot.img` sha256
  `c8c33b9e54965fb79752e60cfcf987e5d0675801e7544169073d1661ad674d74`（201,887,744 B）；
  `kernel.macho` sha256
  `bf2df340794d92ad50137ba7af3c3f1506ae0196a53ef70a5735e11abca0c6a3`（105,500,672 B）。
- **基线**：origin/main `ecda32f`，series 224 条 / sha 前 16 `34cf51e4`，工作区 dirty 0；
  `kernel_args_requested = [""]`（不传 backlight 参数，即 control 默认 0）。
- **日志**：`E:\k60-work\evidence\usblog-20261115-134638\console.log`（217,179 B），
  无 panic、无 `sig=11`；SpringBoard 128 行；`K60 DISPLAY: first frame presented` 出现。
- **判定器**：`python3 scripts/check-backlight-log.py <console.log>` → **EXIT=0**
  （`check-backlight-log: PASS (control=0 image)`），逐条：service published level 2047 at dbv 0xff /
  control=0 / conformance=0 / stats[0]=3 / request[4]=0 / request[5]=0 / no SIGSEGV / first frame presented /
  SpringBoard lines: 128。

### 决定性日志行（`console.log:183`，原文）

```
K60 BACKLIGHT: published level 2047 dbv 0xff conformance=0 control=0 stats=3,0,2047,2047 req=0,0,0,0 (no AppleARMBacklight conformance)
```

读法：`stats[0]`=3（已发布、未声称 AppleARMBacklight）、`stats[1]`=0（发布时还没有亮度请求）、
`stats[2]`=2047（最后写入 level）、`stats[3]`=2047（由回读 DBV 0xff 反算，与 [2] 一致）、
`req[4]`=0（conformance 不成立）、`req[5]`=0（没发 `backlight-control`）。
槽位语义见 [`STATS-INDEX.md`](STATS-INDEX.md)。

### 这轮证明了什么、没证明什么

- **证明**：发布层本身是安全的 —— 默认形态下 `control=0`、没有 SIGSEGV、SpringBoard 正常进桌面、
  首帧呈现。对照 brightness-4（`control=1`）的 4 次崩溃，int-236 的触发条件被隔离到
  「发布 backlight-control」这一个动作上。
- **没证明**：滑块真的改变物理亮度。默认形态不发布 `backlight-control`，
  服务没有向 CoreBrightness 声称接管内置屏背光；若用户拉滑块时 `stats[1]` 不增，
  说明请求根本没到服务（预期中的可能结果），那就需要另设计一条不触发 int-236 的接管路径，
  而不是重飞 `control=1` 的旧图（brightness-4 已崩 4 次）。

## 滑块三档实测要看的三个数字（第 4 轮起口径）

用户在场时拉一次亮度滑块（最低 / 中间 / 最高各停一次），只看三处：

1. **屏幕**：亮度是否随之变化（这是唯一能证明物理调光的证据，DCS 0x51 没有读回命令）。
2. **每请求一行日志**：`K60 BACKLIGHT: brightness… -> level … dbv 0x…`。第 4 轮起每个请求打一行，
   行里同时给出 CoreBrightness 用的键（`brightness-nits` 还是 `brightness`）、滑块量程与落到的 DBV。
   没有这一行 = 请求根本没到服务（CoreBrightness 未接管），不是「调光无效」。
3. **两端的 DBV**：最低档应落到 `dbv 0x1`、最高档 `dbv 0xfff`（第 5 轮起的 12 位域；第 4 轮是 8 位的 `0xff`）。这两端是 Android 对照的硬指标；
   中间档只记不判。

第 3 轮（brightness-15）没有每请求日志，`stats[1]` 事后读不到，只能靠「屏上可见变化」判物理链路；
那一轮的 `published level` 行是启动时打的一次快照，不能当三档读数。

## 第 3 轮（2026-11-17 00:48）— brightness-15 control=1：发布层 PASS，两端不对

- **镜像**：`brightness-15`，`boot.img` sha256
  `67acb40376a468137401f65483169809e064c3f905e1e9b13c0ce54cea103ff6`（201,887,744 B；
  fastboot 启动时打印的前缀 `67ACB403…` 与构建一致）；`kernel.macho` sha256
  `513cc329347eef2715635cd5fb3ec4f692c56e487281bccc4cff86268fd7a4fe`（105,521,152 B）；
  manifest repo head `a322b58`、dirty 0、series 227、`kernel_args_requested=["k60_backlight_control=1"]`。
- **改动**：`publishCalibration` 不再发布 `backlight-calibration-parameters`（b4 的半截字典让
  CoreBrightness 的 `CFNumberGetValue` 收到 NULL，见 `INT-236-CHAIN.md` §11）。
- **日志**：`E:\k60-work\evidence\usblog-20261117-004800\console.log`，236,694 B；
  `sig=11` 0 次、`getBytes:range|unrecognized selector` 0 次、无 panic。
- **判据 1（发布层）PASS**：`:184` 的 published 行
  `K60 BACKLIGHT: published level 2047 dbv 0xff conformance=1 control=1 stats=4,0,2047,2047 req=0,0,1,1`
  —— **`conformance=1` 第一次在真机成立**，`backlight-control` 已发布，int-236 未复现；
  `:1284` `Pong UI: 20G81 compatibility library entered backboardd`；
  `:2292` `K60 DISPLAY: first frame presented (swap 1, 1440x3200 canvas on 1440x3200 panel)`；
  SpringBoard 128 行。
- **判据 2（物理调光）部分 PASS**：用户拉滑块，屏上可见变化 ⇒ 请求确实到达服务、DCS 0x51 生效。
  `stats[1]` 无法事后读（该构建每个请求不打日志，published 行只在启动时打一次）⇒ 这一子项记
  INCONCLUSIVE，由第 4 轮的 per-request 行补上。
- **新问题**：两端与 Android 不一致 —— 最低不够低、最高疑似不到顶。离线分析：CoreBrightness 走它
  自己的默认标定 5 / 140 / 400 nits，而本构建 `levelFromNits` 是 nits*kMaxLevel/kMaxNits 线性映射
  （kMaxNits=500）⇒ 400 nits 只到 level 1638 = DBV 0xcc、5 nits 只到 DBV 0x03；面板下限 DBV 0x01、
  上限 0xff。修法见第 4 轮。

## 第 4 轮（2026-11-17 01:30 / 01:37）— brightness-16：8 位 DBV 两端到达，最低仍不够低

- **镜像**：`brightness-16`（commit `f4679902`，父 `c6cd304`）；`boot.img` sha256
  `bfaa3912a0e4dd3828681ca4b0a847a043f9fb2c85c0360537fd9e0d3ce21d98`（201,887,744 B）；
  `kernel.macho` sha256 `845c3c9db9580287b5cdce74eaaf65aedfe29e0cb098691c4f210098ae076a13`；
  manifest repo head `f97ab49`、dirty 0、series 227、`kernel_args_requested=["k60_backlight_control=1"]`。
- **改动（相对第 3 轮两处）**：`kMinNits=5` / `kMidNits=140` / `kMaxNits=400`，`levelFromNits` 把
  CoreBrightness 的 [5..400] nits 区间拉伸到 level [1..2047]；`setProperties` 每条请求打一行日志。
- **第一飞**（`E:\k60-work\evidence\usblog-20261117-013028-658\console.log`，249,449 B）：`:184` published
  `K60 BACKLIGHT: published level 2047 dbv 0xff conformance=1 control=1 stats=4,0,2047,2047 req=0,0,1,1`；
  `first frame presented` 1 次；首次出现每请求行 `:2240 K60 BACKLIGHT: brightness level 1024 -> level 1024 dbv 0x80`、
  `:2241 K60 BACKLIGHT: brightness-nits 0.00000 -> level 0 dbv 0x0` ⇒ **16.6.1 拖滑块走的是 `brightness` 键，
  不是 `brightness-nits`**（后者只在启动时发一次 0.0）。
- **第二飞**（`E:\k60-work\evidence\usblog-20261117-013717-505\console.log`，264,170 B；先拉最顶 3 秒、
  再拉最底 3 秒）：`:2930` `brightness level 2047 -> level 2047 dbv 0xff`（2045/2046 也到 0xff）；
  `:3205` `brightness level 1 -> level 1 dbv 0x1`；请求行 53 条（52 条 `brightness level` + 1 条
  `brightness-nits`）；`sig=11` 0、entered backboardd 1、SpringBoard 129、`getBytes:range` 0。
- **判据 1（发布层）PASS**；**判据 2（请求可见）PASS**；**判据 3（最高）在 8 位域 PASS**（0xff）；
  **判据 4（最低）在 8 位域 PASS**（0x1），但**观感仍不够低**：8 位底 1/255 ≈ 0.39%，而本板面板
  live FDT 是 12 位域（`qcom,mdss-dsi-bl-max-level=0xfff`、`bl-min-level=0x1`、`bl-inverted-dbv`），
  Android 最低 1/4095 ≈ 0.024%，相差 16 倍 ⇒ 第 5 轮改 12 位双字节写入。
- **判读命令**：`grep -a 'K60 BACKLIGHT: brightness' <console.log>`。

## 第 5 轮（预注册，2026-11-17；镜像 brightness-17，待飞）

- **镜像**：`brightness-17`（commit 待填）；`boot.img` / `kernel.macho` sha256 飞后填。
- **改动（相对第 4 轮两处）**：
  1. `PongDsiPanel.cpp`：`pong_panel_set_brightness` 与 bring-up 都改发两字节 DCS 0x51
     （`pong_panel_dbv_bytes()`：高字节在前 `{level>>8, level&0xff}`）；bring-up 发 `0x51 0x0f 0xff`，
     `panel_brightness=0xfff`。依据：live FDT `qcom,mdss-dsi-bl-max-level=0xfff`、`bl-min-level=0x1`、
     `qcom,mdss-dsi-bl-inverted-dbv` 存在；Android `dsi_panel_update_backlight()` 对 `bl_inverted_dbv`
     先交换字节，`mipi_dsi_dcs_set_display_brightness()` 永远发 `u8 payload[2]`，`sde_connector` 把
     brightness 夹到 `bl_max_level=0xfff` 后下发。0x51 双字节 = DCS long write，报文头布局与
     vendor `dsi_ctrl_copy_and_pad_cmd()` 的 `{wc, datatype, flags}` 逐位一致。
  2. `K60BacklightCodec.h`：`kMaxDbv=0xfff`，`dbvFromLevel`/`levelFromDbv` 以
     `kDarkestLevel(1) -> kMinDbvOn(1)`、`kMaxLevel(2047) -> kMaxDbv(4095)` 端点对齐。
- **预注册判据（飞之前写死）**：
  1. **PASS（发布层）**：published 行 `conformance=1 control=1`、`dbv 0xfff`；`sig=11` 0；
     `entered backboardd` 1；SpringBoard ≥100；`first frame presented` ≥1。
  2. **PASS（请求可见）**：用户拖滑块后 ≥3 条 `K60 BACKLIGHT: brightness…` 行。
  3. **PASS（最高）**：最高档请求行 `dbv 0xfff`，观感不低于 Android。
  4. **PASS（最低）**：最低档请求行 `dbv 0x1`，观感明显比第 4 轮最低档更暗（用户判断）。
  5. **FAIL**：任一 `sig=11`、无 first frame、没有任何请求行、最高不是 0xfff / 最低不是 0x1、
     或 `K60 PANEL: sending DCS 0x51 0x0f 0xff (brightness max)` 之后没有 `K60 PANEL: bring-up complete`
     （长写路径失败）。
- **判读命令**：`grep -a 'K60 BACKLIGHT: brightness' <console.log>`；
  `grep -a 'K60 PANEL:' <console.log>`；`python3 scripts/check-backlight-log.py <console.log>`。


