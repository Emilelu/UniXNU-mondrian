
- [ADSP-PAS1.md](audio/ADSP-PAS1.md) — PAS1 的 SCM 常量与调用序列
- [ADSP-MD0.md](audio/ADSP-MD0.md) — `vmd0`/`md0` 载体为什么读不通（外部中止、页单位、IO_MAP 上限）
- [ADSP-CARRIER.md](audio/ADSP-CARRIER.md) — ADSP 固件载体决策：固定物理地址 + ADT 常量，已排除的三条路
- [ADSP-CLAIMS.toml](audio/ADSP-CLAIMS.toml) — 8 条可核对断言，`scripts/check-adsp-claims.py` 逐条校验
- [GLINK-HANDOFF.md](battery/GLINK-HANDOFF.md) — 104 字节 `k60-adsp-glink-handoff` lease 的字节布局与生产者要求
- [POWER-RPMH-LDOC2.md](touch/POWER-RPMH-LDOC2.md) — `pm8350c_l2`（触摸 IOVDD 1.8 V）如何从 AP 侧通过 RPMh TCS3 投票点亮：硬件常量、v2 寄存器布局、11 步投票序列、ACK 之后的 observer 验证、Berlin D 上电时序、SPI 引脚角色、八个已知陷阱
- [01-ANDROID-INVENTORY.md](cellular/01-ANDROID-INVENTORY.md) — Android 侧 modem 取证：分区布局、104.02 MiB `modem.*` 固件、`MPSS.DE.2.0.c1-CN` 版本串、AF_QIPCRTR 而非 unix socket、IPA 与 MHI 的归属、EFS/NV 在裸 `modemst` 分区
- [02-DT-TRUTH.md](cellular/02-DT-TRUTH.md) — 活 FDT 字节级取证：`remoteproc-mss@04080000`（`qcom,cape-modem-pas`）、`mpss_region` 0x8bc00000/0x13200000 与 `modem.mdt` 段表严丝合缝、GLINK `IPCRTR` 通道与 intents、IPA 节点、QRTR 三个传输节点谁属于谁
- [03-SCOPE.md](cellular/03-SCOPE.md) — 范围判定：L1 固件加载 + L2 QRTR 枚举在范围内（PAS/GLINK 已有 70% 代码），IPA 数据面/EFS/mbn/IMS 明确排除；含双系统残留风险与开工前必须澄清的 `qrtr-lookup` 未解项
