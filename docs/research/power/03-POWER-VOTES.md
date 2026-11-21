# 外设电源投票记账（官网 §5 要求）

状态：**纯逻辑记账模块 + host 58 项断言，无消费者、未上机**。官网
`https://unixnu.com/zh/porting/power` §5 要求「为外设电源投票明确所有权和引用计数。
停止依赖的 DMA 和中断后再释放资源」（快照 `E:/k60-work/scratch/power-page-20261117.txt:109-110`）。
本仓库没有任何外设电源投票实现：`K60PmicRail.h` 只是只读采样，HR-01 又禁止写 RSC/TCS，
所以先把「谁持有、持有几次、什么时候可以释放」做成可测试的纯逻辑。

## 1. 模型

`drivers/PongPower/K60PowerVotePlan.h` + `.c`：

- 16 个资源槽、32 个 owner（位图 + 16 位计数）。
- 每个资源有一个模式：`Free` / `Shared` / `Exclusive`。第一个 owner 决定模式：
  shared 资源可被多个 owner 同时持有；exclusive 资源在最后一个释放前拒绝其他人。
- 同一 owner 对同一资源只能持有一份（重复申请返回 `-3`），因此
  `count == owner 位图的人数`，不需要每 owner 计数。
- 返回值：`0` 成功；`-1` 空指针/越界/无效模式；`-2` 模式冲突；
  `-3` 重复申请。释放返回 `1` 表示这是最后一次（可以下电）、`0` 仍有人持有、
  `-1` 没有这份 claim。
- 释放顺序由 `k60_vote_release_steps()` 固定为：`stop-dma` → `mask-irq` → `drop-vote`。
  模块无法检查前两步，只把顺序写成调用方与 host 测试共同的契约。

## 2. 为什么不是 rail 驱动

- HR-01（`docs/ops/HARD-RULES.md`）规定 `0x17a00000` RSC 绝对禁止映射；
  `0x17a20000` DRV-2 仅在四个条件同时满足时允许一次只读采样；TCS 写与
  `CONTROL_TRIGGER` 禁止。
- 因此这里的 vote 只是驱动侧的引用计数声明，不发送 RPMh 请求、不写 TCS、
  不改变任何电压。真正下电仍要等 rail 所有权问题解决后另行实现。
- 当前没有消费者：显示、USB、PCIe 等外设各自持有自己的电源路径，尚未接入本模块。

## 3. Host 验证

`scripts/tests/test-k60-power-vote-plan.c`，58 项断言：

- shared 两个 owner 共存、exclusive 拒绝第三人、exclusive 首个 owner 期间 shared 被拒；
- 重复申请返回 `-3`（优先于模式冲突）、释放后位图/计数/模式正确回落；
- 最后一次释放返回 `1`，未持有的释放返回 `-1`；
- owner 0/31 边界、资源 15/16 边界、空指针与无效模式；
- 释放顺序三步、容量不足不写、步骤名与未知步骤文本。

运行：

```sh
cc -Wall -Wextra -Werror -std=c11 -o /tmp/tk60vote \
  scripts/tests/test-k60-power-vote-plan.c drivers/PongPower/K60PowerVotePlan.c
/tmp/tk60vote
```

结果：`TESTS OK 58 checks (0 failures)`。

## 4. 边界与下一步

- 未上机，也没有任何真实 rail 名称、consumer 列表或下电时序证据。
- 下一步（需要设备/其他线配合）：把实际消费者列出来（显示、USB、PCIe、ADSP rail），
  在各自驱动里登记 owner，确认释放前的 DMA/中断停止点，再讨论 rail 写路径。
- 不要把本模块当成 §5 完成：GPU 调频、外设 rail 实际供电、平台睡眠的 ArmCpu 路径都还没有。

## 5. 参考

- 官网快照：`E:/k60-work/scratch/power-page-20261117.txt:109-110`。
- 规则：`docs/ops/HARD-RULES.md` HR-01；只读采样：`drivers/PongPower/K60PmicRail.h`。
- 官方参考实现：`UniXNU-sheng` 的 `package/QcomRpmh.c`/`QcomQmp.c` 与
  `ShengPlatformPower.cpp`（后者只做 PMGR ABI 资格验证，未实现槽位会 panic）。

## 6. 音频消费者的投票契约（2026-11-21）

audio 第 5 轮问的五个参数（`E:/k60-work/scratch/reply-power-audio-sync.md`）在这里一次定死。
本节仍是**纯记账契约**：没有 PMIC 写、没有 RSC/TCS、没有实现，也没有上机。audio 可以据此写离线
consumer；power 的 wrapper 落地时以本节数值为准。

### 6.1 owner 与资源号

| 名称 | 值 | 用途 |
|---|---|---|
| `K60VoteOwnerPower` | 0 | power/未知，保留，永不给 audio |
| `K60VoteOwnerAudio` | 1 | audio 的唯一 owner id |
| `K60VoteResourceCodecRail` | 0 | WCD938x codec supply |
| `K60VoteResourceAmp0Rail` | 1 | AW88261 #0 |
| `K60VoteResourceAmp1Rail` | 2 | AW88261 #1 |
| `K60VoteResourceTxSwr` | 3 | TX SoundWire master / GCC gate |
| `K60VoteResourceTxCoreClock` | 4 | TX core `0x30c`（可选） |
| `K60VoteResourceQup15Gcc` | 5 | QUP15 I2C GCC（可选，先按诊断） |
| 6–15 | — | 不分配给 audio |

- **owner id 写进 power 侧 header enum，不放在单例内部。** audio 必须 include 或复制同一个常量；
  不要在自己代码里另写一个 `1` 后与 power 分叉。header 随 wrapper 落地；本轮先以本节数值为准。
- 0–3 是 v1 的四类，各占一个槽：codec rail、amp0、amp1、TX SWR/GCC。4–5 是提案 §5.3 里
  另外两个可选时钟；只有它们也进入 power 记账时才占用，否则 audio 不 claim。
- reset GPIO（amp0/1、codec、spksw）不是 PMIC rail，**不占 vote 槽**，仍由 audio 写 TLMM；
  `reset_gpios` 只是记录，0 不产生 `-3001`。
- audio 的所有资源用 `K60VoteShared`。当前没有 audio exclusive 资源；要 exclusive 必须另立裁定，
  不能让 consumer 自己猜。

### 6.2 单例与入口

- `K60VoteState` 单例归 power 私有，放在将来的 `drivers/PongPower/K60PowerVoteAudio.c`，
  `static`，不导出指针。16×32 的算术和 owner 位图只保留这一处实现。
- `k60_power_audio_init()` 由 `K60Battery::begin()`（`drivers/PongPower/K60Battery.cpp:550`）
  在 handoff 解析之后、transport open 之前调用一次；audio 不初始化、不 reset。
- audio 只调用 `k60_power_audio_claim()` / `k60_power_audio_release()`，**不直接调用**
  `k60_vote_acquire()` / `k60_vote_release()`，也不拿 `K60VoteState *`。
  未 init 时 claim 返回 `-3003`；audio 把它当“本构建没有账本后端”，不能当 rail 失败。

### 6.3 结构与返回值

```c
#define K60_AUDIO_POWER_VERSION 1u
#define K60_VOTE_OWNER_POWER 0u
#define K60_VOTE_OWNER_AUDIO 1u

typedef struct {
    uint32_t version;       /* K60_AUDIO_POWER_VERSION */
    uint32_t resource;      /* 上表 0..5 */
    uint32_t id;            /* cmd-db/clock id；0 = 未测量 */
    uint32_t min_uv, max_uv, hz, flags;
    const char *name;       /* 静态字符串，不转移所有权 */
} K60AudioResource;

typedef struct {
    uint32_t version;
    uint32_t rail_count, clock_count;
    K60AudioResource rails[4];
    K60AudioResource clocks[3];
    uint32_t reset_gpios[4]; /* 仅记录；audio 写 TLMM */
} K60AudioPowerNeed;

typedef struct {
    uint32_t version;
    uint32_t owner;         /* 固定 K60_VOTE_OWNER_AUDIO */
    uint32_t granted;       /* 1 = 全部记账成功 */
    uint32_t acquired_mask; /* 成功占用的 resource 位；release 用 */
} K60AudioPowerClaim;

int k60_power_audio_init(void);
int k60_power_audio_claim(const K60AudioPowerNeed *, K60AudioPowerClaim *);
int k60_power_audio_release(const K60AudioPowerClaim *);
```

- claim 遍历 need；任一 `id == 0`、未知 resource、重复 resource、`k60_vote_acquire()` 失败，
  都**回滚已拿到的 vote（逆序 release）**，`granted = 0`、`acquired_mask = 0`，返回第一个错误。
- 返回：`0` 成功；`-3001` 必需资源未测量（`id == 0`）；`-3002` 冲突/重复/释放未持有；
  `-3003` 账本未初始化/本构建无后端；`-3004` 参数非法（空指针、version/count 不对）。
  **不把 `k60_vote` 的 `-1/-2/-3` 直接暴露给 audio**；wrapper 负责翻译。
- release 按 `acquired_mask` 逆序释放；成功返回 0；重复 release 返回 `-3002`，不静默成功。
  调用前 audio 自己按 `stop-dma` → `mask-irq` → `drop-vote` 停自己的 DMA/中断；
  wrapper 不检查，也无法检查。
- `acquired_mask` 是提案 §5.2 原结构缺的字段；没有它，部分成功无法正确回滚。

### 6.4 边界

- `k60_power_audio_claim()` 只调用 `k60_vote_acquire()`，后者是纯算术；没有 MMIO、RPMh、
  RSC/TCS、PMIC 写。`granted = 1` 只表示“账本记下了”，**不表示 rail 已上电**，
  也不表示音频域可用。
- audio 不得把 claim 当 rail 上电；仍要等 `k60_pmic_glink_audio_ready()` 与 APM
  `GET_SPF_STATE == 1`（提案 §4.2）。
- 时钟门控寄存器写权仍按 R-01 归 audio；power 只记账，不代写。QUP15 GCC 若走正式路径，
  必须先在 need 里登记 `K60VoteResourceQup15Gcc`，否则只能算诊断探针。
