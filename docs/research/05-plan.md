# 触摸 ⑤ 方案（更新：K60 板级层已实现）

> 2026-11-08 21:15 更新。方案 C 的三处冲突已全部落地。

## 已实施（本轮）

| # | 冲突点 | 文档依据 | 实现 |
|---|---|---|---|
| 1 | **RSC 首读整机死** | `GOODIX-TOUCH-PORT.md §2.4`（findings 0246/0248）、`0x17a20000` 首次读 TCS 即死 | `touch_thread` 里 `rsc=0; cmd_db=0`，**不再 `ml_io_map`**；判空检查同步去掉 |
| 2 | **AVDD 是 GPIO71** | live FDT `goodix,avdd-gpio = <&tlmm 0x47 0x0>` | `io_supply_on()` 改为 `gpio_output(71, true, PULL_NONE, 6); sleep_ms(15); return true;`，删除全部 `rpmh_address/rpmh_write` |
| 3 | GCC 448 KB 分配 | `kmem_alloc(…,458752)` 日志 | 拆 `GCC_QUP_OFFSET 0x27000` + `GCC_VOTE_OFFSET 0x62000` 两个 4 KB 映射 |
| 4 | boot-arg gate | `PE_parse_boot_argn` 缺参数返回 FALSE | `(void)PE_parse_boot_argn(...)` |

## 仍待处理

| # | 项 | 影响 | 计划 |
|---|---|---|---|
| A | max-x/max-y 断言 1080/2412 vs 原始 14400/32000 | 触摸坐标被压缩 | 先让设备节点出现；再改驱动断言为 14400/32000 并按 raw 缩放 |
| B | 固件 `goodix_firmware_m11a` / 配置组未提取 | 可能无法 probe 到 chip id | 需要 K60 Android 的 `/vendor/firmware` dump |
| C | 冷启动 IOVDD | 只有 warm boot 有 1.8 V | 首通只做 warm boot（文档 §2.4） |

## 失败形态与回退

- 若 `ml_io_map(SE_PHYS)` 也挂死 → 改为 bitbang（驱动已内置 `bitbang_transfer` 路径）。
- 若 GPIO71 拉高后 probe 仍失败 → 回 Android 热重启再 `fastboot boot`（保 IOVDD）。
- 回退镜像：上一版内核 `5c3b9602` 的镜像。
