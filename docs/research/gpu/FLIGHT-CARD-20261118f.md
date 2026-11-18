# 上机卡 20261118f — 关掉 managed-page 报告后帧率是否上升

## 1. 目的

镜像 `gpu-quiet-20261118`。单变量 = 内核里的
`NATIVE_QUIET_MANAGED_PAGE_REPORT=1`（新增 `patches/xnu/0624-k60-quiet-managed-page-report.patch`，
series 227→228），把 `IOMemoryDescriptor::populateDevicePager` 里那段
「physical with managed page」+ `OSReportWithBacktrace` 的 DEVELOPMENT 报告编译掉。
对照基准是同插件、同参数、只差这一个内核开关的前一飞 `usblog-20261118-124317`：
那一飞 `IOMemoryDescriptor physical` **25,149 次**、日志 5,611,548 B / 54,518 行、
`scanout frames=60 at 104.572 s` / `=480 at 183.780 s`（104→184 s 区间约 5.3 fps）、
`K60HB` 从 t=75 起 `lag=1`。

## 2. 前提证据

- P1 `patches/xnu/0624-k60-quiet-managed-page-report.patch`（1,470 B）在已应用树上
  `git apply --check -R` 通过（REVERSE-APPLY-OK），说明补丁与树的现状严格对应。
- P2 守卫 `scripts/tests/test-managed-page-quiet.py` 5 例全过：宏被定义、条件使用宏、
  被守护的打印行仍是**上下文**（不是删除，所以开关还是开关）、series 末位列出该补丁、
  hunk 头与结尾换行合法。
- P3 该补丁已同步进 `K60_DEVICE_INPUT=/opt/k60/trees/gates-device`（`diff -q` 相同），
  `check-patch-apply.py` ✅、`check-line-endings.py` no CRLF。
- P4 插件侧不变：仍用 `metal-plugin-20261118d`（含 0013，`strings … | grep -c PerViewport` = 11）。

## 3. 抓取

`K60_FORCE_NEW=1 bash scripts/flash.sh <boot.img> 240`，证据落 `E:/k60-work/evidence/usblog-<ts>/`。
只在 `fastboot devices` 非空时飞。

## 4. 判据

- **S1** `K60KEXC` 出现次数 = 0。
- **S2** `K60METAL deploy` 出现且 `error=0`。
- **S3** `Pong Metal: real Vulkan-backed device created` 出现 ≥1。
- **S4** `Pong Metal: scanout frames=` 出现 ≥**3** 次（即出帧 ≥180，超过基准的 2 次 / 480 帧）。
- **S5** `IOMemoryDescriptor physical with managed page` 出现次数 = **0**（守卫生效）。
- **S6** `crashed: backboardd` 出现次数 = 0。
- **S7** 出帧速率：取最后两条 `scanout frames=N at T s`，`(N2-N1)/(T2-T1)` **≥ 15 fps**
  （基准同式 = 420 帧 / 79.2 s ≈ **5.3 fps**；15 fps 是它的 3 倍，足以证明不是噪声）。
  **不要用 `K60HB` 的 `lag=` 当卡顿判据**：`patches/xnu/0303-k60-heartbeat.patch:58` 是
  `unsigned int k60_lag = k60_storm_count("launchd");` —— 它是 **launchd 的 exec 风暴计数**，
  不是延迟/滞后标志；`lag=1` 只表示 1 次异常 exec，与掉帧无关（我在 12:50 的汇报里误读过一次）。
- **F1** 出现 `K60KEXC` ⇒ 内核异常。
- **F2** `K60METAL deploy` 缺失或 `error!=0`。
- **F3** 没有 `real Vulkan-backed device created`。
- **F4** `scanout frames=` 少于 3 次 ⇒ 帧率没改善。
- **F5** `IOMemoryDescriptor physical with managed page` 仍出现 ⇒ 守卫没生效（补丁没进内核）。
- **F6** `crashed: backboardd` 出现。
- **F7** S7 的速率 < 15 fps ⇒ 打印风暴消失但帧率没改善，卡顿另有原因（下一层查映射粒度）。

## 5. 结果登记
