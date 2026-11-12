# 上下游分工

> 日期：2026-11-12
> 依据：yibiya 近 300 个提交的领域分布统计（见下）

---

## 一、为什么需要分工

yibiya 平均每几分钟提交一次。**他正在修的组件，我们重写就是浪费**；我们该做的是
pick 他的成果，把力气花在他没碰的地方。

## 二、他的领域分布（近 300 提交）

| 领域 | 提交数 | 说明 |
|---|---|---|
| 文档 | 181 | 最多，但价值低 |
| **启动链** | **102** | 他最投入的地方 |
| **GPU/Metal** | **56** | 第二投入 |
| XNU 补丁 | 51 | |
| **显示** | **39** | |
| 框架 CLI | 34 | `scripts/unixnu/` |
| CI | 26 | |
| UEFI 固件 | 25 | |
| UFS/存储 | 17 | |
| 触摸 | 16 | |
| ADT/DT | 14 | |
| WiFi | 7 | 弱 |
| 按键 | 4 | 弱 |
| USB | 4 | 弱 |
| **电池/PMIC** | **3** | **几乎没碰** |
| **音频/DSP** | **2** | **几乎没碰** |

## 三、分工结论

### 他主攻 → 我们只 pick，不重写

```
启动链      patches/xnu/039x-040x, 0600, configs/, board.toml
GPU/Metal   drivers/PongAdreno, PongMetal, NativeMetal
显示        display-composition, MiniIOMobileFramebuffer
XNU 通用    框架 CLI, devicetree.py
触摸        pong-touch-console
ADT/DT      [adt.arm-io.*] 转换
UFS         NativeUfs 属性类型
```

### 我们主攻 → 他的空白，且我们已有调研

| 领域 | 他的提交数 | 我们的基础 | 八步进度 |
|---|---|---|---|
| **电池 / PMIC** | 3 | `docs/research/battery/RESEARCH.md`（③④⑤⑥⑦ 已有） | 5/7 |
| **音频 / DSP** | 2 | `docs/research/audio/RESEARCH.md`（①-⑥ 已有） | 5/8 |
| **WiFi** | 7 | `docs/research/wifi/RESEARCH.md`（①-⑥ 已有） | 5/8 |
| **USB** | 4 | 无 | 0/8 |
| **按键** | 4 | 诊断已就绪（实测 `power=1 up=1 down=1`） | 4/8 |

**这三个（电池/音频/WiFi）的调研已经做完了 ①②③④⑤⑥，正好是他不管的地方。**

## 四、跟进机制

```
scripts/watch-upstream.py              增量报告（只报新的，自动分类）
scripts/watch-upstream.py --mark       记录基线
scripts/watch-upstream.py --loop 300   每 5 分钟轮询
```

分类规则见脚本里的 `RULES`：boot / touch / gpu / battery / audio / input /
build / docs，按 `WEIGHT` 排序，**文档类排最后不占注意力**。

研判台账：`docs/research/UPSTREAM-TRIAGE.toml`
门禁：`scripts/check-upstream-triage.py`（铁则 6）

## 五、已 pick 清单

| 上游提交 | 内容 | 方式 |
|---|---|---|
| `c80e0e1` | 触摸驱动重写 | 手工（cc584ca） |
| `04a819c` | 握手 / config / 坐标模式 | 手工重写 |
| `04bda86` | 1488 字节 config 确认 | 部分采纳 |
| `1e1a70e` | `[adt.arm-io.*]` 生效 | 直接取 devicetree.py |
| `182c0a2` | CPU/UFS 属性类型 + handoff 测试 | 直接取 devicetree.py + 测试 |
| `ffb9fb7` | bootimg 回归测试思路 | 重写为 `test-bootimg-layout.py` |
| `0401` 系列 | 三个 init blob | 直接取补丁 |

## 六、待 pick

| 上游提交 | 内容 | 状态 |
|---|---|---|
| `e7391cb` | native lockscreen 保持锁定 | 未评估 |
| `810eecb` | ADT contract omissions 文档 | 未评估 |
| `9a32b61` | CPU/UFS handoff 文档 | 未评估 |
| `0600-k60-display-composition.patch` | 显示合成 | 已取文件，待构建验证 |
| `PongPower/*` 13 个文件 | 电池栈 | 待评估（我们主攻方向） |

---

## 仓库覆盖与跟进机制（2026-11-12 核实）

### 三个层次，覆盖范围不同

| 机制 | 脚本 | 覆盖 | 频率 |
|---|---|---|---|
| **跟踪** | `track-upstream-branches.py` | **23 个仓库，全部分支** | 每 4 小时 `:10` |
| **同步** | `sync-all-repos-v2.sh` | **48 个仓库**（A 6 / B 11 / C 7） | 每 4 小时 `:10` |
| **pick** | `pick-upstream.py` | **3 个**（yibiya 的 UniXNU-mondrian / UniXNU / uefi-mondrian） | 每 30 分钟 |

### 为什么 pick 只覆盖三个

**fork ≠ 参考实现。**

| 类型 | 仓库 | 关系 | 做法 |
|---|---|---|---|
| Fork | `yibiya/UniXNU-mondrian`、`yibiya/UniXNU`、`yibiya/uefi-mondrian` | 同一项目的不同分支 | **pick**（文件能直接用）|
| 参考实现 | `UniXNU-pong`、`UniXNU-sheng`、`UniXNU-zizhan`、`phk110-port`、`AdrenoMetal`、`QcomGeniSpi`、`uefi-pong`、`pong-*` | **不同代码库** | **① 同型**（读、理解、改写）|

对参考实现做 pick 是错的：它们的文件结构和我们的不同，直接复制会把别人的架构塞进来，
而且会在 `git apply` / 编译阶段以难以诊断的方式失败。

### 真实空缺

参考仓库的变更**被跟踪到了**，但没有任何机制把它们转成 ① 同型调研。
`research-gate.py` 要求 `SOURCES.toml` 每条源有 `examined` + `finding` —— 那是正确入口，
但它只在**手工添加源**时生效。

**所以：23 个仓库的新提交会被报告，只有 yibiya 三个会被自动取用，
其余 20 个需要人工判断要不要读。**

这是设计选择，不是遗漏：自动 pick 一个参考实现和自动 pick 一个 fork 是完全不同的操作。
但「报告了新提交 → 没人读」这个风险是真实的，处理方式是每次报告里对参考仓库的
硬件相关提交给出一句判断，而不是攒着。

### 覆盖清单（23 个被跟踪的仓库）

```
fork（pick）:      yibiya-upstream(8 分支) yibiya-unixnu-upstream(5) yibiya-uefi-upstream(2)
Pong 系列:         UniXNU-pong(8) pong-unixnu-upstream(14) pong-power(3) pong-wifi(3)
                   pong-ufs(3) pong-usb(3) pong-adreno(3) pong-metal(3) pong-ram-block(2)
Sheng:             UniXNU-sheng(5) UniXNU-sheng-upstream(5)
其它参考:          UniXNU-upstream(3) UniXNU-zizhan(2) phk110-port(4)
                   AdrenoMetal(3) QcomGeniSpi(2) uefi-pong(7)
我们自己的:        UniXNU-mondrian(3) UniXNU-sm8475-common(1)
```
