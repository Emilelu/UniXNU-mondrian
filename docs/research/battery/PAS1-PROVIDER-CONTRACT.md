# PAS1 provider 调用契约

> 2026-11-15；供 Lead/ADSP、audio、battery、charger 共同评审。当前分支没有满足本契约的真实 provider；这仍是共享阻塞项。本文登记既有 API 和未来实现必须满足的条件，不新增 provider、默认参数、内核构建或设备操作。

本文件以 [K60AdspOwner.h](../../../drivers/PongPower/K60AdspOwner.h)、[当前缺省实现](../../../drivers/PongPower/K60AdspOwner.c)、[runtime](../../../drivers/PongPower/K60HandoffRuntime.cpp) 和 [publisher](../../../drivers/PongPower/K60HandoffPublish.c) 为准。启动顺序见 [INTEGRATION-ORDER.md](INTEGRATION-ORDER.md)，调用点前置条件见 [HANDOFF-PUBLISH.md](HANDOFF-PUBLISH.md#调用点契约)。0619 仅留试验分支，最终 provider 与调用点由 Lead 集成。

## 入口与参数

这些是当前 C ABI；C++ 调用者通过头文件的 extern "C" 使用。不得把旧 PAS 诊断函数的返回值直接当作这些入口的成功结果。

~~~c
typedef struct {
    uint32_t version, bytes, flags, epoch;
    void *token;
} K60AdspOwnerLease;

#define K60_ADSP_OWNER_VERSION 1u
#define K60_ADSP_OWNER_UNAVAILABLE (-1000)

int k60_adsp_owner_acquire(const K60BatteryConfig *config,
                           K60AdspOwnerLease *lease);
int k60_adsp_owner_revalidate(const K60AdspOwnerLease *lease);
void k60_adsp_owner_abort(const K60AdspOwnerLease *lease);
int k60_adsp_handoff_publish(void);
~~~

| 函数 | 参数与调用边界 | 返回语义/责任 |
|---|---|---|
| k60_adsp_owner_acquire | config 是已解析并做过 XNU RAM 重叠拒绝的本板配置；lease 是调用方清零的可写输出。此时 root/Data 尚未挂载，runtime 尚未映射 SMEM/TCSR；不持 TCSR 或 registry property 锁。 | 只有已认证并启动 PAS1、资源持续持有、fresh FIFO 与排他 token/epoch 全部成立才可返回 0。其余情况非零，禁止制造 flags/epoch/token。缺省实现清零非空 lease 并返回 -1000。 |
| k60_adsp_owner_revalidate | lease 必须来自同一成功 acquire，token 仍被 pin；调用期间不持 TCSR 或 registry property 锁。 | 0 表示同一当前启动/配置/几何的所有权仍有效且资源未释放；任何非零均中止交接。必须只读、非阻塞，不重启、补投票、重取租约或开启 GLINK worker。缺省返回 -1000。 |
| k60_adsp_owner_abort | 仅用于属性成功提交之前的失败清理；runtime 在 TCSR 解锁后调用。 | void，无成功返回码。先停止并隔离本 provider 的活动，再安全撤销其取得的资源；不能留下有效旧 token。缺省未取得资源，因此为空操作。成功提交后绝不调用。 |
| k60_adsp_handoff_publish | 无参数；由 IOKitBSDInit 的默认关闭门控在 IOBSD/电池入口之前同步调用。 | 返回 K60Publish* 阶段码，成功为 0。当前缺省 owner 路径返回 K60PublishPasFailed (-42)，不是原样返回 provider 的 -1000。 |

未来 acquire 若部分失败，必须自行清理全部已取得资源，或返回一个仍可由 abort 安全清理的真实 token。当前 runtime 仅在失败 lease.token 非空时调用 abort；失败且 token 为空时，不能遗留资源或工作线程。此要求是接入条件，不是当前缺省实现已经完成硬件清理的证据。

## Lease 成功条件

| 字段 | runtime 的必要检查 | provider 必须证明的事实 |
|---|---|---|
| version / bytes | version == 1；bytes == sizeof(K60AdspOwnerLease) | 这是当前进程/内核内的 native ABI，不能把结构体直接当作 104 字节线格式，也不能硬编码跨架构 sizeof。 |
| flags | 精确 K60AdspHandoffRequired == 15 | bit0 Authenticated、bit1 ResourcesHeld、bit2 GlinkExclusive、bit3 FreshHostFifos 分别都有真实依据。数字 15 本身不是依据。 |
| epoch | uint32_t 且非零 | 绑定当前启动、板级配置、SMEM items 几何和同一个 token；不能使用常量占位、旧启动或重启后的租约。序列化记录中的 epoch 字段为 64 位，本入口目前只提供 32 位 epoch。 |
| token | 非空，后续 revalidate 一直有效 | 由 provider 持有的真实、不提前过期的排他所有权；不是随意非空地址。runtime 的栈上 lease 副本会在返回时消失，provider 必须自行保证 token/资源的持久生命周期。 |

板级输入来自 K60BatteryConfig：SMEM 0x80900000/0x200000、ADSP 0x9fd00000/0x3100000、mutex 0x1f4100c、IPCC 0xed18000/0x1000、remote PID 2、client 3/signal 0、desc/TX/RX/SMP2P items 478/479/480/443、protocol 1。provider 必须绑定传入的实际配置，不得另用旧固定 carveout 或其他板参数。

## 所有权与发布时序

1. 门控通过后，runtime 取得不可回收的 startup owner=1 claim，验证配置/重叠和 /chosen，拒绝重复属性并预分配 OSData。acquire 的固件载体、SCM 和资源依赖必须已可用；不能等 vfs_mountroot 或 Data 挂载。
2. provider 在 PAS1 stopped 的安全准备阶段准备新鲜、精确的 host desc/TX/RX items（32/4096/4096 字节）及零 host indices；认证、启动 PAS1，并持续持有 power/XO/interconnect 等所需资源。SMEM 准备须有正确互斥；不能清除运行中 DSP 的进展，也不能创建 item 443 冒充远端 ready。纯 MDT 解析结果不是认证完成。
3. acquire 返回后，provider 排斥其他 GLINK worker、复位/重启和资源撤销路径。pin 必须覆盖所有 revalidate 之间的解锁窗口；一次瞬时检查成功不足以满足此契约。
4. publisher 经 o->pas 重验，再以短 TCSR 锁发现 host0/ADSP2 partition 和 slave-kernel；要求 (state & 2u) != 0、(state & 1u) == 0，保存并复核 restart。每次 ready 最多 2000 ms、间隔 20 ms；每次 mutex 尝试最多 1000 us、间隔 10 us，不是整个交接总共 2 秒。
5. 最终 TCSR 临界区内复查 partition、ready/restart、全零 32 字节 descriptor 及既有 items，调用 k60_handoff_build_existing() 并 self-parse。同一锁不得由外层预持；builder 自身不锁。plan.required 必须精确 15、epoch 非零；live 路径不分配或清零 FIFO。
6. 解锁后再次重验 owner 和 ready/restart，对精确 104 字节 OSData 自解析，在 runPropertyAction 中原子检查/提交 /chosen/k60-adsp-glink-handoff。成功必须早于 k60_physical_battery_start()，因此也早于 vfs_mountroot()。
7. 提交前失败，对已取得的 owner 执行 abort；提交成功后，GLINK 交给既有 consumer，provider 不再运行竞争 worker，资源/token/epoch 必须持续保留。本 API 没有成功后的 release 入口；不能按普通临时探针退出而掉票或复位 DSP。重启恢复协议仍须另行设计，当前没有自动恢复保证。

Provider callback、registry commit、OSData 分配和 sleep 均不在最终 TCSR 临界区内。TCSR 不会冻结 DSP，restart 检查也不能保证未来不崩溃。当前全零 descriptor 策略可能拒绝真实远端进展，不能为让发布成功而清零它。

## PAS 未就绪与失败的可观察结果

以下默认 provider 场景以电池宏启用、门控成功、无预存属性、runtime 前置检查通过为条件；它们是源码预期，不是本轮上机观察。

| 情况 | 返回/日志 | 发布和后续行为 |
|---|---|---|
| 缺省 provider / acquire 不可用 | acquire 清零 lease，返回 -1000；runtime 记录 K60Handoff: PAS1 bring-up/retained ownership failed rc=-1000; no lease published，返回 -42。 | runtime 未到 SMEM/TCSR 映射；不新增属性。原有 IOBSD/电池顺序继续。 |
| acquire 返回 0 但 lease 字段无效或首次 revalidate 非零 | runtime 返回 -42；同一日志的 rc 仍取 acquire 返回值，因此可能显示 rc=0。 | 这不是成功；有 token 时调用 abort，不发布。诊断时不能只看日志中的 rc=0。 |
| 成功 acquire 后，o->pas 重验失败 | publisher stage=-42，result.detail 保存 callback 的非零 rc。 | 不继续 ready/build/property；runtime 对已取得 owner 执行 abort。 |
| owner 有效但 SMP2P 不 ready、reset、超时或 restart 改变 | publisher stage=K60PublishNotReady (-43)。若只在最终 property callback 的复核失败，则外层 stage=K60PublishPropertyFailed (-48)。 | 无新属性；最终锁已释放后 abort。缺省 -1000 在更早一步失败，不能误写成已经轮询到 -43。 |
| 无属性而一次性电池入口执行 | consumer 得到 K60ConfigNoOwnership (-4)，记录 K60Battery: blocked rc=-4: no authenticated exclusive PAS1/SMEM/GLINK platform handoff; no MMIO, FIFO writes or power-source publication。 | consumer 在传输映射/电源源发布前退出；后到属性不会自动重试。此结论只覆盖这条受检路径。 |
| 已有属性或 startup claim 已占用 | 返回 K60PublishExists (-41)，早于 acquire；保留既有属性。 | 不能声称本次新发布，也不能凭重复退出判定既有属性有效。早期尝试失败仍保留 startup claim，排斥晚期诊断。 |
| opt-in 关闭 / 电池宏关闭 | 调用点不进入 publisher；电池宏关闭时连参数解析也被编译掉。 | 14 项宿主 dispatch 用 spy 检查此边界，不证明其他 boot 模块没有 SMEM 访问。 |

门控检查的是 PE_parse_boot_argn 成功且 unsigned 解析结果等于 1，不是原始字符串必须恰为 pong_handoff_publish=1；裸参数和四字节截断语义见集成顺序文档。没有修改 board 默认参数或镜像白名单。

## 当前实现缺口与验收边界

- 当前 K60AdspOwner.c 只实现 -1000 缺省路径，没有早期固件 carrier/reader、已审计的 SCM/PAS 事务与 metadata 一致性、资源/复位 provider、fresh FIFO 准备或成功后持久排他所有权。Lead/ADSP 的 PAS/boot 工作须按本契约逐项接入；仅有函数符号或诊断返回 0 不满足要求。
- 此缺口共同阻塞 battery/charger 的真实 GLINK 和依赖 ADSP 的 audio 路径。本契约不宣称其余音频/充电功能已具备，其他各自依赖仍须验证。
- 0619 重编号后先运行 check-patch-apply.py，再运行 14 项宿主场景：5 个局部 fixture 补丁段 fuzz 0、3 份 canonical mirrors 一致。前者仅检查 git apply 解析语法，后者是受限 predecessor fixture，不是完整 series 干净重放、内核链接、PAS1 启动或 GLINK 报文证据。
- 完成标准仍是独立记录真实认证/启动、持续资源、排他 token/epoch、SMP2P ready/non-reset、104 字节发布、consumer 采用以及真实 GLINK 事务；不能用 host PASS、合法 blob、发布日志或一次 SMC 返回代替。后续构建和设备验证必须另获授权，本轮均未执行。

## 编号与证据台账

按 Lead 本轮编号决定：已构建归档的 thermal-20261115a 保留 0617，springboard 保留 0618，本线仅将原 handoff 补丁改为 0619；不改动其他线补丁，也不并 main。0619 补丁正文保持 SHA-256 b7eb981351f828023af827a649dc77a93146ac26ac14117de43e9482fcf3508b。

本轮离线记录位于 E:/k60-work/artifacts/adsp-handoff-0619-20261115/：patch-apply.log 为改动补丁语法检查，integration.log 为 14 项 dispatch/5 段 fuzz 0/3 镜像检查，owner.log 为本线作用域检查。八步台账的 verify/local_verified/device 继续为 false。未生成 kernel/image，也未执行设备、boot 或串口操作。
