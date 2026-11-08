# K60 调试加速 · 两件成品集成说明（Agent-B 交付，Agent-A 只需集成）

日期：2026-10-27 14:30。目标：① UEFI 日志落到安卓 ramoops，重启后 adb 直接读全文；② UEFI 任何 ResetSystem 自动回 fastboot，迭代循环不再经过安卓、不再按键救砖。

## 成品 1：K60RamoopsLogLib（日志进 ramoops）

**事实依据（全部已核实）**
- K60 dtbo 26 个变体都有：`ramoops@0xa7000000`，`compatible="ramoops"`，`console-size=0x200000`，`pmsg-size=0x200000`。
- 真机 `/proc/device-tree/reserved-memory` 同址同大小（dump-reserved.sh adb 抓取）。
- 内核 `fs/pstore/ram_core.c` 校验逻辑：`sig ^= PERSISTENT_RAM_SIG` 后比对 `buffer->sig`；console zone 上层传入 sig=0（ram.c 实锤），故**存储值必须 = 0x43474244（"DBGC"）**。结构（无 ECC）：`u32 sig @0 / u32 start @4 / u32 size @8 / data[] @12`。
- MemoryMapLib 的 ramoops 条目已是 WRITE_BACK（可写）。

**集成步骤**
1. 把 `deliverables/K60RamoopsLogLib/` 三个文件复制到
   `Platforms/Xiaomi/mondrianPkg/Library/K60RamoopsLogLib/`。
2. mondrianPkg.dsc `[LibraryClasses]` 加一行：
   `K60RamoopsLogLib|Platforms/Xiaomi/mondrianPkg/Library/K60RamoopsLogLib/K60RamoopsLogLib.inf`
3. FrameBufferSerialPortLib.c：
   - 头部 `#include <Library/K60RamoopsLogLib.h>`
   - 构造函数（SerialPortInitialize）末尾加 `K60RamoopsInit ();`
   - `SerialPortWrite` 末尾（return 前）加：
     `K60RamoopsWrite ((CONST CHAR8 *)Buffer, NumberOfBytes);`

**注意**
- SEC/PEI 最早几行日志若发生在构造函数前会被跳过（mBuf==NULL 安全跳过），DXE 全量日志都会落。
- flush 范围 = 头 + 已写字节数，随日志增长，单行开销 KB 级，远小于现在 44MB 全 fb flush。
- ramoops 区有 XBL scheduler 遗留代码（fix-ramoops-xn.py 的动机）：本库只在 boot 早期 memset 该区——请确认 UEFI 阶段无执行流在该区取指；warm reset 后 PBL 从 flash 重载 XBL，理论无碍。

## 成品 2：K60RebootFastbootDxe（ResetSystem 自动回 fastboot）

**事实依据**
- K60 DT：`qcom,msm-imem@146aa000` 内 `restart_reason@65c`（reg = 0x65c/0x04）→ **cookie 地址 0x146AA65C**。
- 值表（内核 msm_reboot_call 与 bootloader check_reboot_mode 两端一致、多源交叉）：
  `0x77665500 = FASTBOOT_MODE`（cmd "bootloader"）；`0x77665501 = adb reboot`；`0x77665502 = recovery`。
- K60 走 `qcom,reboot-reason`（nvmem cell restart_reason 映射 IMEM 0x65C）。
- IMEM Cookie Base（0x146AA000+0x16000）在 MemoryMapLib 已映射 AddDev/MMAP_IO/NS_DEVICE → `MmioWrite32` 直接可用，**内存表零改动**。

**集成步骤**
1. 把 `deliverables/K60RebootFastbootDxe/` 两个文件复制到
   `Platforms/Xiaomi/mondrianPkg/Drivers/K60RebootFastbootDxe/`。
2. mondrianPkg.dsc `[Components]` 加：
   `Platforms/Xiaomi/mondrianPkg/Drivers/K60RebootFastbootDxe/K60RebootFastbootDxe.inf`
3. DXE.inc（FV 模块清单）加对应 INF 行；如用 APRIORI，放普通节即可（依赖 ResetRuntimeDxe 的 ResetNotification protocol，LocateProtocol 失败会打 WARN 退出，必要时把本驱动排在 ResetRuntimeDxe 之后）。

**效果**
- BDS 超时 ResetSystem / 任何 UEFI reset → IMEM 写 0x77665500 → ABL 读 → **直接进 fastboot**。
- 完整循环：`fastboot boot bootN.img` → UEFI 跑（日志已进 ramoops）→ reset → ABL → fastboot → `fastboot boot boot(N+1).img`。全程不碰安卓。
- DarwinBoot 正常跳 XNU 不走 ResetSystem，不受影响。

**验证**
- 上机后若仍回安卓而非 fastboot：说明小米 ABL 不认 IMEM 值，备选路线 ① misc 分区 BCB `bootonce-bootloader`（需存储驱动，payload 链通后可做）② 反汇编 imagefv_a.img 的 reboot 判定（FV 压缩，需先解 LZMA section）。

## 读取端（安卓侧零开发）

```
adb root shell cat /sys/fs/pstore/console-ramoops-0     # 上一次 UEFI 日志全文
adb root shell cat /sys/fs/pstore/console-ramoops-1     # 更早一次（若存在）
```
需要 root。若 pstore 目录为空：查 `dmesg | grep -i ramoops`（驱动没挂 → 检查 K60 内核 CONFIG_PSTORE_RAM 与 ramoops 节点变体）。

## 按键（boot33 v7）评审意见

boot33 的 EE0 owner 过滤方向正确（boot26 bus error 根因）。上机判据建议加一条：dump 表里若 EE0-owned apid 数为 0（FEATURES/owner 表为空），则 SPMI 路线死路，回退 GPIO/TLMM 方案（音量键若在 TLMM 而非 PMIC）。日志现在有 ramoops 通道后，K60BTN 的每阶段输出都能在电脑上看到，迭代会快很多。
