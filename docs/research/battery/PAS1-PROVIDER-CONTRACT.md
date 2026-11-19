# PAS1 provider 五阶段调用契约

> 2026-11-15；本分支已实现可注入的五阶段编排和持久 owner wrapper，宿主覆盖 77 个场景。真实 carrier、SCM/PAS、资源及硬件互斥后端未安装；未证明 PAS1、GLINK、电池、充电或音频可用。0619 仅留分支，不并 main。

源码以 [K60AdspOwnerStages.h](../../../drivers/PongPower/K60AdspOwnerStages.h)、[五阶段实现](../../../drivers/PongPower/K60AdspOwnerStages.c)、[持久 wrapper](../../../drivers/PongPower/K60AdspOwner.c) 和 [runtime](../../../drivers/PongPower/K60HandoffRuntime.cpp) 为准。调用点见 [INTEGRATION-ORDER.md](INTEGRATION-ORDER.md)，台账见 [HANDOFF-PUBLISH.md](HANDOFF-PUBLISH.md)。

## 入口、参数与返回

~~~c
int k60_owner_claim(K60OwnerSession *session,
    const K60BatteryConfig *config, const K60OwnerOps *ops, void *context);
int k60_owner_prepare_pas1(K60OwnerSession *session);
int k60_owner_auth_and_start(K60OwnerSession *session);
int k60_owner_build_handoff(K60OwnerSession *session,
    const K60HandoffPlan *plan);
int k60_owner_publish(K60OwnerSession *session,
    const K60OwnerPublishOps *ops, void *context);
void k60_owner_abort(K60OwnerSession *session);

typedef int (*k60_owner_image_reader)(void *context, K60OwnerImage *image);
int k60_adsp_owner_install(const K60OwnerOps *ops, void *context);
int k60_adsp_owner_acquire(const K60BatteryConfig *config,
    K60AdspOwnerLease *lease);
int k60_adsp_owner_revalidate(const K60AdspOwnerLease *lease);
void k60_adsp_owner_abort(const K60AdspOwnerLease *lease);
int k60_adsp_owner_publish(const K60AdspOwnerLease *lease,
    const K60OwnerPublishOps *ops, void *context);
~~~

Session 一次清零，之后不复制、不重置 live 状态；只有 API 可改动它。config/ops 在 claim 中复制，context、reader 缓冲、metadata 和排他 cookie 必须具有持久生命周期并满足不重叠约束。生产 wrapper 使用静态 session，不依赖 runtime 的栈上 lease。API 以非阻塞 CAS 串行化；重入/并发调用拒绝，忙时 abort 不介入。软件 gate 不等于 TCSR，也不代替真实平台排他所有权。

| 阶段 | 执行条件和行为 | 返回及后置条件 | 宿主测试 |
|---|---|---|---|
| 1 k60_owner_claim | Empty；核对本板配置和完整 ops/version/sizeof，available 必须为 1；reader pin 固件并完成真实 MDT 解析，再取得非零当前启动 epoch/cookie、资源和 stopped/live 证明，之后才 map SMEM、短暂探测 TCSR。 | 成功 0，Claimed；不分配 FIFO，不返回 lease。缺依赖/错误几何/忙 mutex 为 -1000。失败取得的锁不会多解锁；映射基址须 8 字节对齐、大小精确。 | [claim](../../../scripts/tests/test-k60-owner-claim.c)：17 场景 |
| 2 k60_owner_prepare_pas1 | Claimed 且 live/stopped；在短 TCSR 内发现 host0/ADSP2 partition，对精确尺寸的既有 429/478/479/480 清零后复用，缺失项按 340/32/16384/16384 分配并初始化 SMP2P master-kernel 输出项 429；尺寸不符则拒绝；不创建远端 443。 | 成功 0，Prepared；只增加真实 FreshHostFifos 依据。失败 -1000。部分 allocator 改动不回滚、不当作可重试 fresh 状态。 | [prepare](../../../scripts/tests/test-k60-owner-prepare.c)：12 场景 |
| 3 k60_owner_auth_and_start | Prepared、排他且 PAS stopped；一次 INIT_IMAGE(header+hash metadata) → 可重定位时 MEM_SETUP(物理 region/span) → 每段 COPY/BSS/CACHE → AUTH_AND_RESET。reader bytes 必须一直被 pin。 | 成功 0，Started，才设置 public Authenticated bit0；仍无 lease。失败 -1000，无有效 lease；AUTH 已尝试则 shutdown 后独立确认 stopped，不能确认时 Poisoned 并保留资源。 | [auth](../../../scripts/tests/test-k60-owner-auth.c)：12 场景 |
| 4 k60_owner_build_handoff | Started 且 public facts 精确 15；plan.required 精确 15、epoch 匹配。ready callback 后短锁发现 partition/真实 443/descriptor word1-2/精确 items，解锁重验 live；最终短锁只 build_existing+self-parse，再解锁核对 offsets/epoch/restart。 | 成功 0，Built，才产生 native lease 并设置内部 build/self-parse bit1。required=14 返回 -47；缺 partition -45，不写 /chosen；其余见下表。 | [build](../../../scripts/tests/test-k60-owner-build.c)：15 场景 |
| 5 k60_owner_publish | Built；/chosen registry root 就绪、无已有属性、owner live；再次 ready/restart、自解析同一 blob/epoch，再调用原子 no-clobber commit。root 不是已挂载 rootfs。 | 成功 0，Published，当前启动 epoch 的 104 字节记录已提交；没有成功后的 release 路径。已有属性 -41，root 不就绪 -43；commit 失败 -48。 | [publish](../../../scripts/tests/test-k60-owner-publish.c)：22 场景 |

阶段诊断格式为 K60ADSP owner stage=%d rc=%d。日志及 report observer 在 TCSR 释放后执行；report 不得重新进入硬件事务。忙时 API gate 的拒绝不进入阶段主体。无效/陈旧阶段入口拒绝而不拆除已有 Built/Published 状态。

## 注入后端与 Lead-owned carrier

K60OwnerOps version=1，bytes=sizeof(K60OwnerOps)。除 available/stopped/live 必须精确返回 1 表示已证明的事实外，返回 int 的回调以 0 成功、非零失败；锁忙不可冒充成功。失败的 acquisition callback 必须自行事务性清理，不得把部分资源隐藏在失败返回中。

| 注入组 | 接口与义务 |
|---|---|
| 准备状态 | available(context, config) 无副作用，覆盖 SCM、投票、reset/exclusion 及 carrier 可用性；不是“DSP 正在运行”的别名。未就绪必须先于任何 SMEM/TCSR map/访问返回。 |
| 固件 | image_reader(context, image) 由 Lead 提供；成功须给非空 handle、MDT、可写且不别名的 metadata/capacity，以及所需 piece callback/context。MDT 和全部 .bNN 稳定、不可变并 pin 至 image_close；必须覆盖实际 load，而非只覆盖 parser 调用。失败 transactional。 |
| 持续排他 | exclusive(context, config, &epoch, &cookie) 返回真实非零 cookie/当前启动 epoch；resources(context,cookie) 保留 power/XO/interconnect。live(context,cookie,epoch) 只读、非阻塞，绑定同一配置/几何/启动。禁止 reset/restart、并行 GLINK worker、掉票或 token 过期跨越解锁窗口。 |
| stopped 与映射 | stopped(context,cookie) 独立证明 PAS stopped；未知/正在运行拒绝 takeover。map_smem(context,config,&smem) 只在上述依赖和 stopped 证明后执行；返回精确 0x200000 大小、8 字节对齐映射。lock/unlock 是真实 TCSR 短锁，不是长期软件 lease。 |
| PAS/装载 | init_image(context,metadata,bytes)、mem_setup(context,base,span)、load(context,destination,bytes,copy_bytes,zero_bytes)、auth_and_reset(context)、shutdown(context)。load 必须写入规划的 ADSP 物理区域并完成 BSS 清零及 cache 同步，AUTH 之前全部完成；不能仅处理 host 缓冲就声称装载。安全后端负责 SCM 串行化、interrupted resume/busy 处理、coherent metadata 和有界事务。 |
| ready | ready(context,config,smem,&bytes,&restart) 有界等待真实 slave-kernel；每次 discovery 自己取得/释放短 TCSR，sleep 只在解锁后。要求 state&2 且 !(state&1)，保持 restart 一致；不能创建 443 或伪造 ready。本板 K60AdspPlatform 以 5000×1 ms 有界轮询实现，只在解锁后等待。 |
| registry | K60OwnerPublishOps 的 root_ready(context)、exists(context)、commit(context,blob,bytes)；commit 原子无覆盖且失败不得先写属性。runtime 先分配 OSData，commit 内 append/self-parse 后 runPropertyAction 检查/设置。 |

未自动安装旧 K60AdspPas/K60AdspBoot 的 raw SMC 路径：其一次调用不能提供完整 SCM 事务、coherence、资源或 stopped 证明，旧 AUTH-before-INIT 顺序也未复用。真实后端仍由 Lead/ADSP 接入，测试 fake 不安装到生产入口。

## Bounded image-reader implementation

[K60AdspImageReader.c/.h](../../../drivers/PongPower/K60AdspImageReader.h) now provides a K60AdspRead-compatible k60_adsp_read(part,dst,bytes), explicit contextual blob/FAT source initialization and k60_adsp_owner_image_open/close callbacks for this existing image_reader ABI. Names adsp/mdt alias adsp.mdt; canonical pieces use adsp.bNN. Exact read/size failure -5, missing source/part -6, corrupt/bounds -7 and unsupported mode/packed-size policy -8 remain reader-specific; the owner does not leak them as valid ownership. Missing linked symbols fail -6; no backend or carrier is installed automatically.

The frozen production K60A encoding uses a 12-byte LE header {K60A,u32 count,u32 reserved=0} and sequential 24-byte records {u32 name_len=9,u32 mode=0644,u64 size,u64 packed_size=size}. Canonical names include NUL; names and bodies start on 8-byte boundaries with zero padding. A single cursor gives total 23,506,184 bytes for 26 captured inputs; k60_adsp_blob_len includes all padding. No flat format, compression or second dispatch is accepted. The [generator](../../../scripts/gen-k60-adsp-blob.py) and [checker](../../../scripts/check-adsp-blob.py) exist; root verified the final production host suite with exit 0, including five reader variants with 31 scenarios each and all five independent blob assertions with negative mutations; see [production host evidence](CARRIER-BLOB-PLAN.md#4-independent-host-fixture).

Configure a persistent K60AdspOwnerReader with a validated source and disjoint writable metadata. A composite platform context must use wrappers forwarding image_open/close to its reader member; bare k60_adsp_owner_image_open/close require the K60AdspOwnerReader pointer directly. Source storage must be immutable and pin for all parser+stage3 loads, forever if owner succeeds or becomes Poisoned. Caller supplies the pin lifetime: this adapter never allocates, maps or frees image storage. Atomic open rejects a second session without erasing live pins; close checks exact image identity. Parser errors still zero the plan and leave metadata untouched under its disjointness preconditions.

Stage3 calls k60_adsp_image_segment to reborrow the exact indexed piece or bounded contained source; BSS-only segment24 returns NULL/0 and still runs the zero/load callback. Stage4 build_handoff never reads firmware under final TCSR. Legacy fixed-address k60_adsp_copy is not used for relocated owner loads. FAT mode is explicit and requires bounded pre-mapped contiguous file storage, not late Data I/O. The owner-reader linked binding may use the legacy pre-mapped FAT hook only for an absent carrier; a present malformed blob fails -7/-8 without fallback. No owner_install call exists before first acquire. The hook only reuses an already-ready reader; the later old probe is excluded by the startup claim and cannot prepare FAT for the early owner. Lead's build-strict/archive/manifest/link integration and platform backend installation remain separate; see [carrier ABI](PAS1-PROVIDER-CARRIER.md#implemented-reader-boundary).

## 公共 flags 与内部完成位

K60AdspOwnerLease 保持 uint32_t version, bytes, flags, epoch 加 void *token；version=1、bytes 使用 native sizeof。104 字节 little-endian wire record 的 epoch 是 64 位，不能直接序列化 native struct。

| mask | 固定语义 |
|---|---|
| 公共 flags bit0/bit1/bit2/bit3 | Authenticated / ResourcesHeld / GlinkExclusive / FreshHostFifos；精确合计 15，各项来自对应成功事件。bit1 始终是 ResourcesHeld。 |
| session.completed | Claim=1、Build/self-parse=2、Prepare=4、Auth=8、Publish=16；仅软件内部进度，绝不转换为公共硬件事实。 |
| epoch / token | 非零当前启动 epoch，绑定 cookie、板级配置和 items；native token 指向持久 session。revalidate 同时验证真实 backend live，不能仅凭非空地址或数字 15 授权。 |

固定板级输入为 SMEM 0x80900000/0x200000、ADSP 0x9fd00000/0x3100000、mutex 0x1f43000、IPCC 0xed18000、remote PID2、client3/signal0、478/479/480/443、protocol1；runtime 在 provider 有副作用之前拒绝 XNU RAM 重叠。没有另取旧 carveout 或合成 epoch。

## 锁、失败和终态

逻辑软件 lease 覆盖阶段 2–4 及阶段 5 的 commit；不能在阶段间释放 votes/exclusion。短 TCSR 分别保护 stopped allocation、SMEM discovery 及最终序列化。最终区间只执行 k60_handoff_build_existing()+k60_adsp_handoff_parse()，不执行 PAS/owner callback、OSData/registry 操作、sleep 或日志。builder 自身不锁，不能外层预持同一个不可重入锁调用阶段 API，也不包裹旧 aggregate k60_handoff_publish()；旧 helper 保留单独宿主测试，runtime 不再通过它发布。

提交前经 fail()/abort 处理的事务失败会清除可用 lease；无效参数/缺少 callback、忙 gate 或陈旧阶段等入口拒绝不进入清理，保留已有 Built lease/resources。AUTH 已尝试时执行 shutdown 并独立证明 stopped；只有确认安全才 unmap → image_close → resources_release → exclusive_release，各已取得资源只释放一次。shutdown/stopped 不确定时进入 Poisoned，保留排他、votes、映射和 reader 状态，拒绝重试；不能宣称硬件已停止。未尝试 AUTH 也要求 stopped 证明后才释放。

commit 与 Published 状态切换受同一非阻塞 API gate 保护；重入 abort/publish 不能在属性成功后撤销资源。Published 后 abort 是 no-op，资源/token 持续保留。新启动、DSP crash/reset 后的恢复协议未实现。

## SMC 调用约定（2026-11-20）

PAS 的 `k60_scm_call()` 是直接内联 `smc #0` 的包装器（`drivers/PongPower/K60AdspPas.c`，
同样的代码也以 `+` 行存在于 `patches/xnu/0613-k60-adsp-pas.patch`）。它必须按 SMCCC 1.x
声明寄存器：`x0..x7` 全部读写（参数进、结果与 payload 状态出，preempt 时 `x6` 还回传
session cookie），`x8..x17` 与 `memory` 进 clobber 列表。只把 `x0..x3` 当输出的旧写法
让编译器有权把活值留在 `x4..x17`，一次成功或被打断的 SMC 之后那些值可能已经变了——
症状是 PAS 之后随机位置的数据损坏，不是编译错误。

这条契约与 OS 版本无关（SMCCC 是固件 ABI），所以由
`scripts/tests/test-k60-adsp-smccc.py` 守：两份代码各有且仅有一个 `smc #0` 站点、操作数与
clobber 行齐全、旧的输入-only 形状必须消失，并用合成旧文件证明门禁会红。判据是文本级
的（host 上无法执行 `smc`），但它扫的是**两份会分别进内核和被人阅读的副本**，这正是
[P-255](../../engineering/PITFALLS.md) 记下的失败形态。

合入 ADSP 载体分支（`feat/adsp-carrier`）时这条契约要重贴一次：那边的 `a0547907` 只改了
驱动副本，`0613` 补丁里的 `k60_scm_call()` 仍是输入-only 的旧形。整侧取对面会让本门禁变红，
而更危险的做法是让门禁变绿之后再也没人看——所以合并时以本节的形状为准，两份副本都要过
`test-k60-adsp-smccc.py`；那条门禁还要求注释里同时出现 `SMCCC` 与 `x4..x17`，因为下一个人
需要读到的理由是“监视器可以改写这些寄存器”，而不是一串 clobber 名字。

## 返回与可观察结果

| 层/情况 | 结果 |
|---|---|
| 未安装 ops/image_reader 或平台不可用 | wrapper acquire 清零 lease，返回 -1000；尚未 SMEM/TCSR mapping。runtime 在前置检查通过时映射为 -42，不新增属性。 |
| 阶段 1–3 失败 | -1000；阶段 4 的 lock/partition/dirty/build/ready 分别为 -44/-45/-46/-47/-43，owner 失效 -42。阶段 4 无 property callback，不能写 /chosen。 |
| acquire 内阶段 4 失败 | acquire 保留其错误码；runtime 当前统一映射 acquire/revalidate 失败为 -42。日志 rc 取 acquire 结果，若 acquire=0 而 revalidate 失败可显示 rc=0，仍不是成功。 |
| 阶段 5 | 无效参数 -40；已有属性/原子重复 race -41；初始 lease/live 检查失效 -42；root/ready/restart 不就绪 -43；最终 blob 自解析/epoch/live 复核失败 -47（该最终 live 失效也返回 -47）；其他 commit 失败 -48；成功 0。runtime 保留这些 publish 返回码。 |
| 缺属性的一次性 consumer | consumer 在映射前返回 K60ConfigNoOwnership(-4)，不自动等待晚到属性；当前默认门控保持关闭。已有属性提前重复退出保持原值，不能证明其有效。 |

默认关闭门控仍是 PE_parse_boot_argn 成功且 unsigned 结果为 1；不是严格原始字符串匹配。裸参数/四字节截断 caveat 及 14 个 parser-stub dispatch 测试见集成顺序。未改 board 参数/白名单。

## 历史 owner 阶段检查与剩余阻塞

五个宿主测试共 77 场景（17/11/12/15/22），使用 [共享 fixture](../../../scripts/tests/test-k60-owner-fixture.h) 注入 fake carrier/PAS/资源/registry，运行真实 MDT、SMEM allocator、build-existing、consumer parser 和持久 wrapper。覆盖 required14、缺 partition、AUTH 失败/Poisoned、错 epoch/token、重入/陈旧阶段、配置栈寿命、8 字节对齐、重复属性、root 未就绪及成功后不释放。它们验证编排和失败边界，不验证硬件。

冻结生产载体 ABI 之前的历史 [run-k60-handoff-host.sh](../../../scripts/tests/run-k60-handoff-host.sh) 证据在 E:/k60-work/artifacts/adsp-owner-stages-20261115/final-host/host-tests.log。另有 49 publisher、10 builder、16 MDT、21 通知资格、27 单位转换、14 dispatch、5 个局部 patch sections fuzz0/3 canonical mirrors，以及 SDK 语法检查。该历史结果不替代冻结生产 ABI 的全套 host 证据；root 已核验当前生产 host suite exit0：owner77（17/11/12/15/22）、reader 五变体各31场景、blob 五ASSERT及各自负例，以及49publisher/10builder/16MDT/21notify/27battery/14dispatch/5sections/3mirrors全部通过。当前日志 [host-tests.log](E:/k60-work/artifacts/adsp-carrier-20261115/final/host-tests.log)，SHA256 `51bf1696ec950e112b29f92972e7e9f596c2a91180080e1c9ba79417921e22c1`；reader/stages/Boot arm64 SDK语法SHA256 `6d3b5f1cc1bfbfdca7ba3cb9172317bed19469f26b12defbfeba2afb4817055e`，runtime C++语法也通过。10项scoped检查通过（docs193/table/owner/secrets/battery/patch parse/diff/staged-diff/build片段/checker负例）；candidate与未修改HEAD的porting均为相同54项既有错误，新增0，非零门禁未豁免。不是完整 series 重放、整核链接、PAS1 认证或 GLINK 报文证明。

五阶段实现替代了“只有缺省 stub”的软件缺口；生产后端和 Lead-owned carrier 仍未安装，battery/audio/charger 的真实 PAS1/GLINK 共享阻塞未解除。verify/local_verified/device 维持 false；未执行内核/镜像构建、设备、boot 或串口操作。编号仍为 thermal0617、springboard0618、本线 handoff0619；本轮 builder 精确 required=15 的变更另有新 patch hash，不能沿用重编号时旧 hash。
