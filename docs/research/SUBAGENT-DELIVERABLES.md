# Subagent 交付物台账

> 为什么有这张表（P-150）：派出去的 subagent 产出的调研报告，如果不立刻落进仓库，
> 就会随着上下文压缩一起消失，下一轮又从零开始调研 —— 同一件事调查三遍。
>
> 但「落库」还不够。落库了也可能被忘掉：文件写好了，改动没做，等于没查。
> 所以每条记录还带一列 **产出断言** —— 一句门禁能机器验证的话，
> 用来证明「这份调研派生出的改动真的在树上」。
>
> ## 规则（AGENTS.md 铁则 8）
>
> 1. 派出 subagent 时立刻登记一行，状态 `running`
> 2. subagent 返回后，**同一轮内**把结论写进 `落库文件`
> 3. 同时填 `产出断言`，必须是能失败的一句话：
>    - `file:drivers/PongPower/K60Battery.cpp` 文件存在且非空
>    - `grep:configs/mondrian_defconfig:CONFIG_XNU_K60_PHYSICAL_BATTERY=y` 文件里含这行
>    - `series:0602-k60-physical-battery.patch` series 里有这条
>    - `git:drivers/NativeUfs/CompletionWait.h` 已被 git 跟踪
> 4. 状态改 `landed` 时填 `落库提交`
> 5. **断言不成立 = 门禁失败**。调研写了但改动没做，构建就不过。

---

## 当前

| 编号 | 任务 | 派发时间 | 落库文件 | 产出断言 | 状态 | 落库提交 |
|---|---|---|---|---|---|---|
| SA-01 | 电池栈构建集成调研 | 2026-11-12 11:35 | `docs/engineering/BATTERY-INTEGRATION.md` | `grep:configs/mondrian_defconfig:CONFIG_XNU_K60_PHYSICAL_BATTERY` | landed | PENDING |
| SA-02 | 音频/DSP 栈差距调研 | 2026-11-12 11:36 | `docs/research/audio/GAP-ANALYSIS.md` | `grep:docs/research/audio/GAP-ANALYSIS.md:PAS1` | landed | PENDING |
| SA-03 | WiFi 实现差距调研 | 2026-11-12 11:37 | `docs/research/wifi/GAP-ANALYSIS.md` | `file:docs/research/wifi/FIRMWARE.md` | landed | PENDING |
| SA-CONFIG-CONSISTENCY | defconfig vs generated .config checker | 2026-11-12 19:35 | `docs/research/evidence/SA-CONFIG-CONSISTENCY.md` | `grep:docs/research/evidence/SA-CONFIG-CONSISTENCY.md:.config` | landed | `faacc2d` |
| SA-BOOT-EVIDENCE | boot evidence audit: battery image reached SpringBoard, k60_touch_se=19 killed touch | 2026-11-12 19:35 | `docs/research/evidence/SA-BOOT-EVIDENCE-20261112.md` | `grep:docs/research/evidence/SA-BOOT-EVIDENCE-20261112.md:k60_touch_se` | landed | `faacc2d` |
| SA-CELLULAR | cellular 线第一阶段只读取证：Android 侧 modem/QRTR/IPA 清单、活 FDT 字节级真相、范围判定、X65 封装归属 | 2026-11-14 11:08 | `docs/research/cellular/02-DT-TRUTH.md` | `grep:porting.toml:0x13200000` | landed | `06e266b` |

## 已落库并应用

| 编号 | 任务 | 落库文件 | 产出断言 | 落库提交 |
|---|---|---|---|---|
| — | （暂无） | — | — | — |

---

## 反面教材（调研做了但没落库，或落库了但没应用）

| 调研内容 | 做了什么 | 结果 | 本可避免的方式 |
|---|---|---|---|
| `0403` 固件补丁 | 读完、验了 sha256、算出 1627/1609/1488/1486 的来源 | 只写进 PITFALLS，没接进构建，后来又回退 | 断言 `series:0403-k60-goodix-fw.patch` 早就会暴露「没接进构建」 |
| `Ath12kWifi` 适配性 | 读完 `nw_abi.h` + `nw_wifi.c`，判定不能驱动 QCA6490 | 写进 RESEARCH.md，但没转成任何改动 | 断言 `file:drivers/PongWifi/nw_abi.h` 会要求真的把 ABI 落成代码 |
| `1e1a70e` ADT 修复 | 早几个小时就看到了 | 拖到最后才取，中间在 DTS 上绕了好几圈 | 断言 `grep:<devicetree.py>:configured_hardware` 会早早要求取回 |
| 上游 13 个分支 | 列全了分支和提交 | 只「报告」，一个都没 pick，直到被追问 | 断言 `series:0401-k60-embedded-init.patch` 会要求真的取进来 |

**共同模式**：调研 → 写一段文档 → 继续在别处瞎试。文档写了但没变成改动。
产出断言就是为了堵这个：**没有改动，构建不过。**

---

## 历史遗留（2026-11-08 那批 teammate，落库于 2026-11-12）

这批 teammate 当时产出了 ~560 KB 调研，但全部留在 `scratch/`，不在版本控制里，
后续几轮完全没被引用。按铁则 8 补做落库。

| 编号 | 任务 | 落库文件 | 产出断言 | 状态 | 落库提交 |
|---|---|---|---|---|---|
| SA-BT | 蓝牙调研（bt-porter） | `docs/research/evidence/bluetooth-kext-symbol-detail.txt` | `file:docs/research/evidence/bluetooth-kext-symbol-detail.txt` | running | — |
| SA-GPU | GPU/触摸/按键（gpu-rebaser 等） | `docs/research/evidence/touch-gpu-notes.txt` | `file:docs/research/evidence/touch-gpu-notes.txt` | running | — |
| SA-SB | SpringBoard 真相 | `docs/research/evidence/springboard-truth.txt` | `file:docs/research/evidence/springboard-truth.txt` | running | — |

**注意**：这三条的 `状态` 现在是 running 而不是 landed —— 因为原始输出落库了，
但「提炼成结论并用于决策」这一步还没做。门禁会在 6 小时后提醒。
真正 landed 的条件是：读一遍、把结论写进对应 `RESEARCH.md`、填上 sha。
