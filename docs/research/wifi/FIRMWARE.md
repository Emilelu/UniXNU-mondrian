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

> 2026-11-14 复核：本机副本 `firmware/qca6490/` 里这四个文件的大小与 sha256 **逐字节一致**（重算通过）。
> 但**未能与设备再核对**：设备当时在 fastboot，`adb devices` 为空，读不到 `/vendor/firmware_mnt/image/qca6490/`。
> 因此「与设备一致」只能算 2026-11-12 那次提取的记录，不是本次实测。

## 目录里的其余文件（2026-11-14 实测）

| 文件 | 大小 | sha256 |
|---|---|---|
| `m3.bin` | 266,684 | `ad234ac8879e29a113893b87dc90335cff8eb89717580d5a06a49e7b9e322ed7` |
| `regdb.bin` | 24,278 | `06810e85c94c8f412c4e72cb38546cac90db7fdbadd45aae00f977f862d38a7b` |
| `regdb_xiaomi.bin` | 24,278 | `b7647cde6c6b157c11d2ed54f4da74abce653a3d70456e52665292369e560588` |
| `bdwlan.elf` | 59,932 | `2ddf43c01f2ef490cd5128c56e6ef0f8704dbc675a351ea37d8ae6eb93404231` |
| `bdwlang.elf` | 59,936 | `895d5028b5a40f9e0ca84c0f3ac9619d5f99f97d0f36031310f2638f4c7e002b` |

**「六文件」的说法要作废**：构建脚本（`patches/wifi/0009`）实际断言的是
`amss.bin` + `amss20.bin` + `m3.bin` + `regdb.bin`，外加必须存在任一 `bdwlan.*`（board data），
`Data.msc`/`Data20.msc` 没有被断言。

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

~~`bd_*.elf` 共 42 个（蓝牙固件，每个约 60 KB）没有提取 —— 那是蓝牙移植用的，WiFi 不需要。~~

**这条不成立（2026-11-14 更正）**：`bdwlan.elf` / `bdwlang.elf` 是 **WiFi 的 board data**，不是蓝牙。
`patches/wifi/0009` 的 `build.patch:937` 明确 `if not any(f['name'].startswith('bdwlan.') for f in inventory): raise RuntimeError('Missing board data')`，
`build.patch:110` 还按 `chip_id & 0x10` 在 `bdwlang` / `bdwlan` 之间选前缀。两者都已在本机副本里。

---

## 验证方式

```bash
sha256sum <workspace>/firmware/qca6490/*
```
对照上表。

设备上原始位置的权限是 `-r--r----- system system`，普通 adb 可读。
