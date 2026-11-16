# WiFi 显式 flash 门禁提案

状态：**未应用、未集成，c8 HOLD**。本提案只交付可审查补丁与主机反例；不构建、不上机，也没有修改活动 gate、八步状态或 done 字段。

## 已核对的缺口

- [eight-step-gate.py](<../../../scripts/eight-step-gate.py#L116>) 先筛 active；[EIGHT-STEPS.toml](<../EIGHT-STEPS.toml#L390>) 的 WiFi 是 parked，因此现有 `--flash` 会跳过 WiFi。
- [eight-step-gate.py](<../../../scripts/eight-step-gate.py#L125>) 只在 build 模式解析 `K60_EIGHT_STEP_ITEMS`；[build-strict.sh](<../../../scripts/build-strict.sh#L149>) 运行 `--build`，manifest 的默认 `eight_step_items=all` 不能证明 WiFi 被 flash 检查覆盖。
- 实际 c8 构建 wrapper [run-c8.sh:110–113](<E:/k60-work/scratch/run-c8.sh#L110-L113>) 调用 strict build，没有运行显式 WiFi flash gate。本提案没有修改这个 wrapper。
- [eight-step-gate.py](<../../../scripts/eight-step-gate.py#L175>) 的⑧只要求 success/failure 非空；当前 WiFi ⑦仍是旧核验，⑧没有 prediction。补丁应用后的真实 WiFi记录应保持拒绝，不能为 c8 放行。

## 未应用补丁的语义

[wifi-eight-step-gate.patch](<../../../scripts/proposals/wifi-eight-step-gate.patch>) 只修改 gate：

1. `--flash` 必须声明 `K60_FLASH_ITEMS`，拒绝未知、空、部分空或重复范围。
2. 检查集合为 `active 全机底线 ∪ 显式目标`。显式 `wifi` 会把 parked WiFi纳入，不能用范围跳过其他 active项。build 的原有声明保持原行为。
3. 只要设置 `K60_FLASH_OBSERVATION`，显式范围就必须包含 `wifi`。WiFi入选后这个标识必须非空且仅含字母、数字、点、下划线、短横线。
4. WiFi ①–⑦照原规则检查；⑦的 local_verified/static_check/unit_test/artifact_check 仍必须齐全。
5. WiFi⑦的 `observation` 与⑧ prediction的 `observation` 必须均精确等于本次 `K60_FLASH_OBSERVATION`，且两者各自有 `reference`。旧 observation、缺 observation或无可核查引用都拒绝；⑧ success/failure仍必须齐全。
6. 本提案的“旧”指相对本次目标观察标识不一致，不是任意墙钟 TTL。标识不能自行证明资料真实或适用于该镜像。`has_reference` 仅做引用形状的语法检查，不确认文件存在、行号有效、内容真实或与镜像相符；测试夹具的引用字符串不作为项目证据。实际绑定仍由下节的 wrapper 审核承担。

新增字段示意，仅说明格式，不替当前记录填绿：

```toml
[hardware.wifi.step.verify]
# 既有 done/local_verified/evidence/static_check/unit_test/artifact_check 仍必需
observation = "wifi-YYYYMMDD-purpose-revision"
reference = "docs/research/wifi/LOCAL-VERIFICATION.md:123"

[hardware.wifi.step.device.prediction]
observation = "wifi-YYYYMMDD-purpose-revision"
reference = "docs/research/wifi/OBSERVATION-SPEC.md:45"
success = "本次单变量观察成功时应出现的具体记录"
failure = "本次观察失败时的具体记录、缺失项与判废条件"
```

## 仍阻断实际使用的镜像绑定

**gate 本身不知道即将启动的镜像包含 WiFi。** 可执行反例：active底线全通过、WiFi仍 parked，调用者只写 `K60_FLASH_ITEMS=display` 且不写 OBS，gate仍可能通过并漏掉 WiFi。测试用同义 active项 touch演示此边界。显式范围字符串不等于真实镜像目标；现有 wrapper尚未修复。

未来 boot wrapper必须在任何设备动作之前完成以下绑定，缺任一项保持阻断：

1. 接受唯一 boot image和对应 manifest；验证目标镜像 SHA256与 manifest记录一致，禁止环境变量声明覆盖目标身份。
2. 由被验证的 manifest中的 WiFi archive/配置/参数及镜像核验结果判定该图含 WiFi。含 WiFi就必须纳入 `wifi`；未知目标或缺 scope失败。仅凭构建名称不能判定。
3. 从本次已审查的观察规格取得 observation ID，并把镜像摘要/完整 source revision/参数/归档摘要/核验报告引用与该 ID绑定。⑦和⑧必须同一个 ID；不能把旧 ID整段复制到新图。
4. 在不放宽 active底线的前提下设置 `K60_FLASH_ITEMS=wifi` 与匹配的 `K60_FLASH_OBSERVATION`，运行真实 `--flash` 并保存退出码和完整输出；失败立即结束，设备命令不可执行。
5. 包装器反例必须覆盖“实际 WiFi图 + display scope/缺 scope/缺观察绑定”均失败。这些镜像绑定检查未包含在本最小 gate diff中，须由后续 wrapper补丁和测试实现后再审。

本提案没有把⑧ done设 true；观察预测与设备成功是两件事。c8仍 HOLD，任何主机测试通过都不授权构建或上机。

## 主机验证

执行：

```sh
python3 scripts/tests/test-wifi-flash-gate-proposal.py
```

[test-wifi-flash-gate-proposal.py](<../../../scripts/tests/test-wifi-flash-gate-proposal.py>) 先在临时树执行 `git apply --check`，再应用补丁；每个用例运行真实 patched CLI subprocess，避免 import时落入 `__main__` 后未定义的 sec代码。只 stub无关 README renderer以隔离表格状态，不 stub选择/证据/预测逻辑；TOML由每例独立夹具生成。运行前后比对活动 gate及 TOML的 SHA256。

矩阵包含正向 parked WiFi、无 active时显式 WiFi、active底线、缺/未知/空/重复范围、未选 WiFi的 OBS、缺/无效观察标识、旧/缺⑦或⑧观察、缺/无引用、逐项缺①–⑦、缺⑦三类子证据/local_verified、缺⑧ success/failure，以及不带镜像绑定的漏选反例。

最终主机验证：37例全部通过，活动 gate与 TOML的 SHA256前后不变。临时树中 `git apply --check` 与应用均成功。没有执行构建、flash或boot。
