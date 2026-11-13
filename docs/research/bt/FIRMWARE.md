# K60 Bluetooth 固件实测（QCA6490，2026-11-14）

本文记录 BT 固件在 K60 Android 侧的**真实位置、文件名、大小与 SHA-256**，取代 `RESEARCH.md` §7 的旧推断。

## 0. 结论

- 位置：BT 固件**不在** `/vendor/firmware_mnt/image/qca6490/`（该目录是 WiFi 的 `amss*.bin`/`Data*.msc` 与 42 个 `bd_*.elf` 板级数据），而在独立分区目录 **`/vendor/bt_firmware/image/`**。
- 规模：实测 **113 个文件，合计 1,063,407 B**，已用只读 `adb pull` 取到 `E:/k60-work/firmware/qca6490-bt/` 并逐个哈希。
- 命名：不是旧推断的 `htbtfw21.tlv`/`htnv21.bin`。rampacth 实测为 **`hpbtfw20.tlv`**（201,560 B）与 **`hpbtfw21.tlv`**（146,068 B）；NVM 为 **`hpnv20*`（20 个）** 与 **`hpnv21*`（90 个，含 `g` 与 `sony` 变体）**。
- 这与 `bsd/dev/qbt/btqca.c` 的 WCN6855 分支一致：先请求 `qca/wcnhpbtfw%02x.tlv`，失败回退 `qca/hpbtfw%02x.tlv`；NVM 先 `qca/wcnhpnv…`，失败回退 `qca/hpnv…`。本机固件集只有 `hp*`/`hpnv*` 拼写，即 K60 走的是**回退名**，而 0500 的 `k60_firmware_get()` alias 正是为此写的。

## 1. 关键文件（M：本机 adb 实测）

| 文件 | 字节 | SHA-256 | 说明 |
|---|---|---|---|
| `hpbtfw20.tlv` | 201,560 | `b7fcf643ee458eab7bb21e7324b915e8772f81ee9d222e039425fa65f614f929` | rampatch（rom 0x20 名） |
| `hpbtfw20.ver` | 33 | `11d526728c6cab43d2d1200bf4e18040ec4857a1b4437e61f2ece9ff3c7c17b7` | 版本串 `BTFW.HSP.2.0.1-00252-HSP_PATCH-1` |
| `hpbtfw21.tlv` | 146,068 | `8ccb65437781f31e52ea065c0e71f0c3a0e876ef56f7abec20020f63da5fbe72` | rampatch（rom 0x21 名） |
| `hpnv20.bin` | 6,319 | `a48f55389677340a8b4a9a0531e606172909e506e1dfdbe460b684e285a830bf` | NVM 默认（bid=0） |
| `hpnv20g.bin` | 6,329 | `41192727f175139b21dbc5d57aa179f1753a2f51a89961030e7b9836f6bc3653` | NVM 默认（GF 变体） |
| `hpnv21.bin` | 6,602 | `bacab7345f02c4f34b7e95fef09be941bef82569781507a5ad42aaff41d3a859` | NVM 默认（rom 0x21） |
| `hpnv21g.bin` | 6,442 | `e2bc61dd8152e640a6f8f0ec2eb91403e02b97cc60ba455dd584e425de361552` | NVM 默认（rom 0x21，GF） |

计数：`hpnv20*` 20 个（10 个普通 + 10 个 `g`，含 `.bin` 与 `.bXX` 板级变体，如 `hpnv20.b2f`、`hpnv20g.b8d`）；`hpnv21*` 90 个（`.bXXX` 板级变体 + `g` + `hpnv21_sony.302`）。总计 113 = 3 个 `hpbtfw*` + 110 个 `hpnv*`。

全部文件哈希可用一条命令复现（见 §5）。`hpnv21_sony.302` 不在 0500 白名单内，`btqca` 也不会请求，staging 时可忽略。

## 2. 设备侧证据（M）

- 设备 6033dbec 处于 Android 启动（2026-11-14 只读会话）。
- `find /vendor /system /product -maxdepth 5 \( -iname '*btfw*' -o -iname '*.tlv' -o -iname '*htnv*' -o -iname '*hpbtfw*' -o -iname '*hmt*' \)` → 只有 `/vendor/bt_firmware/image/hpbtfw20.tlv`、`hpbtfw20.ver`、`hpbtfw21.tlv` 三个 rampatch 命中。
- `ls -l /vendor/bt_firmware/image/` → 113 项；除 §1 文件外全部为 `hpnv20*`/`hpnv21*`/`hpnv21g*`。
- DT：`/proc/device-tree/soc/bt_qca6490/compatible` = `qcom,qca6490`；`/proc/device-tree/soc/qcom,qup_uart@894000/compatible` = `qcom,msm-geni-serial-hs` —— 与 live FDT 反编译一致。
- Android BT 状态：`dumpsys bluetooth_manager` 初始 `State: OFF`；`cmd bluetooth_manager enable` 后 `State: ON`，但 `/sys/class/bluetooth/` 为空、无 `hci0`，servicemanager 报 VINTF 缺 `android.hardware.bluetooth.IBluetoothHci/default`。dmesg 可见 `bluetooth_power: on: 1|2`、`btpower_set_xo_clk_gpio_state:gpio(505) success`。
- 结论：本轮 Android 的 BT HAL 未注册 HCI，**拿不到** `QCA controller version`/`Downloading qca/...` 运行日志；文件身份是 M 级，`rom_ver` 与 board id 仍需 HCI 起来后确认（见 §4）。
- 只读拉取：`adb pull /vendor/bt_firmware/image/. E:/k60-work/firmware/qca6490-bt/` → 113 files, 1,063,407 B。

## 3. `btqca.c` 选名逻辑（A：0500 内同一文件的行号）

| 步骤 | WCN6855 分支 | 行号 |
|---|---|---|
| rom_ver | `((soc_ver & 0x00000f00) >> 4) | (soc_ver & 0x0000000f)` | `btqca.c:770-779` |
| rampatch 首选 | `qca/wcnhpbtfw%02x.tlv` | `:822-824` |
| rampatch 回退 | `qca/hpbtfw%02x.tlv` | `:847-852` |
| NVM 首选 | `qca_read_fw_board_id` + `qca_get_nvm_name_by_board("wcnhpnv")` | `:884-888`、`:715-745` |
| NVM 回退 | 同函数换成 `"hpnv"` | `:915-921` |
| GF 变体 | `(soc_id & QCA_HSP_GF_SOC_MASK) == QCA_HSP_GF_SOC_ID` → 插 `g` | `:723-728` |

命名格式（`qca_get_nvm_name_by_board`，`:715-745`）：

- `bid == 0 || bid == 0xffff` → `qca/<stem><rom_ver:02x><g?>.bin`
- 否则 → `qca/<stem><rom_ver:02x><g?>.b<bid:02x>`

即设备上的 `hpnv20.b2f` 对应 stem=`hpnv`、rom_ver=0x20、GF 否、board id=0x2f；`hpnv20g.b8d` 对应 GF 变体 + bid 0x8d。

## 4. 与已 staged 内核后端的兼容性（核对 `qbt_k60.c`）

- 白名单 `k60_firmware_name_ok()`（`qbt_k60.c:815-856`）接受 `hpbtfw|wcnhpbtfw|htbtfw` + 2 位 hex + `.tlv`，以及 `hpnv|wcnhpnv|htnv` + 2 位 hex + 可选 `g` + `.bin` 或 `.b<2-4 hex>`。实测 `hpbtfw20.tlv`、`hpnv20.bin`、`hpnv20g.b2f`、`hpnv21.b10c` 全部通过；`hpnv21_sony.302` 不通过。
- alias（`qbt_k60.c:924-960`）：`wcnhpbtfw→hpbtfw→htbtfw`、`wcnhpnv→hpnv→htnv`，命中回退名时会打印实际文件名。
- 根路径：`K60_BT_FIRMWARE_ROOT "/private/var/ngpu/firmware/qca"`（`:158`），roots 表（`:863-869`）另有 `/vendor/firmware/qca`、`/vendor/firmware`、`/firmware/image`、`/modem/image/qca6490`。**不含** Android 真实路径 `/vendor/bt_firmware/image` —— 对 iOS 正常启动无影响；若想让 dev 构建直接复用 Android 分区，需要 Lead 加一行。
- 文件名以 `qca/` 开头，reader 会剥掉前缀再拼根（`:867-874`）；因此 iOS 落盘路径为 `/private/var/ngpu/firmware/qca/hpbtfw20.tlv`。

## 5. staging 方案（属 Lead 写权限）

仿 sheng 三件套：

1. `firmware/bluetooth/manifest.json`：`repository` / `commit` / `files{bytes,sha256}`（sheng 的 schema，见 `UniXNU-sheng/firmware/bluetooth/manifest.json`）。
2. `scripts/stage-bluetooth-firmware.py`：sheng 版（`UniXNU-sheng/scripts/stage-bluetooth-firmware.py`）把名字正则写死成 `hmtbtfw[0-9a-f]{2}\.tlv|hmtnv[0-9a-f]{2}\.(bin|b[0-9a-f]{2,4})`（WCN7850）。K60 需改成 `(wcn)?hp(btfw|nv)…` 形式，并允许 `g` 变体与 `.bXXXX`；落盘前缀取 `K60_BT_FIRMWARE_ROOT` 的去 `qca` 父目录（`/private/var/ngpu/firmware`）或直接按 `package/BluetoothFirmware.h` 等价常量。
3. `board.toml` `[payload.runtime]`：`bluetooth_tool = "scripts/build-bluetooth-userspace.py"`、`bluetooth_target = "ios20"`（20G81 口径；sheng 是 `ios27`）。

来源目录：`/mnt/e/k60-work/firmware/qca6490-bt`（用 `--source` 传入）。**不要把厂商固件提交进仓库**——sheng 也是外部固件仓 pin hash；K60 可先本地 pin（`hardware_verified=false`），需要时再建私有固件仓。

最小 manifest 片段（在确认 `rom_ver` 前建议 20/21 双份 + `hpnv20*`/`hpnv21*` 全量，总计约 1.06 MB）：

```json
{
  "repository": "local:/mnt/e/k60-work/firmware/qca6490-bt",
  "commit": "device-pull-2026-11-14",
  "files": {
    "hpbtfw20.tlv": {"bytes": 201560, "sha256": "b7fcf643ee458eab7bb21e7324b915e8772f81ee9d222e039425fa65f614f929"},
    "hpbtfw21.tlv": {"bytes": 146068, "sha256": "8ccb65437781f31e52ea065c0e71f0c3a0e876ef56f7abec20020f63da5fbe72"},
    "hpnv20.bin": {"bytes": 6319, "sha256": "a48f55389677340a8b4a9a0531e606172909e506e1dfdbe460b684e285a830bf"},
    "hpnv20g.bin": {"bytes": 6329, "sha256": "41192727f175139b21dbc5d57aa179f1753a2f51a89961030e7b9836f6bc3653"},
    "hpnv21.bin": {"bytes": 6602, "sha256": "bacab7345f02c4f34b7e95fef09be941bef82569781507a5ad42aaff41d3a859"},
    "hpnv21g.bin": {"bytes": 6442, "sha256": "e2bc61dd8152e640a6f8f0ec2eb91403e02b97cc60ba455dd584e425de361552"}
  }
}
```

全量 113 个文件的哈希：

```bash
wsl -e bash -lc 'cd /mnt/e/k60-work/firmware/qca6490-bt && sha256sum * | sort -k2'
```

## 6. 尚不能离线确定（只有一项）

- 本机真实 `rom_ver`（0x20 还是 0x21）与 board id（`.bXX`）：需 HCI 通道起来后由 `btqca` 打印 `QCA controller version 0x…` 与 `QCA Downloading qca/…`（S2/S3 日志或一轮正常 Android BT 启动）。保底做法：同时 staging 两个 rampatch 与 `hpnv20*`+`hpnv21*` 全量，运行时按名取。
- 42 个 `bd_*.elf` 属 WiFi 侧板级数据，与 BT rampatch/NVM 无关，不要混放。

## 7. 复现命令

```bash
adb shell "ls -l /vendor/bt_firmware/image/"
adb shell "cat /proc/device-tree/soc/bt_qca6490/compatible; echo"
adb pull /vendor/bt_firmware/image/. E:/k60-work/firmware/qca6490-bt/
wsl -e bash -lc 'cd /mnt/e/k60-work/firmware/qca6490-bt && sha256sum * | sort -k2'
```

## 8. 对 RESEARCH.md 的影响

- §7 的「预期 `htbtfw21.tlv`/`htnv21.bin`、rom_ver 0x21」作废，改为本文。
- §8 的 I-2 关闭；I-3 缩窄为「本机 rom_ver/board id 待 HCI 确认」；I-8（是否要 `qca/` 子目录）关闭：reader 剥前缀后拼根。
- S4（固件）从「被 Android 启动阻塞」变为「只差 staging 接线（Lead）」。
