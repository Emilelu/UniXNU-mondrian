# 先例覆盖率的真实数字（2026-11-23 实测）

冻结期审计。问题：`PRECEDENT-MANIFEST.toml` 写着 **1527 条 / 0 unknown**，这个数字到底覆盖了什么？

## 1 旧口径覆盖的是什么

`scripts/scan-precedents.py` 的 `patches()` 每个仓库只走 `LAYOUT` 里那**一个**补丁目录（多数是 `patches/xnu-12377`，t970/zizhan/pong 各走自己的一个），`board_keys()` 只记录键名（`flatten()` 丢掉值），defconfig 也只记键名。所以「0 unknown」的含义是：**我们构建配方读取的那一个目录里、我们列出的那几类条目**都判过了，不是「每个仓库的每个补丁文件都判过了」。

## 2 新口径的实测

`scripts/audit-precedent-coverage.py`（新增）递归枚举每个仓库 `patches/**/*.patch`，按文件名**或** sha256 与账本匹配（改名也算），结果：

| 仓库 | 补丁文件 | 账本内(按名) | 账本内(按哈希) | 未入账 |
| --- | ---: | ---: | ---: | ---: |
| asteroids | 21 | 20 | 0 | **1** |
| uke | 90 | 67 | 0 | **23** |
| cupid | 14 | 11 | 0 | **3** |
| vermeer | 5 | 5 | 0 | 0 |
| sheng | 28 | 28 | 0 | 0 |
| t970 | 229 | 169 | 0 | **60** |
| zizhan | 49 | 34 | 0 | **15** |
| pong | 93 | 28 | 0 | **65** |
| 本仓库(ios16 线，非先例) | 394 | 280 | 2 | 112 |
| **合计** | **923** | | | **279** |

排除本仓库自己的 112 个，**先例仓库有 167 个补丁文件从未被判过**。

## 3 167 个的构成

- **140 个是 GPU 翻译层**：`patches/mesa/**` 与 `patches/metal2vulkan/**`（t970 60 个里 59 个、zizhan 15 个全部、pong 65 个全部）。stage-0 27 配方不启用 Vulkan 翻译层，`docs/engineering/IOS-SCOPE.md` 已把 16 线的 `patches/metal2vulkan` 迭代列为停止项；这批要等 GPU 线重开时逐条判，现在既不能说「不需要」也不能说「已抄」。
- **27 个非 GPU**：`uke` 23 个 upstream 补丁、`cupid` 3 个（darwinboot 日志窗口失败、entry-probe 跳过 nm 头、ramdisk 在 initrd 里找 FAT）、`asteroids` 1 个（`zzzzzzzzzz-ios27-dataconst-room.patch`）、`t970` 1 个（`0001-t970-rootlayout-pinned-shngroot.patch`）。这 27 个已派子代理逐条判定（交付 `/mnt/e/k60-work/scratch/precedent-gap-verdicts.toml`），判据要求每条给出我们树里的 `file:line` 或明确的不适用理由，不允许 `deferred`。

## 4 门禁

`scripts/audit-precedent-coverage.py` 未入账即退 1（本仓库除外，自己的 27 系列不算先例）。`--json` 给机器可读明细，`--verbose` 按目录聚合。

## 5 还没做的（下一步）

`board.toml` 与 defconfig 的**值**没有对账：旧账本只记键名，所以「两边都有这个键、值不同」这类疏漏目前看不见。审计脚本已经统计 `board_pairs` / `defconfig_pairs`（带值），但还没有与「应该相同」的语义表比对。
