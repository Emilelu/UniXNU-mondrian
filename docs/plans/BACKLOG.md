# 白天待办（2026-11-12 整理）

> **规则**：本文件不写死任何上游 SHA。上游随时会推进，
> 硬编码的 SHA 第二天就过时。所有「取上游最新」的项都写成查询命令，
> 执行时现查现取。见 ★37。

---

## 一、上游追平（全部动态）

### 1.1 yibiya fork

```bash
# 查所有分支最新状态
python3 /mnt/e/k60-work/scripts/track-upstream-branches.py 2>&1 | grep -A6 'yibiya-upstream'

# 查某个分支相对我们的未取提交
wsl -u root -e bash -c "cd /mnt/e/hackios/UniXNU-mondrian && \
  git fetch yibiya --prune && \
  git log --oneline main..yibiya/fix/touch-gpu-bringup | head -20"
```

**已知需关注的方向**（不绑定 SHA）：
- `fix/touch-gpu-bringup` 分支上，触摸握手 / GPU RSC 的后续修复
- 他们记录「未硬件验证」的 porting.toml 变更 —— 这类记录要读，
  但不要整份覆盖我们的 14-area 版本，只取 limits/next_action 的措辞

**判断标准**：涉及 K60/SM8475 硬件、启动链、与
`docs/research/EIGHT-STEPS.toml` 里 ⑦ 未通过项相关 → 取；纯文档 → 读但不取。

### 1.2 Pong（14 个仓库）

```bash
for r in UniXNU-pong pong-adreno pong-adreno-metal pong-arm-cpu \
         pong-arm-dt-platform pong-boot-capture pong-darwin-boot24 \
         pong-metal pong-power pong-ram-block pong-ufs pong-usb \
         pong-wifi uefi-pong; do
  d=/mnt/e/k60-work/references/$r
  [ -d "$d/.git" ] || continue
  echo "=== $r ==="
  git -C "$d" log --oneline --all --since='3 days ago' | head -5
done
```

**已知需关注的方向**（不绑定 SHA）：
- `port/ios18e-native-302` 分支：Pong 的 native22G100 系列，
  包含基带（`PongBasebandService.cpp`）、音频（`PongWcd938.h` + `PongAdsp.cpp`）、
  Glyph（`PongGlyph.cpp` AW20036）
- `pong-ufs` 的该分支相对我们 S3 版本的差异
- `pong-metal` 的 `NativeBridgeMetalFrontend.mm`（166 KB，我们的 1.5 倍）

### 1.3 UniXNU 官方

```bash
python3 /mnt/e/k60-work/scripts/track-upstream-branches.py 2>&1 | \
  grep -A4 'AdrenoMetal\|ShengUfs\|UniXNU-upstream'
```

**已知需关注的方向**：
- `UniXNU/AdrenoMetal`：24 小时内 8 个 perf/diag 提交，仍在推进
- `UniXNU/ShengUfs`：`VerifiedTableCache.h` / `CompletionWait.h`（纯逻辑，可移植）
- `UniXNU/UniXNU`：`components.toml` 是否新增组件

---

## 二、按优先级排序的实现工作

### P0 — 触摸 ⑦ 核验（卡住刷机的唯一原因）

当前 `docs/research/EIGHT-STEPS.toml` 里 touch 的 ⑦ 只有 `static_check`，
`unit_test` 和 `artifact_check` 为空，八步门禁因此拒绝刷机。

要补的三件：
1. **离线单测**：用 `references/phk110-port/docs/phk110/waves/wave12c-electrical.md`
   里记录的原始字节序列（`a5 10 1c 00 01 01 53 33 39` 等）喂我们的 BRL 解析函数，
   验证触点计数解析正确
2. **产物检查**：确认 `0340` 里嵌入的 UI 库与 `userland/touch.c` 源码一致
3. **节拍验证**：静态核对 `sleep_ms(20)` 分支在 INT 高/低两种情况下都走到

### P1 — GPU Metal 用户态追平

见 [`GPU-TODO.md`](GPU-TODO.md) 的 P0–P3。

### P2 — UFS 对齐官方架构

移植 `VerifiedTableCache.h` + `CompletionWait.h`（纯逻辑，不含平台地址）。
`NativeUfs.cpp` 不能整体替换（SM8550 硬编码），只能按能力逐块对齐。

### P3 — 全新子系统（Pong 已有完整实现）

| 子系统 | Pong 的实现 | 我们的状态 |
|---|---|---|
| 基带 | `PongBasebandService.cpp` 1,070 行 + 15 个配套头 | `porting.toml` = planned |
| 音频 | `PongWcd938.h` 121 行 + `PongAdsp.cpp` + `PongAudio.cpp` | planned |
| Glyph | `PongGlyph.cpp` 115 行（AW20036）| 无 |
| WiFi | `PongWifiFirmware.cpp` 76 行 | planned |

**顺序**：WiFi（风险最低）→ 音频 → Glyph → 基带（最高风险，涉及 PAS 固件与 persist 分区）。

---

## 三、每次动手前的固定动作

```bash
# 1. 查上游有没有新东西
python3 /mnt/e/k60-work/scripts/track-upstream-branches.py

# 2. 查研究门禁要求读什么
python3 /mnt/e/hackios/UniXNU-mondrian/scripts/research-gate.py

# 3. 查八步走到哪
python3 /mnt/e/hackios/UniXNU-mondrian/scripts/eight-step-gate.py --build

# 4. 查文档是否同步
python3 /mnt/e/hackios/UniXNU-mondrian/scripts/check-docs.py
```

四道全绿才能开始写代码。
