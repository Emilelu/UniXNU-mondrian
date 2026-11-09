# 触摸 ④ 广域验证矩阵

> 状态：◐ 进行中。证据等级：文档/实测。

| 结论 | 来源 A | 来源 B | 来源 C | 一致？ | 备注 |
|---|---|---|---|---|---|
| SPI 基址 `0x00990000` | live FDT `spi@990000` | `GOODIX-TOUCH-PORT.md §3.4` | 本机 build 的 ADT（`pong-touch` 节点） | ✅ 三者一致 | — |
| INT = GPIO21 / RESET = GPIO20 | live FDT `interrupts`/`reset-gpio` | `K60-TOUCH-PARAMS.md §1.3` | pong 驱动 `PIN_INT`/`PIN_RESET` | ✅ | — |
| AVDD = GPIO71 | live FDT `goodix,avdd-gpio` | `GOODIX-TOUCH-PORT.md §3.3` | pong 驱动 **无此属性**（用 LDO3/LDO12） | ❌ **冲突** | K60 必须新增 |
| max-x/max-y | live FDT **14400/32000**（raw） | `GOODIX-TOUCH-PORT.md §3.1` 称驱动断言 14400/32000 | 实际补丁第 65 行断言 **1080/2412** | ❌ **冲突** | 见 ⑦ 核验 |
| RSC / cmd-db | K60 走 RPMh? | `GOODIX-TOUCH-PORT.md §2.4`：K60 不用 RPMh，须 `k60rpmhoff=1` | pong 驱动无条件 `ml_io_map(RSC)` + `cmd_db` | ❌ **冲突** | 需 K60 板级层 |
| 15 MHz SPI | live FDT `spi-max-frequency` | `GOODIX-TOUCH-PORT.md §3.4` | pong 驱动 `bring_up()` 先 4 MHz | ✅ | 上电后切 15 MHz |
