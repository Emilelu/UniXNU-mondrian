# K60 移植下一步

日期：2026-10-27。当前已通过：UEFI 全链、显示、按键、Tools -> Advanced Logger QR。
下面按顺序推进，**一次只做一步**，每一步都留 QR 日志。

## 1. XNU 内核 `kernel.macho`

官方支持 Linux 构建（`UniXNU/docs/guide/requirements.md`），不需要 Mac：

```sh
# 一次性，需要 root；会编译 clang/cctools/mig/iig/lzfse 到 /opt/unixnu-linux
cd ~/UniXNU                       # the UniXNU core checkout
sudo scripts/linux/setup-toolchain.py
./unixnu build kernel -D ../UniXNU-mondrian
```

产物：`<output>/kernel/kernel.macho`（`unixnu status` 打印 output 路径）。
本机 WSL：16 核 / 9.7 GB RAM / 947 GB 空闲；工具链构建耗时长，先确认 sudo。

## 2. Payload（FAT 卷）

```sh
./unixnu build payload -D ../UniXNU-mondrian
./unixnu bootimg --uefi ../uefi-mondrian --dtb ../uefi-mondrian/Platforms/Xiaomi/mondrianPkg/FdtBlob/sm8475-xiaomi-mondrian.dtb -D ../UniXNU-mondrian --output mondrian-boot-payload.img
```

- 检查 `boot.json` 的 `ramdisk_bytes` 非 0。
- payload/ramdisk 必须 **4 KiB 对齐**（坑 8）；否则 `UniXNURamDiskDxe` 会跳过。
- 需要 trust cache / Data seed / unique chip ID 等输入时，按
  `unixnu.local.toml` 和 `docs/building.md` 准备。

## 3. boot_args / DT / 内存窗口

首启只改这几项（详见 γ 交付包）：

- 内存窗口 **p0prime**：`dram-base = 0xB9200000`，
  `dram-size = 0x26C0000`（620 MiB）；4K 空闲页应为 **145502**，
  16K 为 **36905**。给大 = 无声猝死（XPU 墙 0xE9F00000）。
- 命令行：`-v keepsyms=1 debug=0x14e cpus=1`；**不要 `cpus=8`**。
- ADT sidecar 必须含 `RAMDisk`/`TrustCache`/`darwinboot-memory-size` 占位；
  DarwinBoot 缺占位会 `EFI_COMPROMISED_DATA`。
- 首启看 QR 日志里的 `vm_page_bootstrap` 页数，对不上先查 ADT/foot，不要先查驱动。

## 4. 存储：独立 `unixnu` 分区（双系统）

先读 `docs/DUAL-SYSTEM.md`。要点：缩 F2FS + 在 userdata 尾部新建
`unixnu`，安卓 `userdata` 保留；TWRP + root ADB + 解密 + F2FS 在线缩容是硬前提。
K60 的 UFS/Data/root 必须显式指向 `unixnu`，**不能**用默认 userdata。

## 5. 驱动与用户态

按依赖顺序：UFS/GPT -> APFS/HFSX root -> 显示/触摸（K60 是 Goodix）-> GPU
（Adreno 730）-> 音频/网络/电源。每项都要有 QR 日志和页面判读，不要凭“感觉”推进。

## 安全规则

- bring-up 只用 `fastboot boot`；不 `flash` 分区。
- `persist` 绝对禁刷；`flash all` 禁。
- 任何分区写之前：备份、确认目标、用户明确同意。
- 一次只改一个变量；失败也上板。
