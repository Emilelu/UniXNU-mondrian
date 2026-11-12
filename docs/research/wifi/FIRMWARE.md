# qca6490 WiFi 固件清单

> 从设备 `/vendor/firmware_mnt/image/qca6490/` 只读提取，2026-11-12
> 设备：Redmi K60（23013RK75C）/ mondrian / SM8475
> 提取方式：`adb pull`，未修改设备

---

## 文件

| 文件 | 大小 | sha256 |
|---|---|---|
| `amss.bin` | 5470128 | `a626cfc1882b3e386154fac655652005e8f20ff0176b4c63de99cd082d5d75c2` |
| `amss20.bin` | 5296128 | `903c378a972b4294fef5c926e34c2cfb03eb042f6a1e38101f0073b33792df86` |
| `Data.msc` | 889524 | `31d5fee12d94bf86841c4c06d3460959373f3468ea4ca0f13d7da67de739a0cc` |
| `Data20.msc` | 916071 | `3c87a16e6c6814b5356ead716b87af5c14c32efba113fe51b2600e44ad126c41` |

**合计 12,571,851 B**

本地存放位置（不在仓库里，因为文件太大）：`<workspace>/firmware/qca6490/`

---

## 用途

| 文件 | 用途 |
|---|---|
| `amss.bin` | ath11k 主固件（`fw_get("amss.bin")`）|
| `amss20.bin` | 备用/第二版固件 |
| `Data.msc` | 校准/board data |
| `Data20.msc` | 备用 board data |

PWF2 打包格式（magic `0x32465750`）由 `PongWifiFirmware.cpp` 解析。
`build-k60-wifi` 会把它们打成 `PongWifiFirmware.bin`。

---

## 还缺什么

`bd_*.elf` 共 42 个（蓝牙固件，每个约 60 KB）没有提取 —— 那是蓝牙移植用的，
WiFi 不需要。需要时再取。

---

## 验证方式

```bash
sha256sum <workspace>/firmware/qca6490/*
```
对照上表。

设备上原始位置的权限是 `-r--r----- system system`，普通 adb 可读。
