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

取样端修复生效：失败行变成

```
K60MODEM qrtr: glink poll rc=-5 at 2 rx avail=576 head=648 tail=72 cmd=0x5 p1=0x1 p2=0x1
```

即环头最旧一条是 **GLINK INTENT（cmd=5）**，`param1=1`（rcid）、`param2=1`（一个 pair）。
`QcomGlink.c:393-421` 的 INTENT 分支只有四种 `QcomGlinkCorrupt` 出口：`:394` 计数越界、
`:403` pair 的 size 或 id 为 0、`:407` 同 id 已在 busy、`:411` 48 个槽全满。通道刚打开，
槽不可能满，所以嫌疑集中在 `:403`：要么这条 INTENT 真的带 0 pair，要么我们从 0 开始读到的
576+72 字节根本不是本次会话的环，而是上一次会话留下的残料。区分它需要两样 k31 没打印的东西：
adopt 瞬间的 `desc[0]/desc[3]` 与环首 32 字节，以及配对本身的 size/id（`0x1 0x1` 之后没有打印）。


### 3.18 k32：adopt 时的环状态与 32 字节损坏快照（离线，未上机）

k31 的失败行把坏消息定位到了命令号，但没有打印判据点本身：`cmd=0x5`（INTENT）、`p1=0x1`（rcid）、
`p2=0x1`（一个 pair）。`QcomGlink.c:393-421` 的 INTENT 分支只有四个 `QcomGlinkCorrupt` 出口——
`:394` 计数越界、`:403` pair 的 size 或 id 为 0、`:407` 同 id 已在 busy、`:411` 48 个远端槽全满。
通道刚打开，槽不可能满；剩下的是 `:403`（真的零 pair）与“环里是上一次会话的残料、对齐早已错位”两种互斥解释。

k32（`55259825`）**不改任何行为**，只加两处诊断：

1. `qcom_glink_adopt()` 成功后立刻打印 `desc[0]`（modem 侧 tx tail）、`desc[3]`（modem 侧 rx head）与环首
   32 字节（8 个小端 u32；此刻 `*rx.tail` 必为 0，这是 adopt 的前置条件）。新会话在我们发出 VERSION 之前
   不可能已经排好 648 字节的完整握手；如果此处 head 已非 0 且 `w0` 不是 VERSION/OPEN 的命令号，
   说明环里是旧会话的残料。
2. 损坏路径的 8 字节快照扩到 32 字节，**保留原前缀**（`glink poll rc=… at … rx avail=… head=… tail=… cmd=… p1=… p2=…`）
   以便 `check-modem-flight-log.py` 与既有 `grep` 不失效，并追加 `tx head=… tx tail=…` 与 `w2..w7`。
   字布局：`w0 = cmd | p1 << 16`、`w1 = p2`、`w2/w3 = 第一个 INTENT pair 的 size/id`、`w4/w5 = 下一条消息头`。

| 项 | 值 |
|---|---|
| 源码 | `55259825`（"feat(cellular): dump the GLINK ring at adopt and on corruption"） |
| 主机验证 | 0622 96,781 B / 5 files；`test-k60-modem-image.py` TESTS OK 30 segments；`test-k60-ipa-patch.py` PASS；`run-host-tests.sh` rc0（含 FLIGHT LOG） |
| kernel | `E:/k60-work/artifacts/modem-20261117k32/kernel.macho`，105,582,592 B，sha256 `f9c915aa361075277a6bf33a123ba0167cd72638e53474c9793033fedd6152ad` |
| 镜像 | `E:/k60-work/artifacts/modem-20261117k32/boot-modem-b-full.img`，201,895,936 B，sha256 `5571c7f293021c54f7b0f6c43799f028e3953875542db9cb701a65e619f5d145` |
| payload | `95d4cd30e3f68932829743e3b62cd4c9a445a63f1d44fdd0b079f7bee271807d`（json `b7560ab4488857f1d315620cc4b714989dde7f3d38d2b9bc00415eebd04b22a7`）；payload kernel `8a6749c6ce873217b8b2e2a832ebcbfd8c662e47a8a59e42240f5b86508395fb`；adt `7b3119fb3dff370460c1ed6d655c2db484c4fdb82d7bb471b9b6a92e87c74c73` |
| args | 末尾 `pong_modem=2 pong_ipa=0`；FD `40c29d513eab0dca410c36bceeef936244cf2a20c3233f48bbbaa8ae69a07386` |
| 布局 | 560,384 / 201,326,592 / 3,145,840 / 4,024；`verify-boot-image.py` rc0 OK |
| 判据 | S3 必须保持 PASS；S4 仍要求 `dms revision`。新行只用于在“旧会话残料”和“真实零 pair”之间定性，不改变 S4 的通过条件 |
| 状态 | 已打包、未上机；与 k31 只差两处诊断打印 |

**更正（2026-11-19 08:30）：k32 的 adopt 诊断打错了路径，镜像作废。** 那行打印只挂在
`k60_modem_glink_start()`（transport 路径，源码第 1087 行）；而 B 形态每次都在 `mem_setup` 打印
`K60MODEM transport remote glink fifo absent, defer IPCRTR`，真正的 adopt 发生在探针路径
（`K60ModemLink.c:1212`）。证据：`git show 55259825:drivers/PongCellular/K60ModemLink.c | grep -n 'glink adopt'`
只列出 1087 与 1200 两行，探针函数切片内命中 0 次。因此 k32 的 adopt 行在 B 飞行中不可能出现，
由 §3.19 的 k33 取代。

### 3.19 k33：探针路径的 adopt 诊断与旧环残料丢弃（离线，未上机）

k31 的失败行（`rc=-5 at 2 rx avail=576 head=648 tail=72 cmd=0x5 p1=0x1 p2=0x1`）已经说明坏消息是
一条只有一个 pair 的 GLINK INTENT，但还缺两样东西：adopt 那一刻对端写指针是多少，以及 tx 环是否也在
重放旧数据。k33 由两个提交组成：

1. `52c741a8` "fix(cellular): drop a stale GLINK ring at adopt"：把环形打印抽成
   `k60_qrtr_print_ring()`，两条 adopt 路径都调用；探针路径在 adopt 成功后打印
   `K60MODEM qrtr: glink adopt (probe) …`，**若 `*rx.head` 非 0，则把我们的读指针 `*rx.tail` 对齐到它**
   （`k60_modem_fence()` 后）并打印 `K60MODEM qrtr: glink adopt dropped N stale bytes (head=…)`。
2. `979bf601` "feat(cellular): print both GLINK queue indices at adopt"：打印行同时带 tx 环的
   head/tail（`desc[1]`/`desc[0]`）与环首 8 个小端 u32，格式
   `K60MODEM qrtr: %s rx head=%u tail=%u avail=%u tx head=%u tail=%u cmd=%#x p1=%#x p2=%#x w2=… w7=%#x`。

丢弃为什么安全：`qcom_glink_adopt()` 的前置条件是我们的两个索引为 0，而 `k60_modem_transport_prepare()`
（`K60ModemLink.c:933-938`）只清 AP-owned 的 `desc[1]`（tx head）与 `desc[2]`（rx tail）；`desc[0]`/`desc[3]`
是 modem 的读/写指针，跨热启动留在 SMEM 里——hakios 的同名步骤（`hakios.mpss.c:2656-2673`）同样只清那两个。
在我们发出第一条 VERSION 之前，modem 不可能已经排好一条 648 字节的、指向本通道的完整握手，所以 adopt 时
`rx.head` 非零只能是上一会话（甚至 Android）的残料；k30 与 k31 两次失败行逐字节相同，也正符合“每次重放同一段
残料”。tx 环的这一侧本轮**只观测不重置**（`tx tail` 若也非零，说明 `desc[0]` 同样过期，留到 k34 一起清），
保持单变量。

| 项 | 值 |
|---|---|
| 源码 | `52c741a8` + `979bf601`（"feat(cellular): print both GLINK queue indices at adopt"） |
| 主机验证 | 0622 98,216 B / 5 files（52c741a8 后为 98,049 B）；`test-k60-modem-image.py` TESTS OK 30 segments；`test-k60-ipa-patch.py` PASS；`run-host-tests.sh` rc0（QMAP/QMI/SERVER/TRANSPORT/QRTR/FLIGHT LOG 全绿） |
| kernel | `E:/k60-work/artifacts/modem-20261117k33/kernel.macho`，105,582,592 B，sha256 `5b84e7c561b64c6882dab7d63359dad991265f941535175c4233ef1bfc94cf61`；`llvm-strings` 命中 `glink adopt (probe)`、`glink adopt (transport)`、`glink adopt dropped %u stale bytes (head=%u)` |
| 镜像 | `E:/k60-work/artifacts/modem-20261117k33/boot-modem-b-full.img`，201,895,936 B，sha256 `d467eee47ae7e21f0d70210119b3b92a5be55bef9a91be39c41c749c72676a54` |
| payload | `ae943899297d27890f8acb945c775b6f3a968ae9de0e8fc96c033b6c1cfef040`（json `97864e04223d6a39bbacca16b35b17065a7265c58cd311c533fadfd67b348b86`）；payload kernel `db5d04035fc6cba8144e3fc2ebc4809ed3893d2e89acd29622988a201c6d2207`；adt `43b356612a51f2587d06b5fff8b7bbcdaeaf55b0e72c7f65e87d53f805cfc7c7` |
| args | 末尾 `k60_autoreset=300 applog=1 pong_modem=2 pong_ipa=0`；FD `40c29d513eab0dca410c36bceeef936244cf2a20c3233f48bbbaa8ae69a07386`；carrier `1b4631a6…` |
| 布局 | 560,384 / 201,326,592 / 3,145,840 / 4,024；`verify-boot-image.py` rc0 OK，`test-bootimg-layout.py` OK |
| 判据 | S3 必须保持 PASS；S4 仍要求 `dms revision`。adopt 行与 `dropped … stale bytes` 行用于判定残料假设，不改变 S4 的通过条件 |
| 采集 | 本次 `flash.sh` 的采集秒数由 300 改为 **420**：autoreset 在 300 s 触发，过去两次采集都在复位行之后 1.3 s 结束，无法判定 `PE_k60_reset_now()` 是否真的复位；多观察 120 s，USB 断开即复位生效 |
| 状态 | 已打包、未上机；已被 §3.20 的 k34 取代（k34 只多一行 bridge 状态打印） |


### 3.20 k34：bridge 晚发布的状态行（离线，未上机）

k33 打包后设备一直挂死、没能起飞，等待期间复核 S6 时发现**这条判据按原代码永远无法满足**：
`K60MODEM baseband: bridge ` 状态行在轮询循环**之前**只打印一次，而 `coachz_baseband_configure()`
的重试在循环里（每 500 次 poll 一次）。QcomBaseband 组件在 IOResources 未就绪时会推迟发布
（`patches/qcombaseband/0001-coachz-defer-publication.patch`），因此一个**工作正常但晚发布**的桥
只会留下开头的 `bridge disabled`，S6 会被误判为失败，白飞一次。

k34（`cfb2917f`）只加一段：重试块里若 `!bridge_reported && coachz_baseband_enabled()`，打印
`K60MODEM baseband: bridge enabled (poll %u)` 并置位。行为无其他变化，与 k33 的差别就是这一行。

同轮把判据机械化：`scripts/check-modem-flight-log.py --phase b` 现在输出 **S3/S4/S5/S6** 四组
（新增 S5 判 `K60MODEM qrtr: verdict ok services=N node0=M` 的 N>0、M≥1；S6 判 bridge enabled 行与
`COACHZ baseband: %d of %u services published` 的 N>0），回归 `test-check-modem-flight-log.py`
输出 `K60 FLIGHT LOG PASS p1 c b s5 s6 negative-cases`。

| 项 | 值 |
|---|---|
| 源码 | `cfb2917f982095a4799cba19361b6f3b5ede19e2`（叠加 k33 的 `52c741a8`+`979bf601`） |
| 主机验证 | 0622 98,625 B / 5 files；`test-k60-modem-image.py` TESTS OK 30 segments；`test-k60-ipa-patch.py` PASS；`run-host-tests.sh` rc0（含 S5/S6 判读回归） |
| kernel | `E:/k60-work/artifacts/modem-20261117k34/kernel.macho`，105,582,592 B，sha256 `68c6c9bcfbf8258f134714ecab5a6c4e5371bb3f3996e0d8bf86fed1d5b05501`；`llvm-strings` 命中 `K60MODEM baseband: bridge enabled (poll %u)` |
| 镜像 | `E:/k60-work/artifacts/modem-20261117k34/boot-modem-b-full.img`，201,895,936 B，sha256 `20fff9f27110ef723c281efabd01599b70dfaf43cc0dde91b93da5123b994a98` |
| payload | `2beb6fd370752abdccdae39d8f821ab5420587058d6aaabf74d073c4cc4dd875`（json `50ba0a1d3838cbc718e7b703f9fb8dd65a6a7689a6875aa984074b72ec38c7b0`）；payload kernel `56d8dd65d9273a50901c16004e980b32fe91e7a806bab561d66d783da7cd033d`；adt `fdc1a9818dd5fcf3ce0cf972faff1434df440917d7c74f5782912b53c2ca91f7` |
| args | 末尾 `k60_autoreset=300 applog=1 pong_modem=2 pong_ipa=0`；FD `40c29d513eab…`；carrier `1b4631a6…` |
| 布局 | 560,384 / 201,326,592 / 3,145,840 / 4,024；`verify-boot-image.py` rc0 OK |
| 状态 | 已打包、未上机（k33 未飞即被取代） |
| 判读 | `--phase b` 四组全过才算 B PASS；采集 420 s 以判定 autoreset |

### 3.21 QcomBaseband 没有链进内核：生成配置过期（2026-11-19 查明）

等待设备期间把 S6 一路查到根：**内核里没有 QcomBaseband 组件，只有 weak 兜底。** 证据链：

- 构建产物存在：`/tmp/k60-modem-20261117c/mondrian/ipados-16.6.1-20G81/mondrian/tree/build/qcom-baseband/libQcomBaseband.a`
  767,600 B（k34 构建 09:02 重写），`llvm-nm --defined-only` 给出 `T _coachz_baseband_configure`、
  `T _coachz_baseband_enabled`，`llvm-strings` 有 40 条 `COACHZ`；其 272 个未定义符号在
  `kernel.macho` 里**全部**有定义（逐个 diff，缺失 0），静态 force-load 在符号层面可链接；
- 但 `llvm-strings kernel.macho | grep -c COACHZ` = **0**，`llvm-nm` 只看到七个间隔 8 字节的 `S` 符号
  （`fffffff007762978/80/84/88/8c/94/98`），正是 0622 里 `__attribute__((weak))` 的兜底。

**根因（更正 2026-11-19 09:40）**：链接配置本身是对的，问题在生成配置过期。

- `configs/mondrian_defconfig:82` 早在 `c2ced39c`（2026-11-18 00:12）就有
  `CONFIG_XNU_EXTRA_LD_ARCHIVES="-Wl,-force_load,{tree}/build/qcom-baseband/libQcomBaseband.a"`；
- `scripts/build-xnu-4k-baseline.sh:1181-1183` 确实把它拼进 `PLATFORM_ARCHIVES`，
  `/opt/k60/trees/k60build/scripts/unixnu/kernel.py:18-27` 的 `xnu_env()` 会把 `CONFIG_XNU_*` 去掉前缀、
  展开 `{tree}` 后放进环境；
- 但构建树用的是 `/tmp/k60-modem-20261117c/mondrian/ipados-16.6.1-20G81/mondrian/.config`，
  写于 2026-11-18 02:29 的 105 行版本，**不含该符号**；而 `unixnu build` 不重新生成配置
  （`cli.py:306` 的 `cmd_defconfig` 只在 `release` 路径里），所以此后每次 `build kernel` 的
  `XNU_EXTRA_LD_ARCHIVES` 都是空串，archive 从未进入链接行；
- 验证：`./unixnu defconfig mondrian_defconfig -D /mnt/e/hackios/k60-cellular --out /tmp/k60-modem-20261117c`
  之后 `.config` 只多 4 行（3 行注释 + 该符号，diff `105a106,109`），其余 105 行逐字节不变。

影响：`coachz_baseband_configure()` 是空函数、`coachz_baseband_enabled()` 恒 0，AppleBaseband /
AppleBasebandPCIControl / AppleBasebandPCIInterface / PDP manager / AppleIPAppender **一次都没发布过**；
k30/k31 日志里只有 `bridge disabled`、没有任何 `COACHZ baseband:` 行，原因就是这个（不是 IOResources
未就绪）。k34 的 `bridge enabled (poll N)` 只有在组件链入后才有意义。

教训：**改 `configs/*_defconfig` 不会影响 `unixnu build`，除非先显式跑 `defconfig`（或走 `release`）**；
判断一条 `CONFIG_XNU_*` 是否生效，看的是 out 目录里的 `.config`，不是仓库里的 defconfig。

下一步：用重新生成的 `.config` 重建内核（k35），量 `COACHZ` 条数、`_coachz_baseband_configure` 是否
变成 `T`、镜像体积变化；上机前仍要评估 Coachz PCIe/MHI 参考实现与 K60 SM8475 集成 modem 的差异。

### 3.22 k35：把 QcomBaseband 真正链进内核（离线构建，未上机）

§3.21 的根因是**生成配置过期**而不是接线缺失，所以不需要改链接脚本，只要重新生成 `.config` 再构建：

- `./unixnu defconfig mondrian_defconfig -D /mnt/e/hackios/k60-cellular --out /tmp/k60-modem-20261117c`
  之后 `.config` 只多 4 行（3 行注释 + `CONFIG_XNU_EXTRA_LD_ARCHIVES=...`，diff `105a106,109`），其余 105 行不变；
- 用该配置重建（`build-k35-kernel.sh`）得到 `kernel.macho` 105,734,144 B（k34 是 105,582,592 B，**+151,552 B**），
  sha256 `80fb13351479f0fecdb46b7e5e349d87524a61caba9bef221ff512ebab701f93`；
- `llvm-strings kernel.macho | grep -c COACHZ` 从 **0 变成 40**；`llvm-nm -m` 显示
  `_coachz_baseband_configure` 在 `(__TEXT_EXEC,__text) external`、地址 `fffffff007a8c078`，
  `_coachz_baseband_enabled` 在 `fffffff007a871f8`。注意 `llvm-nm --defined-only` 对
  `__TEXT_EXEC` 段统一打印字母 `S`（我们自己的 `_k60_modem_init_image` 也是 `S`，`fffffff007765478`），
  所以判断链入与否要看段名与 `COACHZ` 字符串，不能只看字母；
- 该 archive 的 272 个未定义符号在 `kernel.macho` 里全部有定义（缺失 0），静态 force-load 在符号层面可链接。

k35 B 镜像（与 k34 只差这一层）：

| 项 | 值 |
|---|---|
| 镜像 | `E:/k60-work/artifacts/modem-20261117k35/boot-modem-b-full.img` 201,895,936 B `2f989b28acace59dc1162c45d14956bc24c7fe8c5c4a8eabf4ef4bac44b56fa1` |
| kernel | `80fb1335…`（105,734,144 B）；payload kernel `f059d1232fc5b11cafcf5e150b43b8834764b9752a5a31d4184a1e06c52818b3` |
| payload | `7ae83050869cf7f134eab7c97ea6ae969ddb4fbed830ebd8653ef04842c40fda` |
| args | 末尾仍是 `k60_autoreset=300 applog=1 pong_modem=2 pong_ipa=0`；FD `40c29d513eab…` |
| 布局 | 560,384 / 201,326,592 / 3,145,840 / 4,024；`verify-boot-image.py` rc0 OK |

上机期望与风险：`coachz_baseband_configure()` 现在会真正执行（`bb_init`/`bb_pdp_init`，然后
`IOService::getResourceService()` + `registerService()`，源码 `build/qcom-baseband/src/baseband/coachz_baseband.cpp`，
`registerService` 在 1144 行），日志应出现 `COACHZ baseband:` 行；若 IOResources 未就绪则走
`patches/qcombaseband/0001-coachz-defer-publication.patch` 的延迟发布分支。它只是把 AppleBaseband 类发布出来、
把 QRTR 包交给我们的 `bb_send` 回调（`coachz_baseband_qrtr` 在 1190 行），configure 阶段不碰 PCIe/MHI
（`--coachz` 适配器没有编进来），因此这是一次有界的单变量实验。S3 必须保持 PASS，S4 仍按 `dms revision`
判，S6 从 N/A 变成真判。

#### 实机结果（2026-11-19 10:03，420 s 采集）

- 镜像就是上表那一份 `2f989b28…`，10:03:33 起飞，10:09:27 采集结束；证据
  `E:/k60-work/evidence/usblog-20261119-100331`，`capture.json` 记
  `state=captured-disconnected`、`complete=false`、`bytes=182646`、
  `logSha256=37BF3BFA0AAE2F07A8542552671613B023DE44151929C65A2B9206407372030C`、
  `stopReason=fastboot-return`、`resetMarker=K60 USBLOG: restart reason published`、`lastDataAt=10:09:22`。
  `K60AUTORESET: 300 s since boot; resetting to fastboot` 之后 USB 真的断开并回到 fastboot——这一次复位生效了，
  与 k31 之后那次挂死不同。
- 机械判读（`--phase b`）：**S3 PASS**、**S4 FAIL**（0 条 `dms revision`）、**S5 FAIL**（0 条 `verdict`）、
  **S6 PASS**，rc=1。
- S3 保持：`power ok cx=0x30000/6 mss=0x30060/7 xo=0x300b0/3`、`init_image ok metadata=0xb7ff0000 bytes=5884`、
  `transport ok smp2p=0xe3070/340` + prepared、`mem_setup ok base=0x8bc00000 span=0x13200000`、
  `scm cmd=0x5 ok calls=181`、`auth_reset ok`（第四次独立复现）。
- adopt 行第一次把四个索引都带出来（console.log:498-499）：

  ```
  K60MODEM qrtr: glink adopt (probe) rx head=8 tail=0 avail=8 tx head=0 tail=0 cmd=0 p1=0x1 p2=0x7 w2=0 w3=0 w4=0 w5=0 w6=0 w7=0
  K60MODEM qrtr: glink adopt dropped 8 stale bytes (head=8)
  ```

  即 adopt 时环里确实有 8 字节上一轮的残料（对端写指针 8，内容是 `cmd=0`、`p1=1`、`p2=7`，一个 VERSION 帧，来自 Android 时代的 SMEM），
  §3.19 的丢弃逻辑按预期清掉它，随后 `opening IPCRTR as initiator`。
- **S6 第一次真正判定并通过**：`K60MODEM baseband: bridge enabled`（:501）、
  `COACHZ baseband: 22 of 22 services published (AppleBaseband, AppleBasebandPCIControl, 18 channels, the PDP manager, AppleIPAppender)`（:522）、
  `K60MODEM baseband: data receiver registered`（:521），以及 `COACHZ pdp: plumb unit 0..3 family 2/30 result 0` 与
  `COACHZ pdp: pdp_ip0..3 mux 1..4 registered result 0 (initially down)`（:504-520）。§3.21 的结论因此被实机确认：
  组件链入后 AppleBaseband 家族与 PDP 管理器真的发布了。
- **S4 失败点被硬件钉死**（console.log:523）：

  ```
  K60MODEM qrtr: glink poll rc=-5 at 2 rx avail=488 head=560 tail=72 tx head=32 tx tail=32 cmd=0x5 p1=0x1 p2=0x1 w2=0x80 w3=0 w4=0x10005 w5=0x1 w6=0x80 w7=0x1
  ```

  `cmd=0x5` 是 GLINK INTENT，`p1=0x1` 是 rcid，`p2=0x1` 是 pair 数；第一对是 **size=0x80、id=0**，
  `w4/w5=0x10005/0x1` 是下一条消息的头（同样是 cmd 5、rcid 1、1 对），`w6/w7=0x80/0x1` 是第二对。
  也就是说 modem 从 **id 0** 开始广告 128 字节接收缓冲，而不是从 1 开始。
  `drivers/PongPower/QcomGlink.c:403` 的 `if (!size || !id) return QcomGlinkCorrupt;` 把合法的 id 0 判成损坏，
  于是第三次 poll 就断了链路——这才是 S4 过不去的唯一原因（其余三个 Corrupt 出口都需要计数越界、同 id 忙碌或 48 槽用满，
  通道刚打开不可能成立）。
- 参照实现同样接受 0：Linux `qcom_glink_handle_intent()` 对每对做 `idr_alloc(&riids, intent, intent->id, intent->id + 1, ...)`，
  0 是合法起点；`references/phk110-port/drivers/modem/hakios.mpss.c:2882-2897` 只把 words[0]/words[1] 存进 `their_intents`，
  不做零值校验。修复见 §3.23。

### 3.23 k36：接受 GLINK INTENT 的 id 0（离线，未上机）

§3.22 的失败行说明 modem 从 **id 0** 开始编号接收缓冲。这不是设备异常：Linux 的
`qcom_glink_handle_intent()` 对每一对都做 `idr_alloc(&riids, intent, intent->id, intent->id + 1, ...)`，
0 是合法起点；`references/phk110-port/drivers/modem/hakios.mpss.c:2882-2897` 也只把 words[0]/words[1] 存进
`their_intents`，不做零值校验。真正的协议错误是 **size 为 0**（一个没有字节的缓冲），id 为 0 不是。

`drivers/PongPower/QcomGlink.c` 属充电线（`docs/engineering/TREE-OWNERS.toml:70`），本线不改它；内核编译的是
0622 里的副本，所以修法落在生成器里的一行 delta：

- `scripts/update-modem-qrtr-patch.py` 新增 `DELTA` 常量，键是源文件路径，值是一条 (old, new)；
  `body()` 在改名之后应用它，并要求 old 在源文件里**恰好出现一次**——上游若改了这行，生成器会直接报错，
  不会静默丢掉修正；
- 改的是 `            if (!size || !id) return QcomGlinkCorrupt;` →
  `            if (!size) return QcomGlinkCorrupt;  /* id 0 is a legal buffer number */`；
- `scripts/tests/test-k60-modem-image.py` 不再自己复述 include 改名与 `k60m_glink_` 前缀，而是加载生成器并
  用 `body()` 的输出与 0622 里的副本比较，因此三处 delta（include 名、符号前缀、id 0）只有一个来源；
- 0622 重新生成后 98,655 B / 5 files；`test-k60-modem-image.py` 仍输出
  `TESTS OK 30 segments … table+patch agree`，`test-k60-ipa-patch.py` 仍 `K60 IPA PATCH PASS`。

行为验证（新增宿主测试 `scripts/tests/test-k60-glink-intent.py`）：它把生成器产出的 `qcom_glink.c` / `qcom_glink.h`
写到临时目录，用 gcc 编进一个小 harness，然后喂两段字节流——

- `id0`：VERSION、OPEN(`IPCRTR`)、INTENT(size 0x80, id 0)、INTENT(size 0x80, id 1)。期望不报损坏并把第一对存成 id 0，
  实测 `poll=4 broken=0`、`remote id=0 size=128 busy=0`；
- `size0`：INTENT(size 0, id 0)。期望仍然 `QcomGlinkCorrupt`，实测 `poll=-5 broken=1`——修复没有把真正的错误一起吞掉。

输出：`K60 GLINK INTENT PASS id0 accepted, size0 rejected`。修复提交 `1a4055b3`。

镜像状态（2026-11-19 10:32，**已打包、未上机**）：

| 项 | 值 |
|---|---|
| kernel | `E:/k60-work/artifacts/modem-20261117k36/kernel.macho`，105,734,144 B，`b7d52a68bc45bc3a08c10b0c297cbeeeca001886971e8ec0224a5f661e8222eb`（`COACHZ` 40 条） |
| boot image | `E:/k60-work/artifacts/modem-20261117k36/boot-modem-b-full.img`，201,895,936 B，`6f015eb672b9f759d398464b6d7b444ecb7e8eeb3bfb18978c8cc1353940e3e7` |
| payload | `2dad8fd3d48a8e07affec36cc252d4dbcc89ac06fcfdddcfe766ae8355b79267`；payload.json `ff35bfcb…`；payload kernel `35a77d07c77790fc5f0781660f3a6e23a284e2871866b8d7178701506d2c6b1d`；ADT `6beda904aecf05b2b695e46901ba17e117cd59c8ec9ff78dc057e7f5f1345e13` |
| FD / args / 布局 | `40c29d51…`；末尾 `k60_autoreset=300 applog=1 pong_modem=2 pong_ipa=0`；560,384 / 201,326,592 / 3,145,840 / 4,024 |
| 校验 | `verify-k36-b.py` rc0 `verify-boot-image: OK`；`test-bootimg-layout.py` 布局全部正确 |

判据不变：S3 必须保持 PASS；S4 要求 `K60MODEM qrtr: dms revision …` 出现（id 0 的 INTENT 不再中断 poll 是本飞的**唯一**
变量，若仍失败，损坏行里的下一对才是新线索）；S6 仍要 `bridge enabled` 与 N>0 的发布行；S5 只有在 servloc 应答后才可能通过。

## 4. 预先写死的判据（S1–S6 / F1–F7）

判读是机械的：`python3 scripts/check-modem-flight-log.py --phase {p1,c,b} <console.log>`
按本节判据输出 PASS/FAIL（B 分 S3/S4/S5/S6 四组，任一组 FAIL 即退出码非 0），自身回归是
`scripts/tests/test-check-modem-flight-log.py`（`K60 FLIGHT LOG PASS p1 c b negative-cases`）。
拿它复判已保存的 k18 C 日志（`E:/k60-work/evidence/usblog-20261118-234555/console.log`）仍是
`C: PASS`；同一份日志按 `--phase p1` 判则 FAIL（没有 power 行且出现 init/mem），说明相位不可互换。

### 4.1 成功判据（全部满足才算 S）

- **S1**（静态门禁 + UEFI 日志，不是 CDC console 行）：`python3 scripts/check-modem-metadata.py` 必须 PASS，
  内嵌数组 5,884 B、crc32 `0xac600b5d`、sha256 `78d5f2f45aefeab7…`。
  那条 `modem-image: metadata 5884 bytes crc32 0x… at 0xb7ff0000` 是 UEFI `Print`，只出现在 UEFI 日志里
  （`Tools → Advanced Logger` 的 QR 抓取）；USB CDC console 由 XNU 建立，**不会有这一行**，
  不得因为 CDC console 缺它而判 F1。若这次飞行顺手抓了 UEFI 日志，CRC 必须是 `0xac600b5d`。
  实机上的等价证明是 `K60MODEM init_image ok metadata=0xb7ff0000 bytes=5884`（TZ 接受了这一页）。
  历史：`0x5ce97b8d` / `09180d7c…` 属于 CRLF 污染 blob，已被干净 blob 取代（`06-MODEM-PAS.md:60`）。
- **S2**：27 个 `.lzma` 全部成功（无 `did not decompress` / `decoded ..., table says ...` 失败行）；三条 D3 行一条不少：
  `modem-image: chosen dtb at `、`modem-image: window 0x8bc00000..0x9ee00000`、`modem-image: abl staging ends at `；
  carrier 汇总行存在；`K60ModemImage` 照常发布；XNU 起得来。
- **P1**（power-only，`pong_modem=4`）：恰好一行 `K60MODEM power ok cx=... mss=... xo=...`、
  一行 `K60MODEM power prepared` 和 `K60MODEM diagnostic stop after power: init_image not sent`；
  不得出现 `K60MODEM init_image` / `mem_setup` / `auth_reset` 行，也不得出现 `K60MODEM power failed`；
  `xo=` 的投票值必须是字面 3（§3.11），不是 cmd-db 的 level 索引，出现 `K60MODEM power failed: xo.lvl` 即判失败。
   实机结果见 §3.12（2026-11-19 04:23，P1 PASS，`xo=0x300b0/3`）。
- **S3**：B 要求以下五行都出现且 rc=0；C 只要求 `init_image`、`mem_setup` 和诊断停机行
  （C 不执行 power/transport）：
  `K60MODEM power ok cx=`（含 mss/xo）
  `K60MODEM init_image ok metadata=0xb7ff0000 bytes=5884`
  `K60MODEM transport ok smp2p=`
  `K60MODEM mem_setup ok base=0x8bc00000 span=0x13200000`
  `K60MODEM auth_reset ok`，且此前出现 `K60MODEM scm cmd=0x5 ok calls=N`（k29 起会打印；`rc=-3` + `calls=` 达到上限仍是失败）
   实机结果见 §3.15（2026-11-19 06:23，k29 B 的 S3 PASS，`calls=182`）。
- **S4**：auth 后 10 秒内出现 `K60MODEM qrtr: glink desc=` 与 `K60MODEM qrtr: dms revision `（后随非空版本串），且没有
  `K60MODEM qrtr: modem not ready`、`K60MODEM qrtr: dms revision missing`。
  实机结果见 §3.15：`glink desc` 出现，但随后 `channel up` → `channel down` → `glink poll rc=-5 at 2`，
  没有 dms revision，按 S4 判失败（F8）。
  k30 起，失败行会带 `rx avail=… head=… tail=… cmd=… p1=… p2=…`（§3.16），用于区分 VERSION/OPEN/INTENT/DATA 分支。
  k30 B（07:26）实测 S3 PASS、S4 FAIL，但该行取样在 `head`，`cmd/p1/p2` 全 0，不能用于分支判断；
  k31 起改从 `tail` 取样（§3.17），该行的 `cmd/p1/p2` 才代表环头最旧消息；
  k31 B（07:49）实测 S3 PASS、S4 FAIL，该行是 `cmd=0x5 p1=0x1 p2=0x1`，即一条 GLINK INTENT；
  k33 起该行还带 `tx head/tx tail` 与 `w2..w7`（§3.19），`w2/w3` 就是这条 INTENT 的 pair size/id；
  adopt 时另有一行 `glink adopt (probe) rx head=… tail=… avail=… tx head=… tail=… cmd=… w2..w7`，
  head 非 0 时紧跟 `glink adopt dropped N stale bytes (head=…)`（环里是上一会话残料，已被丢弃）。
  §3.18 的 k32 adopt 行只在 transport 路径，B 形态不会打印，不能作为判据。
- **S5**：`K60MODEM plan rows=30` 存在，且 `K60MODEM qrtr: verdict ok services=` 的
  `services` 大于 0、`node0` 不小于 1；不能是 `verdict no reply`。`--phase b` 的 S5 组按这条判，
  `verdict` 字段允许是两个词（`no reply`）。
- **S6**：`K60MODEM baseband: bridge enabled` 存在，且 `COACHZ baseband: N of M services published`
  （组件原文格式串是 `COACHZ baseband: %d of %u services published (...)`）的 N 大于 0；只有 `bridge disabled`
  或 N=0 算失败。开关行有两个来源：探测开头打印的静态状态，以及 `cfb2917f` 起轮询中 `coachz_baseband_configure()`
  重试成功后的 `K60MODEM baseband: bridge enabled (poll N)`——组件在 IOResources 未就绪时会推迟发布，
  只判开头那一行会把“晚发布”误判成失败。
  **但 S6 目前判不了**：§3.21 已查明本内核只链入 `coachz_baseband_*` 的 weak 兜底，`libQcomBaseband.a`
  从来没被 force_load 进 kernel，因此任何镜像都不会打印 `COACHZ baseband: …`，`bridge enabled`
  也永远不会出现。判读器因此把“有 `bridge disabled` 且全文没有任何 COACHZ 发布行”判为 **N/A**
  （不算失败、不影响退出码），只有“组件在场却发布 0 个服务”或“有发布行却没有 bridge enabled”
  才算失败。组件链入之后 N/A 会自动消失，判据恢复为上面的两条。

### 4.2 失败判据（一条失败即停，一次开机只归一类，不重试）

- **F1**：S1 缺失，或 XNU 没起来 ⇒ UEFI 回归，飞回回滚镜像；不解释 PAS。
- **F2**：`K60MODEM init_image failed ... rc=-22` ⇒ metadata 内容/地址分支；下一飞换页或重算 blob。
- **F3**：`K60MODEM init_image failed ... rc=-13` ⇒ TZ 不放行；下一飞换 PA 或查 TZ 策略。
- **F4a**：`K60MODEM power failed:` 出现在 init_image 之前 ⇒ AOP QMP/RPMh 路径；记录冒号后的原因，下一飞只修 power，不发送 PAS。
- **F4b**：`K60MODEM transport failed rc!=0` 出现在 init_image 之后 ⇒ SMEM item 428/478/479 或 modem 分区；下一飞只修 transport。
- **F4**：`K60MODEM auth_reset failed rc!=0` ⇒ power 已投票但 PAS 仍失败。`rc=-3` 表示 resume 预算耗尽（先看 `calls=`：100 是旧上限，100000 是 Pong 上限）；`rc=-13` 才是 TZ 拒绝。下一飞按 `calls=` 判断是加预算还是查 TZ，不是复查电源。
- **F5**：auth_reset ok 但 S4 超时（出现 `modem not ready` 或没有 `glink desc`）⇒ 固件/SMP2P；下一飞补写 host item 428。
- **F6**：S4 过但 S5 不是 `verdict ok` ⇒ GLINK/QRTR；转 QRTR 调查，不再改 PAS。
- **F7**：S4/S5 通过但 S6 失败 ⇒ QcomBaseband 控制桥/ADT；下一飞只查 `chosen/coachz-baseband`、AppleBaseband 类注册和 `coachz_baseband_configure()`。
- **F8**：S3 通过、`glink desc` 出现，但随后 `K60MODEM qrtr: channel down` 与 `K60MODEM qrtr: glink poll rc=-5`
  （`QcomGlinkCorrupt`）⇒ GLINK 消息解析；下一飞只加 RX 快照（cmd/param1/param2），不动 PAS/电源。
  2026-11-19 06:23 的 k29 B 属于这一类（§3.15）。

## 5. 飞行顺序

1. **C（诊断）**：`pong_modem=3`，只到 `mem_setup`，不发 `auth_reset`；断言 `init_image`/`mem_setup` 两行、
   停在 `K60MODEM diagnostic stop after mem_setup: auth_reset not sent`。
   **已飞并 PASS**：k18 `E:/k60-work/artifacts/modem-20261117k18/boot-modem-c-diagnostic-m2.img`
   （`1ae178bb…`，§3.6，2026-11-18 23:45）。此条保留为判据定义，不再重复飞。
2. **P1（power-only，单变量，先飞）**：`pong_modem=4`，用 k22 的
   `E:/k60-work/artifacts/modem-20261117k22/boot-modem-rails-only.img`（`393d7f2f…`，§3.11），按 P1 判；
   **已飞并 PASS**：2026-11-19 04:23，证据 `E:/k60-work/evidence/usblog-20261119-042322`（§3.12），
   `xo=0x300b0/3`、三条 rail 全成功、停在 `diagnostic stop after power`。
   用户授权（2026-11-19 04:16）：代码准备充分且无其他 agent 飞行时可自主上机。
3. **B（完整，后飞）**：P1 全绿后，`pong_modem=2`，用 k29 的
   `E:/k60-work/artifacts/modem-20261117k29/boot-modem-b-full.img`（`92359e3d…`，§3.14），按 §4 的 S3/S4 判。
   k28 B（`d86a73ac…`）已飞：power/init/transport/mem 全部通过，auth_reset 因 100 次 resume 上限
   报 `rc=-3 x0=0x1 x1=0x1`（§3.14）；k29 只改这一个上限与计数打印。UEFI/DTB/carrier 与 C/P1 相同。
   C/P1 已用 k22 内核证明，B 不得在同一个镜像里再顺手改第二件事。
   **k29 B 已飞（2026-11-19 06:23）**：S3 PASS（`auth_reset ok`，`calls=182`），S4 FAIL
   （`channel up` → `channel down` → `glink poll rc=-5 at 2`，无 dms revision，§3.15）。
   **k30 B 已飞（2026-11-19 07:26）**：S3 PASS（`calls=179`、`auth_reset ok`），S4 FAIL，失败行
   `glink poll rc=-5 at 2 rx avail=576 head=648 tail=72 cmd=0 p1=0 p2=0`；快照读的是 `head`，因此全 0（§3.16）。
   **k31 B 已飞（2026-11-19 07:49）**：S3 PASS（`calls=181`、`auth_reset ok`），S4 FAIL，失败行
   `glink poll rc=-5 at 2 rx avail=576 head=648 tail=72 cmd=0x5 p1=0x1 p2=0x1`——tail 取样生效，
   坏消息是一条带单个 pair 的 GLINK INTENT（§3.17）。
   k32（`5571c7f2…`）**作废**：它的 adopt 诊断只挂在 transport 路径，B 形态总在 `mem_setup` 打印
   `transport remote glink fifo absent, defer IPCRTR` 并改走探针路径 adopt，那一行永远不会出现（§3.18 更正）。
    k35（`2f989b28…`）已于 2026-11-19 10:03 飞过：S3 PASS（calls=181）、S6 首次 PASS、S4 仍 FAIL，失败行把
    第一对 pair 钉成 `size=0x80 id=0`（§3.22），adopt 行的 8 字节旧残料被丢弃逻辑清掉（§3.19）。
    下一飞用 k36 的 `E:/k60-work/artifacts/modem-20261117k36/boot-modem-b-full.img`（`6f015eb6…`，§3.23）：
    它只把 0622 里那份 GLINK 副本的 `if (!size || !id)` 收窄成 `if (!size)`，`drivers/PongPower/QcomGlink.c` 本体不动。
    S3 必须保持，S4 仍按 dms revision 判，S5/S6 由同一份日志判读。
   采集秒数由 300 改为 **420**，用于在 `k60_autoreset=300` 复位后多观察 120 s（USB 断开即 PSCI `SYSTEM_RESET` 生效）。

## 6. 本飞不验证（明确写死，不算“已知缺陷”）

- 框架 `payload.py`/CLI 的通用性；本飞只使用已在 `feat/modem-carrier`（`92bb60f`）上实测过的 carrier 钩子（27 streams / 109,060,761 B declared）。
- 数据业务：QMI 数据面（WDS/IMS/RFS/NV/VoLTE/拨号）；本次只做 QRTR 枚举、servloc 应答和 DMS GetRevision（S4），数据业务仍是 PAS 之后的工作。
- TZ 的完整策略、性能与功耗；本飞只观察 `init/auth` 的 rc。
- 27 个流的压缩内容之外的第 28 个文件（metadata 已内嵌在 UEFI，不进 payload）。

## 7. 回滚

上一张已知可启动镜像：`E:/k60-work/artifacts/gpu-iosurf-20261116/boot.img`，
sha256 `4E8DA23012D88D5C3C01992B0286F1D0BBBA7D83980E0EDE3AAEDB3D95BBEA96`。
若 F1 或任何 UEFI 回归，飞回这张；不要在失败的开机里重试。

## 8. 历史状态（k14 代，2026-11-18 09:25；当前状态见 §3.6–§3.10）

- QcomBaseband 控制桥已接入：`board.toml` 选择 `component:QcomBaseband`，`K60ModemLink.c` 在 QRTR 上转发 NEW_SERVER/DEL_SERVER/DATA 到 `coachz_baseband_*`，probe 打开 GLINK 后调用 `coachz_baseband_configure()`；ADT 增加 `chosen/coachz-baseband=1` 与 `product/baseband-chipset=mav16`。
- 共享 `kernel.macho`：`E:/k60-work/artifacts/modem-20261117k14/kernel.macho`，105,562,112 B / `619acc64a33fc4b62ba167b5034b81951ad09d971f6671feff7b10091d3272eb`；源码提交 k60-cellular `5d59eab7`（基于 d828f3ab、71e7c43、4764d170、b9de56b9、e4b5cfd5、50aa1261 与 e7bdbf16）（含 IPA M0 骨架 + M1 固件暂存/PAS 路径 + payload FAT 调用点 + IP0 时钟 + IPA 资源表初始化 + GSI EE0 预检 + M2 运行时 glue（1 MiB ring、ArmSmmu4K、SMEM item 497 在 TCSR mutex 下分配、GSI command-DMA，pong_ipa=2 门控）），基于携带 QcomBaseband 设备 patch 的 `8af93c9a`、`352d7f30` / `3d4a4be4`。
- 四张 payload 均为 201,326,592 B：C（`pong_modem=3`）`a3ab1f52e2734e0017889b8f4ee4bd4c7636f23f3b03eb9bb235e68090db524b`，C0（`pong_modem=3` 且无 carrier）`df159b8f7f2ab91fb1d2a3b466e79f296ec371ffec3be32682bb28727ad72500`，B（`pong_modem=2`）`314714d5517fcc67d732a267956daf7faf397f526073fff4a9f380f266cda82f`，IPA-only（`pong_modem=0`）`f90fa367fa88e35dd7808585908bbd611a652c1867aa7939f806303f6ec1d307`。
- k14 代沿用 j2 的 UEFI FD 修正；j2 代的关键变化是 UEFI FD：旧 FD `38c1293b...` 的 mtime 01:28:38 早于 `c1ea878`（01:35:06，新增 `CarrierLoadMetadata`），不含 metadata page；新 FD `e007de8a2cbed4ec22d8502a89ff3eef79337bc712ccb6c2414c4b175b5d2589` mtime 02:17:24，已把 `CarrierLoadMetadata` 编进 ImageCarrierLib。k14 代沿用 e007de8a；C 于 01:49 使用旧 FD，因此连 S1 的 metadata 行都不可能出现，不能据此判断 kernel 或 QcomBaseband 桥。
- 四张 boot.img 均 201,895,936 B：C = `E:/k60-work/artifacts/modem-20261117k14/boot-modem-c-diagnostic.img` / `fb002a47abc209385f09d180ebdcfa95895288c602f24ca762b19a4226763562`；C0 = `E:/k60-work/artifacts/modem-20261117k14/boot-modem-c-nocarrier.img` / `7ca3e1197e95bfb1b22202bad80140a107f9f594b91156021447713b85b4f7f8`；B = `E:/k60-work/artifacts/modem-20261117k14/boot-modem-b-full.img` / `e6c181dd67ca7f93aa7e06f0890f7fbc17d80b8c992894b5026068a88394baca`；IPA-only = `E:/k60-work/artifacts/modem-20261117k14/boot-modem-ipa-only.img` / `3bbed14172a675a4288770bf383065de3229065b26fe6a3f14cdc3783a2d786f`。boot 头 kernel_size=559,476、ramdisk=201,326,592、payload_offset=565,248，公式与 §3.2 一致；`test-bootimg-layout.py` 四张均 OK。
- 四张 boot.img 的 `kernel_args` 分别以 `pong_modem=3 pong_ipa=1`（C/C0）、`pong_modem=2 pong_ipa=1`（B）与 `pong_modem=0 pong_ipa=1`（IPA-only）恰一次结尾；C 只到 `mem_setup` 后诊断停机，B 走完整 power/transport/auth/QRTR，IPA-only 在 modem probe 之前即进入 IPA probe。
- 2026-11-17 review 的 B 阻塞项已修复并进入 `6a02c710`：TCS4 等待前写入 `1u<<16` 触发位；`k60_modem_wait_word` 每次迭代 `delay(10)`，QMP 握手/load_state 等待 1 s，TCS 等待 10 ms；QRTR probe 先只要求 AP-owned 478/479，再在 10 s 内轮询 modem-owned 480/435；只有 480 与 435 都出现才退出轮询，stale FIFO 返回 -1。
- 2026-11-18 modem-review 的 P0/P1/P2 修复已进入 `3d4a4be4`：RSC IRQ 状态/清除改用 `K60_MODEM_TCS_BASE + 0xd04/0xd08`；item 435 的 stale/Ready 检查前移到 copy/init_image/rails 之前（`k60_modem_transport_stale`，Ready 返回 -16）；QMP mailbox 边界补全并给 AOP QMP open/load_state 有界重试；GLINK descriptor 只清 AP-owned `desc[1]/desc[2]`；`k60_modem_wr32` 后加 `dsb oshst`；QcomBaseband provider NULL 时不再 latch `bb_published`，K60 每秒重试 `coachz_baseband_configure()`。
- 2026-11-18 复评后的收口在 `352d7f30`：QMP open/load_state 重试由 600 次改为 10 次（约 2 分钟上界），并删除 `k60_modem_glink_start()` 中恒假的 `desc[1]/desc[2] != 0` 门禁；QcomBaseband provider 修复改为 k60-cellular 的 `patches/qcombaseband/0001-coachz-defer-publication.patch`：`scripts/build-qcom-baseband.py` 对上游 `dd0199cf` 的 `baseband/coachz_baseband.cpp` 暂存并 apply，不再依赖私有分支或工作树脏文件。
- 离线门禁：`test-k60-modem-image.py`（30 segments）、`run-host-tests.sh`（9/5/13/16）、`test-bootimg-layout.py`（四张均 kernel=559476 ramdisk=201326592 DTB=4024）、`check-modem-metadata.py`（14 PASS）、`check-docs.py`、`check-line-endings.py`、`check-secrets.py` 均通过；`check-build-applied.py` 的 P-166 仍报告仓库与输入的历史 audio patch 漂移。
- 2026-11-18 09:25 设备状态为 `none`（adb/fastboot 都没有）；未 boot、未 flash。k14 的 C/C0/IPA-only/B 仍在等待设备恢复 fastboot 后按 C → C0（仅当 C 无 console）→ IPA-only → B 顺序验证。
- **本候选不是飞行许可**：payload 与 bootimg 均使用 `--skip-gates`，因为本机合规注册表当前为红（P-165/P-166 等历史 sync/build 输入漂移）；§3 的 1/2/4/5 项还必须在飞行前逐条实跑并记录真实 rc，且必须由 Lead 授权后按 §5 的 C → C0 → IPA-only → B 顺序飞行。禁止自行上机。
