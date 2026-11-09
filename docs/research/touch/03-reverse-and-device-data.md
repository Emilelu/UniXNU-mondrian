# 触摸 ③ 反编译资料 + 真机数据

> 状态：◐ 部分完成。证据等级：实测（FDT/日志）+ 文档（kext 字符串）。

## 反编译 / 二进制提取

| # | 对象 | 命令 | sha256 / 结果 | 用途 |
|---|---|---|---|---|
| 1 | K60 live merged FDT | `adb shell "cat /proc/device-tree/..."` → `live-6033dbec-fdt.dtb` | `95c02052b773a1b8df8ec20f6368ba80c87717206ed40682046e2ad6f29fdac8` (919,210 B, FDT v17) | 触摸节点全部属性真值 |
| 2 | 20G81 kernelcache | `img4` 解压 | 48,644,096 B，`/mnt/e/hackios/UniXNU/out/ipsw/20G81/kernelcache.decompressed` | 确认无 `IOHIDEventSystemClientCreateWithType`（用户态走 HID.framework） |
| 3 | pong 协议核 | `git show FETCH_HEAD:bsd/dev/pong_goodix.c` | 36,603 B 原始补丁 `scratch/pong-drivers/…pong-touch-console.patch` | 协议核来源 |

## 真机数据

| # | 数据 | 值 | 来源 |
|---|---|---|---|
| 1 | 触摸 SPI 控制器 | `spi@990000`，QUPV3_1 SE0 | live FDT |
| 2 | 中断号 | GPIO 21 → GIC SPI **605** | `GOODIX-TOUCH-PORT.md §3.4` |
| 3 | 显示面板 | 1440×3200，DSI0 `0x0ae94000` | 内核日志 `K60 PANEL: DSI0 version=0x20060000` |
| 4 | 首次上机日志 | `Pong touch: missing/incompatible Pong DT; SKIP`（ADT 无节点）→ 补节点后 `Pong touch HID: real touch device unavailable (Operation timed out)`（用户态等 `/dev/pong-touch` 30 s 超时） | `evidence/usblog-20261108-180257`、`usblog-20261108-210018` |

## 缺口

- ❌ 未反编译 K60 Android 的 `goodix_ts.ko`（原厂驱动），因为本机没有 Android 分区 dump。
- ❌ 未提取 `goodix_firmware_m11a` 固件二进制。

## 2026-11-09 00:05 — 固件已从真机提取（重大补充）

设备回到 Android 后通过 adb 直接提取，**sha256 与设备端完全一致**：

| 文件 | 大小 | sha256 | 设备路径 |
|---|---|---|---|
| `goodix_firmware_m11a.bin` | 223,744 B | `1e647510cdc4c0293aa06fa7cb5d0a2f3558fcc151ac2785786fa6c31b560509` | `/vendor/firmware/` |
| `goodix_cfg_group_m11a.bin` | 1,627 B | `a730e3f1238d651c531bc375fb477c6036f7112570cbc98220bf5e50a6f8af79` | `/vendor/firmware/` |

本地副本：`/mnt/e/k60-work/scratch/goodix-fw/`

**头部解析**：
```
offset 0x00: f8 69 03 00   (长度?)
offset 0x04: 67 54 5b 78
offset 0x08: "BERLIN"       ← 芯片系列确认
offset 0x0E: 02 00
offset 0x10: 04 39 39 31 36 52   ← "9916R" = GT9916
```
→ **Goodix Berlin-D / GT9916**，与 pong 驱动的协议目标一致。

**意义**：之前 `goodix: no valid firmware version: 00 00 ...` 的原因是芯片未被正确初始化（时钟/SE 模式），但**固件本身现在在手**，可以在驱动里加 firmware download 路径（参考 Linux `goodix.c` 的 `goodix_firmware_download`）。

**其他 Android 实测（同时验证了其他子 agent 的假设）**：
- `/vendor/firmware_mnt/image/slpi.b00…b08` **存在** → sensors-porter 的 SLPI 假设成立
- `/vendor/firmware/wlan/qca_cld/qca6490/` **存在** → wifi-porter 的固件路径假设成立
- `/vendor/etc/sensors/config/{lsm6dso,qmc6308,stk3bcx}_0.json` **存在** → sensors-porter 的型号正确
