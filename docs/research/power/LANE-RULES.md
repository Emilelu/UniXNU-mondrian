# 电源线内规则（Lead 裁定）

状态：生效，2026-11-21。本页是电源线跨线边界与提交纪律的唯一落点；技术细节留在各专题页。
规则变更须 Lead 明确裁定。

## R-01 音频时钟门控：audio 消费 / power 记账

**裁定**：TX SoundWire master 的 clock gating 寄存器写权归 audio；power 只记「谁投了票、投了几次」，
不写、不代写音频时钟。

- audio 是唯一写者。audio 在 PAS1 租约有效后自行请求/开关时钟；PAS1 只证明 `/chosen` 里
  `k60-adsp-glink-handoff` 可解析且租约有效，不证明音频域可用
  （`docs/research/power/00-POWER-PAGE-CONFORMANCE.md:17` 已把 codec/bus/clock/routing 委派给音频分支）。
- power 侧没有音频时钟写路径：`K60PmicRail` 只读 DRV-2/cmd-db，`K60PowerVotePlan` 是
  16 资源 × 32 owner 的纯记账，`K60RailPlan` 只生成顺序；三者的授权边界在
  `docs/research/power/03-POWER-VOTES.md` §2 与 `07-RAIL-ORDERING.md` §2/§4。
- power 记账的字段是 owner 位图和引用计数；**当前没有时间字段**。要落「什么时候」，
  必须先给 `K60PowerVotePlan` 加单调时钟并补 host 断言，不能只在文档里写「已记录时间」。
- 若音频时钟最终要经过 RSC/TCS，走 HR-01 扩权流程（单次、白名单、失败回滚），
  不得借 vote ledger 绕过；`0x17a00000` 仍绝对禁止。
- 对侧义务：audio 必须在其自己的契约表写同一条「audio 写、power 记账」，
  不得把这条写进 power 文档；本页是 power 侧唯一落点。两边的表必须同义；
  冲突时由 Lead 裁定，不互相改表。
- 当前证据：`docs/research/audio/RESEARCH.md:164-165` 给出 TX core clock `0x30c` 与
  「VA macro 和 TX macro 都要打开 TX SoundWire master 的时钟门控」；
  `:176` 的 Pong `0x6d30000`/`gpio108`/`ldob15` 对 K60 未确认。
  本仓库 `drivers/` 目前没有音频时钟门控实现。

读法：power 侧查 `07-RAIL-ORDERING.md` §2 的「音频时钟门控」行；audio 侧查其契约表。

## R-02 归属提交边界

**裁定**：204 条未归属路径的 41 条 pattern 一次性提交；只加 area/owner，不改脚本行为。

- 提交信息必须写明 `ownership only, no behavior change`。
- `porting.toml:76` 的 cpu evidence 悬空引用 `drivers/armcpu-darwin24/ArmCpu.cpp`
  是独立缺陷，不得混入这 41 条提交；恢复文件或换引用另开提交。
- 验收：`PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python3 scripts/check-porting-paths.py --quiet`
  从 `FAILED: 205 problem(s)` 降到 `FAILED: 1 problem(s)`，唯一剩余就是上述 cpu 引用；
  既有「pattern 未命中任何文件」警告不因这 41 条新增。
- 逐路径清单与 41 条 pattern 原文在 `docs/research/PORTING-OWNER-MAP.tsv` / `.md`；
  area 与 owner 只作审查归属，不改变文件内容或运行行为。

## R-03 与 Lead / 其他 agent 的通信顺序

**裁定**：发消息一律先 `steer`；只有被拒（目标 idle / 不适用 steer）才改 `followup`。
不要反过来，也不要因为怕被拒直接 followup。

- 用 `send_agent_message`，`mode: "steer"` 先试；返回明确说明 steer 被拒时，
  才用同内容 `mode: "followup"` 重发。
- 每次覆盖 `reply-*.md` 时保留首行 `delivery: ...`；它是 Lead 的投递标记，
  不属于本轮正文。只替换首行之后的正文。
- 该规则同样适用于给 audio 等其它线的消息：先 steer，被拒才 followup。

## 参考

- Lead 裁定：2026-11-21（本轮）。
- 页面委派：`docs/research/power/00-POWER-PAGE-CONFORMANCE.md:17`。
- 写路径表：`docs/research/power/07-RAIL-ORDERING.md` §2；HR-01：`docs/ops/HARD-RULES.md:24-72`。
- 音频事实：`docs/research/audio/RESEARCH.md:164-176`。
- 归属清单：`docs/research/PORTING-OWNER-MAP.md`。
