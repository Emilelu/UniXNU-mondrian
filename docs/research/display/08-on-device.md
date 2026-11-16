# 显示 ⑧ 真机验证记录（背光发布层）

| 轮次 | 镜像 | boot.img sha256 | kernel.macho sha256 | 结果 | 证据 |
|---|---|---|---|---|---|
| 0 | brightness-4 | 30ccafb3… | 488a1d8f… | control=1：发布层生效，但 backboardd 4 次 `sig=11`、SpringBoard 7 行、无 first frame（int-236 形状） | `usblog-20261115-013520` |
| 1 | brightness-13 | `c8c33b9e…` | `bf2df340…` | **PASS（发布层）**：control=0 / conformance=0 / stats[0]=3 / 无 SIGSEGV / first frame / SpringBoard 128 行 | `usblog-20261115-134638` |
| 参照 | brightness-9（旧格式） | `ca992179…` | `7e809dc5…` | 行为同 13：control=0、无 SIGSEGV、SpringBoard 208 行；判定器只能给 INCONCLUSIVE（日志无 `stats=`） | `usblog-20261115-134001` |
| 3（预注册） | brightness-15 | `67acb403…` | `513cc329…` | 待飞：control=1 + 删半截标定字典（b4 崩因修复） | 见文末第 3 轮 |

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

## 滑块三档实测要看的三个数字

用户在场时拉一次亮度滑块（最低 / 中间 / 最高各停一次），只看三处：

1. **屏幕**：亮度是否随之变化（这是唯一能证明物理调光的证据，DCS 0x51 没有读回命令）。
2. **`stats[1]`**：请求计数是否随滑动增加；不增 = 请求没到服务（CoreBrightness 未接管）。
3. **`published level` 行 / `stats[2]`、`stats[4]`**：每次请求后内核会重新 publish 一行，
   看 level 与 DBV 是否跟着三档变化（例如 0 / ~1024 / 2047）。

前两项任一为否，都不能算「亮度可调」已验收；只能算「发布层安全」已验收。

## 第 3 轮（预注册，2026-11-16；镜像 brightness-15，待飞）

- 镜像：`brightness-15`，`boot.img` sha256 `67acb403…`（201,887,744 B），
  `kernel.macho` sha256 `513cc329…`（105,521,152 B）；manifest repo head `a322b58`、dirty 0、
  series 227、`kernel_args_requested=["k60_backlight_control=1"]`。
- 改动：`publishCalibration` 不再发布 `backlight-calibration-parameters`。b4 的 SIGSEGV 根因是
  半截字典让 CoreBrightness 的 `CFNumberGetValue` 收到 NULL，见 `INT-236-CHAIN.md` §11。
- 预注册判据（飞之前写死，不事后解释）：
  1. **PASS（发布层）**：日志有 `conformance=1 control=1` 的 published 行；`sig=11` 计数 0；
     `entered backboardd` 1 次；SpringBoard ≥100 行；`first frame presented` ≥1。
  2. **PASS（物理调光）**：用户拉滑块 min/mid/max，屏上可见变化，`stats[1]` 递增，
     `stats[2]/stats[4]` 跟随；屏幕全程持续更新。
  3. **FAIL**：任一 `sig=11`、无 first frame、停更、或三档无可见变化。FAIL 即停 control=1 路线
     （交付保持 `control=0` 的 brightness-13），转 SnapAdreno 的 swap-record 路线。
  4. **INCONCLUSIVE**：`conformance=0`（impersonation 未成立、control 没申请）——等同没测，不是失败。
- 判读命令：`python3 scripts/check-backlight-log.py <console.log>`；物理三档另记 published 行里的 `stats=`。

