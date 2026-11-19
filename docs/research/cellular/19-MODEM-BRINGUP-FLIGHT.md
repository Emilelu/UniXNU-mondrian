# 19 — 基带 PAS 上机计划（route B/C）

- 日期：2026-11-18
- **2026-11-18 23:45 k18 C-M2**：PAS4 C 判据 PASS（`init_image`、`mem_setup`、诊断停机三行齐全）；随后 launchd 阶段出现 K60EXC 异常循环并回到 fastboot。IPA PAS15 仍返回 rc=-7，B/QRTR 未验证。详见 §3.6。
- **2026-11-18 20:42 k16 C-M2**：loader/XNU 已通过，但 PAS4 INIT_IMAGE 返回 SCM_INTERRUPTED（x0=1, x1=0x82），旧封装未续调，**M2 未通过**；同日审计发现内嵌 metadata 被 CRLF 污染，干净 header 已重新生成，但 UEFI FD/boot image 尚未重建。
- 2026-11-18 M2 上机前检查与 IP0 探针：**IP0 单变量探针已于 15:57 PASS；k14 的 IP0 HOLD 已解除，M2 仍未上机。** [修订后的 HR‑01](../../ops/HARD-RULES.md) 不再全面禁写；k14 的 `pong_ipa=1/2` 在 PAS15 前执行 `k60_ipa_clock_vote()`（DRV‑2/TCS4 的 IP0 投票），不属于 Goodix 已验证路径，已按单变量、可观测完成判据单独验证。独立的 porting 门禁已由 `K60_DEVICE_INPUT=/mnt/e/k60-work/mirror-k14-device` 解决。IP0 单变量探针（k15 内核 `4e40af75`、镜像 `d704e376`、参数 `pong_modem=0 pong_ipa=1 ipclk=1`）已通过：console.log:480-483 打印 address=0x50040 unit_khz=40 vote=0x60000bb8 rc=0，并在 payload FAT/PAS 之前停止。k14 标准/M2 镜像的 IP0 HOLD 解除，但 PAS15/IPA_VERSION/GSI 仍无实机观测。
- 状态：**判据已冻结；k14 代（历史）C/B/C0/IPA-only 候选重建于 2026-11-18 09:25；k16 当前八图见 §3.3。k14 代：QcomBaseband 设备 patch + IPA M0 骨架 + M1 固件暂存/PAS 路径 + payload FAT 调用点 + IP0 时钟 + IPA 资源表初始化 + GSI EE0 预检 + M2 运行时 glue（1 MiB ring、ArmSmmu4K、SMEM item 497 在 TCSR mutex 下分配、GSI command-DMA，pong_ipa=2 门控）+ 0621-k60-io-submap-budget.patch（IO_MAP_SIZE 32 MiB，P-219）+ SMMU IDR/context 诊断日志，kernel 619acc64）；2026-11-18 01:49 的 C 首飞因旧 FD 无 metadata 未取得 console，待复飞；本文件仍不是飞行许可**
- k14 M2 诊断（历史）：2026-11-18 09:25 另生成 C/C0/IPA-only/B-full 四张 `pong_ipa=2` 镜像（kernel 619acc64），只用于 M2 运行时验证，不是完整 B 候选；细节见 `20-IPA-V51-DATA-PATH.md`。
- k14 完整代（历史）：在 b9de56b9 的 Device‑nGnRE 修复、71e7c43 的 SMMU 日志、d828f3ab 的 SMEM item 497 分配和 5d59eab7 的 0621 预算修复上重编内核 `619acc64`（105,562,112 B）。标准版和 M2 的 k14 哈希见下文及 [M2 数据通路记录](20-IPA-V51-DATA-PATH.md)；核对哈希不构成上机许可。
- 范围：UEFI 把 5,884 B 的 PAS metadata 放进 DRAM；内核在完整模式下按 `power → init_image → transport → mem_setup → auth_reset` 发 SMC，并如实报告 rc；QRTR 侧接 QcomBaseband 的 AppleBaseband 控制桥，完成 servloc 应答与 DMS 版本读取。
- 本飞只声称：**UEFI 能放对 metadata，内核能按顺序发 SMC 并报出 rc，QRTR 能枚举并读到 DMS 版本**。不声称基带数据业务可用。

## 0. 为什么先做这一次飞行

pong（Nothing Phone 2，SM8475/X65，Darwin24）是同一 SoC 的已工作先例：PAS4 的调用顺序是
`INIT_IMAGE(metadata) → MEM_SETUP(base, span) → AUTH_AND_RESET`，metadata 是
`modem.mdt[0:1076] + modem.mdt[1076:5884]`（5,884 B）。K60 的镜像布局与 pong 相同
（`0x8bc00000 + 0x13200000`），差别只在 K60 的 27 个段由 UEFI carrier 放进 carveout，pong 从
`/pong/firmware/modem.mbn` 读。

所以这一飞只验证 **K60 特有的三个未知**：TZ 是否接受这个 metadata 页；K60 的 27 段布局是否与
`mdt` 的 30 行表（27 个有文件名的段 + 3 个纯 bss 行，bss 大小 4,096 / 163,696,640 / 15,851,520）
一致；auth 之后 SMP2P/GLINK 是否给出可读的 QRTR 响应。其余顺序、metadata 内容、地址和缓存清理
都已经在 host 侧固定。

## 1. 当前代码基线（已提交）

| 件 | 仓库 / 提交 | 说明 |
|---|---|---|
| metadata 工具 | k60-cellular `80c72f16` | `scripts/build-modem-metadata.py`；从 `modem.mdt` 取 ELF 头 + hash 段，产出 5,884 B |
| 内核顺序 | k60-cellular `6a02c710` | `K60ModemBoot.c`：`power` → `init_image(0xB7FF0000)` 一次 → `transport` → `mem_setup(base,span)` → `auth_and_reset`；`pong_modem=3` 在 `mem_setup` 后停，不执行 power/transport |
| QcomBaseband 桥 | k60-cellular `3d4a4be4` / `352d7f30`；`patches/qcombaseband/0001-coachz-defer-publication.patch` | `board.toml` 选 `component:QcomBaseband`；`K60ModemLink.c` 把 NEW_SERVER/DEL_SERVER/DATA 转给 `coachz_baseband_*`，probe 打开 GLINK 后调用 `coachz_baseband_configure()`；ADT 增加 `chosen/coachz-baseband=1` 与 `product/baseband-chipset=mav16` |
| UEFI metadata 页 | uefi-mondrian `c1ea878` | `ImageCarrierLib.c` 的 `CarrierLoadMetadata()`；`K60ModemMetadata.h` 内嵌 5,884 B；写 `0xB7FF0000` 后 `WriteBackDataCacheRange` |
| metadata 门禁 | k60-cellular `fc69e861` | `scripts/check-modem-metadata.py`；14 项全部 PASS |
| 宿主顺序测试 | k60-cellular `fbc03066` | `scripts/tests/test-k60-modem-bringup.c`；`TESTS OK 12`，含 rails → init → mem → auth 顺序、两次诊断各自的停机点、rail 失败与 copy 失败反例 |
| power-only 诊断 | k60-cellular `fbc03066` | `pong_modem=4`：投完 cx.lvl/mss.lvl/xo.lvl 三条 rail 后停在 `init_image` 之前，不发任何 PAS 命令；0621 由 `scripts/update-modem-pas-patch.py` 重生成 |

## 2. 证据矩阵（上机前必须全绿）

| 改动 | 静态 | 单元 / 宿主 | 产物 |
|---|---|---|---|
| M1 metadata 工具 | `python3 -m py_compile scripts/build-modem-metadata.py` | `scripts/tests/test-build-modem-metadata.py` | 干净 `modem.mdt.bin` → 5,884 B；sha256 `78d5f2f45aefeab7d2920bc5753009ade0371aa7d9be5eb0f2d21a72704c1fb8`；crc32 `0xac600b5d`（旧的 `09180d7c…` / `0x5ce97b8d` 是 CRLF 污染 blob，仅作历史） |
| M2/M4 双端常量与地址 | `scripts/check-modem-metadata.py` | 14 项 PASS（见 §3） | 内核 `K60_MODEM_METADATA=0xB7FF0000u` 与 UEFI `K60_MODEM_METADATA_ADDRESS=0xB7FF0000ULL` 相等；页在 `[0xA8300000,0xB8000000)` 内且 4 KiB 对齐 |
| M3 UEFI carrier | `clang -fsyntax-only -Werror`；完整 `build_uefi.py` | DXE 无宿主 harness；逻辑集中在 M1，UEFI 只做 `CopyMem` + 清缓存 + CRC | FD 精确 3,145,728 B；干净 metadata 版 sha256 `40c29d513eab0dca410c36bceeef936244cf2a20c3233f48bbbaa8ae69a07386`（k18/k20/k21 都用它）；k16 的 fixed-window 版是 `9b7155f6…`，更早的 `e007de8a` 是污染 metadata，均已过时 |
| M5 内核顺序 | 内核编译 `-Werror` | `run-bringup-test.sh`：`TESTS OK 12` rc0；断言 `init_image` 只调一次、先于 `mem_setup`、先于 `auth_and_reset`，并含 rail-only 停机与 rail 失败、copy 失败共 5 个反例 | `patches/xnu/0621-k60-modem-pas.patch` 与 `K60ModemBoot.c` 一致；内核二进制应含 §4 的 verdict 行 |
| M6 夹具 | `scripts/build-modem-metadata.py` + UEFI 内嵌头（不再有第 28 个 payload 文件） | `check-modem-metadata.py` 对嵌入数组做长度/ELF/crc/sha 校验 | 当前 `boot-metadata-fixture.img` 仅为 UEFI-only 夹具；其 payload 内核早于 `d7890e26`，**不是候选** |
| M7 boot.img | 现有 `test-bootimg-layout.py` | — | 本夹具 201,895,936 B = `4096 + ceil(559,358/4096)*4096 + 201,326,592 + 4096`（`ksz` 读自 boot.img 头 offset 8）；sha256 `1193a1e718badd2de5908c4ec24e97afc18272de4910d7c3fdd282b5cdaa3839` |
| M8 本判据文档 | `check-docs.py` | — | 本文件提交在飞行之前；含 manifest 与回滚镜像 |

## 3. 飞行前置门禁（必须全部真实 rc=0，禁止用 `tail` 或 `echo` 掩盖）

1. `cd /mnt/e/hackios/k60-cellular && PYTHONIOENCODING=utf-8 python3 scripts/check-modem-metadata.py`
   → 14 行 PASS，末行 `METADATA OK`，真实 rc 0。
2. `bash /mnt/e/k60-work/artifacts/run-bringup-test.sh`
   → 末行 `TESTS OK 9`，真实 rc 0；输出必须含 §4 的 S3 三行（正常路径）。
3. 真实候选（不是当前 UEFI-only 夹具）的 `kernel.macho` 必须由 `d7890e26` 或其后代构建；
   `payload.img` 必须含 27 个 `.lzma` 和 K60ModemImage 占位；`boot.img` 必须由新 FD + 新 payload + 4,024 B DTB 打包；
   记录四个 sha256：FD、payload、boot.img、kernel.macho。
4. `stat -c %s` 的 FD 必须精确等于 `3145728`；boot.img 必须等于
   `4096 + ceil(ksz/4096)*4096 + 201326592 + 4096`（`ksz` 从 boot.img 头 offset 8 读）。
5. `scripts/check-docs.py`、`scripts/check-line-endings.py`、`scripts/check-secrets.py`、`check-tree-owner.py` 全 rc0。
6. 飞行 manifest（本文件 §3.1 / §3.2）四项哈希与构建回执逐项相等；任何一项不相等即 STOP。

### 3.1 本次可用产物（UEFI-only 夹具，不是候选）

| 件 | 字节 | sha256 |
|---|---:|---|
| FD `Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd` | 3,145,728 | `38c1293b11fa7e48f9a701d4d94ec838657fca9e8d03bc975c339eb318f33c61` |
| DTB `Resources/DTBs/mondrian.dtb` | 4,024 | `2d044eaa08b7e58c0510a33da795c960085e13d6943cd4c25e0e050e0bfa33cd` |
| payload `E:/k60-work/artifacts/bootimg-test/payload-modem.img` | 201,326,592 | `9eb14f6768110605b05c9c56d70a9baebfbd6651716c424385086b3bca1e6126` |
| UEFI-only boot fixture `E:/k60-work/artifacts/modem-20261117a/boot-metadata-fixture.img` | 201,895,936 | `1193a1e718badd2de5908c4ec24e97afc18272de4910d7c3fdd282b5cdaa3839` |
| metadata blob `E:/k60-work/artifacts/modem-metadata.bin`（**已作废**） | 5,884 | 文件仍是污染 blob `09180d7c…`；当前真源是 `K60ModemMetadata.h` 的内嵌数组（sha256 `78d5f2f4…`、crc32 `0xac600b5d`），由 `check-modem-metadata.py` 直接校验 |

**这张 UEFI-only 夹具的 payload 内核早于 `d7890e26`，只能证明 UEFI 的 metadata 行、不能证明内核顺序；
禁止把它当作 PAS 候选飞行。**

### 3.2 本次 route B/C 候选（QcomBaseband 桥接后重建，待门禁与 Lead 授权，不是飞行许可）

| 件 | 路径 | 字节 | sha256 |
|---|---|---:|---|
| FD | `E:/hackios/uefi-mondrian/Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd` | 3,145,728 | `e007de8a2cbed4ec22d8502a89ff3eef79337bc712ccb6c2414c4b175b5d2589` |
| DTB | `E:/hackios/uefi-mondrian/Resources/DTBs/mondrian.dtb` | 4,024 | `2d044eaa08b7e58c0510a33da795c960085e13d6943cd4c25e0e050e0bfa33cd` |
| kernel.macho | `E:/k60-work/artifacts/modem-20261117k14/kernel.macho` | 105,562,112 | `619acc64a33fc4b62ba167b5034b81951ad09d971f6671feff7b10091d3272eb` |
| payload.img (C, `pong_modem=3`) | `E:/k60-work/artifacts/modem-20261117k14/payload-c-diagnostic/payload.img` | 201,326,592 | `a3ab1f52e2734e0017889b8f4ee4bd4c7636f23f3b03eb9bb235e68090db524b` |
| boot.img (C, `pong_modem=3`) | `E:/k60-work/artifacts/modem-20261117k14/boot-modem-c-diagnostic.img` | 201,895,936 | `fb002a47abc209385f09d180ebdcfa95895288c602f24ca762b19a4226763562` |
| payload.img (C0, no carrier control) | `E:/k60-work/artifacts/modem-20261117k14/payload-c-nocarrier/payload.img` | 201,326,592 | `df159b8f7f2ab91fb1d2a3b466e79f296ec371ffec3be32682bb28727ad72500` |
| boot.img (C0, no carrier control) | `E:/k60-work/artifacts/modem-20261117k14/boot-modem-c-nocarrier.img` | 201,895,936 | `7ca3e1197e95bfb1b22202bad80140a107f9f594b91156021447713b85b4f7f8` |
| payload.img (B, `pong_modem=2`) | `E:/k60-work/artifacts/modem-20261117k14/payload-b-full/payload.img` | 201,326,592 | `314714d5517fcc67d732a267956daf7faf397f526073fff4a9f380f266cda82f` |
| boot.img (B, canonical) | `E:/k60-work/artifacts/modem-20261117k14/boot-modem-b-full.img` | 201,895,936 | `e6c181dd67ca7f93aa7e06f0890f7fbc17d80b8c992894b5026068a88394baca` |
| payload.img (IPA-only, `pong_modem=0`) | `E:/k60-work/artifacts/modem-20261117k14/payload-ipa-only/payload.img` | 201,326,592 | `f90fa367fa88e35dd7808585908bbd611a652c1867aa7939f806303f6ec1d307` |
| boot.img (IPA-only) | `E:/k60-work/artifacts/modem-20261117k14/boot-modem-ipa-only.img` | 201,895,936 | `3bbed14172a675a4288770bf383065de3229065b26fe6a3f14cdc3783a2d786f` |

- 构建源：k60-cellular feat/cellular 的 k14 代工作树（QcomBaseband 控制桥 + QMI servloc/DMS + IPA M0 骨架 + M1 固件暂存/PAS 路径 + payload FAT 调用点 + IP0 时钟 + IPA 资源表初始化 + GSI EE0 预检 + M2 运行时 glue（1 MiB ring、ArmSmmu4K、SMEM item 497 在 TCSR mutex 下分配、GSI command-DMA，pong_ipa=2 门控），代码提交 `5d59eab7`（基于 d828f3ab、71e7c43、4764d170、b9de56b9、e4b5cfd5、50aa1261 与 e7bdbf16），基于携带设备 patch 的 `8af93c9a`、`352d7f30` 与 `3d4a4be4` 的 P0/P1/P2 修复和 `6a02c710` 的 power/transport）；UEFI `c1ea878`；payload 由 UniXNU `feat/modem-carrier`（`92bb60f`）的 `unixnu` 生成（`--modem-carrier E:/k60-work/artifacts/modem-carrier`）。k14 沿用 j2 的 UEFI FD e007de8a；kernel 由 `scripts/build-qcom-baseband.py` 对上游 `dd0199cf` 暂存并 apply `patches/qcombaseband/0001-coachz-defer-publication.patch` 后重建（build-report 的 `compiled_sha256=9a51613d...`，`device_patch=true`）。C/B 使用同一份 kernel、UEFI、DTB 与 modem carrier，只在打包 payload 时分别追加 `--kernel-arg pong_modem=3 --kernel-arg pong_ipa=1` / `--kernel-arg pong_modem=2 --kernel-arg pong_ipa=1`；C0 使用同一份 kernel、UEFI、DTB，不带 carrier，`--kernel-arg pong_modem=3 --kernel-arg pong_ipa=1`；IPA-only 使用同一份 kernel、UEFI、DTB，不带 carrier，`--kernel-arg pong_modem=0 --kernel-arg pong_ipa=1`；每张 payload 的 `::/IPA/ipa_fws.mbn` 均为 40,376 B，payload.json 记录 `ipa_fws_sha256=30517300...`。
- boot.img 头（四张相同）：`kernel_size=559,476`，`ramdisk_size=201,326,592`；`4096 + ceil(559476/4096)*4096 + 201326592 + 4096 = 201,895,936`，与文件大小相等；`test-bootimg-layout.py` 四张均 OK。
- boot.img 内 ramdisk 切片 sha256：C = payload 的 `99a11883...`，C0 = payload 的 `48a679a9...`，B = payload 的 `5c2c5b03...`，IPA-only = payload 的 `c5b2d98e...`，说明 payload 原样嵌入。
- k14 代 QRTR 在 f 的 QMI 面（AP 以 service 64 / instance 0x101 / port 0x100 应答 servloc 的 GET_DOMAIN_LIST，并从 modem 的 service 2 NEW_SERVER 端点发送 DMS GetRevision（message 0x23））之外，把 NEW_SERVER/DEL_SERVER/DATA 转给 QcomBaseband 的 `coachz_baseband_*`，并在打开 GLINK 后调用 `coachz_baseband_configure()` 发布 AppleBaseband/AppleBasebandPCIControl/AppleBasebandPCIInterface；S4 仍要求读到版本串。
- 实测 payload（C/B 相同，C0 无 carrier）：`mdir ::/EFI/UniXNU/MODEM` 恰好列出 27 个 `.lzma`（名称 b01–b13 / b15–b20 / b22–b29），`/EFI/UniXNU/Payloads/kernel.macho.adt` 的 `/chosen/memory-map["K60ModemImage"]` 是 16 个零字节；payload.json 记录 `kernel_sha256=619acc64...` / `payload_kernel_sha256=aa1a8136...`，ADT C=`48d2ba8a...`、B=`d058d81f...`、C0=`7877d0d1...`、IPA-only=`2ce3639e...`；每张 payload 的 `::/IPA/ipa_fws.mbn` 为 40,376 B（sha256 `30517300...`）。
- **注意：payload 与 bootimg 都使用了 `--skip-gates`**；本机 `unixnu bootimg` 的合规注册表当前为红（P-165/P-166 等历史 sync/build 输入漂移），所以这些候选不是“门禁全绿”的产物，也不是飞行许可。
- 飞行工具：k14 历史记录使用 `E:/k60-work/artifacts/fly-modem.ps1`（先校验 C/B 哈希，再调用 `boot-and-capture.ps1` 和 `check-modem-flight.py`）、`E:/k60-work/artifacts/modem-20261117k14/FLIGHT-README.md`、`manifest-k14.json`；未获 Lead 授权不要加 `-Execute`。

### 3.3 k16 当前候选（fixed-window IPA handoff，2026-11-18 19:48–19:56，未上机）

k16 是当前代：共享 kernel `03a3aeab3a5df334c70b1389b1840574efbbb7804fcc2caeaf89cfc46b9a9409`（105,562,112 B，源码 `a2d11e2b`），UEFI FD `9b7155f674f2654334cf5c97260e5cd36844e7d3ba8786b4dd9c39d62599c1f8`（3,145,728 B，UEFI `05df05f`），payload kernel `17521e7d...`，IPA `30517300...`。八张 boot 均 201,895,936 B，`kernel_size=560,487`，ramdisk 201,326,592 B，DTB `2d044eaa...`，gzip 内是 112 字节 shim + 上述 FD；payload 根目录 `IPA/ipa_fws.mbn` 为 40,376 B。

| 模式 | boot | boot sha256 | kernel args |
|---|---|---|---|
| C 标准 | `boot-modem-c-diagnostic.img` | `a69ec57ca9a9df03c956faad13ed830ba320f1f509f29f6ce8239daabeb53903` | `pong_modem=3 pong_ipa=1` |
| C0 标准 | `boot-modem-c-nocarrier.img` | `d179b2c98398d808ae961836be5ccd0d0d56897fd58abc43dee2d762d4de08cd` | `pong_modem=3 pong_ipa=1` |
| IPA-only 标准 | `boot-modem-ipa-only.img` | `5e435b71353c5fe960727eb165e52974f5e137d708b76ae2b883ffda8e4e3857` | `pong_modem=0 pong_ipa=1` |
| B 标准 | `boot-modem-b-full.img` | `d31e502a763c35f74ed4bba4a377e3ef5d17cd10993cbbc592f4cf0eb277c92b` | `pong_modem=2 pong_ipa=1` |
| C M2 | `boot-modem-c-diagnostic-m2.img` | `25b21fcdc43d573be323e5020438e8b04b0ee3401b80df8daf68cbf25350c0a5` | `pong_modem=3 pong_ipa=2` |
| C0 M2 | `boot-modem-c-nocarrier-m2.img` | `9bb349c88983f60edc4874f3c3106d4a14d540ed832d9102e80c7b001e3ce877` | `pong_modem=3 pong_ipa=2` |
| IPA-only M2 | `boot-modem-ipa-only-m2.img` | `7514866356129e2ca7e448e1dd05839ffe4b6537768c284528bbb71ceed70081` | `pong_modem=0 pong_ipa=2` |
| B M2 | `boot-modem-b-full-m2.img` | `8cdae11f395224757f0699e28431eaa514f8c30faee0afcfb729bd9de93470dd` | `pong_modem=2 pong_ipa=2` |

完整 payload/ADT 哈希与工件清单见 `E:/k60-work/artifacts/modem-20261117k16/manifest-k16.json` 和 `FLIGHT-README.md`。**这八张图仍是离线构建（`--skip-gates`）且没有实机观测，不是飞行许可。** k14 的 16:11 C-M2（`002d9a57`，FD `e007de8a`）停在 loader 的 Device Error，不能作为内核结论；k16 的意义是同时带上 fixedwindow FD 与 `a2d11e2b` 的固定窗口消费，把这条 loader 变量隔离出来。

### 3.4 k16 C-M2 实机结果（2026-11-18 20:42，未通过）

- boot `E:/k60-work/artifacts/modem-20261117k16/boot-modem-c-diagnostic-m2.img`，SHA256 `25b21fcd...c0a5`，源码提交 `8842352c`，kernel `a2d11e2b`。
- 证据 `E:/k60-work/evidence/usblog-20261118-204241`：bootAccepted=true/exitCode=0；capture complete=true，34,071 B，stopReason=budget，panic/reset marker 均为空；console.log 587 行，SHA256 `25a9b5aae99681f5cdee41715589cca7c17ac4353b788922b658ae7960941642`。
- XNU、USB CDC、UFS/APFS、显示和触摸均启动；`:475-478` 读到 carrier、30 行表并 copy skipped。旧 k14 的 loader Device Error 未复现。
- `:479-480` 为 `scm cmd=0x1 rc=-1 x0=0x1 x1=0x82` / `init_image failed metadata=0xb7ff0000 rc=-1`。**x0=1 是 QCOM_SCM_INTERRUPTED，不是 PAS 终局拒绝；旧代码只发一次 SMC，所以 INIT_IMAGE 没有完成。** 不构成 C/M2 PASS。
- IPA `:481-486` 确认固定窗口 0x8b900000/57344、IP0 投票、span=0x9000/metadata=0xe8c/3 loads 和暂存地址；PAS15 的最终返回、IPA_VERSION 和 GSI runtime 未验证。
- GUI 未出现；`:539-546` 有 PAS13 ZAP/CP 失败，诊断图 `pong_metal=2` 与 20:16 GUI 成功图存在 kernel/FD/参数差异，原因尚未隔离。K60AUTORESET 300 s 后设备回到 fastboot；本次 capture 内无 reset marker。

### 3.5 PAS4 续调修正与 k17 内核（离线，未上机）

`92657c8f` 修正 PAS4 wrapper：保留 x6 context、每轮重送原参数，以 x0=1 继续同一事务，最多 100 次，耗尽返回 `K60ModemPasInterrupted=-3`；详见 [PAS 续调说明](06-MODEM-PAS.md#21-scm_interrupted-的续调修正2026-11-18)。
实际 `K60ModemPas.c` 的模拟 monitor 回归 8 组通过，0621 与源码一致；k17 kernel `E:/k60-work/artifacts/modem-20261117k17/kernel.macho` 105,562,112 B，SHA256 `9b21321f3ba3b0fd77c8b572381e1c5798c42bb627c89e01ea47d16a9d08164a`，由 `--skip-gates` 离线编译。
**metadata 已修复**：内嵌 array 原从 CRLF 污染的 `modem.mdt` 生成，hash segment 有 25 个 `0x0d` 插入/截断，3,362 B 与 `modem.mdt.bin` 不同。已从干净 binary 重新生成（CRC32 `0xac600b5d`，SHA256 `78d5f2f4...`），并编入 clean-metadata FD `40c29d51...`；k18 C-M2 boot `1ae178bb...`（kernel `f245d506...`）已打包、离线校验并于 23:45 上机；PAS4 C 判据通过，结果见 §3.6。
k18 已飞行；B/QRTR 仍需在明确授权和 rail/QMP 条件满足后验证，未通过前不推进 M3–M6。

### 3.6 k18 C-M2 实机结果（2026-11-18 23:45，S3 C 判据 PASS）

- boot `1ae178bb5367366493a334eb5e93f000ab7a095ecdbcbe676bdaa13e39155e12`，201,895,936 B；kernel `f245d5066bdcba2ec5b79a274bd302619f0de0a0b58b20af5e19631f059bf784`；FD `40c29d513eab0dca410c36bceeef936244cf2a20c3233f48bbbaa8ae69a07386`。
- 证据 `E:/k60-work/evidence/usblog-20261118-234555`：`bootAccepted=true`，capture 39,372 B，`stopReason=fastboot-return`，console.log 648 行 sha256 `FAF90D29B40EA8E2B995B5FC358CF3ABFEE30BF40FFBA2620F3273B067AF8099`。
- `:482` `K60MODEM init_image ok metadata=0xb7ff0000 bytes=5884`；`:483` `K60MODEM mem_setup ok base=0x8bc00000 span=0x13200000`；`:484` `K60MODEM diagnostic stop after mem_setup: auth_reset not sent`。C 判据要求的三行全部出现，PAS4 C 判据通过；没有发 `auth_reset`，所以 B/QRTR 仍未验证。
- `:485-492` IPA PAS15：固定窗口 57,344 B、IP0 vote 和 staging 都成功，但 `init_image` 返回 rc=-7（x0=1, x1=0x82）；`K60Ipa.c` 仍是单次 SMC，没有使用 PAS4 的续调封装。该失败不属于 PAS4 C 判据，但阻塞 IPA 数据通路。
- `:519-613` 出现 64 次 `K60EXC`，`:570`/`:581` 为 launchd shared_region 失败，随后设备回到 fastboot；这是独立的用户态/共享区域问题，不能归因于基带。
- 本飞没有执行 `fastboot flash`，没有发 `auth_reset`，也没有 QRTR 枚举；M2 只按 C 判据 PASS，不是 B/完整基带 PASS。

### 3.7 k19：IPA SCM 续调（2026-11-19，离线，未上机）

k18 的 IPA PAS15 失败在 `init_image`：`x0=1` 是 SCM_INTERRUPTED，而 `K60Ipa.c` 当时只发一次 SMC。`bba7dcaa`（"fix(cellular): resume interrupted IPA SCM transactions"，3 文件 +112/-34）把 `K60ModemPas.c` 已验证的有界续调复制到 IPA 客户端：最多 100 次，续做时 `x0=1`、每轮重送原参数、`x6` 保留 context，耗尽返回 `K60IpaPasInterrupted=-22`；`K60Ipa.h` 增加该返回值。选择本地循环而不是抽公共事务层，是因为 `0621` 是手写补丁且 `test-k60-modem-image.py:232-257` 固定了它携带的 PAS 文件；本次只重新生成 `0623`（120,556 B，8 文件，numstat rc0）。host 侧 `K60 IPA M0/RES/GSI` 仍 PASS；SMC 代码在 `K60_HOST_TEST` 下不参与，所以续调本身由硬件验证。

| 项 | 值 |
|---|---|
| kernel | `ce46173c713288f47572ff4a51de321f10ecb434f203a2819a06a89c19134803`，105,562,112 B |
| FD | `40c29d513eab0dca410c36bceeef936244cf2a20c3233f48bbbaa8ae69a07386`（clean metadata） |
| IPA-only 标准（pong_ipa=1） | `boot-modem-ipa-only.img`，201,895,936 B，`d68134123153c8cf494284d1701c49aaccabe320e95a6b54cc545db3abe0b429`；payload `f9c4eaec...`，payload.json `078992045...` |
| IPA-only M2（pong_ipa=2） | `boot-modem-ipa-only-m2.img`，`57e41991844eaf05df34c61cb1f5fa67825815ac28dae8a419316bab31300044`；payload `50b4f7d0...` |

打包后的 payload kernel `0f64b70374ed3a0b91eb6f8dc1c06b4968c418c43f7d92f3a269f7a004a98363` 与 k19 kernel 经同一个 `patch-armcpu-validate.py` 处理后逐字节一致；反汇编 `_k60_ipa_pas_call` 只有一处 `smc`，`x0==1` 时以 `x0=1` 重发并保留上一轮返回的 `x6`，最多 100 次，成功后 `cbz x0` 判 0。两张图都经 `test-bootimg-layout.py` 通过（`kernel_size=560,384`，ramdisk 201,326,592 B，解压 3,145,840 B，DTB 4,024 B）；两张图另用仓库内的 `scripts/verify-boot-image.py` 复核，FD `40c29d51...`、payload、payload kernel `0f64b703...`、DTB `2d044eaa...` 全部匹配；清单和飞行说明为 `E:/k60-work/artifacts/modem-20261117k19/manifest-k19.json` 与同目录 `FLIGHT-README.md`。**p1 是单变量测试**：`pong_modem=0` 跳过 modem 探测，`pong_ipa=1` 只到 M1，与 k18 的唯一行为差是 IPA 的 INIT_IMAGE 会续做；`pong_ipa=2` 会同时启动 M2 GSI/SMMU runtime，不作为首个变量。两图均未上机。

### 3.8 k20：IPA PAS15 上机通过（2026-11-19 01:21，单变量 pong_ipa=1）

k19 的 p1 图打包后设备被 mission18 占用，未飞；k20 在同一源码 `a2ba2e22`（k19 的续调 + SMC 调用计数打印，0623 patch 120,659 B）上重打 p1。2026-11-19 01:21:54 由 `scripts/flash.sh` 飞 `E:/k60-work/artifacts/modem-20261117k20/boot-modem-ipa-only.img`，args 以 `pong_modem=0 pong_ipa=1` 结尾；设备在 240 s 抓取结束后由 `k60_autoreset=300` 回到 fastboot。

| 项 | 值 |
|---|---|
| kernel | `dd881b0e361a2f9c27f639996ed109d93f6805687417bee30a55af3a2108fc55`，105,562,112 B |
| FD | `40c29d513eab0dca410c36bceeef936244cf2a20c3233f48bbbaa8ae69a07386` |
| boot | `41abb12548de35532272973f35847857968c7211e3b6e221ee98b783734c9cc1`，201,895,936 B |
| payload | `347c3092a61c3199b843e88ebd619aee1b871a64bdbb52bf5104c495615f3105` |
| 证据 | `E:/k60-work/evidence/usblog-20261119-012152`，console.log 2,783 行，`8fc784e5e530af5b93c84a308b93bcb7dcb493f1c5f0b2e1608693d153bb31709a`，stopReason=budget，无 panic/reset |

console.log:480-494 的关键行：

```
K60IPA firmware source=0x8b900000 bytes=57344
K60IPA scm cmd=0x1 rc=0 calls=5 x0=0 x1=0
K60IPA init_image ok
K60IPA scm cmd=0x2 rc=0 calls=1 x0=0 x1=0
K60IPA mem_setup ok base=0x8b910000 span=0x9000
K60IPA scm cmd=0x5 rc=0 calls=1 x0=0 x1=0
K60IPA auth_and_reset ok
K60IPA post-PAS GSI status=0x1 channels=28 events=27
K60IPA version=0x45 comp=0x50010000
K60IPA resources ready=1
K60IPA M2 runtime gated pong_ipa=1
```

判读：INIT_IMAGE 在第 5 次 SMC 才成功，前 4 次 `x0=1`（SCM_INTERRUPTED）由续调重发，这是 `bba7dcaa` 续调在硬件上的直接证据；MEM_SETUP/AUTH_AND_RESET 各一次成功；IPA 固件 5.256.2 起跑，IPA_VERSION=0x45、COMP=0x50010000；`pong_ipa=1` 确认 M2 runtime 未启动。`boot.json` 的 `bootAccepted=false`/`bootExitCode=-1` 仍是 PowerShell 把 fastboot stderr 当错误的老 artifact，`fastboot.log` 实际是 `Sending ... OKAY` 与 `Booting OKAY`。仍未验证：M2 runtime（p2 图 `b2474eea4ac777d185605642a22e1ca94cd364345e43c9130a62a2cdf21c65e3` 用 `pong_ipa=2`，单独飞）、QMAP/ifnet、GSI IRQ 432/654、flight mode 与 reset 恢复。

### 3.9 k20 p2：IPA M2 运行时上机通过（2026-11-19 01:30，单变量 pong_ipa=2）

p2 图 `E:/k60-work/artifacts/modem-20261117k20/boot-modem-ipa-only-m2.img`（201,895,936 B，`b2474eea4ac777d185605642a22e1ca94cd364345e43c9130a62a2cdf21c65e3`，payload `e817cb3b2d399f7dc5d42c8d0e0e4a1c43bd50b9adc5a042cdd37ee5f232158b`，同 kernel `dd881b0e...`、FD `40c29d...`）于 01:30:21 飞，args `pong_modem=0 pong_ipa=2`；与 p1 的唯一差别是 M2 runtime 门控打开。证据 `E:/k60-work/evidence/usblog-20261119-013021`，console.log 3,204 行，`8218c3caf5528294bf8c44d203c40faf108ec0cf3fcbbc39450ed44dbd612aaa`，抓取完整、无 panic/reset。

关键行 console.log:483-502：

```
K60IPA scm cmd=0x1 rc=0 calls=4 x0=0 x1=0
K60IPA init_image ok
K60IPA scm cmd=0x2 rc=0 calls=1 x0=0 x1=0
K60IPA mem_setup ok base=0x8b910000 span=0x9000
K60IPA scm cmd=0x5 rc=0 calls=2 x0=0 x1=0
K60IPA auth_and_reset ok
K60IPA post-PAS GSI status=0x1 channels=28 events=27
K60IPA version=0x45 comp=0x50010000
K60IPA resources ready=1
K60IPA M2 ring=0x90d50d000 tables=0x90d60d000
K60IPA M2 SMMU idr id0=0x4c017e71 id1=0x6000004b id2=0x5111
K60IPA M2 SMMU context id0=0x4c017e71 id1=0x6000004b id2=0x5111 cbar=0x1f300 sctlr=0x27
K60IPA M2 SMMU bank=72 slot=110 pages=6 leaf=268 smem=0x809e3000/0xa000
K60IPA M2 GSI ready stage=10 channels=3825493276 events=8219 restricted=0 sram=0x5000 completed=3
```

判读：PAS15 仍 PASS（INIT_IMAGE 续做 3 次后成功，auth_and_reset 2 次），随后 M2 runtime 完整启动——1 MiB ring 与 0x8000 表块分配、SMMU 识别/上下文编程（id0=0x4c017e71 id1=0x6000004b id2=0x5111，cbar=0x1f300，sctlr=0x27）、SMEM item 497 取得 0x9000（页对齐后 0xa000）、GSI stage=10 且 `completed=3`（命令通道实际完成 3 条命令），restricted=0、sram=0x5000。`channels=3825493276 events=8219` 是 GSI 状态寄存器的原始读数（0xE4000BFC/8219），不是通道计数。仍未做：GSI IRQ 432/654 处理、QMAP/ifnet 数据面、flight mode 与 reset 恢复。

### 3.10 k21：power-only 诊断（`pong_modem=4`，离线，未上机）

B 之前唯一还没有实机证据的层是三条 modem rail 的 TCS4 投票：HR-01 准入台账
`docs/ops/HARD-RULES.md:58` 仍是「未验证（离线）」。k18 的 C 诊断不执行 power，k20 的
IPA 图完全不碰 modem，所以 B 一旦上机会同时改变「供电」和「auth_reset」两件事，不满足
单变量。`fbc03066` 因此加了一个只投票的相位：

- `K60_MODEM_PHASE_RAILS_ONLY = 2`；`k60_modem_bring_up()` 投完三条 rail 后打印
  `K60MODEM diagnostic stop after power: init_image not sent` 并返回，不再发 PAS SMC。
- `pong_modem=4` 选择它；`3` 仍是 metadata-only，`2` 仍是 full + QRTR，未知值保持 full
  （拼错不能静默少做一步）。QRTR 只在 `enabled == 2` 且 phase 为 full 时执行。

宿主证据：`scripts/tests/test-k60-modem-bringup.c` 用记录型 `k60_modem_rails_vote()` 证明
full 的顺序是 rails → `init_image` → `mem_setup` → `auth_reset`，phase 2 只调用一次
rails（`ncalls==1`，一条 PAS 命令都没有），rail 返回 -7 时在 `init_image` 之前停止；
`TESTS OK 12` rc0。`K60ModemBoot.c` 的改动由新脚本
`scripts/update-modem-pas-patch.py` 重生成 0621 的三段 new-file hunk（手改行数导致 patch
不可应用的那类错误也就不会再出现），`scripts/tests/test-k60-modem-image.py` 通过。

k21 内核与 `pong_modem=4 pong_ipa=0` 的图是离线候选；`3e449773` 把 xo.lvl 改成 Pong 的字面 3 之后，P1 候选换成了 §3.11 的 k22。

打包结果：

| 项 | 值 |
|---|---|
| kernel | `7e4832f49238a71e59346969cdd1fda234c1d72869a4c235aa5c8af720c2097f`，105,562,112 B（源 `fbc03066`） |
| FD | `40c29d513eab0dca410c36bceeef936244cf2a20c3233f48bbbaa8ae69a07386`（clean metadata） |
| boot | `7b6bb385ed2405253abdd24db076810548ff65791a4afda9434effd149b975f1`，201,895,936 B |
| payload | `9eb54da47484498bb45c94c51ae77e31254bbe02ca1cc9d382e0264ec4836a7c`；payload.json `fd74efd6317cc0647554989ff81ac52745340aa8a25a774ea9bdab6e99fbc73f` |
| payload kernel | `0eed483a9e01f7d4f3d7df19f1d13cc3e9adb25ba079dca747b897c84903f464`（strings 含 `diagnostic stop after power` 与 `K60MODEM power ok cx=`） |
| args / 布局 | `pong_modem=4 pong_ipa=0`；kernel_size 560,384、ramdisk 201,326,592、解压 3,145,840、DTB 4,024；`test-bootimg-layout.py` 与 `scripts/verify-boot-image.py` 均 PASS |

同一个 k21 内核还离线打包了 B 图（`pong_modem=2 pong_ipa=0`，只动 modem 相位，IPA 保持关闭），
P1 通过并拿到 B 的显式授权后可以直接飞，不需要再改代码或重新打包：

| 项 | 值 |
|---|---|
| boot | `eefe6fdfb426910a9990ae6a3e274f9f89ed9f9bb7dd7c2a7a9380e5416e2f0a`，201,895,936 B |
| payload | `e0c1f86c714b7f192b5a6a43dd001b7e3dae7e7c95c4b5518f45b2312646fda7`；payload.json `b00879d08b1e20b1a61cb9d0cc46aa1be66cef8107855c156fc4898752fbb5cd` |
| payload kernel | `0eed483a9e01f7d4f3d7df19f1d13cc3e9adb25ba079dca747b897c84903f464`（与 P1 同一内核） |
| carrier / FD | 27 streams / 109,060,761 B declared；FD `40c29d51…`，与 C/P1 同一份 |
| 状态 | 已打包，`test-bootimg-layout.py` 与 `scripts/verify-boot-image.py` 均 OK，未上机；只在 P1 PASS 且 B 获授权后飞 |

B 图在 `mem_setup` 之后还会执行 `transport_prepare`（SMEM 428/478/479、SMP2P、GLINK adopt）与
`auth_reset`，并按 §4 的 S3–S6 判；它不能替代 P1。

上机判据只有三行：`K60MODEM power ok cx=... mss=... xo=...`、`K60MODEM power prepared`、
`K60MODEM diagnostic stop after power: init_image not sent`；出现任何 `init_image` /
`mem_setup` / `auth_reset` 行即实现有 bug。它是 HR-01 要求的「单资源、单变量、显式授权」
诊断，尚未飞行。

### 3.11 k22：xo.lvl 与 Pong 对齐（离线，未上机）

上机前按仓库规则做了同型机基准对照。Pong 自己的 modem runtime
`E:/k60-work/references/pong-baseband/PongModemRuntime.cpp:146-161` 对 cx.lvl / mss.lvl
先用 `qcom_rpmh_level_index(&resource, 384, &level)` 把 384 换算成索引再投，而 xo.lvl 直接
`pong_rpmh_vote(xo.address, 3)` —— 写的是字面 3，不过 level 表。我们原来的
`k60_modem_find_rail(db, "xo.lvl", 3u, ...)` 无条件调用 `k60_rpmh_level_index`
（`drivers/PongPower/K60PmicRail.c:120-140`：`level_count == 0` 直接返回 `K60RpmhNoLevel`），
于是同一条 rail 要么打印 `K60MODEM power failed: xo.lvl`，要么把索引当值写进去 —— 而这正是
P1 唯一要测的动作，属于「测之前先把被测动作改对」。

`3e449773` 改成 `k60_cmd_db_find(..., "xo.lvl", &xo)` 后按字面 `3u` 投票，cx/mss 保持索引语义；
同时新增 `scripts/update-modem-qrtr-patch.py`，按 `scripts/update-modem-pas-patch.py` 的模式从源码
重生成 0622 的五段 new-file hunk（含 include 改名与 `qcom_glink_ → k60m_glink_`，P-190），
`scripts/tests/test-k60-modem-image.py` 通过，宿主套件仍 `TESTS OK 12`。

静态证据（k22 kernel 的 `llvm-objdump`）：`_k60_modem_rails_vote` 里只有 3 次
`_k60_modem_vote_tcs4`、2 次 `_k60_modem_find_rail`（cx/mss）和 1 次 `_k60_cmd_db_find`（xo）；
第三次投票前是 `mov w3, #0x3`（`fffffff00776320c`），投票值是字面 3，不是算出的索引。

打包结果（P1 的新候选）：

| 项 | 值 |
|---|---|
| kernel | `a2139ecb5e3e65e76ab29dbb8fab2584c691fc0aad7940b153d93f32d02ae147`，105,562,112 B（源 `3e449773`） |
| FD | `40c29d513eab0dca410c36bceeef936244cf2a20c3233f48bbbaa8ae69a07386`（与 C 同一份 clean metadata） |
| boot | `393d7f2f01b878ace9bfb2cafec1614b68a4e2ce23f1170072f14379a2c70947`，201,895,936 B |
| payload | `74ade8b1a62ee63f8a1cb318a9104a41d9571c8201852efd4b90c9069c6ca752`；payload.json `0e7b52a7ce4c24be869169baf1cb323fe606072c6ecf0a51472c69180a48f496` |
| payload kernel | `229ebe507bf6a2475f3bd390c0d48033e1bb40bfb5453adde90c445979a2d599`（strings 含 `diagnostic stop after power` 与 `K60MODEM power ok cx=`） |
| args / 布局 | `pong_modem=4 pong_ipa=0`；560,384 / 201,326,592 / 3,145,840 / 4,024；`verify-boot-image.py` 与 `test-bootimg-layout.py` 均 PASS |

同一个 k22 内核也已离线重打成 B 图（`pong_modem=2 pong_ipa=0`，只把 modem 相位从 power-only 改成 full，
IPA 仍关闭），所以 P1 通过并拿到 B 的显式授权后无需再改代码或重打包：

| 项 | 值 |
|---|---|
| boot | `82c0cab36e5d3d8d7a5d88a21b625163c5aa10cba8ee684e3c826a494cbd04d9`，201,895,936 B |
| payload | `1baec54fdbaa7aab84dd04ba41ad90c23dcb63aa19e009a1caf9e3e27fa62a56`；payload.json `115616728d0cd7e1c9374088d34139432106e01ccef405e816779bd36a1500eb` |
| payload kernel | `229ebe507bf6a2475f3bd390c0d48033e1bb40bfb5453adde90c445979a2d599`（与 P1 同一内核） |
| 打包脚本 | `E:/k60-work/artifacts/build-k22-b-full.sh`；FD/DTB/carrier 与 C/P1 同一份 |
| 验证 | `scripts/verify-boot-image.py` OK；`test-bootimg-layout.py` OK；args 字符串恰好各出现一次 `pong_modem=2`/`pong_ipa=0` |
| 状态 | 已打包、未上机；只替代 k21 的 B 图 `eefe6fdf`，不能替代 P1 |

k21 的 `7b6bb385` 保留为历史，不再上机；k21 的 B 图 `eefe6fdf` 也随之作废，因为它是带 xo.lvl
索引缺陷的内核。P1 判据本身不变（§4.1），只是 `xo=` 现在必须是字面 3。

### 3.12 k22 P1 rail-only：上机 PASS（2026-11-19 04:23，单变量）

`pong_modem=4` 的 k22 图（`393d7f2f…`，§3.11）在设备上只投三条 modem rail，不发送任何 PAS 命令：

| 项 | 值 |
|---|---|
| 证据 | `E:/k60-work/evidence/usblog-20261119-042322`；`console.log` 213,490 B，sha256 `c94dceedd888e70f0dcf4ac761a51d403c5d4450bdaaa86cd59c863752a9e67e` |
| 抓取 | `capture.json` `captured-budget-complete`、`complete=true`、无 panic/reset；`boot.json` `bootAccepted=true`，`fastboot.log` `Sending ... OKAY / Booting OKAY` |
| 结果行 | `:481 K60MODEM carrier present at 0x8bc00000`；`:484 K60MODEM power ok cx=0x30000/6 mss=0x30060/7 xo=0x300b0/3`；`:485 K60MODEM power prepared`；`:486 K60MODEM diagnostic stop after power: init_image not sent` |
| 判读 | `python3 scripts/check-modem-flight-log.py --phase p1 ...` → `P1: PASS`（rc 0） |
| 结论 | 三条 TCS4 rail 在实际 RSC 上全部投票成功，xo 投票值是字面 3；P1 通过，HR-01 的“未验证（离线）”行改为已上机。未发送 init_image/mem_setup/auth_reset，QRTR 仍无证据。 |

这是 k22 内核（`a2139ecb…`）第一次上机；同一内核的 B 图 `82c0cab3…`（§3.11）在 P1 PASS 后成为下一步，
但仍受“无其他 agent 占用 console”的单一 supervisor 约束。用户 2026-11-19 04:16 明确允许：
代码准备充分且其他 agent 没有 boot 时，可以自主上机。

### 3.13 k28：B 的 modem 就绪窗口延长到 30 s（离线，未上机）

B 的 QRTR 探测在 `AUTH_AND_RESET` 之后等 modem 自己启动。Pong 是常驻 worker 轮询
（`PongModemQrtr.cpp:108`），我们只有单次 boot 窗口；原实现 5,000 × 2 ms = 10 s
（`K60ModemLink.c` 的 `K60_QRTR_POLLS`）可能早于 modem 就绪。`8a2d44fc` 把就绪等待
单独拆成 `K60_QRTR_READY_POLLS` 15,000（30 s），verdict 轮询仍是 5,000（10 s）。

| 项 | 值 |
|---|---|
| 源码 | `8a2d44fc23c893d6c884ca664bfa5e9e36c9f9fd`；0622 重新生成 94,545 B（5 files） |
| kernel | `E:/k60-work/artifacts/modem-20261117k28/kernel.macho`，105,582,592 B，sha256 `3e4e69fd6695509c64d42d35983c573fbef11f4160f358edc9f601a6dfa527b6` |
| 镜像 | `E:/k60-work/artifacts/modem-20261117k28/boot-modem-b-full.img`，201,895,936 B，sha256 `d86a73ac12040413f62f7da45dc7af19d0729eea157cb6d36df1e835dca9ac38` |
| payload | `ecd2ecf489f2ebb22a64c9623bbe20bebd9e857d3ff1fe9f4e708682f169af40`（json `96aea7b3…`）；payload kernel `e3f75274…` |
| args | `pong_modem=2 pong_ipa=0`；FD `40c29d51…`；carrier 27 streams / 109,060,761 B |
| 静态证据 | `llvm-objdump` `_k60_modem_qrtr_probe`：`mov w23,#0x3a98` @ `fffffff007764044`、`mov w8,#0x3a98` @ `fffffff00776416c`、`mov w8,#0x1388` @ `fffffff007764274`、`mov w23,#0x1388` @ `fffffff007764628` |
| 验证 | `scripts/verify-boot-image.py` rc0 OK；`test-bootimg-layout.py` OK；主机套件 rc0（QRTR/QMI/QMAP/TRANSPORT PASS，`TESTS OK 30 segments`） |
| 结论 | B 判据不变（§4 的 S3/S4）；k22 的 B 图 `82c0cab3` 作废，但 k22 内核已在 P1 上机，k28 的差异只有这一个常量。 |

B 仍受单一 supervisor 约束：只允许 `scripts/flash.sh`、只允许 `fastboot boot`。
用户 2026-11-19 04:16 的授权是“代码准备充分且其他 agent 没有 boot 时可以自主上机”。

### 3.14 k28 B：AUTH_AND_RESET 在 100 次 resume 处被我们的上限截断（2026-11-19 05:53，S3 FAIL）

k28 B 镜像（`d86a73ac…`）于 05:53:43 起飞，`bootAccepted=true`，05:55:13 自行回到
fastboot；证据 `E:/k60-work/evidence/usblog-20261119-055343`（`console.log` 41,962 B，
sha256 `c6caac8cd59966bf6102f9cc1ac15b52bde7c40779d308706964ad6c7239535a`）。S3 之前的分段全部通过：

```
K60MODEM power ok cx=0x30000/6 mss=0x30060/7 xo=0x300b0/3
K60MODEM power prepared
K60MODEM init_image ok metadata=0xb7ff0000 bytes=5884
K60MODEM transport: remote glink fifo absent, defer IPCRTR
K60MODEM transport ok smp2p=0xe3070/340 desc=0xdf030/32 tx=0xdf060/16384
K60MODEM transport prepared
K60MODEM mem_setup ok base=0x8bc00000 span=0x13200000
K60MODEM scm cmd=0x5 rc=-3 x0=0x1 x1=0x1
K60MODEM auth_reset failed rc=-3
```

`rc=-3` 是 `K60ModemPasInterrupted`；`x0=1` 是 `QCOM_SCM_INTERRUPTED`。monitor 仍在要求
resume，而 `K60M_SCM_MAX_CALLS` 只有 100，循环耗尽后我们把它当成了失败。Pong 的同一事务
最多 resume 100000 次（`PongModemRuntime.cpp:112-118`）。

`d549badd` 把上限改成 100000，并在 `calls > 100` 时打印
`K60MODEM scm cmd=...# ok calls=N`；主机测试新增 1001 次中断后成功的用例（超过旧的 100
上限），`TESTS OK 8 groups`，其中 last-call 用例打印 `calls=99999`。0621 重新生成为 17,666 B（3 files）。

| 项 | 值 |
|---|---|
| 源码 | `d549badd79bb4a42c8f33caa90b7ab8ecf740a43` |
| kernel | `E:/k60-work/artifacts/modem-20261117k29/kernel.macho`，105,582,592 B，sha256 `80fe7d6ece5c7e3d573e5d327737e18d551e520a58a76624ca48f3d3c05fe19f` |
| 镜像 | `E:/k60-work/artifacts/modem-20261117k29/boot-modem-b-full.img`，201,895,936 B，sha256 `92359e3d246f9df8e6578533b71772e3fb245d09ffb90c76b02a0cd04c55a57a` |
| payload | `2b7107f9205f39b2624089fec3ebb781e351d43ad50f042375b1ddb4dd59733e`（json `911e6fac…`）；payload kernel `e9b2f946…` |
| args | `pong_modem=2 pong_ipa=0`；FD `40c29d51…`；carrier 27 streams / 109,060,761 B |
| 静态证据 | `llvm-objdump` `_k60_modem_pas_call`：`mov w8,#0x86a0` + `movk w8,#0x1,lsl #16` = 100000（`fffffff0077613f0`–`fffffff0077613f8`）；`cmp w20,#0x65` 是 calls>100 的打印阈值（`fffffff007761418`） |
| 验证 | `scripts/verify-boot-image.py` rc0 OK；`test-bootimg-layout.py` OK（560384 / 201326592 / 3145840 / 4024）；主机套件 rc0 |
| 结论 | k28 B 图作废；k29 是新的 B 候选，判据仍是 §4 的 S3/S4。判读时 auth 行必须出现 `K60MODEM scm cmd=0x5 ok calls=N` 且 `auth_reset ok`；若仍 `rc=-3` 且 `calls=100000`，说明 100000 次仍不够，属于 PAS/TZ 而不是电源。 |

B 仍受单一 supervisor 约束：只允许 `scripts/flash.sh`、只允许 `fastboot boot`；用户的
2026-11-19 04:16 授权只在“代码准备充分且其他 agent 没有 boot”时成立。

### 3.15 k29 B：AUTH_AND_RESET 上机 PASS，S4 卡在 GLINK 通道（2026-11-19 06:23，S3 PASS / S4 FAIL）

k29 B 镜像（`92359e3d…`）于 06:23:23 起飞；`boot.json` 记 `bootAccepted=false` / `bootExitCode=-1`，
但 console 从 06:23:25 持续写到 06:29:12，捕获完整 230,060 B，sha256 `9ecde6b8…`，
`stopReason=budget`，无 panic。机械判读：

```
python3 scripts/check-modem-flight-log.py --phase b …/console.log
S3: PASS
S4: FAIL
  expected exactly one K60MODEM qrtr: dms revision line, found 0
```

S3 全绿的关键行：

```
K60MODEM power ok cx=0x30000/6 mss=0x30060/7 xo=0x300b0/3
K60MODEM init_image ok metadata=0xb7ff0000 bytes=5884
K60MODEM transport ok smp2p=0xe3070/340 desc=0xdf030/32 tx=0xdf060/16384
K60MODEM transport prepared
K60MODEM mem_setup ok base=0x8bc00000 span=0x13200000
K60MODEM scm cmd=0x5 ok calls=182
K60MODEM auth_reset ok
```

`calls=182` 证明 k28 的 `rc=-3` 不是 TZ 拒绝，而是我们的 100 次 resume 上限；monitor 在第 182 次
resume 后完成，AUTH_AND_RESET 首次上机通过。电源、carrier 暂存、transport、mem_setup 也随同一条
路径首次在 B 形态下全部验证。

S4 的第一手证据（同一次捕获，`console.log` 493–499 行）：

```
K60MODEM qrtr: glink desc=0xdf030/32 ours=0xdf060/16384 theirs=0xe31d8/16384
K60MODEM qrtr: modem ready (smp2p items=2)
K60MODEM qrtr: opening IPCRTR as initiator
K60MODEM baseband: bridge disabled
K60MODEM qrtr: channel up
K60MODEM qrtr: channel down
K60MODEM qrtr: glink poll rc=-5 at 2
```

`rc=-5` 是 `QcomGlinkCorrupt`（`drivers/PongPower/QcomGlink.h`）：RX FIFO 里的下一条消息无法按
GLINK 命令解析，`k60m_glink_poll()` 因此调用 `k60m_glink_stop()` 并返回 -5；`channel down` 是 stop
关闭通道时的回调，所以它打印在 rc 之前。通道确实 up 过（OPEN_ACK 已匹配 lcid），命名与方向不是
这一步的问题；坏的是紧接着的那条命令。`bridge disabled` 属于 QcomBaseband 控制桥（S6），在 S4
失败之后不再解释。此后 K60DATA/K60DYLD/K60INIT 正常启动，K60EXC n=1 pid=1 是既有 userland 问题。

下一飞（k30）只做一件事：在 `K60ModemLink.c` 的 poll 错误路径里、`return` 之前快照 RX 环头 16 字节，
打印 `cmd / param1 / param2 / avail`，据此判定是 VERSION、OPEN、INTENT 还是 DATA 分支触发 Corrupt。
`drivers/PongPower/QcomGlink.c` 属充电线（`docs/engineering/TREE-OWNERS.toml:70`），本线不改它。

| 项 | 值 |
|---|---|
| 源码 | `d549badd79bb4a42c8f33caa90b7ab8ecf740a43`（k29，只改 resume 上限与计数打印） |
| 镜像 | `E:/k60-work/artifacts/modem-20261117k29/boot-modem-b-full.img`，sha256 `92359e3d246f9df8e6578533b71772e3fb245d09ffb90c76b02a0cd04c55a57a` |
| 证据 | `E:/k60-work/evidence/usblog-20261119-062321`（console 230,060 B，sha256 `9ecde6b82b8122fb1418aae20788be57a15cb09286fa20bf5fb3b708d9b70200`，complete，budget） |
| 判读 | S3 PASS；S4 FAIL（`channel down` + `glink poll rc=-5 at 2`，无 dms revision） |
| 结论 | 电源/PAS/transport/mem 已上机；下一层是 GLINK 消息解析，不是 PAS 或电源 |

### 3.16 k30：GLINK 损坏消息的 RX 快照（离线，未上机）

k29 B 的 S4 只给出一行 `glink poll rc=-5 at 2`，不足以判断是哪一条 GLINK 命令触发了
`QcomGlinkCorrupt`。`receive_one()` 在 Corrupt 路径上只 peek、不 advance，`k60m_glink_stop()`
也不动 RX 环，所以坏消息在 poll 返回时仍留在环头：k30 只改 `K60ModemLink.c` 的错误路径，
在 `return` 之前快照 RX 环头 8 字节并打印

```
K60MODEM qrtr: glink poll rc=%d at %u rx avail=%u head=%u tail=%u cmd=%#x p1=%#x p2=%#x
```

命令号按 `drivers/PongPower/QcomGlink.h` 的枚举解读（0 VERSION、1 VERSION_ACK、2 OPEN、
3 CLOSE、4 OPEN_ACK、5 INTENT、6 RX_DONE、7 RX_INTENT_REQ、8 ACK、9 TX_DATA、11 CLOSE_ACK、
12 TX_DATA_CONT、13 READ_NOTIF、14 RX_DONE_W_REUSE、15 SIGNALS；10 在协议里未使用）。
这与 hakios 的 `GLINK_DATA_MORE=12 / GLINK_READ_NOTIFY=13` 编号一致
（`E:/k60-work/references/phk110-port/drivers/modem/hakios.mpss.c:2574-2575`），所以不存在
“我们把 12/13 记错”的假设。`drivers/PongPower/QcomGlink.c` 属充电线
（`docs/engineering/TREE-OWNERS.toml:70`），本线只在 `K60ModemLink.c` 里做只读快照，不改它。

0622 重新生成为 95,370 B / 5 files；`test-k60-modem-image.py` TESTS OK 30 segments、
`test-k60-ipa-patch.py` PASS、`run-host-tests.sh` rc0。静态证据：`llvm-strings` 在
kernel.macho 里恰好命中一次 `glink poll rc=%d at %u rx avail`；`llvm-nm` 有
`_k60_modem_qrtr_probe fffffff007763ca0` 与 `_k60_ipa_qrtr_reset fffffff00776be3c`。

| 项 | 值 |
|---|---|
| 源码 | `3c68b7a8`（"feat(cellular): snapshot the GLINK RX message on corruption"） |
| kernel | `E:/k60-work/artifacts/modem-20261117k30/kernel.macho`，105,582,592 B，sha256 `c6de4ad86e36ca3240cbfa2189ad3e8ed30fa43dd4717c977b8eb55918a24dfd` |
| 镜像 | `E:/k60-work/artifacts/modem-20261117k30/boot-modem-b-full.img`，201,895,936 B，sha256 `d17550354629f4f18bdb4ced8dcb1bc05f87d652dfcc1250a79913c94195cb17` |
| payload | `7a2d771692d56d878e449bdfc29aa602c337ebfdc89a9e0cd35f4d688b31f6b8`（json `54dc54d5…`）；payload kernel `95163b59…` |
| args | 末尾 `pong_modem=2 pong_ipa=0`；FD `40c29d51…`；carrier 27 streams / 109,060,761 B |
| 验证 | `scripts/verify-boot-image.py` rc0 OK；`test-bootimg-layout.py` OK（560384 / 201326592 / 3145840 / 4024） |
| 判据 | S3 必须保持；S4 仍要求 `dms revision`。新增的 `rx avail=… cmd=… p1=… p2=…` 行只用于定位分支，不改变 S4 的通过条件 |
| 状态 | 已打包、未上机；k29 的 S3 PASS 与这一行诊断一起构成下一次单变量飞行 |

**实机结果（2026-11-19 07:26，k30 B）**：S3 仍然 PASS（`scm cmd=0x5 ok calls=179`、`auth_reset ok`、
`transport prepared`、`mem_setup ok`），S4 仍然 FAIL，失败行是

```
K60MODEM qrtr: glink poll rc=-5 at 2 rx avail=576 head=648 tail=72 cmd=0 p1=0 p2=0
```

`cmd=0 p1=0 p2=0` 不是“VERSION 命令坏了”，而是快照取错了环的一端：`head` 是 modem 的写指针
（下一个空位），解析器与 `rx_peek()` 读的是 `*rx->tail`（最旧未读消息，
`drivers/PongPower/QcomGlink.c:47-55`，`rx_advance` 在 `:57-63` 推进 tail）。
`avail=576` 正好等于 `head-tail=648-72`，所以坏消息在 `tail=72`。k30 证明 S3、固件与 SMP2P
仍然成立，但没有证明 GLINK 命令内容；把取样端改到 tail 的修复是 `d257e2bb`（§3.17）。

### 3.17 k31：RX 快照改读 FIFO tail（离线，未上机）

k30 的失败行读的是 `rx->head`（modem 写指针），而 `k60m_glink_receive_one()` 与 `rx_peek()` 都从
`*rx->tail` 开始、`rx_advance()` 只推进 tail，所以那 8 个字节永远是环上空位。`d257e2bb` 把快照改成

```
m[b] = rx->data[(tail + b) % rx->length];
```

并在注释里记下 k30 的 `cmd=0 p1=0 p2=0` 教训；打印格式不变
（`K60MODEM qrtr: glink poll rc=%d at %u rx avail=%u head=%u tail=%u cmd=%#x p1=%#x p2=%#x`），
所以 `check-modem-flight-log.py` 与既有判据不需要改。0622 重新生成为 95,552 B / 5 files；
`test-k60-modem-image.py` TESTS OK 30 segments、`test-k60-ipa-patch.py` PASS、
`run-host-tests.sh` rc0（含 FLIGHT LOG）。

| 项 | 值 |
|---|---|
| 源码 | `d257e2bb`（"fix(cellular): read the GLINK snapshot from the fifo tail"） |
| kernel | `E:/k60-work/artifacts/modem-20261117k31/kernel.macho`，105,582,592 B，sha256 `b58ca6927757598f188f7f7ac5e95104c1427bf4bd336336c1ae19c0c0dd1b34` |
| 镜像 | `E:/k60-work/artifacts/modem-20261117k31/boot-modem-b-full.img`，201,895,936 B，sha256 `e9b43266dc804ed9d11f09efaf3e2b86ac59671111acea71e45e3f2019b02cd1` |
| payload | `2deb9135f48e3a622b1ae758464671ab80c067e8f53c6c5277bf17c6a745fff4`（json `d8d263806580d4a37ef35ba8678301a85f1cdd5e54ac3ee2bf75a7a32b410fb2`）；payload kernel `d1a8fb91ca0d15d72dd4538be01db87d6364d22b3e1484ea732b93185817fdfd` |
| args | 末尾 `pong_modem=2 pong_ipa=0`；FD `40c29d513eab0dca410c36bceeef936244cf2a20c3233f48bbbaa8ae69a07386`；carrier 27 streams / 109,060,761 B |
| 验证 | `scripts/verify-boot-image.py` rc0 OK；`test-bootimg-layout.py` OK（560384 / 201326592 / 3145840 / 4024） |
| 判据 | S3 必须保持 PASS；S4 仍要求 `dms revision`。新的 rx 行必须显示 `tail` 处真实的最旧消息：`cmd` 是 0～15 的命令号且 `p1/p2` 不再是全 0（若仍是全 0，说明取样或打印仍有错） |
| 状态 | 已打包、未上机；与 k30 只差快照取样端 |

**实机结果（2026-11-19 07:49，S3 PASS / S4 FAIL）**：证据 `E:/k60-work/evidence/usblog-20261119-074912`，
console 220,975 B，sha256 `09aea18d11d6aefa212e1de3e562032a9d82b238a5fb01229bddc97b9ced56bd`，
capture 完整（`captured-budget-complete`、stopReason budget、无 panic、有 restart marker）。
`check-modem-flight-log.py --phase b` 判 S3 PASS、S4 FAIL（dms revision 0 条）。
S3 行与 k29/k30 相同，`scm cmd=0x5 ok calls=181` 是第三次独立复现 auth_reset。

### 3.37 k50（离线）：存储数据面的第一块——EFS 镜像表与 scatter 计划

k46 的应答只到 open，k47–k49 把共享区和它的归属做完了，但 `rw` 仍然回 result 1。缺的是同一件事的两半：四个镜像**在哪**（哪块 GPT 分区、多大），以及一条 scatter 项**对应哪一段**（镜像偏移 → 共享区偏移、多少字节）。这一节只做这两半里能在纸面和宿主上验证的部分。

新文件 `drivers/PongCellular/K60ModemEfs.h` / `.c`（协议与表，不含 UFS、SCM、分配）：

- `k60_efs_partition(1..4)` / `k60_efs_boot_path(1..4)`：按 RMTFS 的编号给出 `modemst1`、`modemst2`、`fsg`、`fsc`，与 `/boot/modem_fs1|fs2|fsg|fsc` 一一对应（PongModemRmtfs.h 的同一张表）；0 与 5 返回 NULL；
- `k60_efs_name_matches(entry, bytes, name)`：GPT 分区名是 36 个 UTF-16LE 码元的定长字段、余下补零，所以比较必须按码元读、按 NUL 截断，不能当 C 字符串；
- `k60_efs_plan(request, image_bytes, window_base, window_bytes, spans, cap)`：把已通过 `k60_rmtfs_check_vectors` 的 rw 请求翻译成拷贝表 `{image_offset, buffer_offset, bytes}`，并再加两道它自己的边界：每一段必须整段落在镜像内、且整段落在共享区内。

宿主测试 `scripts/tests/test-k60-efs.c`（`gcc -O1 -Wall -Wextra -Werror -Idrivers/PongCellular`，链接 `K60ModemEfs.c` + `K60ModemRmtfs.c`）：表映射与越界、`modemst1`/`fsg`/`userdata` 的 UTF-16LE 比较（含 NULL 与零长）、两段散列表的计划值与拒绝路径（越过镜像末尾、低于窗口、结尾越过窗口、全零长度、无向量、容量不足、非 rw 消息）。输出 `K60 EFS PASS table, gpt names, scatter plan, refusals`；已登记进 `/mnt/e/k60-work/artifacts/run-host-tests.sh`（整套 19 条 PASS）。

**还没做的**：① 按名字查 LUN 0 的 GPT 得到 `first_lba`/`blocks`（`drivers/NativeUfs/RootLayout.h` 现在只找 `userdata`/`unixnu`，要抽一个按名字查的入口）；② 把 `K60EfsSpan` 变成真实的块读（写只进 boot-session 影子）；③ 在 `K60ModemLink.c` 的 rw 分支里调用它。这三步都要动内核，等 `/opt/k60/trees/cellular-k49` 建好后再做，本轮不往 `/tmp` 树里编；因此 `K60ModemEfs.*` **还没进 0622**，进 0622 与接线同批完成。

