# 固件卷（FD）重建手册

固件卷是 `fastboot boot` 时塞进 boot image kernel 槽的那 3 MiB 里的一部分：112 B 的 shim +
3,145,728 B 的 UEFI 固件卷 + 一个裸 DTB。它决定 UEFI 侧的一切——能不能找到 payload、ADT 怎么写、
有没有厂商 AO 之外的驱动。这份文档只讲**怎么重建、怎么判断重建出来的卷能不能用**，以及
2026-11-12 那条「重建的卷找不到 payload」（P-154）现在处于什么状态。

## 1. 谁在构建它

- 入口：`unixnu build`（框架仓 `scripts/unixnu/cli.py:63`）的 firmware 步骤，实现在
  `scripts/unixnu/firmware.py`。
- 配置：本仓 `board.toml` 的 `[firmware]` 段——`dsc = "Platforms/Xiaomi/mondrianPkg/mondrian.dsc"`、
  输出 `fd = "Build/mondrianPkg/{target}_CLANGPDB/FV/SILICIUM_UEFI.fd"`、`packages`、
  `[firmware.defines]`（`DEVICE_MODEL` / `ENABLE_SECUREBOOT` / `MEMORY_PROTECTION` / `SHIP_MODE` /
  `BUILDID_STRING`）。
- 命令形态（`firmware.py:60-80`）：`build -p <dsc> -a AARCH64 -b <target> -t CLANGPDB -n <jobs>`
  加 `-D FD_BASE=… -D FD_SIZE=… -D FD_BLOCKS=…` 与 `[firmware.defines]` 的每一项，
  `WORKSPACE=<uefi 检出>`、`PACKAGES_PATH=<packages 拼起来的冒号列表>`、`CONF_PATH=<work>/edk2-conf`。
- `board.toml:61-65` 的 `[firmware].patches` 目前是空列表，注释写明原因：Mu_Basecore `6f805f2`
  已经包含全部六个 K60 修复（`3d2a9fa` 是它的祖先），重复打 `Boot-Manager.patch` 正是 2026-11-12
  之前的错误做法。

## 2. 它是确定性的（同源 ⇒ 同字节）

`firmware.py:85` 把 `SOURCE_DATE_EPOCH` 固定成 uefi 仓最后一次提交的时间
（`git -C <uefi> log -1 --format=%ct`）。所以**同样的源码 + 同样的 pin ⇒ 同一个 FD**，
哈希差异只可能来自源码/pin/`board.toml` 的变化。这一点很重要：FD 的 sha256 是一个可用作
判据的身份，不是随机数。

## 3. 现场存在的两个卷

| sha256（前 12） | 大小 | 出现在 | 结论 |
| --- | --- | --- | --- |
| `cf4485712c29` | 3,145,728 B | 2026-11-12 之后几乎所有镜像（`/mnt/e/k60-work/artifacts/fd/*-cf4485712c29.fd`，建筑入口 `--fd` 的默认归档） | 已验证能找 payload |
| `4bbe7601 7eb4` | 3,145,728 B | `audio-probe-20261114j` / `-k` / `20261115l` / `-m`（四张） | **重建出来的卷，且上机成功进过 SpringBoard** |

第二行是本节的关键：它证明**重建的固件卷能找到 payload**。

## 4. P-154 现在是什么状态

P-154 记录的是 2026-11-12 的实测：重建出来的卷报
`UNIXNU: config: no boot entry found` / `menu: default 0 'exit'`，也就是 UEFI 侧没找到 payload 里的
`unixnu.toml`。当时不知道为什么，于是定下「`bootimg --fd /tmp/old-fd-cf448571.fd` 存档变通」。

后来 P-176 找到了其中一半根因：`[firmware].packages` 把 `{tree}/package` 排在
`{uefi}/Platforms/Xiaomi` 之前，EDK II 于是编译了框架里那份陈旧的 `UniXNUPkg`，而它携带的
`UniXNURamDiskDxe` 不把 initrd 发布成文件系统——payload 自然摸不到。`board.toml:66-75` 现在是修好的
顺序。

所以准确的状态是：**「重建的卷找不到 payload」这条不再无条件成立**——`4bbe7601…` 是修好顺序之后
重建的卷，它找到了 payload 并进了桌面。仍然没有验证的是：**从当前 pin 重建是否也能找到 payload**，
以及旧的那几张失败卷具体差在哪一步。

## 5. 下一次重建怎么做（实验协议）

1. 记录基线：`git -C /mnt/e/hackios/uefi-mondrian rev-parse HEAD`、`board.toml` 的 `[firmware]` 段、
   edk2 检出路径与版本。
2. `unixnu build`（带 firmware 步骤）→ 得到 `SILICIUM_UEFI.fd`，`sha256sum` 它，并把副本归档到
   `/mnt/e/k60-work/artifacts/fd/<tag>-<前 12>.fd`。
3. 用一个**已知能启动的 payload** 打包：`unixnu bootimg --kernel <payload> --fd <新 FD> --out <img>`，
   同时用 `scripts/check-image-args.py` 与 `scripts/verify-boot-image.py` 过一遍。
4. 上机，判据两条：控制台出现 `Early boot complete`（说明 payload 找到了、内核起来了），
   且 SpringBoard 行数 ≥ 100。任一条不成立就是「卷不能用」，把 `menu:` 与 `config:` 两行原始输出留下来。
5. 失败时的判别顺序：先看 `UNIXNU: config: no boot entry found` 是否出现（找 payload 失败，P-176 家族），
   再看 `UniXNURamDiskDxe` 有没有打 initrd 追踪行——两个卷用 `strings` 对比这一行，是排查这件事最快的刀。

只有第 4 步通过，才可以把 `build-strict.sh --fd` 的默认值从归档卷换成新卷；在那之前，所有镜像
继续用 `--fd /mnt/e/k60-work/artifacts/old-fd-cf448571.fd`，并且 `components.fd` 会记录它，
事后能追出每张图到底带了哪个卷。

## 6. 为什么这件事现在很要紧

- **modem 载具**（cellular 线）：modem 镜像 27 个文件、拷贝量 109,060,761 B，装不进 192 MiB 的
  payload（内核已经 105 MB）。唯一可行的载具是固件侧把镜像放到固定物理地址并发布
  `/chosen/memory-map/K60ModemImage`——也就是说必须先能重建并验证 FD。
- **ADSP 已走内核内嵌 blob**（0620 + `--adsp-blob`，23,506,184 B），所以它**不**依赖这条路径；
  这也说明「内核内嵌」是可行方案，只是容量上不适合 modem。
- **BT / wifi 的固件侧打点**：能在固件里打一行，比在核心里猜一轮便宜得多。

## 7. 一条硬约束：DarwinBoot 只认固定的属性名

`Platforms/Xiaomi/DarwinBootPkg/Driver/DarwinBoot.c:225-300` 的扫描器在 `/chosen` 与
`/chosen/memory-map` 下只认这些名字：`name`、`RAMDisk`、`PackedRAMDisk`、
`darwinboot-memory-ranges`、`pong-allocatable-ram`、`pong-audio-dma`、`TrustCache`、
`darwinboot-memory-size`。它**不是**「把 memory-map 下所有属性搬进 ADT」的通用拷贝器。

因此任何新属性（例如 `K60ModemImage`）都必须同时改三处：产生者（固件/DXE）、DarwinBoot 扫描器
（把值记进 ADT）、消费者（内核）。少一处就会出现「固件发布了、ADT 里没有、内核说没载具」的形状，
而这正是 P-197 教过一次的坑（GpuAddon 恒全零）。

## 8. 相关的坑

- **P-154**：重建的卷找不到 payload（本条正在被 `4bbe7601…` 部分推翻）。
- **P-176**：`[firmware].packages` 顺序让 EDK II 编译了陈旧的 `UniXNUPkg`。
- **P-197**：固件没有 GpuAddon 装载器，`/chosen/memory-map/GpuAddon` 恒全零——「固件搭车」的假设
  在没有装载器时不可能成立。
