# PRIOR-ART-FIRST：写代码前先调研

> 2026-10-28 立规。任何"实现某功能 / 写某驱动 / 打某补丁"之前，**先调研现有仓库和分支**，确认没人做过、或确认能复用/适配，再动手。禁止直接开写。

## 为什么立这条

ios-sweet-k60 的教训：我们这边正准备自己写 K60 的 GPU GMU、显示 canvas、触摸映射、ADT 生成，而 `XTOM0706/ios-sweet-k60` 已经有 **K60 (mondrian/SM8475) 的完整实现**（Adreno 730 GMU M1–M3、1125×2436 canvas、Goodix m11a SPI 触摸、K60 ADT、裸机 shim）。差点重复造轮子。

## 调研范围（每次至少过一遍）

| 仓库 | 用途 | 分支 |
|---|---|---|
| `XTOM0706/ios-sweet-k60` | K60 的 HackiOS/ios-sweet 移植（最相关） | `main`、`fb-probe`、`cache-ci` |
| `dipa-studio/ios-sweet` | 上游 sweet（SM7150）原版 | `main` |
| `UniXNU/UniXNU` | 我们的 core | `main` |
| `Chengdong-Yu/UniXNU-pong` | 我们的 pong 基座 | `main` |
| `UniXNU/UniXNU-sheng` / `UniXNU/UniXNU-liuqin` | 其他设备参考 | `main` |
| `blacktop/darwin-xnu-build` | macOS CI 构建脚本 | `main` |
| `Chengdong-Yu/uefi-pong` | pong UEFI 参考 | `main` |
| `Emilelu/UniXNU-mondrian` / `Emilelu/uefi-mondrian` | 我们自己的仓 | `main`、`k60` |

> 新发现的仓库/分支，追加到本表。

## 步骤（每次功能开工前）

1. **同步**：`bash /mnt/d/Android/k60-ios/sync-refs.sh`（clone/fetch 全部仓库 + 列出分支 + 最近提交）。
2. **看更新**：对每个仓库 `git log --all --since=<上次调研日期> --oneline`，重点看 `k60-*`、`sweet-*`、`prelink`、`adreno`、`panel`、`touch`、`ufs`、`adt` 关键词。
3. **搜代码**：`git grep -n <关键词> $(git rev-list --all)` 或 `gh search code`；补丁目录直接 `grep -rn`。
4. **看分支**：`git branch -a`，对可疑分支 `git log main..<branch>` 看差异。
5. **记录**：写 `deliverables/prior-art/<feature>.md`：
   - 找到什么（repo/branch/file:line）；
   - 是否兼容（XNU 版本、machine config、boot 链、SoC）；
   - 许可证状态；
   - 结论：**直接复用 / 适配 / 自研**，以及理由。
6. **决策门**：没有这份记录，不开工。若自研，在记录里写清"为什么现有实现不能用"。

## 许可证规则

- **硬件事实/常量/寄存器图**：可自由参考（事实不受版权保护）。
- **代码/补丁/脚本**：必须看 LICENSE；**没有 LICENSE 的仓库默认保留所有权利**，整段复制前先联系作者拿许可，或只做"读思路、自己重写"。
- 记录里必须写"许可证状态"一栏。

## 当前已应用

- **prelink `--slide=auto`**（2026-10-28）：查过 `UniXNU/UniXNU` 的 `kits/XnuPrelink`，最后改动 10-24，无 slide 修复；`ios-sweet-k60` 不用 prelink。→ 结论：**自研**（记录见 board 2026-10-28 10:37）。
- **K60 GPU/显示/触摸/ADT**：`ios-sweet-k60` 有实现，待逐项评估"适配 vs 自研"（许可证：该仓无 LICENSE，需联系作者）。