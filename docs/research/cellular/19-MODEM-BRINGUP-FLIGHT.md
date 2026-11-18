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
| 宿主顺序测试 | k60-cellular `d7890e26` | `scripts/tests/test-k60-modem-bringup.c`；`TESTS OK 9`，含顺序、次数与 3 个反例 |

## 2. 证据矩阵（上机前必须全绿）

| 改动 | 静态 | 单元 / 宿主 | 产物 |
|---|---|---|---|
| M1 metadata 工具 | `python3 -m py_compile scripts/build-modem-metadata.py` | `scripts/tests/test-build-modem-metadata.py` | 真实 `modem.mdt` → 5,884 B；sha256 `09180d7c3a4bc59bfe4718263668c49aa42945519087562aa106b2fc6f4dfab4`；crc32 `0x5ce97b8d` |
| M2/M4 双端常量与地址 | `scripts/check-modem-metadata.py` | 14 项 PASS（见 §3） | 内核 `K60_MODEM_METADATA=0xB7FF0000u` 与 UEFI `K60_MODEM_METADATA_ADDRESS=0xB7FF0000ULL` 相等；页在 `[0xA8300000,0xB8000000)` 内且 4 KiB 对齐 |
| M3 UEFI carrier | `clang -fsyntax-only -Werror`；完整 `build_uefi.py` | DXE 无宿主 harness；逻辑集中在 M1，UEFI 只做 `CopyMem` + 清缓存 + CRC | FD 精确 3,145,728 B；sha256 `e007de8a2cbed4ec22d8502a89ff3eef79337bc712ccb6c2414c4b175b5d2589`；源码含 `CarrierLoadMetadata` |
| M5 内核顺序 | 内核编译 `-Werror` | `run-bringup-test.sh`：`TESTS OK 9` rc0；断言 `init_image` 只调一次、先于 `mem_setup`、先于 `auth_and_reset`；3 个反例失败 | `patches/xnu/0621-k60-modem-pas.patch` 与 `K60ModemBoot.c` 一致；内核二进制应含 §4 的 verdict 行 |
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
| metadata blob `E:/k60-work/artifacts/modem-metadata.bin` | 5,884 | `09180d7c3a4bc59bfe4718263668c49aa42945519087562aa106b2fc6f4dfab4` |

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

## 4. 预先写死的判据（S1–S6 / F1–F7）

### 4.1 成功判据（全部满足才算 S）

- **S1**：console 恰好一行
  `modem-image: metadata 5884 bytes crc32 0x5ce97b8d at 0xb7ff0000`，
  且 CRC 等于预计算值 `0x5ce97b8d`。
- **S2**：27 个 `.lzma` 全部成功（无 `did not decompress` / `decoded ..., table says ...` 失败行）；三条 D3 行一条不少：
  `modem-image: chosen dtb at `、`modem-image: window 0x8bc00000..0x9ee00000`、`modem-image: abl staging ends at `；
  carrier 汇总行存在；`K60ModemImage` 照常发布；XNU 起得来。
- **S3**：B 要求以下五行都出现且 rc=0；C 只要求 `init_image`、`mem_setup` 和诊断停机行
  （C 不执行 power/transport）：
  `K60MODEM power ok cx=`（含 mss/xo）
  `K60MODEM init_image ok metadata=0xb7ff0000 bytes=5884`
  `K60MODEM transport ok smp2p=`
  `K60MODEM mem_setup ok base=0x8bc00000 span=0x13200000`
  `K60MODEM auth_reset ok`
- **S4**：auth 后 10 秒内出现 `K60MODEM qrtr: glink desc=` 与 `K60MODEM qrtr: dms revision `（后随非空版本串），且没有
  `K60MODEM qrtr: modem not ready`、`K60MODEM qrtr: dms revision missing`。
- **S5**：`K60MODEM plan rows=30` 存在，且 `K60MODEM qrtr: verdict ok services=` 的
  `services` 大于 0、`node0` 不小于 1；不能是 `verdict no reply`。
- **S6**：`K60MODEM baseband: bridge enabled` 存在，且 `COACHZ baseband: N of M services published` 的 N 大于 0；bridge disabled 或 N=0 都算失败。

### 4.2 失败判据（一条失败即停，一次开机只归一类，不重试）

- **F1**：S1 缺失，或 XNU 没起来 ⇒ UEFI 回归，飞回回滚镜像；不解释 PAS。
- **F2**：`K60MODEM init_image failed ... rc=-22` ⇒ metadata 内容/地址分支；下一飞换页或重算 blob。
- **F3**：`K60MODEM init_image failed ... rc=-13` ⇒ TZ 不放行；下一飞换 PA 或查 TZ 策略。
- **F4a**：`K60MODEM power failed:` 出现在 init_image 之前 ⇒ AOP QMP/RPMh 路径；记录冒号后的原因，下一飞只修 power，不发送 PAS。
- **F4b**：`K60MODEM transport failed rc!=0` 出现在 init_image 之后 ⇒ SMEM item 428/478/479 或 modem 分区；下一飞只修 transport。
- **F4**：`K60MODEM auth_reset failed rc!=0` ⇒ power 已投票但 PAS 仍失败；下一飞复查 `cx.lvl/mss.lvl` 投票与 AOP 顺序。
- **F5**：auth_reset ok 但 S4 超时（出现 `modem not ready` 或没有 `glink desc`）⇒ 固件/SMP2P；下一飞补写 host item 428。
- **F6**：S4 过但 S5 不是 `verdict ok` ⇒ GLINK/QRTR；转 QRTR 调查，不再改 PAS。
- **F7**：S4/S5 通过但 S6 失败 ⇒ QcomBaseband 控制桥/ADT；下一飞只查 `chosen/coachz-baseband`、AppleBaseband 类注册和 `coachz_baseband_configure()`。

## 5. 飞行顺序

1. **C（诊断，先飞）**：`pong_modem=3`，用
   `E:/k60-work/artifacts/modem-20261117k14/boot-modem-c-diagnostic.img`，只到 `mem_setup`，不发 `auth_reset`。
   用途：在不动 modem 的前提下证明 U1（metadata 行）和 S3 的 `init_image`/`mem_setup` 两行
   （C 不执行 power/transport）；预期在
   `K60MODEM diagnostic stop after mem_setup: auth_reset not sent` 停。
2. **B（完整，后飞）**：C 全绿且真候选存在后，`pong_modem=2`，用
   `E:/k60-work/artifacts/modem-20261117k14/boot-modem-b-full.img`，按 §4 的 S/F 判。
   C/B 必须是同一份 kernel/UEFI/DTB/carrier，只在打包 payload 时改 `--kernel-arg`；不得在 B 上顺手改代码。

## 6. 本飞不验证（明确写死，不算“已知缺陷”）

- 框架 `payload.py`/CLI 的通用性；本飞只使用已在 `feat/modem-carrier`（`92bb60f`）上实测过的 carrier 钩子（27 streams / 109,060,761 B declared）。
- 数据业务：QMI 数据面（WDS/IMS/RFS/NV/VoLTE/拨号）；本次只做 QRTR 枚举、servloc 应答和 DMS GetRevision（S4），数据业务仍是 PAS 之后的工作。
- TZ 的完整策略、性能与功耗；本飞只观察 `init/auth` 的 rc。
- 27 个流的压缩内容之外的第 28 个文件（metadata 已内嵌在 UEFI，不进 payload）。

## 7. 回滚

上一张已知可启动镜像：`E:/k60-work/artifacts/gpu-iosurf-20261116/boot.img`，
sha256 `4E8DA23012D88D5C3C01992B0286F1D0BBBA7D83980E0EDE3AAEDB3D95BBEA96`。
若 F1 或任何 UEFI 回归，飞回这张；不要在失败的开机里重试。

## 8. 当前状态（更新于 2026-11-18 09:25）

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
