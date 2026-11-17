# 19 — 基带 PAS 上机计划（route B/C）

- 日期：2026-11-18
- 状态：**判据已冻结；C/B/C0/IPA-only 候选已重建（2026-11-18 05:36，k5 代：QcomBaseband 设备 patch + IPA M0 骨架 + M1 固件暂存/PAS 路径 + payload FAT 调用点 + IP0 时钟构建，kernel 1bee7953）；2026-11-18 01:49 的 C 首飞因旧 FD 无 metadata 未取得 console，待复飞；本文件仍不是飞行许可**
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
| kernel.macho | `E:/k60-work/artifacts/modem-20261117k5/kernel.macho` | 105,558,016 | `1bee79534cb8e2c2660774eff1a781da52baa163910c20d82f9768b32ebd4064` |
| payload.img (C, `pong_modem=3`) | `E:/k60-work/artifacts/modem-20261117k5/payload-c-diagnostic/payload.img` | 201,326,592 | `ba688b9da287b11cc4b1c0712a39b3c133310101ad2ca27f51cefdbf44697156` |
| boot.img (C, `pong_modem=3`) | `E:/k60-work/artifacts/modem-20261117k5/boot-modem-c-diagnostic.img` | 201,895,936 | `c5a2034c944e883bc71fc3d79c77e99f85dc0e72c29db10ec8929c1e23d1b12d` |
| payload.img (C0, no carrier control) | `E:/k60-work/artifacts/modem-20261117k5/payload-c-nocarrier/payload.img` | 201,326,592 | `d72fc2ec641279fce46ef4d7e4fc7b6e90f181d4370580c2f601094141046c6b` |
| boot.img (C0, no carrier control) | `E:/k60-work/artifacts/modem-20261117k5/boot-modem-c-nocarrier.img` | 201,895,936 | `aa24aa9bce21c50c3f587923fca3178908aed86334ac20e3d0578afd24c94257` |
| payload.img (B, `pong_modem=2`) | `E:/k60-work/artifacts/modem-20261117k5/payload-b-full/payload.img` | 201,326,592 | `ea5ccb9672469ae90412a82e555cfb2ef49a432f1ad9eb18ae3745b00d0b427e` |
| boot.img (B, canonical) | `E:/k60-work/artifacts/modem-20261117k5/boot-modem-b-full.img` | 201,895,936 | `939939091854f443a64a6536780bcb8b209d5ae49591b8b163c4e117876a6ba2` |
| payload.img (IPA-only, `pong_modem=0`) | `E:/k60-work/artifacts/modem-20261117k5/payload-ipa-only/payload.img` | 201,326,592 | `0c3fc986bf3ab5bf97c3c83caec4568a3ca7281cb583814915fec0e288514d75` |
| boot.img (IPA-only) | `E:/k60-work/artifacts/modem-20261117k5/boot-modem-ipa-only.img` | 201,895,936 | `cc872deb50ab6196f359a6b2c6882bc2ffb14dbdcff593a3cc9c98aaf46ebf21` |

- 构建源：k60-cellular feat/cellular 的 k5 代工作树（QcomBaseband 控制桥 + QMI servloc/DMS + IPA M0 骨架 + M1 固件暂存/PAS 路径 + payload FAT 调用点 + IP0 时钟，代码提交 `d6f1e719`，基于携带设备 patch 的 `8af93c9a`、`352d7f30` 与 `3d4a4be4` 的 P0/P1/P2 修复和 `6a02c710` 的 power/transport）；UEFI `c1ea878`；payload 由 UniXNU `feat/modem-carrier`（`92bb60f`）的 `unixnu` 生成（`--modem-carrier E:/k60-work/artifacts/modem-carrier`）。k5 沿用 j2 的 UEFI FD e007de8a；kernel 由 `scripts/build-qcom-baseband.py` 对上游 `dd0199cf` 暂存并 apply `patches/qcombaseband/0001-coachz-defer-publication.patch` 后重建（build-report 的 `compiled_sha256=9a51613d...`，`device_patch=true`）。C/B 使用同一份 kernel、UEFI、DTB 与 modem carrier，只在打包 payload 时分别追加 `--kernel-arg pong_modem=3 --kernel-arg pong_ipa=1` / `--kernel-arg pong_modem=2 --kernel-arg pong_ipa=1`；C0 使用同一份 kernel、UEFI、DTB，不带 carrier，`--kernel-arg pong_modem=3 --kernel-arg pong_ipa=1`；IPA-only 使用同一份 kernel、UEFI、DTB，不带 carrier，`--kernel-arg pong_modem=0 --kernel-arg pong_ipa=1`；每张 payload 的 `::/IPA/ipa_fws.mbn` 均为 40,376 B，payload.json 记录 `ipa_fws_sha256=30517300...`。
- boot.img 头（三张相同）：`kernel_size=559,476`，`ramdisk_size=201,326,592`；`4096 + ceil(559476/4096)*4096 + 201326592 + 4096 = 201,895,936`，与文件大小相等；`test-bootimg-layout.py` 三张均 OK。
- boot.img 内 ramdisk 切片 sha256：C = payload 的 `ba688b9d...`，C0 = payload 的 `d72fc2ec...`，B = payload 的 `ea5ccb96...`，IPA-only = payload 的 `0c3fc986...`，说明 payload 原样嵌入。
- k5 代 QRTR 在 f 的 QMI 面（AP 以 service 64 / instance 0x101 / port 0x100 应答 servloc 的 GET_DOMAIN_LIST，并从 modem 的 service 2 NEW_SERVER 端点发送 DMS GetRevision（message 0x23））之外，把 NEW_SERVER/DEL_SERVER/DATA 转给 QcomBaseband 的 `coachz_baseband_*`，并在打开 GLINK 后调用 `coachz_baseband_configure()` 发布 AppleBaseband/AppleBasebandPCIControl/AppleBasebandPCIInterface；S4 仍要求读到版本串。
- 实测 payload（C/B 相同，C0 无 carrier）：`mdir ::/EFI/UniXNU/MODEM` 恰好列出 27 个 `.lzma`（名称 b01–b13 / b15–b20 / b22–b29），`/EFI/UniXNU/Payloads/kernel.macho.adt` 的 `/chosen/memory-map["K60ModemImage"]` 是 16 个零字节；payload.json 记录 `kernel_sha256=1bee7953...` / `payload_kernel_sha256=0b886d6a...`，ADT C=`324961e8...`、B=`dc0f203c...`、C0=`dd057f27...`、IPA-only=`4d6db63f...`；每张 payload 的 `::/IPA/ipa_fws.mbn` 为 40,376 B（sha256 `30517300...`）。
- **注意：payload 与 bootimg 都使用了 `--skip-gates`**；本机 `unixnu bootimg` 的合规注册表当前为红（P-165/P-166 等历史 sync/build 输入漂移），所以这些候选不是“门禁全绿”的产物，也不是飞行许可。
- 飞行工具：`E:/k60-work/artifacts/fly-modem.ps1`（先校验 C/B 哈希，再调用 `boot-and-capture.ps1` 和 `check-modem-flight.py`）、`E:/k60-work/artifacts/modem-20261117k5/FLIGHT-README.md`、`manifest-k5.json`；未获 Lead 授权不要加 `-Execute`。

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
   `E:/k60-work/artifacts/modem-20261117k5/boot-modem-c-diagnostic.img`，只到 `mem_setup`，不发 `auth_reset`。
   用途：在不动 modem 的前提下证明 U1（metadata 行）和 S3 的 `init_image`/`mem_setup` 两行
   （C 不执行 power/transport）；预期在
   `K60MODEM diagnostic stop after mem_setup: auth_reset not sent` 停。
2. **B（完整，后飞）**：C 全绿且真候选存在后，`pong_modem=2`，用
   `E:/k60-work/artifacts/modem-20261117k5/boot-modem-b-full.img`，按 §4 的 S/F 判。
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

## 8. 当前状态（更新于 2026-11-18 05:36）

- QcomBaseband 控制桥已接入：`board.toml` 选择 `component:QcomBaseband`，`K60ModemLink.c` 在 QRTR 上转发 NEW_SERVER/DEL_SERVER/DATA 到 `coachz_baseband_*`，probe 打开 GLINK 后调用 `coachz_baseband_configure()`；ADT 增加 `chosen/coachz-baseband=1` 与 `product/baseband-chipset=mav16`。
- 共享 `kernel.macho`：`E:/k60-work/artifacts/modem-20261117k5/kernel.macho`，105,558,016 B / `1bee79534cb8e2c2660774eff1a781da52baa163910c20d82f9768b32ebd4064`；源码提交 k60-cellular `d6f1e719`（含 IPA M0 骨架 + M1 固件暂存/PAS 路径 + payload FAT 调用点 + IP0 时钟），基于携带 QcomBaseband 设备 patch 的 `8af93c9a`、`352d7f30` / `3d4a4be4`。
- 四张 payload 均为 201,326,592 B：C（`pong_modem=3`）`ba688b9da287b11cc4b1c0712a39b3c133310101ad2ca27f51cefdbf44697156`，C0（`pong_modem=3` 且无 carrier）`d72fc2ec641279fce46ef4d7e4fc7b6e90f181d4370580c2f601094141046c6b`，B（`pong_modem=2`）`ea5ccb9672469ae90412a82e555cfb2ef49a432f1ad9eb18ae3745b00d0b427e`，IPA-only（`pong_modem=0`）`0c3fc986bf3ab5bf97c3c83caec4568a3ca7281cb583814915fec0e288514d75`。
- k5 代沿用 j2 的 UEFI FD 修正；j2 代的关键变化是 UEFI FD：旧 FD `38c1293b...` 的 mtime 01:28:38 早于 `c1ea878`（01:35:06，新增 `CarrierLoadMetadata`），不含 metadata page；新 FD `e007de8a2cbed4ec22d8502a89ff3eef79337bc712ccb6c2414c4b175b5d2589` mtime 02:17:24，已把 `CarrierLoadMetadata` 编进 ImageCarrierLib。k5 代沿用 e007de8a；C 于 01:49 使用旧 FD，因此连 S1 的 metadata 行都不可能出现，不能据此判断 kernel 或 QcomBaseband 桥。
- 四张 boot.img 均 201,895,936 B：C = `E:/k60-work/artifacts/modem-20261117k5/boot-modem-c-diagnostic.img` / `c5a2034c944e883bc71fc3d79c77e99f85dc0e72c29db10ec8929c1e23d1b12d`；C0 = `E:/k60-work/artifacts/modem-20261117k5/boot-modem-c-nocarrier.img` / `aa24aa9bce21c50c3f587923fca3178908aed86334ac20e3d0578afd24c94257`；B = `E:/k60-work/artifacts/modem-20261117k5/boot-modem-b-full.img` / `939939091854f443a64a6536780bcb8b209d5ae49591b8b163c4e117876a6ba2`；IPA-only = `E:/k60-work/artifacts/modem-20261117k5/boot-modem-ipa-only.img` / `cc872deb50ab6196f359a6b2c6882bc2ffb14dbdcff593a3cc9c98aaf46ebf21`。boot 头 kernel_size=559,476、ramdisk=201,326,592、payload_offset=565,248，公式与 §3.2 一致；`test-bootimg-layout.py` 四张均 OK。
- 四张 boot.img 的 `kernel_args` 分别以 `pong_modem=3 pong_ipa=1`（C/C0）、`pong_modem=2 pong_ipa=1`（B）与 `pong_modem=0 pong_ipa=1`（IPA-only）恰一次结尾；C 只到 `mem_setup` 后诊断停机，B 走完整 power/transport/auth/QRTR，IPA-only 在 modem probe 之前即进入 IPA probe。
- 2026-11-17 review 的 B 阻塞项已修复并进入 `6a02c710`：TCS4 等待前写入 `1u<<16` 触发位；`k60_modem_wait_word` 每次迭代 `delay(10)`，QMP 握手/load_state 等待 1 s，TCS 等待 10 ms；QRTR probe 先只要求 AP-owned 478/479，再在 10 s 内轮询 modem-owned 480/435；只有 480 与 435 都出现才退出轮询，stale FIFO 返回 -1。
- 2026-11-18 modem-review 的 P0/P1/P2 修复已进入 `3d4a4be4`：RSC IRQ 状态/清除改用 `K60_MODEM_TCS_BASE + 0xd04/0xd08`；item 435 的 stale/Ready 检查前移到 copy/init_image/rails 之前（`k60_modem_transport_stale`，Ready 返回 -16）；QMP mailbox 边界补全并给 AOP QMP open/load_state 有界重试；GLINK descriptor 只清 AP-owned `desc[1]/desc[2]`；`k60_modem_wr32` 后加 `dsb oshst`；QcomBaseband provider NULL 时不再 latch `bb_published`，K60 每秒重试 `coachz_baseband_configure()`。
- 2026-11-18 复评后的收口在 `352d7f30`：QMP open/load_state 重试由 600 次改为 10 次（约 2 分钟上界），并删除 `k60_modem_glink_start()` 中恒假的 `desc[1]/desc[2] != 0` 门禁；QcomBaseband provider 修复改为 k60-cellular 的 `patches/qcombaseband/0001-coachz-defer-publication.patch`：`scripts/build-qcom-baseband.py` 对上游 `dd0199cf` 的 `baseband/coachz_baseband.cpp` 暂存并 apply，不再依赖私有分支或工作树脏文件。
- 离线门禁：`test-k60-modem-image.py`（30 segments）、`run-host-tests.sh`（9/5/13/16）、`test-bootimg-layout.py`（四张均 kernel=559476 ramdisk=201326592 DTB=4024）、`check-modem-metadata.py`（14 PASS）、`check-docs.py`、`check-line-endings.py`、`check-secrets.py` 均通过；`check-build-applied.py` 的 P-166 仍报告仓库与输入的历史 audio patch 漂移。
- 2026-11-18 05:36 设备状态为 `none`（adb/fastboot 都没有）；未 boot、未 flash。k5 的 C/C0/IPA-only/B 仍在等待设备恢复 fastboot 后按 C → C0（仅当 C 无 console）→ IPA-only → B 顺序验证。
- **本候选不是飞行许可**：payload 与 bootimg 均使用 `--skip-gates`，因为本机合规注册表当前为红（P-165/P-166 等历史 sync/build 输入漂移）；§3 的 1/2/4/5 项还必须在飞行前逐条实跑并记录真实 rc，且必须由 Lead 授权后按 §5 的 C → C0 → IPA-only → B 顺序飞行。禁止自行上机。
