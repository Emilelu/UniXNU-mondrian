# 电源相关固件清单（官网 §1 :15）

状态：**只记录本分支实际用到的二进制与哈希；没有覆盖整机所有固件，也没有版本号字符串**。
官网 §1 最后一行要求「在固件清单中记录每个二进制的来源和版本」
（快照 `E:/k60-work/scratch/power-page-20261117.txt:15`）。本文件先补齐电池/ADSP/引导
这条链上的输入，避免每次排障都靠目录里的临时文件名。

## 1. ADSP 固件（SplitFirmware，23,016 KB）

本地缓存：`/mnt/e/k60-work/firmware/adsp/`。来源压缩包：
`/mnt/e/k60-work/firmware/mondrian-fw-OS3.0.8.0.zip`，188,863,584 B，
sha256 `f25e1d3b4d0ee39bcdc3037712ef754c7559eac2006131d3e008a0706efe3e8c`。
解包到 `adsp/` 的关系没有仓库内脚本，下一次重建时要补。

`adsp.mdt` 5,404 B sha256
`1238098817957c4d3cd0995fd413332751ac8082ea315e6e1d9bdb247cadc694`；
段文件缺少 `b24`（0–25 中只有 26 个文件：b00–b23、b25），使用前要确认固件本来就没有该段。

| 段 | 字节 | sha256 |
| --- | --- | --- |
| b00 | 884 | `4a2045327dced80500f97214ce3f9e6b60294e7ef34c3e35d8503b30602c0fdc` |
| b01 | 6,952 | `0fe0228c0dee94ff9177bf509db4cbf6e923ed9570f08aba4ed5ebff605b1e26` |
| b02 | 3,216,484 | `5a6d92aa2423fb5a4dbe2543457f17f43f5b4f1a45db3413e8dd435e59e19622` |
| b03 | 25,720 | `c98212af9fcd831bfd942bdca7419ac515394ea26123ffbc56281915c0f97a39` |
| b04 | 34,632 | `a9129e39a8277f87927bc44e857e2ab0d324bb29a3dd8646c05b9ce1d8989e27` |
| b05 | 710,336 | `63500752812e8fb744fc54c308a46e8564caca96218cfb1616577322b4bb41b6` |
| b06 | 220 | `a13aa0238d1852ade8fc104ce6ef9420004a9ff0faabcb253703435b1c5f2a32` |
| b07 | 4,892 | `9f4b3f164a21a97aeaf3d3d2ddcdbfe6da198fa600ac2ddbce1e63e6c56229bc` |
| b08 | 2,306,824 | `3e26c0d0875f533d1921eb5e0a2cbc4e13c595619d6c95f33fa983b883394ac0` |
| b09 | 237,576 | `11c99547d2f4d8faf53b8eeadc8b5fa4fcea2f0f5707b5ea567cd96311e17708` |
| b10 | 720 | `2dd820156d2e4394aab396a5f7bb1c0266abfe42eefd4ae8115234a5236b0ffc` |
| b11 | 9,960 | `56c7ce1fe6ae2b2cbbc43c8a54f6fb607b1681a560cd9a915cc9bbd6df26aca4` |
| b12 | 131,232 | `b852040e758c8ec3fa0e5751ada0eaad140aa6cc810a2f30384b00c9f494a5f7` |
| b13 | 83,220 | `2f0062a982a9e8c822462cc9af41e5a5f22e63fb5f356d88858e02944c51a80f` |
| b14 | 3,167,652 | `2284e98961fc542ca215a4e94c7ad00269f03d0a2651a5d7c2cf5329c8ade00d` |
| b15 | 108,732 | `46c9f2da8a3ad01c685fa9af3a67b4216ef44743881e559d1cdbb17bfbc87450` |
| b16 | 280 | `548d0d3693226833558cff469a4e1ab2ad55e38fd0742ad0e2efadad698dab27` |
| b17 | 185,008 | `f473c8ba64ad2f67e80a8232901418e12fd2861b00ffebd11b5504bc6635bfb7` |
| b18 | 11,511,192 | `a6d0472d3e7d83dbe1b946ba2849c0a9450a68bad1e0c3e792335e868247d45c` |
| b19 | 503,816 | `7c1b7a1eefebc03870dee4654ce214f86a45cda5cd5240f980714d6f53e4bf9e` |
| b20 | 1,936 | `72bbe02f5d750906f143b962a7c5b65bdb775a19153cf04eb6e9400e5270ebec` |
| b21 | 201,084 | `85c94c36045a0fc6a944b329e4eeb8843fae2010b7be8d81f0f08a3b772128c7` |
| b22 | 103,736 | `f846a8d8c4e58c3ab9d68e2577ade5fdd19fcc84a7fed608a26c600ac582e66d` |
| b23 | 942,080 | `708fa8140e70c4cf1334455a64bb3ddbb4a25ffb7670a80b3702e942c2385b61` |
| b25 | 4,520 | `3c89dddb60792e1e986cb38c71be6605636a0f928570be43b08fdb956e7869c9` |

服务注册元数据：

- `adspr.jsn` 513 B sha256
  `66ce8531efb7979d234e0f0eabbe18d038ac97da771a8a194f613df8f0724e81`：
  `root_pd`，QMI instance 74，service `servreg`。
- `adspua.jsn` 703 B sha256
  `982a99853495e34726b8e44697fdfad303334de0a67cbf6cde306c8f1731000b`：
  `audio_pd`，额外注册 `avs/audio`。
- 两者 `sr_version` 都是 1.1.1；没有人类可读的固件版本号，只能靠哈希锁定。

## 2. 电池充电器内核模块

`/mnt/e/k60-work/firmware/qti_battery_charger_main_m81.ko`，247,776 B sha256
`914d12fe026f13bd6c8e0b470872502e6560a2f2d51278d30e1822d1cd758a48`。

它只用于 `scripts/build-battery-archive.sh` 提取属性/结构体定义，不加载进 XNU。
可观察字符串包括 `XM_PROP_AUTHENTIC`、`XM_PROP_SLAVE_AUTHENTIC`、`PD_PPS`，
但没有 `hmac`/`sha256`/`2717` 字样，说明认证不在这个内核模块里做（见 §4）。

## 3. 引导与 UEFI 输入

| 文件 | 字节 | sha256 | 用途 |
| --- | --- | --- | --- |
| `measured-8g.fd` | 3,145,728 | `cf4485712c2999c1fb7c1937a5b1f836dd3e9150073fb9b151b581d375195d0f` | image e/f/g/h 的 carrier FD |
| `measured-high-darwin22.fd` | 3,145,728 | `1c870bb2add6fffe82fb605d5215fde1695523ed8d7d9d7fad8c74a515b3b755` | 另一份 UEFI 构建输入 |
| `hi4g-before-repair.fd` | 3,145,728 | `bada90e777db7db7b16bc8c1108f802b16ac49fea29b5bae6a43605d3d1b1426` | 修复前备份 |
| `hi4g-before-repair-DarwinBoot.efi` | 30,208 | `3b6e25740fd19e55259449820210fb8a98f631d996f8bb7dcbb321ee13467b57` | 修复前 DarwinBoot |

## 4. 还没记录的

- 整机其他固件（modem、IPA、Wi-Fi/BT、touch、display）不在本文件范围；§1 :15 的完整清单
  需要全仓库层面的清单，不能由电源线单独完成。
- 认证相关的固件/密钥没有来源记录：K60 内核模块只暴露 `authentic` 属性，实际 HMAC
  与适配器校验在 DSP 或用户态，当前没有可核对的二进制与密钥来源。
- ADSP 固件的实际运行版本没有从设备读回（`adsp.mdt` 只有哈希），所以「版本」目前等于
  「这份缓存文件的哈希」。

## 5. 参考

- 官网快照：`E:/k60-work/scratch/power-page-20261117.txt:8-15`。
- 构建输入：`scripts/build-battery-archive.sh`、`E:/k60-work/scratch/build-final-image-f.sh`。
- 认证边界：`docs/research/charger/10-POWER-DOC-CONFORMANCE.md` §7.11、§9。
