# ADSP 固件载体决策（round 32，2026-11-13）

ADSP 的 PAS1 装载器已经在内核里（`bsd/dev/pong_adsp_boot.c` + `pong_adsp_pas.c` + `pong_fat.c`，
由 `patches/xnu/0613`、`0614` 引入），唯一缺的是**固件字节本身**：内核必须在 `bsd_init` 之后、
Data 卷挂载之前拿到 `adsp.mdt` + `adsp.b00..b25`（26 个文件，23,494,284 字节）。

这份文档把"用哪条路把字节送进内核"钉死，并把已经排除的路连同证据记下来，避免下一轮重新试错。

## 一、已排除

| 路径 | 结论 | 证据 |
| --- | --- | --- |
| `vmd0` / `md0` 引导参数 | **死路**：窗口能映射，第一次读 FAT 引导扇区（映射基址 + 0x1FE）就 `esr: 0x96000010`——同步外部中止，不是地址翻译失败。说明地址不是 AP 可访问的物理地址（固件虚拟地址或 XPU 保护区），`mdevadd()` 的 `vmd` 分支要求的是已由 XNU 映射过的 VA | `docs/research/audio/ADSP-MD0.md`；`usblog-20261113-124204` |
| 内核内嵌 23.5 MB blob | **不采用**：`patches/xnu/0401-embedded-init.patch` 已经 1.6 MB 就很吃力；23.5 MB 会让 `patches/xnu` 序列每次 `git diff`/`apply` 变成分钟级，且内核 `__DATA` 直接涨 23.5 MB，换不来可维护性 | `patches/xnu/series` 216+ 项；`apply` 实测 |
| 内核自己读 `adsp_a` 分区 | **当前不可行**：`drivers/NativeUfs/RootCommands.h:289` 的 `hostRead4k()` 是 `static`，只在 kext 内部可见；BSD 侧没有任何已导出的块设备读接口。要走这条路必须先给 `NativeUfs` 加 IOKit 方法或导出 C 符号，属于独立工程 | `drivers/NativeUfs/*.h` 无 `read` 导出 |
| 推迟到 Data 挂载后再加载 | **不可行**：PAS1 必须在音频/电池消费者之前完成，电池驱动 `K60PmicGlink::open()` 要求 `epoch != 0` 的 lease 才肯建链 | `drivers/PongPower/K60PmicGlink.cpp:120` |

## 二、选定方案：固件把 ADSP 精确放到固定物理地址，ADT 只带常量

```
boot.img
 ├─ 固件卷（FD）            ← UniXNU + DarwinBoot
 ├─ payload FAT（0x87000）  ← EFI/UniXNU/{unixnu.toml, Payloads/kernel.macho}
 │                            新增 EFI/UniXNU/ADSP/ ← 26 个 adsp 文件（构建期放入）
 └─ initrd（数据种子 32 MiB，已有）
```

1. **构建期**：`unixnu build payload` 的 stage 目录里增加 `EFI/UniXNU/ADSP/`（board.toml 用
   `[payload] assets = ["firmware/adsp"]` 一类的字段声明来源目录，由 payload.py 复制，
   不把 23.5 MB 二进制放进 git）。
2. **固件期**：`uefi-mondrian` 新增一个小 DXE，挂载 payload FAT 后读 `EFI/UniXNU/ADSP/` 全部文件，
   顺序拷进**固定物理地址** `0x8C000000`（在 `MondrianBootMemoryDxe` 里登记为 reserved，
   保证 XNU 的可用内存不包含它），并把 `K60_ADSP_IMAGE_BASE/BYTES` 常量写进 `board.toml [adt]`
   生成的 ADT 属性里。
3. **内核期**：`k60_adsp_md_window()` 改为读 ADT 常量 `adsp-image-base`（4 或 8 字节 cell），
   `ml_io_map_unmappable(base, bytes, 0)` 映射后用 `K60Fat` 在这块内存上解析（固件按 BMP/FAT 布局
   原样拷贝，或固件只拷文件、内核改用"目录项由固件写成 TOC"——首选原样拷贝 FAT 镜像，内核侧零改动）。

## 三、为什么必须走固件

- 固件已经在读同一个 payload FAT（`Platforms/Xiaomi/UniXNUPkg/Library/UniXNULib/Boot.c:150-161`
  打印 `boot: initrd ..., on LoadFile2 initrd media`），它拥有块设备、FAT 栈和内存分配器。
- **ADT 不是固件 FDT**：`/tmp/good.adt`（14,672 B）、`/tmp/cur.adt`、`/tmp/k60-real.adt` 里只有
  `chosen` 节点名，`strings` 搜不到 `linux,initrd-start` / `linux,initrd-end`——说明 DarwinBoot
  生成 ADT 时没有搬运固件在 FDT `/chosen` 上设的运行时属性（`UniXNURamDiskDxe.c:188` 设的是 FDT）。
  这也解释了为什么内核侧 `SecureDTGetProperty(chosen, "linux,initrd-start")` 一直失败。
  因此**运行时地址不能靠 FDT 传**，只能用"双方约定的固定常量 + 构建期写进 ADT"。

## 四、验收标准

- 固件日志出现 `adsp-image: 26 files, 23494284 bytes at 0x8C000000`。
- 内核日志 `K60PAS adt adsp-image base=0x8c000000 bytes=...`，随后 `K60PAS fat open ok`、
  `K60PAS init seg=… rc=0`、`K60PAS mem_setup ok`。
- 电池侧 `K60Battery: adopting authenticated PAS1 GLINK epoch=…`。
