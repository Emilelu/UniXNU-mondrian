
- [ADSP-PAS1.md](audio/ADSP-PAS1.md) — PAS1 的 SCM 常量与调用序列
- [ADSP-MD0.md](audio/ADSP-MD0.md) — `vmd0`/`md0` 载体为什么读不通（外部中止、页单位、IO_MAP 上限）
- [ADSP-CARRIER.md](audio/ADSP-CARRIER.md) — ADSP 固件载体决策：固定物理地址 + ADT 常量，已排除的三条路
- [ADSP-CLAIMS.toml](audio/ADSP-CLAIMS.toml) — 8 条可核对断言，`scripts/check-adsp-claims.py` 逐条校验
- [GLINK-HANDOFF.md](battery/GLINK-HANDOFF.md) — 104 字节 `k60-adsp-glink-handoff` lease 的字节布局与生产者要求
- [POWER-RPMH-LDOC2.md](touch/POWER-RPMH-LDOC2.md) — `pm8350c_l2`（触摸 IOVDD 1.8 V）如何从 AP 侧通过 RPMh TCS3 投票点亮：硬件常量、v2 寄存器布局、11 步投票序列、ACK 之后的 observer 验证、Berlin D 上电时序、SPI 引脚角色、八个已知陷阱
