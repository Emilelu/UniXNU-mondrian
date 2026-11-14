# qca6490 WiFi 固件清单

> 来源：设备 `/vendor/firmware_mnt/image/qca6490/` 只读 `adb pull`，2026-11-14
> 设备：Redmi K60（23013RK75C）/ mondrian / SM8475 / 序列号 6033dbec
> 提取方式：设备启动到 Android 后 `adb pull`，未挂载、未写入任何分区

---

## 1. PWF2 打包实际需要的 4 个文件

`scripts/build-k60-wifi-native.py` 的 `--firmware` 硬校验要求这 4 个文件同时存在，
缺一即 `raise 'Actual Pong modem firmware required'`：

| 文件 | 大小 | sha256 |
|---|---|---|
| `amss.bin` | 5,470,128 | `a626cfc1882b3e386154fac655652005e8f20ff0176b4c63de99cd082d5d75c2` |
| `amss20.bin` | 5,296,128 | `903c378a972b4294fef5c926e34c2cfb03eb042f6a1e38101f0073b33792df86` |
| `m3.bin` | 266,684 | `ad234ac8879e29a113893b87dc90335cff8eb89717580d5a06a49e7b9e322ed7` |
| `regdb.bin` | 24,278 | `06810e85c94c8f412c4e72cb38546cac90db7fdbadd45aae00f977f862d38a7b` |

**合计 11,067,094 B** —— 与 `build-report.json` 里 `firmware_bytes=11067094` 逐字节吻合。

本地存放（不进仓库，体积太大）：

- 干净四文件目录（**打包必须用这个**）：`E:\k60-work\firmware\qca6490-wifi\`
- 完整原始提取目录（222 个文件）：`E:\k60-work\firmware\qca6490\`

**为什么要单独建干净目录**：`build-k60-wifi-native.py` 会把 `--firmware` 目录下
**所有**文件都打进 PWF2 包。直接指向原始目录会得到 13,029,078 B / 10 个文件的包，
把无关的 `Data.msc`、`bd_*.elf` 全塞进内核镜像。

---

## 2. PWF2 包结构（实测，可作 ⑦ 产物检查判据）

生成物 `PongWifiFirmware.bin` 11,067,094 B，头部布局：

```
offset 0   : magic "PWF2"          (4 B)
offset 4   : count = 4             (u32 LE)
offset 8   : 4 × 40 B 条目         (name[32] / offset u32 / size u32)
offset 4096: 第一个 payload（4 KiB 对齐起点）
```

头长度 = `(8 + 4*40 + 4095) & ~4095` = **4096**。实测条目：

| name | offset | size |
|---|---|---|
| `amss.bin` | 4096 | 5,470,128 |
| `amss20.bin` | 5,476,352 | 5,296,128 |
| `m3.bin` | 10,772,480 | 266,684 |
| `regdb.bin` | 11,042,816 | 24,278 |

校验方式：

```bash
python3 - <<'PY'
import struct
b = open('/opt/k60/trees/k60build/wifi/native-real/PongWifiFirmware.bin','rb').read()
assert b[:4] == b'PWF2', b[:4]
n, = struct.unpack_from('<I', b, 4)
for i in range(n):
    name, off, size = struct.unpack_from('<32sII', b, 8 + i*40)
    print(name.rstrip(b'\0').decode(), off, size, b[off:off+4].hex())
PY
```

内核侧消费者：`PongWifiPlatform.cpp` `loadFirmware()` —— 校验 magic `PWF2`，
按 40 字节条目查名字，`memcpy` off/len。符号 `_pong_wifi_firmware` /
`_pong_wifi_firmware_end` 由 `PongWifiFirmware.s` 的
`.section __TEXT,__const` + `.incbin` 提供。

---

## 3. 每个文件在 ath11k 里的角色

K60 的 PCI 端点 `0x1103` 在 Linux `ath11k/pci.c` 里就是 **WCN6855**：

```
drivers/net/wireless/ath/ath11k/pci.c:32   #define WCN6855_DEVICE_ID 0x1103
drivers/net/wireless/ath/ath11k/pci.c:1024 case WCN6855_DEVICE_ID:
drivers/net/wireless/ath/ath11k/pci.c:1321 MODULE_FIRMWARE(ATH11K_FW_DIR "/WCN6855/hw2.0/*")
```

所以走 **hw2.0 固件集**：

| 文件 | 角色 |
|---|---|
| `amss.bin` | MHI 主固件（QMI `fw_get`），ath11k 把它经 MHI 下载进 QCA6490 |
| `amss20.bin` | 第二版 AMSS，`ath11k_core_firmware_request` 按 board/chip id 选择 |
| `m3.bin` | M3 协处理器固件，MHI 启动序列里第一个被加载的镜像 |
| `regdb.bin` | 监管域数据库（regulatory.db 的 QCA 变体），决定可用信道/功率 |

**board data 不在这 4 个里**：ath11k WCN6855 的 board data 是 `bdwlan.*`
（BDF）。设备上有 `bdwlan.elf` 59,932 B（sha256
`2ddf43c01f2ef490cd5128c56e6ef0f8704dbc675a351ea37d8ae6eb93404231`）与
`bdwlang.elf` 59,936 B（sha256
`895d5028b5a40f9e0ca84c0f3ac9619d5f99f97d0f36031310f2638f4c7e002b`），
另有 `bdwlan.e01`..`ee1` 约 160 个变体。

Pong 路线**不从这 4 个文件取 BDF**：`build-k60-ath11k.py` 在 `core.c` 里按
QMI 返回的 board_id/chip_id 现场拼文件名（`id==0xff` → `"%s.elf"`；
`id<0xff` → `"%s.e%02x"`；否则 `"%s%02x.e%02x"`），文件名再由
`PongAth11k.c` 的固件查找钩子解析。**不允许随便挑一个 bdwlan 文件冒充 BDF**
（见 `drivers/PongWifi/proprietary-files.txt` 注释：No fabricated MAC/calibration）。

---

## 4. 原始提取目录里的其它文件（不进 PWF2）

| 文件 | 大小 | 用途 |
|---|---|---|
| `Data.msc` | 889,524 | **modem 数据，不是 WiFi 校准**（旧版本本文档写错） |
| `Data20.msc` | 916,071 | 同上，第二版 |
| `regdb_xiaomi.bin` | 24,278 | 小米改版 regdb（sha256 `b7647cde6c6b157c11d2ed54f4da74abce653a3d70456e52665292369e560588`）|
| `bdwlan.elf` / `bdwlang.elf` | 59,932 / 59,936 | BDF，见上 |
| `bdwlan.e01`..`ee1` | ~160 个 | BDF 变体 |
| `bd_*.elf` | 42 个，各约 60 KB | 蓝牙固件，WiFi 不需要 |

设备上原始权限 `-r--r----- system system`，普通 adb 可读。

---

## 5. 备用固件源（未采用，仅记录）

`https://raw.githubusercontent.com/armbian/firmware/master/ath11k/WCN6855/hw2.0/`
提供 `amss.bin` 4,988,928 / `board-2.bin` 6,429,240 / `m3.bin` 266,684 /
`regdb.bin` 24,310 / `Notice.txt` 152,394，均 HTTP 200。

**未采用理由**：`m3.bin` 大小与真机一致（266,684）但 `regdb.bin` 不同
（24,310 vs 真机 24,278），`amss.bin` 也小 480 KB。真机固件优先——它是这台
设备 vendor 分区里实际在跑的版本。

---

## 6. 取固件为什么只能走 adb

| 途径 | 结果 |
|---|---|
| `adb pull`（Android 在线） | ✅ 成功，222 文件 |
| `fastboot fetch <part> <out>` | ❌ `Unable to get max-fetch-size. Device does not support fetch command.` |
| 挂载 modem 分区 | ❌ 违反铁则 4（绝不写设备分区） |
| stock ROM / vendor.img 解包 | ❌ 本机无任何归档 |

→ 取固件的唯一合法途径是**把设备启动到 Android 再 `adb pull`**，不改分区。
Windows 侧 adb 必须用 Windows 路径（WSL 的 `/mnt/e` 路径会报
`cannot create file/directory`）：

```bash
./adb.exe pull /vendor/firmware_mnt/image/qca6490/m3.bin 'E:\k60-work\firmware\qca6490\m3.bin'
```

---

## 7. 验证方式

```bash
sha256sum /mnt/e/k60-work/firmware/qca6490-wifi/*
# 对照 §1 表格四行
```

---

## 8. 板级数据（BDF）缺口 —— 通往"扫到 AP"的最后一块固件

PWF2 包现在只有四个文件（amss / amss20 / m3 / regdb）。**ath11k 还需要一份
board data（`bdwlan*`）才能过 WMI 初始化**，而它不在包里。

请求路径（逐行核对过）：

- `scripts/build-k60-ath11k.py:97-113` 把 `core.c` 里
  `bd->fw = ath11k_core_firmware_request(ab, name);` 前面插了一段：
  当 `name` 是 `ATH11K_DEFAULT_BOARD_FILE`（`board-2.bin`，这台机器的
  firmware 分区里没有这种容器）时，就按**真实的 QMI board/chip id** 拼名字：
  `chip_id & 0x10` 决定前缀 `bdwlang`/`bdwlan`，`board_id == 0xff` → `%s.elf`、
  `< 0xff` → `%s.e%02x`、否则 `%s%02x.e%02x`，并在请求**之前**打一行
  `ath11k_info(ab, "Pong: actual QMI board firmware %s\n", name)`。
- `drivers/PongWifi/PongWifiPlatform.cpp:538-546` 的 `fwGet()` 按**文件名**在
  PWF2 里查找（`name` 取路径最后一段；`amss.bin` 在 TCSR HW major == 2 时换成
  `amss20.bin`）。文件不在包里就返回 `-1`，ath11k 的 board data 加载失败。

因此：

1. `stage=8` 那次上机**一定会打印我们需要哪一个 BDF**（`Pong: actual QMI board
   firmware bdwlan.eXX`），紧接着才会因为包里没有它而失败。这行日志就是选择依据，
   不需要猜（proprietary-files.txt 明确禁止乱挑 bdwlan）。
2. 拿到名字后回 Android 用 adb pull 那一个文件（或整套 `bdwlan.*`/`bdwlang.*`），
   放进 `/mnt/e/k60-work/firmware/qca6490-wifi/`，重编 archive + 内核。注意
   `build-k60-wifi-native.py` 会把目录里**所有**文件打进 PWF2，所以目录要保持
   "只放需要的"。
3. 本机已有两个可直接用的候选（真机 pull，未打包）：
   `bdwlan.elf` 59,932 B `2ddf43c01f2ef490cd5128c56e6ef0f8704dbc675a351ea37d8ae6eb93404231`、
   `bdwlang.elf` 59,936 B `895d5028b5a40f9e0ca84c0f3ac9619d5f99f97d0f36031310f2638f4c7e002b`，
   位于 `/mnt/e/k60-work/firmware/qca6490/`。它们覆盖 `board_id == 0xff` 的情况；
   设备上还有 `bdwlan.e01..ee1` 约 160 个分片（未 pull）。
4. stages 1–8 的 host 侧流程都不需要 BDF，BDF 只在最后一级 `ath11k start`
   之后才被请求，届时按上面第 1 步读日志再补（六文件包见 §9）。

## 9. 六文件包（含板级数据）已预构建

上面的第 3 步已经做了：`/mnt/e/k60-work/firmware/qca6490-wifi-bdf/` 里放了
六个文件（四个原样 + `bdwlan.elf` + `bdwlang.elf`），用它编出的 archive 是
`/opt/k60/trees/k60build/wifi/native-bdf/libPongWifiNative.a`（12,066,184 B，
`build-report.json` 记 `firmware_files=6, firmware_bytes=11,189,974`）。
配方：`E:\k60-work\evidence\wifi-trial\build-bdf-archive.sh`（archive）、
`build-bdf-kernel.sh`（内核）。

这两份 BDF 覆盖 `board_id == 0xff` 的情形。若上机日志里的
`Pong: actual QMI board firmware` 打出的是 `bdwlan.eXX` / `bdwlang.eXX`
而不是 `.elf`，说明真机 board id 不是 0xff，需要回 Android
`adb pull /vendor/firmware_mnt/image/qca6490/<那个文件>` 再重编——
依然不需要猜，名字由日志给出。

### 9.1 拿到 BDF 名字之后：一条命令重编

名字由日志给出（`Pong: actual QMI board firmware bdwlan.eXX`），接下来的重编已经脚本化，不需要手改目录：

```
bash E:\k60-work\evidence\wifi-trial\pull-board-data.sh 6033dbec      # 只在手机能 adb 时
bash E:\k60-work\evidence\wifi-trial\mkboot-bdf-add.sh bdwlan.e1a bdf1
```

`mkboot-bdf-add.sh` 做的事（全部在 WSL 里跑，`UNIXNU_SKIP_GATES=1`）：

1. 以六文件包 `/mnt/e/k60-work/firmware/qca6490-wifi-bdf/` 为底，把
   `/mnt/e/k60-work/firmware/qca6490-board/<名字>` 拷进去，得到
   `qca6490-wifi-bdf-<tag>/`（`build-k60-wifi-native.py` 会把目录里所有文件打进 PWF2，所以**只放需要的**）；
2. 重编 archive 到 `wifi/native-<tag>/`；
3. 重链内核（先删 `mach.development.pong` 强制重链），打印新内核 sha256 与大小；
4. `unixnu build payload` + `unixnu bootimg`，只追加 `--kernel-arg pong_wifi=1 --kernel-arg k60_wifi_rsc=2`
   （**不带 k60_wifi_stage**，命令行 602 字节，低于 607 硬线）；
5. 用 `payload.json` 的完整 `kernel_args` 写 manifest，再跑 `verify-boot-image.py` +
   `argcheck1.py` + `check-artifacts.py` + `sha256sum`。

名字不在本地时脚本直接退出（`MISSING ... -- run: bash pull-board-data.sh 6033dbec`，退出码 2），
不会编出一个缺 BDF 的镜像冒充成功。
注意：加上 BDF 后 PWF2 从 11,067,094 B 变成 11,189,974 B，内核
`__TEXT` 段相应变长（见 `LOCAL-VERIFICATION.md` 的段表），但离 DarwinBoot 的
254 MiB 上限仍然极远。

