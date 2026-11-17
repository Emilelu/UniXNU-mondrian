# 19 — 基带 PAS 上机计划（route B/C）

- 日期：2026-11-17
- 状态：**判据已冻结；C/B 候选已生成（2026-11-17 10:07），但本文件仍不是飞行许可**
- 范围：UEFI 把 5,884 B 的 PAS metadata 放进 DRAM；内核在完整模式下按 `power → init_image → transport → mem_setup → auth_reset` 发 SMC，并如实报告 rc。
- 本飞只声称一件事：**UEFI 能放对 metadata，内核能按顺序发 SMC 并报出 rc**。不声称基带数据业务可用。

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
| 内核顺序 | k60-cellular `ac091715` | `K60ModemBoot.c`：`power` → `init_image(0xB7FF0000)` 一次 → `transport` → `mem_setup(base,span)` → `auth_and_reset`；`pong_modem=3` 在 `mem_setup` 后停，不执行 power/transport |
| UEFI metadata 页 | uefi-mondrian `c1ea878` | `ImageCarrierLib.c` 的 `CarrierLoadMetadata()`；`K60ModemMetadata.h` 内嵌 5,884 B；写 `0xB7FF0000` 后 `WriteBackDataCacheRange` |
| metadata 门禁 | k60-cellular `fc69e861` | `scripts/check-modem-metadata.py`；14 项全部 PASS |
| 宿主顺序测试 | k60-cellular `d7890e26` | `scripts/tests/test-k60-modem-bringup.c`；`TESTS OK 9`，含顺序、次数与 3 个反例 |

## 2. 证据矩阵（上机前必须全绿）

| 改动 | 静态 | 单元 / 宿主 | 产物 |
|---|---|---|---|
| M1 metadata 工具 | `python3 -m py_compile scripts/build-modem-metadata.py` | `scripts/tests/test-build-modem-metadata.py` | 真实 `modem.mdt` → 5,884 B；sha256 `09180d7c3a4bc59bfe4718263668c49aa42945519087562aa106b2fc6f4dfab4`；crc32 `0x5ce97b8d` |
| M2/M4 双端常量与地址 | `scripts/check-modem-metadata.py` | 14 项 PASS（见 §3） | 内核 `K60_MODEM_METADATA=0xB7FF0000u` 与 UEFI `K60_MODEM_METADATA_ADDRESS=0xB7FF0000ULL` 相等；页在 `[0xA8300000,0xB8000000)` 内且 4 KiB 对齐 |
| M3 UEFI carrier | `clang -fsyntax-only -Werror`；完整 `build_uefi.py` | DXE 无宿主 harness；逻辑集中在 M1，UEFI 只做 `CopyMem` + 清缓存 + CRC | FD 精确 3,145,728 B；sha256 `38c1293b11fa7e48f9a701d4d94ec838657fca9e8d03bc975c339eb318f33c61`；源码含 `CarrierLoadMetadata` |
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

### 3.2 本次 route B/C 候选（已生成，待门禁与 Lead 授权，不是飞行许可）

| 件 | 路径 | 字节 | sha256 |
|---|---|---:|---|
| FD | `E:/hackios/uefi-mondrian/Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd` | 3,145,728 | `38c1293b11fa7e48f9a701d4d94ec838657fca9e8d03bc975c339eb318f33c61` |
| DTB | `E:/hackios/uefi-mondrian/Resources/DTBs/mondrian.dtb` | 4,024 | `2d044eaa08b7e58c0510a33da795c960085e13d6943cd4c25e0e050e0bfa33cd` |
| kernel.macho | `E:/k60-work/artifacts/modem-order-20261117c/mondrian/ipados-16.6.1-20G81/mondrian/kernel/kernel.macho` | 105,517,056 | `d76eb7d95284521014216c93d6f42cc60a8a87d2c9f7228c9833746e4bab6afe` |
| payload.img (C, `pong_modem=3`) | `E:/k60-work/artifacts/modem-20261117c/payload-c-diagnostic/payload.img` | 201,326,592 | `453cc2d543fd5dbb563da0728313537d11fb130720f481d0849fe07fc693c73b` |
| boot.img (C, `pong_modem=3`) | `E:/k60-work/artifacts/modem-20261117c/boot-modem-c-diagnostic.img` | 201,895,936 | `99e8d2276b80da35da17dbd2769480d025ba4f4969811db7f724782c58c6797b` |
| payload.img (B, `pong_modem=2`) | `E:/k60-work/artifacts/modem-20261117c/payload-b-full/payload.img` | 201,326,592 | `3ae782df7596041b528f33fddd0b786f34c2b6f27b94a70dc0d632f9bab50509` |
| boot.img (B, canonical) | `E:/k60-work/artifacts/modem-20261117c/boot-modem-power-candidate.img` | 201,895,936 | `ff7d1585ca786574e5f69069a8141a1209943e33201a523149f9746c7b557d93` |

- 构建源：k60-cellular `ac0917155f8f999613894d9199b5b71941f16837`（含 `0c5a0796` 的 power/transport 与本次 review 修复）；UEFI `c1ea878`。C/B 使用同一份 kernel、UEFI、DTB 与 modem carrier，只在打包 payload 时分别追加 `--kernel-arg pong_modem=3` / `--kernel-arg pong_modem=2`；payload.json 的 kernel_args 分别以这两个参数结尾。
- boot.img 头（两张相同）：`kernel_size=559,358`，`ramdisk_size=201,326,592`；`4096 + ceil(559358/4096)*4096 + 201326592 + 4096 = 201,895,936`，与文件大小相等；`test-bootimg-layout.py` 两张均 OK。
- boot.img 内 ramdisk 切片 sha256：C = payload 的 `453cc2d5...`，B = payload 的 `3ae782df...`，说明 payload 原样嵌入。
- 实测 payload（两张相同）：`mdir ::/EFI/UniXNU/MODEM` 恰好列出 27 个 `.lzma`（名称 b01–b13 / b15–b20 / b22–b29），`/EFI/UniXNU/Payloads/kernel.macho.adt` 的 `/chosen/memory-map["K60ModemImage"]` 是 16 个零字节；payload.json 记录 `kernel_sha256=d76eb7d9...` / `payload_kernel_sha256=266e34d0...`。
- **注意：payload 与 bootimg 都使用了 `--skip-gates`**；本机 `unixnu bootimg` 的合规注册表当前为红（P-165/P-166 等历史 sync/build 输入漂移），所以这两张候选不是“门禁全绿”的产物，也不是飞行许可。

## 4. 预先写死的判据（S1–S5 / F1–F6）

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
- **S4**：auth 后 10 秒内出现 `K60MODEM qrtr: glink desc=`，且没有
  `K60MODEM qrtr: modem not ready`。
- **S5**：`K60MODEM plan rows=30` 存在，且 `K60MODEM qrtr: verdict ok services=` 的
  `services` 大于 0、`node0` 不小于 1；不能是 `verdict no reply`。

### 4.2 失败判据（一条失败即停，一次开机只归一类，不重试）

- **F1**：S1 缺失，或 XNU 没起来 ⇒ UEFI 回归，飞回回滚镜像；不解释 PAS。
- **F2**：`K60MODEM init_image failed ... rc=-22` ⇒ metadata 内容/地址分支；下一飞换页或重算 blob。
- **F3**：`K60MODEM init_image failed ... rc=-13` ⇒ TZ 不放行；下一飞换 PA 或查 TZ 策略。
- **F4a**：`K60MODEM power failed:` 出现在 init_image 之前 ⇒ AOP QMP/RPMh 路径；记录冒号后的原因，下一飞只修 power，不发送 PAS。
- **F4b**：`K60MODEM transport failed rc!=0` 出现在 init_image 之后 ⇒ SMEM item 428/478/479 或 modem 分区；下一飞只修 transport。
- **F4**：`K60MODEM auth_reset failed rc!=0` ⇒ power 已投票但 PAS 仍失败；下一飞复查 `cx.lvl/mss.lvl` 投票与 AOP 顺序。
- **F5**：auth_reset ok 但 S4 超时（出现 `modem not ready` 或没有 `glink desc`）⇒ 固件/SMP2P；下一飞补写 host item 428。
- **F6**：S4 过但 S5 不是 `verdict ok` ⇒ GLINK/QRTR；转 QRTR 调查，不再改 PAS。

## 5. 飞行顺序

1. **C（诊断，先飞）**：`pong_modem=3`，只到 `mem_setup`，不发 `auth_reset`。
   用途：在不动 modem 的前提下证明 U1（metadata 行）和 S3 的 `init_image`/`mem_setup` 两行
   （C 不执行 power/transport）；预期在
   `K60MODEM diagnostic stop after mem_setup: auth_reset not sent` 停。
2. **B（完整，后飞）**：C 全绿且真候选存在后，`pong_modem=2`，按 §4 的 S/F 判。
   两张必须是同一份 UEFI 与 payload 构建，只改启动参数；不得在 B 上顺手改代码。

## 6. 本飞不验证（明确写死，不算“已知缺陷”）

- 框架 `payload.py`/CLI 的 carrier 钩子是否端到端可用（本飞用已提交的框架交付件 + 离线夹具）。
- 数据业务：QMI、RFS/NV、IMS、VoLTE、数据拨号；这些是 PAS 之后的工作。
- TZ 的完整策略、性能与功耗；本飞只观察 `init/auth` 的 rc。
- 27 个流的压缩内容之外的第 28 个文件（metadata 已内嵌在 UEFI，不进 payload）。

## 7. 回滚

上一张已知可启动镜像：`E:/k60-work/artifacts/gpu-iosurf-20261116/boot.img`，
sha256 `4E8DA23012D88D5C3C01992B0286F1D0BBBA7D83980E0EDE3AAEDB3D95BBEA96`。
若 F1 或任何 UEFI 回归，飞回这张；不要在失败的开机里重试。

## 8. 当前状态（更新于 2026-11-17 10:07）

- 真候选 payload 已生成：`kernel.macho` 105,517,056 B / `d76eb7d95284521014216c93d6f42cc60a8a87d2c9f7228c9833746e4bab6afe`；
  两张 payload 均为 201,326,592 B：C（`pong_modem=3`）`453cc2d543fd5dbb563da0728313537d11fb130720f481d0849fe07fc693c73b`，
  B（`pong_modem=2`）`3ae782df7596041b528f33fddd0b786f34c2b6f27b94a70dc0d632f9bab50509`；
  payload.json 记录 27 streams / 109,060,761 declared / 48,591,795 compressed / 16 B placeholder，
  `payload_kernel_sha256=266e34d073c3fa72ba68fb6fdd6d8fe36c9fceb5c6cb7f2c8c2f142a40af3971`。
- 内核构建源为 k60-cellular `ac0917155f8f999613894d9199b5b71941f16837`（含 `0c5a0796` 的 power/transport 与本次 review 修复）；
  kernel.macho 内可见 `K60MODEM power ok`、`power prepared`、`init_image ok`、`transport ok`、
  `transport prepared`、`glink: IPCRTR opened as initiator`、`mem_setup ok`、`auth_reset ok` 与
  `diagnostic stop after mem_setup` 字符串。
- review 修复已落地（2026-11-17 09:58）：RSC TCS4 的触发/IRQ 使用 `0xd00/0xd04/0xd08`，超时清理
  `cmd_enable/wait_for_cmpl/trigger`；QMP 邮箱限制在 0x400 B；SMEM/IPCC 可写映射改为非缓存；
  transport 先检查旧 SMP2P 435 并取 TCSR `0x1f43000` 互斥；IPCRTR 在 PAS 前以 initiator 打开；
  QRTR HELLO/LOOKUP 使用 AP node 1、control port 0xfffffffe 和广播/远端 node，send retry，ready 轮询 10 s；
  MEM_SETUP 使用解析出的 segment span。
- boot.img 已打包两张，均 201,895,936 B：C = `E:/k60-work/artifacts/modem-20261117c/boot-modem-c-diagnostic.img` /
  `99e8d2276b80da35da17dbd2769480d025ba4f4969811db7f724782c58c6797b`；B = `E:/k60-work/artifacts/modem-20261117c/boot-modem-power-candidate.img`
  （同 `boot-modem-b-full.img`）/ `ff7d1585ca786574e5f69069a8141a1209943e33201a523149f9746c7b557d93`。公式与头字段见 §3.2。
- 两张 boot.img 的 `kernel_args` 分别以 `pong_modem=3` / `pong_modem=2` 恰一次结尾；C 只到 `mem_setup` 后诊断停机，B 走完整 power/transport/auth/QRTR。
- 离线门禁：`test-k60-modem-image.py`（30 segments）、`run-host-tests.sh`（9/5/6/16）、
  `scripts/tests/test-bootimg-layout.py`（kernel=559358 ramdisk=201326592 DTB=4024）、
  `check-modem-metadata.py`（14 PASS）、`check-docs.py`、`check-line-endings.py`、`check-secrets.py` 均通过。
  `check-build-applied.py` 的 P-166 仍报告仓库与输入的历史 audio patch 漂移。
- **本候选不是飞行许可**：bootimg 使用了 `--skip-gates`，因为本机合规注册表当前为红
  （P-165/P-166 等历史 sync/build 输入漂移）；§3 的 1/2/4/5 项还必须在飞行前逐条实跑并记录真实 rc，
  且必须由 Lead 授权后按 §5 的 C → B 顺序飞行。禁止自行上机。
