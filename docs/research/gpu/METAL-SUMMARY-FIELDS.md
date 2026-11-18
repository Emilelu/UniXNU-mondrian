# Metal 汇总行字段（P-231）

`Pong Metal: S …` 这一行是**唯一**的 Metal 进度判据，字段必须从格式串读，不能按位置猜。
格式串在 `drivers/PongMetal/NativeBridgeMetalFrontend.mm:1604`：

```c
"S c%llu/%llu d%llu p%llu x%llu R%llu D%llu F%llu M%lluk C%llu B%llu"
```

| 字段 | 变量 | 含义 |
|---|---|---|
| `c` | `gCommits`/`gCommitFailures` | command buffer **提交**次数 / 提交失败次数 |
| `d` | `gCompleted` | 完成回调次数 |
| `p` | `gPipelines` | 管线数 |
| `x` | `gProblems` | `noteProblem()` 计数 |
| `R` | `gPasses` | render pass 数 |
| `D` | `gDraws` | draw 调用数 |
| `F` | `gFullScreenPasses` | 全屏 pass 数 |
| `M` | `gBiggestPass>>10` | 最大 pass 大小（**KB**） |
| `C` | `gDispatches` | compute dispatch 数 |
| `B` | `gBlits` | blit 数 |

## 判定规则

1. **`c` 是唯一能证明 Metal 真出帧的字段**：`c0/0` = 一次都没 commit，此时无论 `D`/`F`/`M` 多大都没有帧。
2. `K60 DISPLAY: first frame presented` + `MiniIOSurface: N big surfaces made` 是**软件合成兜底**，不是 Metal 成功；只有 `c>0` 才算 Metal 里程碑。
3. 任何“字段含义”结论必须先 `grep` 格式串并在文档里对表（本文件的表由 `scripts/tests/test-metal-trace-semantics.py` 守卫）。
4. 同一镜像两次结果不同 ⇒ 单次上机只能证明存在性，不能证明稳定性；稳定性判据至少连续两次同镜像同判据一致。
