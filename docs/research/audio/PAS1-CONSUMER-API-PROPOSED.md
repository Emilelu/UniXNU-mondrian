# PAS1 音频消费者接口提案

本文把 power 线第 1 轮回答里的三个“需要 audio 给”的问题，改写成可以照着实现的接口，而不是继续列问题。范围只到接口、状态机、调用点和失败语义；没有编译、没有链接、没有上机。

## 一、结论先说

1. **PAS1 已发布不等于音频域可用。** 现有的 `k60_adsp_handoff_owner_active()` 只表示“早期 handoff 已认领”，`k60_pmic_glink_audio_ready()` 只表示“GLINK 通道已 up”，两者都不表示 APM 已经回答。真正的音频域判据只能是 APM 对 `GET_SPF_STATE` 的回答 `{status: 1}`。
2. **audio 不解析 104 B 的 `k60-adsp-glink-handoff` 属性。** 这个属性由 power 的 `K60HandoffRuntime` 写入，由 `K60Battery` 读取并建立 GLINK；audio 只通过 `k60_pmic_glink_attach_audio()` / `k60_pmic_glink_audio_ready()` 消费已经建立的通道。重复解析会让两份 lease 校验分叉。
3. **电源轨和时钟的写入仍然不在 audio。** 本文只提出 power 侧的**账本/投票**接口；audio 保留 TLMM reset GPIO 与 LPASS 寄存器写入，不写 PMIC、RSC/TCS。power 没有 rail 写路径时，audio 必须把“账本已记账”和“rail 已上电”分开说，不能把 claim 当成功。
4. **0531 继续 HOLD。** 解除条件不是“编译过了”，而是同时满足：选中 0531 的系列、`bsd_init.o` 有引用、`PongAudioAmp.o` 有定义、真实 27 内核的字符串与符号都在。当前补丁是 `#if 1`，且它自己的注释说明 `XNU_PONG_AUDIO` 只到 `PongAudioAmp.o`；只把 `#if 1` 换成那个宏会把调用点从 `bsd_init.c` 编译掉，所以 HOLD 还需要构建侧把同一个开关送到内核目标，详见第六节。

## 二、现在已经存在的三块

### 2.1 power 的发布端与唯一的属性消费者

- 发布点：`adsp:drivers/PongPower/K60HandoffRuntime.cpp:36-83`。它在 `:37` 先做 `k60_adsp_startup_claim(1u)`，在 `:72` 取 lease，`:73` 做 revalidate，`:79` 发布，成功行在 `:81`：`published authenticated PAS1 epoch=%u bytes=104 flags=15`。
- 属性名：`adsp:drivers/PongPower/K60BatteryConfig.h:17` 的 `k60-adsp-glink-handoff`，长度 `K60_ADSP_HANDOFF_BYTES 104`。
- 现有唯一消费者：`adsp:drivers/PongPower/K60Battery.cpp:424-436`。它在 `:427` 从 `/chosen` 取节点，`:428` 取属性，`:430-431` 调 `k60_adsp_handoff_parse()`；失败在 `:434` 打印 `blocked rc=...: no authenticated exclusive PAS1/SMEM/GLINK platform handoff` 并直接返回，不做任何 MMIO。
- 因此：**audio 不应再写第二个 104 B 解析器**；需要的是 power 暴露一个只读状态，或 audio 使用已有的两个布尔查询。

### 2.2 GLINK 音频桥

- 消费者接口：`adsp:drivers/PongPower/K60PmicGlinkAudio.h:36-38` 的 `k60_pmic_glink_attach_audio()`、`k60_pmic_glink_send_audio()`、`k60_pmic_glink_audio_ready()`。
- attach 可以在通道尚未建立时调用：`adsp:drivers/PongPower/K60PmicGlink.cpp:33-44` 先缓存 client，`gActivePmicGlink` 为空时返回 `OK` 排队；`:160-175` 的 open 成功后才 deferred attach。控制台里 deferred 失败只有一行 `K60Battery: deferred audio attach failed: %d`。
- 通道真正 up 才开音频 slot：`adsp:drivers/PongPower/K60PmicGlink.cpp:223-239`，`up` 时先 `k60_audio_glink_open()`，再 service。`adsp:drivers/PongPower/K60AudioGlink.c:195-200` 的 ready 条件是 `attached && channel->up && transport && !transport->broken`。
- 结论：`k60_pmic_glink_audio_ready()` 是 **transport ready**，不是 **audio domain ready**。

### 2.3 音频侧已有的状态码与编码器

- 拒绝码：`drivers/PongAudio/PongAudioAfe.h:50-63`，`PongAudioOk=0`、`ErrNoHandoff=-2001`、`ErrNoLease=-2002`、`ErrStaleLease=-2003`、`ErrApmNotReady=-2004`、`ErrAfeRefused=-2005`、`ErrBadRequest=-2006`、`ErrRingFull=-2007`、`ErrPlayback=-2008`。名字表的注释已经写了“这是 `pong_audio_status()` 的契约”，但函数还没有实现。
- APM 查询编码器：`drivers/PongAudio/PongAudioAfe.h:216-225` 只生成 24 B GPR 头，opcode `0x01001021`、源端口 `0x2001`、目的端口 1、无 payload；常量在 `:145-154`。
- 回应语义：`sheng:package/ShengGpr.h:21` 明确 `GPR_OP_APM_SPF_STATE 0x02001007` 的 payload 是 `{status}: 1 ready`；`sheng:package/ShengGpr.c:84-89` 要求 `payload_bytes >= 4`，取 little-endian 的第一个字，等于 1 才返回 ready。这是 audio 侧解析 APM 回答的唯一依据，不能凭“通道 up”推断。
- 六步发送顺序：`drivers/PongAudio/PongAudioAfe.h:547-554` 的 `PongAfeStepClock → GroupTdm → GroupEnable → PortTdm → SlotMapping → DeviceStart`；注释 `:542-545` 说 clock 必须最先，任何一步失败就停。真正的门要放在第一步之前。
- 现状：没有 `PongAudioAfe.c`，也没有 `pong_audio_status()` 的实现；只有头文件和 host 测试。这是“接口提案”而不是“已有实现”的原因。

## 三、接口 A：power 侧的只读 PAS1 状态

### 3.1 建议的 C 形状

```c
#define K60_ADSP_HANDOFF_STATUS_VERSION 1u

typedef enum {
    K60AdspHandoffAbsent  = 0,  /* 没有配置、也没有认领 */
    K60AdspHandoffBooting = 1,  /* startup claim 已成功，发布尚未完成 */
    K60AdspHandoffReady   = 2,  /* 104 B 属性已发布且 revalidate 通过 */
    K60AdspHandoffFailed  = 3   /* 已尝试且失败，detail 带错误码，粘到重启 */
} K60AdspHandoffState;

typedef struct {
    uint32_t version;   /* K60_ADSP_HANDOFF_STATUS_VERSION */
    uint32_t state;     /* K60AdspHandoffState */
    int32_t  detail;    /* 0，或 K60Publish* / K60_ADSP_OWNER_* 错误 */
    uint32_t epoch;     /* Ready 时有效 */
    uint32_t flags;     /* Ready 时有效，成功发布为 15 */
} K60AdspHandoffStatus;

/* 0 = 已填充；K60_ADSP_STATUS_UNAVAILABLE (-1001) = 当前构建没有这个后端。
 * 只读：不加锁、不映射、不发 SMC、不睡眠；可在任意上下文调用。 */
int k60_adsp_handoff_status(K60AdspHandoffStatus *out);
```

### 3.2 状态迁移与实现点

| 状态 | 置位点 | 语义 |
|---|---|---|
| `Absent` | 启动初值 | 没有 `/chosen` 属性，也没有 startup claim |
| `Booting` | `K60HandoffRuntime.cpp:37` 的 claim 成功之后 | PAS1 正在 bring-up；属性还不应存在 |
| `Ready` | `:79` 的 publish 返回 0 之后 | 与 `:81` 的成功行同一条件；此时 `epoch/flags` 可读 |
| `Failed` | `:73-76` 或 `:79-80` 的失败分支 | `detail` 保存 `K60Publish*` 或 owner 错误；不再重试 |

实现建议：在 `K60HandoffRuntime.cpp` 的 `static K60AdspBoard board`（`:34`）旁边放一个 `static _Atomic uint32_t gHandoffState` 和 `gHandoffDetail/gHandoffEpoch/gHandoffFlags`，只在上述四个点用 release 写、查询用 acquire 读。**不要**让查询走 `K60AdspOwner` 的 `api_busy` 串行区：那个区会拒绝重入（`adsp:drivers/PongPower/K60AdspOwner.c:76-93`），而状态查询必须无副作用。

### 3.3 power 不提供时的安全只读回退

不需要新符号，用现有的两个查询：

```c
const bool claimed = k60_adsp_handoff_owner_active() != 0; /* adsp:drivers/PongPower/K60AdspOwner.h:31 */
const bool link_up = k60_pmic_glink_audio_ready();        /* adsp:drivers/PongPower/K60PmicGlinkAudio.h:38 */
```

| claimed | link_up | 可推断 | 不能推断 |
|---|---|---|---|
| 0 | 0 | 还没认领，按 `Absent` 处理 | 是“没配置”还是“配置了但还没跑” |
| 1 | 0 | `Booting`（或失败） | 分不清正在启动与已失败 |
| 1 | 1 | `Ready` 的传输前提成立 | 仍不能证明 APM ready；还要接口 B 的查询 |

这就是“power 不提供也能安全只读查询”的答案：可以查，但只能得到“未认领 / 启动中或失败 / 传输已 up”三档，分不清 `Booting` 与 `Failed`。所以接口 A 仍然值得做，但不是第一版 audio 的硬依赖；第一版可以先用回退对，日志里写明 `fallback`。

## 四、接口 B：audio 侧的音频域状态

### 4.1 建议的 C 形状

```c
#define K60_AUDIO_DOMAIN_VERSION 1u

typedef enum {
    K60AudioDomainAbsent         = 0, /* 没有 handoff，或 owner 未认领 */
    K60AudioDomainBooting        = 1, /* handoff 已认领；GLINK 或 APM 尚未就绪 */
    K60AudioDomainTransportReady = 2, /* GLINK 音频 slot 已 up；GET_SPF_STATE 未答 */
    K60AudioDomainApmReady       = 3, /* APM 回答 opcode 0x02001007, status == 1 */
    K60AudioDomainFailed         = 4  /* handoff 失败，或 APM 明确拒绝/超时 */
} K60AudioDomainState;

typedef struct {
    uint32_t version;
    uint32_t state;
    int32_t  detail;      /* PongAudioStatus 负值，或 0 */
    uint32_t epoch;       /* 从接口 A 复制；fallback 时为 0 */
    uint32_t flags;
    uint32_t apm_status;  /* 最近一次 APM 回答的 status 字 */
    uint32_t queries, answers, timeouts;
} K60AudioDomainStatus;

/* 发一包 GET_SPF_STATE（不等待）；0 = 已交给 GLINK，负值 = 当前不能发。
 * 只在 TransportReady/ApmReady 时可发；重复调用不重排已有 token。 */
int k60_audio_domain_probe(void);

/* 返回缓存状态，不做 I/O、不睡眠、不加锁。 */
int k60_audio_domain_status(K60AudioDomainStatus *out);

/* 由 K60PmicGlinkAudioClient.receive 调用；校验 token 与 opcode 后更新缓存。 */
void k60_audio_domain_on_packet(const uint8_t *data, unsigned bytes);
```

### 4.2 “音频域可用”的第一条可执行判据

只有同时满足以下三条，才允许进入 `PongAfeStepClock`：

1. 接口 A 为 `Ready`（或回退对为 `claimed && link_up`），且 `epoch != 0`、`flags == 15`；
2. `k60_pmic_glink_audio_ready() == true`；
3. 自己发出的 `GET_SPF_STATE` 收到回答：GPR 头 `opcode == 0x02001007`、`payload_bytes >= 4`、little-endian 的第一个字 `== 1`、token 与请求一致。

第 3 条是唯一能把“传输通了”升级成“音频域可用”的证据。判据写成函数：

```c
int pong_audio_status(void)
{
    K60AudioDomainStatus st;
    if (k60_audio_domain_status(&st) != 0) return PongAudioErrNoHandoff;
    switch (st.state) {
    case K60AudioDomainApmReady:       return PongAudioOk;
    case K60AudioDomainAbsent:         return PongAudioErrNoHandoff;
    case K60AudioDomainBooting:        return PongAudioErrNoLease;
    case K60AudioDomainTransportReady: return PongAudioErrApmNotReady;
    case K60AudioDomainFailed:         return st.detail ? st.detail : PongAudioErrAfeRefused;
    }
    return PongAudioErrAfeRefused;
}
```

`PongAudioErrStaleLease` 只在接口 A 曾经 Ready、随后 revalidate 失败时使用；audio 不持有 lease token，不能自己调 `k60_adsp_owner_revalidate()`，所以这个码必须由接口 A 的 `detail` 或 power 的状态迁移给出。

### 4.3 失败三态与调用点

| 情形 | 状态 | 返回 | 调用点行为 |
|---|---|---|---|
| 没有 handoff / owner 未认领 | `Absent` | `-2001` | 不 attach、不发 GPR；打印一次，不重试 |
| 已认领但 GLINK/APM 未就绪 | `Booting` / `TransportReady` | `-2002` / `-2004` | 可以稍后重试；不阻塞 probe，不写 codec |
| 明确失败、APM 拒绝或超时 | `Failed` | `detail` 或 `-2005` | 停止六步；打印最近 `apm_status`；不重试到死循环 |

调用点固定为三个：

1. **诊断点**：`drivers/PongAudio/PongAudioAmp.c:944` 的 `pong_audio_amp_probe()`。在 `:951` 的 boot-arg 门之后、`:955` 的第一行日志之前调一次 `k60_audio_domain_status()`，只打印 `PongAudio: domain state=%u detail=%d fallback=%u`；**绝不因音频域未 ready 而提前返回**。这个 probe 是 I2C/功放总线诊断，允许在 APM 之前跑。
2. **真正的门**：将来 `PongAudioAfe` 实现文件里的 `pong_audio_start()`（现在只有头文件）。在 `PongAfeStepClock`（`PongAudioAfe.h:547`）之前调用 `pong_audio_status()`；非 0 直接返回，六步一个都不发。这是唯一应该阻塞播放路径的位置。
3. **接收点**：注册 `K60PmicGlinkAudioClient.receive`（`adsp:drivers/PongPower/K60PmicGlinkAudio.h:14-17`）时把回调指向 `k60_audio_domain_on_packet()`；attach 用 `:36` 的 `k60_pmic_glink_attach_audio()`，可以在 `pong_audio_amp_probe()` 里做，因为 `K60PmicGlink.cpp:41-43` 在没有 active 时会排队。

`pong_audio_amp_play()`（`PongAudioAmp.c:903`）不是门。它的注释 `:899-901` 已经写明“TDM speaker graph 跑起来后调用”；把门加在这里会让诊断路径和播放路径混在一起。`pong_audio_amp_stop()`（`:925`）永远安全，不需要状态。

## 五、接口 C：电源轨、复位与时钟的归属

### 5.1 现状：power 没有 rail 写路径，audio 也没有

- `adsp:drivers/PongPower/K60PmicRail.h:1-20` 明确只读：`k60_rail_inherit()` 单次采样，`k60_rail_probe()` 只打印账本，`No path writes a register and no path polls`。
- `drivers/PongPower/K60PowerVotePlan.h:3-13`（27 树里有这个文件）明确“只有所有权与引用计数”，`:9-12` 写 `No MMIO, no RPMh and no TCS writes`，而且 `The module has no caller yet`；`:27-33` 是 free/shared/exclusive 与 stop-DMA → mask-IRQ → drop-vote 的顺序；`:41-58` 才是 acquire/release/count。
- 结论：**“claim 成功”不等于“rail 已上电”。** 现在没有任何一条路径会写 PMIC；audio 不能因为拿到 vote 就开始写 codec/功放寄存器。

### 5.2 建议的账本接口（power 侧）

不要求 power 现在写 PMIC；只要求它把 audio 的资源名、ID 和顺序记进同一份账本：

```c
#define K60_AUDIO_POWER_VERSION 1u
#define K60_AUDIO_POWER_MAX_RAILS 4u
#define K60_AUDIO_POWER_MAX_CLOCKS 3u

typedef struct {
    const char *name;   /* 静态字符串，如 "ldob15"、"tx_core_clk"；不转移所有权 */
    uint32_t id;        /* cmd-db 地址或 clock id；0 = 未测量 */
    uint32_t min_uv;    /* rail */
    uint32_t max_uv;    /* rail */
    uint32_t hz;        /* clock */
    uint32_t flags;
} K60AudioResource;

typedef struct {
    uint32_t version;
    uint32_t rail_count, clock_count;
    K60AudioResource rails[K60_AUDIO_POWER_MAX_RAILS];
    K60AudioResource clocks[K60_AUDIO_POWER_MAX_CLOCKS];
    uint32_t reset_gpios[4]; /* 仅记录；由 audio 写 TLMM */
} K60AudioPowerNeed;

typedef struct {
    uint32_t version;
    uint32_t owner;   /* power 分配的 audio owner id */
    uint32_t granted; /* 1 = 全部记账成功 */
} K60AudioPowerClaim;

/* 0 = 记账成功；-3001 = 有必需 id 为 0（未测量）；-3002 = 共享/独占冲突；
 * -3003 = 当前构建没有 rail/clock 后端。只记账，不写 PMIC/RSC/TCS。 */
int k60_power_audio_claim(const K60AudioPowerNeed *, K60AudioPowerClaim *);
int k60_power_audio_release(const K60AudioPowerClaim *);
```

实现上直接复用 `K60PowerVotePlan.h:41-58` 的 `k60_vote_acquire()/k60_vote_release()`，由 power 持有一个单例 `K60VoteState` 和 audio 的 owner id；`claim` 遍历 need 里的 rail/clock，全部成功才返回 0，任何一项失败就回滚已拿到的 vote。这样不需要改 `K60VoteState` 的 16×32 算术，也不会把 PMIC 写进 audio。

### 5.3 资源名与 ADT 节点（现在能确定的和不能确定的）

| 资源 | 27 树 DT 现状 | 当前代码 | 归属 |
|---|---|---|---|
| codec rail | `dts/mondrian.dts:67` `codec-supply-rail = <0>` | 没有消费者 | power 账本；名字/ID 未测量 |
| amp0/amp1 rail | DT 没有属性 | 没有消费者 | power 账本；需新增 `amp0-supply`/`amp1-supply` |
| amp0 reset | DT 没有属性 | `PongAudioRegs.h:47` GPIO1；`PongAudioAmp.c:991` 写 TLMM | audio（TLMM pad） |
| amp1 reset | DT 没有属性 | `PongAudioRegs.h:48` GPIO3；`PongAudioAmp.c:992` 写 TLMM | audio（TLMM pad） |
| codec reset | `dts/mondrian.dts:63` `codec-reset-gpio = <0>` | `PongAudioRegs.h:155` 常量 43，尚未写 | audio（TLMM pad），填 DT 后启用 |
| spksw | DT 没有属性 | `PongAudioRegs.h:51` GPIO52；`PongAudioAmp.c:165-201` | audio（TLMM pad） |
| amp I2C | `dts/mondrian.dts:65` `amp-i2c-address = <0>` | `PongAudioRegs.h:109-110` 0x34/0x35 | audio |
| TX core clock | `dts/mondrian.dts:66` `tx-core-clock-id = <0>` | 常量 `0x30c`，19.2 MHz，`PongAudioRegs.h:156-157` | LPASS 写 audio；RSC/TCS 账本 power |
| TX SWR master | `dts/mondrian.dts:62` `tx-master-base = <0>` | 参考 `0x33b0000`，`PongAudioRegs.h:158` | audio |
| QUP15 I2C GCC | 无 | `PongAudioAmp.c:259-268` 四个窗口；`:970-979` 先 GPLL0 再 wrapper2 | 生产路径应改 power 投票；当前只用于诊断 |

这张表的关键是：**DT 里 9 个 0 不是“默认值”，是“未测量”**（`dts/mondrian.dts:61` 的注释也这么写）。任何消费者读到 0 都必须拒绝并点名，不能拿头文件常量悄悄替代 DT。填 DT 是 F3 的板级工作，不是本提案的范围。

### 5.4 复位与时钟的写入边界

- audio 写 TLMM：amp0/amp1 reset（GPIO1/3）、spksw（GPIO52）、codec reset（GPIO43，填 DT 后）；这些是 APSS 引脚，不是 PMIC 寄存器。
- audio 写 LPASS：TX core `0x30c` 的 acknowledgement、VA/TX SWR master、TX macro；这些都在 PAS1 起来之后，且必须先有接口 B 的 `ApmReady`。
- power 写：PMIC rail、RSC/TCS、以及任何 clock gating 的 RSC 投票。当前 power 没有这些写路径，所以第一版 audio 只能做到“记账 + 拒绝未测量”，不能做到“真的把 rail 拉起来”。
- 如果 power 决定让 QUP15 GCC 也归它管，audio 需要的是 `k60_power_audio_claim()` 里带 `gcc_qup15` 这一项；在那之前，`PongAudioAmp.c:259-370` 的直接 GCC 写只能标记为**诊断探针**，不能进 27 的正式播放路径。

## 六、0531 的 HOLD 与解除条件

### 6.1 为什么现在必须 HOLD

- 补丁 `patches/xnu-12377/0531-k60-audio-amp-probe-call.patch:7` 是 `#if 1`；`:21` 只是 `extern int pong_audio_amp_probe(void) __attribute__((weak))`，`:23-25` 判非空再调用。弱声明不会让“没有定义”变成安全：`scripts/check-audio27-weak-link.py:560` 的注释和 `:682-690` 的 `WEAK-LINK why` 都写明，内核镜像里未定义的弱函数引用仍是链接错误。
- 补丁自己的注释 `:11-13` 说得很清楚：`XNU_PONG_AUDIO` 只到 `PongAudioAmp.o`，所以调用点故意没有用那个宏。也就是说，**单纯把 `#if 1` 改成 `#if defined(XNU_PONG_AUDIO)` 会把 `bsd_init.c` 里的调用点编译掉**，即使音频对象已经打开。
- 当前 stage-0 的 board 不建音频（`docs/research/audio/IOS27-STAGE0-STATE.md:24-38`），所以此刻没有定义源是设计，不是回归；但这也正是不能解除 HOLD 的原因。

### 6.2 解除 HOLD 需要的证据（全部满足）

1. **选中**：有效系列（`patches/xnu-12377/series` 或 gates 的对应系列）列出 0531，且不再是 HOLD 注释；同时 `--switch off` 必须能把调用点拿掉。
2. **可控的开关**：调用点的 guard 必须对 `bsd_init.c` 真的可见。要么构建把 `-DXNU_PONG_AUDIO=1` 同时送给内核目标（不只是 `PongAudioAmp.o`），要么引入一个专门给 `bsd_init.c` 的宏（例如 `XNU_PONG_AUDIO_CALL`）并在构建里定义。只改补丁文本、不改构建，不算。
3. **链接证明**：`link.filelist` 同时有 `PongAudioAmp.o` 与 `bsd_init.o`；`nm` 里 `bsd_init.o` 是 `U _pong_audio_amp_probe`（arm64e 还可能是 `$auth_ptr$ia` 存根），`PongAudioAmp.o` 是 `T`/`t _pong_audio_amp_probe`。`W`（弱定义）、数据符号、`stub.o` 里的 `T` 都不算。
4. **门禁原文**：`python3 scripts/check-audio27-weak-link.py --tree . --link-filelist <filelist> --symbols <nm 输出>` 返回 0，并打印 `WEAK-LINK OK: 0531 is selected and _pong_audio_amp_probe has a definition in the link`。如果 checker 还不认识第 2 条的新宏，先补 checker 和它的测试，再谈解除。
5. **真实产物**：`python3 scripts/check-audio27-kernel.py <kernel 或 object>` 返回 0，`strings 3/3`、`symbols 3/3`。stage-0 的 `strings 0/3, symbols 0/3` 不能拿来当“音频已经接通”的证据。
6. **上机前的边界**：以上都齐了也只说明“调用点能链、产物里有符号”，不说明功放出声。出声仍要 F3/F4 的 UFS、固件、面板与 APM 图；0531 的 HOLD 解除不等于音频阶段完成。

### 6.3 解除后的验证顺序

先 `check-audio27-weak-link.py --tree . --switch off` 确认关闭时没有调用点；再 `--switch on` 配 link 输入确认有定义；然后 `check-audio27-kernel.py`；最后才允许把 0531 从 HOLD 改成选中。任何一步失败都回到 HOLD，不跳过。

## 七、给 power 的逐条回信

| power 的问题 | 回答 |
|---|---|
| 27 侧提交仍是 `8cbb3af6` / `3e73f4be`？ | 本轮开始时是；本文提交后会变，tip 以回复里的 SHA 为准。 |
| 0531 仍 HOLD？ | 是。解除条件见第六节，不是“编译通过”。 |
| audio 是否已有 `k60-adsp-glink-handoff` 的 consumer 代码/判据？ | **传输 consumer 有，状态判据没有。** attach/send/ready 在 `adsp:drivers/PongPower/K60PmicGlinkAudio.h:36-38`，实现在 `K60PmicGlink.cpp:33-59`；但 audio 不解析 104 B 属性，也没有 `pong_audio_status()` 实现。本文的接口 B 就是补这个判据。 |
| codec/SoundWire 的资源名、ADT 节点、owner 候选？ | 见 5.3 表：codec rail 是 `codec-supply-rail`（当前 0）；amp rail 需要新增属性；TX SWR 是 `tx-master-base`（当前 0）；codec reset 是 `codec-reset-gpio`（当前 0，候选 GPIO43）。owner：rail/RSC 归 power，TLMM reset 与 LPASS 寄存器归 audio。 |
| “音频域可用”的第一条可执行判据？ | `GET_SPF_STATE` 的回答 `opcode 0x02001007` 且 payload 第一个字 `== 1`；加上接口 A 的 `Ready` 与 `k60_pmic_glink_audio_ready()`。见 4.2。 |
| 注册表计数 `103/21/4/78` 与 power 的 `103/20/4/79` 不一致？ | `8166c7dc` 把 `concepts/boot-chain.md` 从 unmapped 改成 mapped；合并前是 `103/20/4/79`，合并后是 `103/21/4/78`。power 的 `95984aca` 在合并前，看到旧计数是正常的。 |

需要 power 做的三件（按优先级）：

1. 决定接口 A 是否在 F3 前实现；如果不实现，确认 audio 使用 3.3 的回退对，并接受“分不清 Booting/Failed”。
2. 给 audio 分配一个 owner id 和单例 `K60VoteState`，实现 5.2 的 claim/release；先只记账，不写 PMIC。
3. 确认 rail/clock 的 DT 属性名与 ID 来源；如果 power 要接管 QUP15 GCC，明确 `gcc_qup15` 作为 clock 项进 need。

## 八、验证命令与不证明什么

离线可跑（不需要编译器、不需要设备）：

```sh
python3 scripts/check-audio27-fptrs.py --repo .
python3 scripts/tests/test-audio27-fptrs.py
python3 scripts/check-audio27-weak-link.py --tree /mnt/e/hackios/k60-gates
python3 scripts/tests/test-audio27-weak-link.py
sh scripts/check-audio27-preflight.sh --pac-only
```

这些命令证明的是：现有 io 表的签名成对、0531 的 HOLD 语义、以及本文引用的现有接口没有被误改。它们**不证明**：

- 本文的 `k60_adsp_handoff_status`、`k60_audio_domain_probe`、`k60_power_audio_claim` 已经实现；它们现在只是提案，源码里没有这些符号。
- APM 会回答 `status == 1`；这要真 PAS1 起来并跑一次 `GET_SPF_STATE` 才知道。
- power 的 rail 会真的上电；当前 power 只读，claim 只是账本。
- 0531 已经解除 HOLD；它仍是 HOLD，解除证据见第六节。
- 音频能出声；本文只到接口与判据，出声仍要 F3/F4。
