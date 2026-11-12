# 调研原始记录

这些是 2026-11-08 那批 teammate（`bt-porter`、`gpu-rebaser`、`power-porter` 等）
留下的原始调研输出。它们原本住在 `<workspace>/scratch/`，不在版本控制里，
随时可能被清理，而且后续几轮完全没被引用过。

2026-11-12 按铁则 8（subagent 交付物必须落库并应用）归档进来，原名改成语义名。

## 文件

| 文件 | 原文件名 | 内容 |
|---|---|---|
| `bluetooth-kext-family-comparison.txt` | `BTCMP.txt` | 20G81(iOS 16.6.1) vs 21H461(iPadOS 17.7.11) 蓝牙家族符号数量对比 |
| `bluetooth-kext-symbol-detail.txt` | `BTCMP2.txt` | 关键蓝牙 kext / 符号逐个对比 |
| `bluetooth-pong-branch-search.txt` | `BTRESEARCH.txt` | 在 Pong 的 iOS 18 分支里搜蓝牙的结果 |
| `bluetooth-kernel-strings-wide.txt` | `BTWIDE.txt` | 两个内核里所有含 Bluetooth 的字符串（去重） |
| `buttons-pong-note.txt` | `PONGBTN.txt` | 按键相关短记录 |
| `buttons-pong-keys.txt` | `PONGBTN2.txt` | Pong 的按键实现 |
| `touch-gpu-notes.txt` | `TOUCHGPU.txt` | 触摸与 GPU 的交叉记录 |
| `gpu-keys-notes.txt` | `GPUKEYS.txt` | GPU 与实体键 |
| `springboard-truth.txt` | `SBTRUTH.txt` | SpringBoard 在 20G81 上的真实依赖 |

## 注意

这些是**原始输出**，没有整理过结论。要用于决策前先读一遍并提炼到对应的
`docs/research/<领域>/RESEARCH.md`。放在这里只是保证它们不会丢。
