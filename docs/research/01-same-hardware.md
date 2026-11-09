# 触摸 ① 同型项目收集

> 状态：✅ 已完成（2026-11-08）。证据等级：文档/实测。

## 同 SoC / 同外设的可用实现

| # | 项目 | 位置 / commit | 与本机关系 | 可复用内容 | 证据 |
|---|---|---|---|---|---|
| 1 | **UniXNU-pong**（ios16 分支） | `https://github.com/Chengdong-Yu/UniXNU-pong`，本地 `/mnt/e/hackios/UniXNU-pong`，`FETCH_HEAD` | 同 SoC 家族（SM8475/SM8550），Goodix Berlin-D 协议核 | `bsd/dev/pong_goodix.c`（36 KB：SPI/GENI、DCS、固件探测、报告解析）、`pong_input.c`（ring 队列） | `patches/xnu/zzzz…-pong-touch-console.patch` |
| 2 | **renoir_xnu_bluethooth** | `https://github.com/daimile2/renoir_xnu_bluethooth` commit `2b9d59c9` | 另一台 XNU 移植机的 Goodix 实现 | `userland/renoir_bt_type0.c`、用户态注入方式 | `QcaBluetooth/tools/source-lock.json` 引用 |
| 3 | **HackiOS redwood** | 上游 `redwood_goodix.c`（APSL 2.0） | Goodix Berlin-D 原始移植来源 | 协议核最早版本 | `pong_goodix.c` 头注释：「Adapted from HackiOS redwood_goodix.c」 |
| 4 | **官方页 marble / fuxi** | 见 `GOODIX-TOUCH-PORT.md §1.1` | 小米官方开源 Goodix 驱动页 | 板级常量参考（GPI/clock ID） | `docs/plans/GOODIX-TOUCH-PORT.md` |

## 结论

- **有同型实现，且不止一个**：pong 的协议核 + renoir 的用户态 + 官方 marble/fuxi 板级参考。
- **不能原样照抄的原因**（见 ⑥ 深挖）：K60 不用 RPMh（RSC/cmd-db），且 AVDD 是 GPIO71。

## 未取得

- K60 原厂 `dtbo_a_fdt15.dtb`（`K60-TOUCH-PARAMS.md §1.1` 记录：全盘扫描未找到，目录已不存在）→ 改用 live merged FDT（见 ③）。
