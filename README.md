# UniXNU-mondrian

Redmi K60（代号 **mondrian**，高通 **SM8475**）的 UniXNU 设备支持仓库。

- 固件：[uefi-mondrian](https://github.com/Emilelu/uefi-mondrian)
- UniXNU 核心：[UniXNU](https://github.com/UniXNU/UniXNU)
- 文档：[unixnu.com](https://unixnu.com)

## 当前状态（2026-10-27）

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| UEFI 启动链 | ✅ | ABL -> `fastboot boot` -> BootShim -> UEFI -> UniXNU 菜单 |
| 显示 | ✅ | ABL splash framebuffer + SimpleFbDxe GOP；无 GPU 加速 |
| 实体按键 | ✅ | 官方 KeypadDevice 链 + `K60KeypadDeviceLib`（SPMI PON/GPIO） |
| Tools -> Advanced Logger | ✅ | 4 MB Advanced Logger + QR 序列帧，OneSend 可抓 DXE 全量日志 |
| XNU 内核 | ❌ | 尚无 `kernel.macho`；下一步用 Linux 工具链构建 |
| 触摸 / GPU / 音频 / 网络 / 相机 | ❌ | 未开始 |
| UFS / Data / root | ❌ | 规划使用独立 `unixnu` 分区（双系统），不动安卓 `userdata` |

## 仓库与构建

需要 UniXNU 核心、本设备仓库、`uefi-mondrian` 三个目录并列。核心仓库先打
`patches/unixnu-core/k60-unixnu-core.patch`：

```sh
git clone --recurse-submodules https://github.com/UniXNU/UniXNU
git clone https://github.com/Emilelu/UniXNU-mondrian
git clone --recurse-submodules https://github.com/Emilelu/uefi-mondrian
cd UniXNU
git checkout ae68700
../UniXNU-mondrian/scripts/apply-core-patches.sh .
./unixnu defconfig mondrian_defconfig -D ../UniXNU-mondrian
./unixnu fetch
./unixnu build firmware --uefi ../uefi-mondrian -D ../UniXNU-mondrian
./unixnu bootimg --uefi ../uefi-mondrian --dtb ../uefi-mondrian/Platforms/Xiaomi/mondrianPkg/FdtBlob/sm8475-xiaomi-mondrian.dtb --ramdisk none -D ../UniXNU-mondrian --output mondrian-boot.img
```

`unixnu fetch` 需要网络。`build firmware` 输出
`uefi-mondrian/Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd`。本机在
WSL Ubuntu 24.04 / 16 核上验证。

XNU 内核构建见 `docs/NEXT-STEPS.md`（官方支持 Linux 构建，不需要 Mac）。

## 数据安全

- 当前 bring-up 只用 `fastboot boot`（RAM 临时引导），不写任何分区；安卓
  `/data`、system、persist 均不动。
- 后续 XNU root/Data 使用**独立 `unixnu` 分区**（双系统方案：缩 F2FS +
  尾部新建分区），不写安卓 `userdata`；见 `docs/DUAL-SYSTEM.md`。
- **绝对禁止** `fastboot flash persist` / `flash all`（TEE 密钥永久损坏）。
- 写任何分区前先备份并确认目标；默认构建命令可能仍指向安卓 `userdata`。

## 许可

设备级代码采用 BSD-2-Clause-Patent。导入组件保留各自 SPDX 标记与原始许可证，
见 `THIRD_PARTY_NOTICES.md`。
