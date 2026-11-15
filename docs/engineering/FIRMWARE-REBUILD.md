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
- `board.toml` 的 `[firmware].patches` 列出五个 K60 修复补丁，构建时 apply、`firmware.py` 的
  `finally` 里 reverse。它们在 uefi 仓的 `Resources/MuPatches/` 下、已被 `origin/main` 跟踪，
  并且对 pin `6f805f2` 逐个 `git apply --check` 通过。
- **第六个修复（`AsmMacroLib` 段命名）不在这里**：上游在 `6f805f2` 用另一种方式解决了
  （`#ifdef __ELF__` 分支，PE 侧用 `.text$ ## Name`），旧补丁已不适用。

### 1.1 `Mu_Basecore` 必须停在仓库记录的 pin 上（P-217）

`Mu_Basecore` 是一个**嵌套仓**：主仓只记录一个 gitlink，构建读的却是工作树的当前内容。
2026-11-16 之前，这个工作树停在一个**只存在于本机**的提交 `3d2a9fa` 上，而 `board.toml` 的注释
声称记录的 pin `6f805f2` 已经包含那六个修复、`3d2a9fa` 是它的祖先。两句话都不成立：

- `git merge-base 3d2a9fa 6f805f2` 返回空——两条历史没有共同祖先；
- `3d2a9fa` 的父提交是 `3c9c7b2`（`[DROP on REBASE]`），不在任何远程分支上；
- 11 个文件里只有 `AsmMacroLib.h` 在 `6f805f2` 上是修好的（且修法不同），其余 10 个是原始状态。

后果：本机构建一直成功（工作树里确实有那些修复），但**干净 clone 会构建出坏的固件卷**。

现状（已修）：工作树切到 `6f805f2`，五个修复改由 `[firmware].patches` 施加。验证过
「pin + 五个补丁」与 `3d2a9fa` 的 11 个文件里有 10 个**逐字节相同**，唯一差异是上游已自行修好的
`AsmMacroLib.h`。门禁 `scripts/check-basecore-pin.py`（P-217）钉住三件事：工作树 HEAD 必须等于
记录的 pin、每个 `[firmware].patches` 必须存在且能 apply、若工作树故意偏离则必须在本文件里写明。

## 2. 它**不是**确定性的（同源也不得同字节）

`firmware.py:85` 确实把 `SOURCE_DATE_EPOCH` 固定成 uefi 仓最后一次提交的时间
（`git -C <uefi> log -1 --format=%ct`），但那只影响真正使用它的字段（`__DATE__`/`__TIME__`、
PE 头时间戳）。**它不影响 LLD 自己派生的 CodeView build-id**，而固件卷是压缩的，一个 GUID 变了
就重写整个压缩段。

2026-11-16 02:31–02:47 的实测（同一检出、同一 pin、无未提交改动）：

| 次 | `SOURCE_DATE_EPOCH` | FD sha256（前 12） |
| --- | --- | --- |
| 基准（已上机验证） | 自然取值 | `4bbe76017eb4` |
| 重建 1 | 自然取值 | `ce12d145a71e` |
| 重建 2 | 显式钉住 `1794541119` | `77ad2474a468` |
| 重建 3 | 自然取值 | `9f20de15388a` |

逐字节 diff `4bbe7601` 与 `ce12d145`：同尺寸 3,145,728 B，**453,604 B 不同、1,739 个不连续区间**，
首差 `0xc8b8`、末差 `0x8dbce`。首个差异是 CodeView 记录——两边都有 `RSDS` + 16 字节 build-id，
但 GUID 不同（`c61b6000b5826a234c4c44205044422e` vs `0b5c83d97f72b6714c4c44205044422e`，
后 8 字节 `4c4c44205044422e` = `"LLD PDB."` 相同）。

两条后果，写在这里以免再犯（P-216）：

1. **FD 的 sha256 不是「身份」，是「这一次构建的标识」。** 任何「两个卷哈希不同 ⇒ 源码不同」的
   推断都是错的。
2. **判定一个重建的卷能不能用，只能上机。** 见 §5 第 4 步。

## 3. 现场存在的卷

| sha256（前 12） | 大小 | 出现在 | 结论 |
| --- | --- | --- | --- |
| `cf4485712c29` | 3,145,728 B | 2026-11-12 之后几乎所有镜像（`/mnt/e/k60-work/artifacts/old-fd-cf448571.fd`，`--fd` 的默认归档） | 已验证能找 payload |
| `4bbe7601 7eb4` | 3,145,728 B | `audio-probe-20261114j` / `-k` / `20261115l` / `-m` | 重建的卷，j/k 上机进过 SpringBoard |
| `9f20de15388a` | 3,145,728 B | `fdtest-20261116a`（`/mnt/e/k60-work/artifacts/fd/fresh-9f20de15388a.fd`） | 从当前 pin 重建，**上机进 SpringBoard 129** |

第三行是 P-154 的终结证据：同一个 payload（`fbc87102…`）只换 FD，`boot.img` 重打成
`51d20538…`，上机 `E:\k60-work\evidence\usblog-20261116-025525`：3384 行 / 230,107 B /
SpringBoard 129 / `Early boot complete` 1 次 / `K60DATA mounted` 1 次 / panic 标记 0 /
`menu:` 与 `config: no boot entry` **0 次**。

## 4. P-154 已关闭

P-154 记录的是 2026-11-12 的实测：重建出来的卷报
`UNIXNU: config: no boot entry found` / `menu: default 0 'exit'`，也就是 UEFI 侧没找到 payload 里的
`unixnu.toml`。当时不知道为什么，于是定下「`bootimg --fd /tmp/old-fd-cf448571.fd` 存档变通」。

P-176 找到了根因：`[firmware].packages` 把 `{tree}/package` 排在 `{uefi}/Platforms/Xiaomi` 之前，
EDK II 于是编译了框架里那份陈旧的 `UniXNUPkg`，而它携带的 `UniXNURamDiskDxe` 不把 initrd 发布成
文件系统——payload 自然摸不到。`board.toml:66-75` 现在是修好的顺序。

**2026-11-16 的单变量上机把这条关闭**（§3 第三行）：从当前 pin 重建的卷能找到 payload 并进桌面。
所以 `--fd` 不再需要指向归档卷；`build-strict.sh` 可以用重建的卷，manifest 的 `components.fd`
只用来回答「这张图带的是哪一次构建的卷」，不用来回答「是不是同一份固件」。

旧的那几张失败卷具体差在哪一步，已经无法核实——原始失败卷零留存，`4bbe7601` 的首现时间
（11-13 15:08:56）也早于 P-176 修复（15:13:07）约四分钟。不要再把这条当未结悬案。

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

第 4 步通过之后，`build-strict.sh --fd` 就可以用重建的卷（P-154 已于 2026-11-16 关闭）。
`components.fd` 仍会记录每一次的哈希——但按 §2，它只是「这一次构建的标识」，不是可比的身份。

## 6. 为什么这件事现在很要紧

- **modem 载具**（cellular 线）：modem 镜像 27 个文件、拷贝量 109,060,761 B，装不进 payload。
  下面的容量表是实测的（`[payload] size_mib`、`build-manifest.json` 的 `kernel_bytes`、
  `gen-modem-table.py` 的 `bytes-copied`）：

  | payload 容量 | 内核 129 MB | 内核 66 MB | 备注 |
  |---|---|---|---|
  | 192 MiB = 201,326,592 B（当前） | **缺 43,501,040 B** | 余 91,765,264 B | 装不下 129 MB 内核那一档 |
  | 256 MiB = 268,435,456 B | 余 23,607,824 B | 余 89,668,112 B | 见下面的硬上限 |

  256 MiB 是**硬上限**，不是随便挑的数：`Platforms/Xiaomi/DarwinBootPkg/Driver/PackedRamdisk.h:16`
  是 `if ((InputSize > SIZE_256MB) || …) { return FALSE; }`，即 ramdisk 一旦超过 256 MiB
  `RamdiskLayout()` 直接拒绝，`DarwinBoot.c:675` 随即 `goto Fail`。所以「把 payload 提到 256 MiB」
  这条路可行但只剩 23.6 MB 余量（内核还会长），**不能当作长期方案**。

  因此 modem 的唯一可行载具是固件侧把镜像放到固定物理地址并发布
  `/chosen/memory-map/K60ModemImage`——也就是说必须先能重建并验证 FD。
  这与 cellular 线 `15-FIRMWARE-CARRIER-LOADER.md` 的结论一致，只是现在有了容量数字。
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

- **P-154**：重建的卷找不到 payload（**已关闭**：根因是 P-176 的包序，`9f20de15388a` 上机验证）。
- **P-176**：`[firmware].packages` 顺序让 EDK II 编译了陈旧的 `UniXNUPkg`。
- **P-197**：固件没有 GpuAddon 装载器，`/chosen/memory-map/GpuAddon` 恒全零——「固件搭车」的假设
  在没有装载器时不可能成立。
