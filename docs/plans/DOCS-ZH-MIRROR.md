# DOCS-ZH-MIRROR：UniXNU 中文文档镜像完整性核对（369 vs 369）

> 核对日期：2026-11-08
> 源仓库：`E:/hackios/UniXNU` @ `75ae626a12764c706fc0b94c52a3eea09447dbaa`
> 目标仓库：`E:/hackios/UniXNU-mondrian`（分支 `fix/k60-measured-high-window`，HEAD `db94d5283773d4348ba852021290438f234335af`）
> 核对范围：`docs/**/*.md`（排除 `docs/zh/**`）369 篇 vs `docs/zh/**/*.md` 369 篇
> 方法：`find docs -name '*.md' -not -path 'docs/zh/*'` 与 `find docs/zh -name '*.md'` 分别生成相对路径清单并排序核对；用脚本逐篇统计标题数/标题层级/代码块数/表格数/表格行数/行数比；对 19 篇结构异常文件逐篇对照全文；对 `zh/devices/mondrian*.md` 与 `zh/devices/pong*.md` 共 9 篇做专项核对。

## 0. 结论速览

1. **文件集合完整：369/369 相对路径完全一致，缺失 0、多余 0。**
2. **结构总量基本对齐：** 标题 10,928 vs 10,927，代码块 328 vs 327，表格 402 vs 402，行数 71,014 vs 70,340（99.1%）。两项差 1 均来自 `reference/cli.md` 缺失 `vendor_boot` 整节。
3. **19 篇触发 ±10% 行数比或结构不一致检查。** 逐篇通读后：17 篇只是中文排版更紧凑（英文硬换行 vs 中文长段），无内容缺失；真正有结构/内容缺口的是 `reference/cli.md` 与 `porting/device-repository.md`。另在超阈值文件 `drivers/sheng-ufs.md` 中发现 1 处技术句缺失。
4. **设备区是系统性“结构镜像、正文不翻译”：** 266 篇设备文档全部结构对齐；186 篇是单行链接桩页，80 篇有实质正文，其中 74 篇正文逐字保留英文原文（仅标题/表头等模板文字译为中文），1 篇 `devices/polaris.md` 完整翻译，5 篇源正文本身为中文。设备页 21,133 条列表项中仅 129 条（0.61%）与英文不同。
5. **结论：不能整体无条件当作“等效中文依据”。** 非设备核心文档基本可直接使用；`reference/cli.md`、`porting/device-repository.md`、`drivers/sheng-ufs.md`、`reference/output-layout.md`、`reference/troubleshooting.md` 需对照英文修正或补读。设备页内容与英文一致，但 74 篇正文仍是英文，对中文读者不等效于中文译本。`mondrian`/`pong` 9 篇专项结构 100% 对齐、正文列表项 100% 相同，可作为等效依据。

---

## ① 镜像对照统计

### 1.1 文件集合

| 项目 | 英文 `docs/` | 中文 `docs/zh/` | 差异 |
| --- | ---: | ---: | ---: |
| Markdown 文件数 | 369 | 369 | 0 |
| 相对路径完全同名 | 369 | 369 | 0 |
| 缺失文件 | — | — | **0** |
| 多余文件 | — | — | **0** |

目录分布（两边一致）：

| 目录 | 文件数 | 英文行数 | 中文行数 | 行数比（中/英） |
| --- | ---: | ---: | ---: | ---: |
| 根目录（`index.md`、`building.md`） | 2 | 397 | 386 | 0.972 |
| `concepts/` | 5 | 594 | 576 | 0.970 |
| `contributing/` | 2 | 209 | 196 | 0.938 |
| `devices/` | 266 | 59,799 | 59,784 | 1.000 |
| `drivers/` | 47 | 2,271 | 2,231 | 0.982 |
| `guide/` | 8 | 1,227 | 1,204 | 0.981 |
| `porting/` | 26 | 4,616 | 4,091 | 0.886 |
| `reference/` | 9 | 1,310 | 1,288 | 0.983 |
| `xnu/` | 4 | 591 | 584 | 0.988 |
| **合计** | **369** | **71,014** | **70,340** | **0.991** |

369 对文件全部逐篇纳入上述统计，无抽样、无跳过。

### 1.2 结构总量

| 指标 | 英文 | 中文 | 中文/英文 |
| --- | ---: | ---: | ---: |
| 总行数 | 71,014 | 70,340 | 99.1% |
| 总字节数 | 6,291,796 | 6,191,608 | 98.4% |
| ATX 标题数 | 10,928 | 10,927 | 99.99% |
| 代码块数 | 328 | 327 | 99.7% |
| 表格数 | 402 | 402 | 100% |
| 表格数据行数（含表头） | 402 张表；除 `porting/device-repository.md` 少 2 行外，其余逐表一致 | — | — |

文件级行数分布：318 篇行数完全相同，48 篇中文更少，3 篇中文更多（最大偏差仅为 `xnu/patch-reference.md` 的 +1.6%）。行数比中位数 1.000；最低 `porting/log-capture.md` 0.756，最高 `xnu/patch-reference.md` 1.016。

结构逐项一致度：

- 标题总数一致：368/369（唯一异常 `reference/cli.md`）。
- 标题层级分布一致：367/369（异常 `reference/cli.md`、`porting/device-repository.md`）。
- 代码块数一致：368/369（异常 `reference/cli.md`）。
- 表格数一致：369/369。
- 表格行数一致：368/369（异常 `porting/device-repository.md`，51 vs 49 数据行）。

### 1.3 全量技术 token 检查

- 版本号/长十六进制提交号：**英文出现的 token 在中文中缺失数为 0**；中文仅在 `porting/power.md` 多 1 个 `0.01`（单位换算示例，非冲突）。
- 行内代码标识符：21 篇存在差异，绝大多数是中文把一句里的多个 code span 合并/拆分（如 `method = "smc"` 被拆成 `method`、`smc`），或把占位符翻译成中文；真正导致技术信息缺失的见 ④。
- 表格状态列（`implemented`/`planned`/`device-verified` 等）：设备页逐行核对未发现状态差异。

---

## ② 缺失/多余清单

### 2.1 中文缺哪些

**无。369 篇英文文档全部存在同名中文文件。**

### 2.2 中文多哪些

**无。中文目录没有英文清单之外的文件。**

### 2.3 说明

唯一“缺失”发生在文件内部：`docs/zh/reference/cli.md` 缺少英文 `docs/reference/cli.md` 的 `### vendor_boot` 整节，不是文件缺失（见 ③/④）。

---

## ③ 结构性差异清单

判定口径：行数比超出 0.9–1.1，或标题层级分布、代码块数、表格数与英文不一致。共 **19 篇**。

| # | 文件 | 英文行 → 中文行（比值） | 结构差异 | 全文核对结论 |
| ---: | --- | --- | --- | --- |
| 1 | `devices/polaris.md` | 64 → 57（0.891） | 无 | 仅中文紧凑排版；内容完整，无实质差异 |
| 2 | `drivers/darwin-boot.md` | 26 → 22（0.846） | 无 | 开头段落顺序调整；内容完整 |
| 3 | `drivers/sheng-ufs.md` | 39 → 35（0.897） | 无 | **缺 1 句技术说明**（display bank / WiFi stage 1 窗口），见 ④ |
| 4 | `drivers/xnu-prelink.md` | 83 → 73（0.880） | 无 | 段落重排（技术段前置），内容完整 |
| 5 | `porting/arm64e.md` | 89 → 73（0.820） | 无 | 中文压缩表达，内容完整 |
| 6 | `porting/device-repository.md` | 505 → 480（0.950） | **标题层级：H2 11→12、H3 11→10；表格少 2 行** | 章节重排 + Board 表缺 `soc_source`/`os_profile` 两行；详见 ④ |
| 7 | `porting/display.md` | 150 → 117（0.780） | 无 | 内容完整，仅段落合并 |
| 8 | `porting/drivers.md` | 123 → 101（0.821） | 无 | 内容完整 |
| 9 | `porting/input.md` | 104 → 85（0.817） | 无 | 内容完整 |
| 10 | `porting/log-capture.md` | 225 → 170（0.756） | 无 | 内容完整，段落合并明显 |
| 11 | `porting/migration.md` | 517 → 399（0.772） | 无 | 内容完整 |
| 12 | `porting/network.md` | 121 → 102（0.843） | 无 | 内容完整 |
| 13 | `porting/packaging.md` | 171 → 141（0.825） | 无 | 内容完整 |
| 14 | `porting/platform.md` | 113 → 99（0.876） | 无 | 内容完整 |
| 15 | `porting/power.md` | 233 → 184（0.790） | 无 | 内容完整 |
| 16 | `porting/soc-support.md` | 151 → 135（0.894） | 无 | 内容完整 |
| 17 | `porting/steps.md` | 184 → 155（0.842） | 无 | 内容完整 |
| 18 | `reference/cli.md` | 171 → 165（0.965） | **标题总数 16→15；H3 10→9；代码块 11→10** | **缺 `vendor_boot` 整节**，见 ④ |
| 19 | `reference/index.md` | 59 → 53（0.898） | 无 | 内容完整 |

**结构性结论：** 19 篇中 17 篇是中文排版导致的“假差异”；真正的结构缺陷只有 `reference/cli.md`（少一节/一代码块）与 `porting/device-repository.md`（章节层级重排 + 两行表格缺失）。其余 350 篇结构指标与英文完全一致。

---

## ④ 实质性内容差异

### 4.1 高优先级：`docs/zh/reference/cli.md` 缺 `vendor_boot` 整节

英文 `docs/reference/cli.md:68-74` 有完整的 `### vendor_boot` 小节：

- 标题 `### vendor_boot`
- 代码块：`unixnu vendor_boot --stock FILE [--ramdisk FILE|none] [--ramdisk-addr ADDR] [--verify-against] [-o FILE]`
- 说明：重写原厂 `vendor_boot` v4 镜像的 vendor ramdisk；设备树、ramdisk table、bootconfig、vbmeta blob 原样复制，AVB footer 重定向；`--ramdisk-addr` 在 stock window 不足时重定位 ramdisk；`--verify-against` 先重打包原厂 ramdisk 并要求逐字节一致；输出默认在 `--stock` 旁生成 `vendor_boot.img`。

中文 `docs/zh/reference/cli.md` 从 `### bootimg` 直接跳到 `### status`，整节完全缺失（仅选项表还保留 `--stock`、`--ramdisk-addr`、`--verify-against` 三行）。这导致：

- 中文用户无法从 CLI 参考发现 `unixnu vendor_boot` 命令及其语义；
- 中文文件标题数少 1、代码块少 1（与结构统计一致）；
- 选项表存在悬空引用（列了参数却没有对应命令说明）。

此外 `status` 小节与英文不一致：中文在代码块后多出一段“打印设备、输出根、配置路径和每个模块来源。标记本地模块并报告未固定的模块。”，英文无此段；英文 `--json` 字段列表（`schema_version`、`device`、`name`、`output`、`configuration`、`config_path`、`configured`、`profiles`、`configuration_sources`、`board`、`components`、`modules`、`patch_order`）在中文中被缩略为“最终配置，字段包括 profiles、board、components、modules 和 patch_order”。

### 4.2 中优先级：`docs/zh/porting/device-repository.md` 结构重排与表格缺项

1. **`Board` 键表少两行。** 英文 `docs/porting/device-repository.md:178-186` 表格 7 行，中文 `docs/zh/porting/device-repository.md` 同行表格只有 5 行：缺 `soc_source`（`feeds.toml` 中的 SoC source 名）与 `os_profile`（`UniXNU/profiles/os/` 下的目录名）两行解释。
2. **“Ordered configuration and patches” 被提升/前移。** 英文是 `## board.toml` 下的 `### Ordered configuration and patches`（H3，位于 `Kernel` 表之后）；中文把它提升为独立 `## 有序配置和补丁`（H2），放在 `## 配置层` 之后、`## board.toml` 之前。这造成 H2 11→12、H3 11→10 的层级差异，也改变了导航顺序。
3. **`feeds.toml` 的 SoC source 示例块被移入上述 H2 小节。** 英文 `## feeds.toml` 下有两个代码块（SoC `[[source]]` + 组件 source `[[source]]`）；中文 `## feeds.toml` 只剩组件 source 一个代码块，SoC 块出现在前面的“有序配置和补丁”小节。内容没有消失，但章节归属改变。
4. **`feeds.toml` 的 kind 列表少两种。** 英文 `kind` 为 `driver`、`kit`、`patch`、`script`、`package`、`refer`、`soc`；中文写成“`driver`、`kit`、`patch`、`package` 或 `refer`”，漏了 `script` 与 `soc`。
5. **`Proprietary files` 段首句被省略。** 英文首句“`proprietary-files.txt` records each required firmware file, source, and hash.”在中文该节缺失；相关内容虽在“有序配置和补丁”尾部有一句“`proprietary-files.txt` 记录固件文件、来源和哈希”，但章节内缺少完整说明。

### 4.3 其他确认的内容缺口

| 文件 | 英文位置 | 中文缺口 | 影响 |
| --- | --- | --- | --- |
| `docs/zh/drivers/sheng-ufs.md` | `docs/drivers/sheng-ufs.md:7-9` | 缺句：“On request it also gives the display bank (`sheng-dpu-scanout`) and the WiFi endpoint (`sheng-wifi=2` or more) stage 1 windows; both are off by default.” | 丢失两个可选 stage 1 窗口及其默认关闭状态，影响 ShengUfs 能力理解 |
| `docs/zh/reference/output-layout.md` | `docs/reference/output-layout.md:79` | 缺整句：“The target `.cache/xnu-work/` contains patched XNU sources; `build/` contains generated headers and archives.”；`## logs` 前也缺“One log per step:”引导句 | 构建树中 `.cache/xnu-work/` 与 `build/` 的用途没有中文说明 |
| `docs/zh/reference/troubleshooting.md` | `docs/reference/troubleshooting.md:23` | `is an EXAMPLE device repository` 行的操作列只写“复制示例并设置真实名称”，漏掉“remove `board.example = true`” | 用户可能保留 example 标记，`build`/`bootimg` 会继续拒绝 |
| `docs/zh/concepts/userdata.md`、`docs/zh/guide/userdata.md` | 两文件 `Next steps` | 链接列表只保留链接名，删掉英文的说明性短句（如“lists the `[userdata]` keys”“describes the build and flash commands”） | 轻微信息损失，不影响操作 |

### 4.4 设备区 266 篇的翻译覆盖（系统性）

统计口径：把标题、表格之外的所有列表项与段落合在一起计算；`reused` 指与英文原文逐字相同（忽略前后空白）的文本。

| 类别 | 篇数 | 说明 |
| --- | ---: | --- |
| 单行链接桩页（≤100 words） | 186 | 只有仓库链接，无正文可译 |
| 有实质正文（>100 words） | 80 | — |
| ├ 英文正文、中文仅译标题/表头 | **74** | 正文与英文逐字相同，中文仅约 400–500 个汉字的模板文字 |
| ├ 源正文本身为中文 | 5 | `j716f.md`、`picasso-suzukir1n.md`、`pong-agxmx666.md`、`pong.md`、`rmx3551.md`，中英两版正文均为中文 |
| └ 完整翻译 | 1 | `polaris.md` |
| 设备页列表项总数 | 21,133 条 | 中英不同的仅 **129 条（0.61%）**，且多为译名（如“状态”“板级配置”） |

74 篇“英文正文未翻译”的设备页清单见附录 A。典型例子：`devices/alioth.md`、`devices/asteroids.md`、`devices/sm-t970.md`、`devices/oneplus13t.md`——英文正文原样保留，只有 `源记录:`、`本页按设备记录自动生成。`、表格表头等模板字符串是中文。

这属于**本地化缺口，不是内容差异**：中文设备页与英文设备页在技术内容上基本逐字一致（列表项 99.39% 相同），但作为“中文文档”不可读；中文读者需要具备英文阅读能力。

### 4.5 `zh/devices/mondrian*.md` 与 `zh/devices/pong*.md` 专项

共 9 篇，全部存在且结构逐项一致：

| 文件 | 行数（英/中） | 标题数（英/中） | 表格数据行 | 列表项（英/中） | 列表项差异 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `devices/mondrian-mzyxsl.md` | 664 / 664 | 118 / 118 | 14 | 258 / 258 | 0 |
| `devices/mondrian-wohusaixing.md` | 503 / 503 | 118 / 118 | 14 | 96 / 96 | 0 |
| `devices/mondrian-xtom0706.md` | 505 / 505 | 118 / 118 | 14 | 96 / 96 | 0 |
| `devices/mondrian.md` | 529 / 529 | 118 / 118 | 14 | 115 / 115 | 0 |
| `devices/pong-agxmx666.md` | 523 / 523 | 118 / 118 | 14 | 104 / 104 | 0 |
| `devices/pong-hxzbaka.md` | 1 / 1 | 0 / 0 | 0 | 0 / 0 | 0 |
| `devices/pong-kmu1757.md` | 7 / 7 | 1 / 1 | 0 | 0 / 0 | 0 |
| `devices/pong-y3d4.md` | 1 / 1 | 0 / 0 | 0 | 0 / 0 | 0 |
| `devices/pong.md` | 1,567 / 1,567 | 289 / 289 | 33 | 559 / 559 | 0 |

专项结论：

- **结构 100% 对齐**：9 篇行数、标题层级、表格数、表格行数、列表项数全部相同。
- **正文 100% 对齐**：所有列表项文本逐条相同；所有状态表的 `implemented`/`planned`/`device-verified` 值逐行相同。
- 中文改动仅限标题、表头、`源记录:`/`本页按设备记录自动生成。` 等模板文字；`pong-kmu1757.md` 的 1 段说明有翻译，`pong-hxzbaka.md`/`pong-y3d4.md` 为单行链接，内容一致。
- 因此 `mondrian`/`pong` 专项页面可作为与英文完全等效的依据（只是正文语言可能仍为英文/原有中文，不是新翻译）。

---

## ⑤ 结论：中文镜像是否可作等效依据

**结论：作为“文件与结构镜像”完整；作为“等效中文依据”只能有条件成立。**

- **可以等效使用的部分：** `concepts/`、`guide/`、`reference/`（除 `cli.md`）、`xnu/`、`porting/`（除 `device-repository.md`）、`drivers/`（除 `sheng-ufs.md`）、`contributing/` 的文档翻译完整，代码块、表格、版本号与英文高度一致。
- **必须对照英文的部分：** `reference/cli.md`（缺 `vendor_boot` 整节）、`porting/device-repository.md`（章节重排、Board 表缺 2 行、kind 列表缺 `script`/`soc`）、`drivers/sheng-ufs.md`（缺 stage 1 窗口说明）、`reference/output-layout.md`（缺 `.cache/xnu-work/`/`build/` 说明）、`reference/troubleshooting.md`（缺 `board.example = true` 操作）。
- **设备区：** 266 篇结构全部对齐全；正文 99.39% 列表项相同，但 **74 篇英文正文没有翻译**，186 篇只是链接桩页。若读者能读英文，设备页可作为英文内容的等价镜像；若要求中文可读，不能作为等效中文依据。
- **专项：** `mondrian`/`pong` 9 篇结构、状态、列表项 100% 对齐，可作等效依据。
- **总体判定：** 若要“拿中文镜像替代英文文档做技术决策”，**不建议无条件替代**：先修正 `reference/cli.md` 与 `porting/device-repository.md` 两处结构性缺陷，并补上 4.3 的 4 处文本缺口；设备区按英文原文核对。若只做导航、检索和结构索引，369/369 的镜像完整，可直接使用。

---

## 附录 A：74 篇正文保留英文的设备页

```text
devices/alioth-taishang1024.md
devices/alioth.md
devices/asteroids.md
devices/camellia.md
devices/cas.md
devices/elden.md
devices/erhai-xingxing19035.md
devices/evb10.md
devices/fuxi-kkkpc.md
devices/fuxi-mouse233.md
devices/fuxi-oddlylabs.md
devices/fuxi.md
devices/gta4l-gta4lunix.md
devices/hero2lte.md
devices/instantnoodlep-zhangp996.md
devices/instantnoodlep.md
devices/ishtar.md
devices/j716f-emptyghost.md
devices/kebab-stevedang67889.md
devices/luming-infinityex-rsxq.md
devices/marble-milacy.md
devices/marble.md
devices/meizu21.md
devices/merlinx-gytis283123.md
devices/miatoll.md
devices/mondrian-mzyxsl.md
devices/mondrian-wohusaixing.md
devices/mondrian-xtom0706.md
devices/mondrian.md
devices/munch-erodenine.md
devices/nabu-zzweiqing.md
devices/nx769j.md
devices/odin.md
devices/odin3.md
devices/oneplus13t-shad0w23333.md
devices/oneplus13t.md
devices/orangepi5.md
devices/pudding.md
devices/raphael-guowenye.md
devices/rmx1971.md
devices/rmx3823.md
devices/ruby.md
devices/sheng-ad1095445.md
devices/sheng-airalex002.md
devices/sheng-bai805.md
devices/sheng-chenjin1494.md
devices/sheng-enlixk.md
devices/sheng-fft-infra.md
devices/sheng-gkxqh.md
devices/sheng-ht94911.md
devices/sheng-hxzbaka.md
devices/sheng-jsongmax.md
devices/sheng-ks114514.md
devices/sheng-lithosss.md
devices/sheng-soneoylys.md
devices/sheng-thearchitectengineer.md
devices/sheng-tkings4chan.md
devices/sheng-v1-727.md
devices/sheng.md
devices/sirius-dddqmmx.md
devices/sirius-huajifruit.md
devices/sirius-yooglery.md
devices/sirius.md
devices/sm-t970.md
devices/starlte.md
devices/tb365fc.md
devices/uke-imposterissus13.md
devices/uke-tonghuaqwq.md
devices/uke.md
devices/umi-jopangjovan.md
devices/venus.md
devices/yunluo.md
devices/zizhan.md
devices/zorn.md
```

## 附录 B：核对边界与判定口径

1. 只统计 `.md` 文件；`docs/zh` 下的非 Markdown 资源不在本次 369 vs 369 范围。
2. 标题按行首 `#`–`######`（ATX）统计，代码块按围栏 ` ``` ` / `~~~` 计，表格按分隔行计。
3. 行数比 = 中文物理行数 / 英文物理行数；英文段落按约 80 列硬换行、中文多为单行段落，会放大“行数差”但不等同于内容缺失，因此 17 篇行数比异常经全文核对后判为无实质差异。
4. “设备页正文未翻译”的判定：非代码、非表格、非模板文本中，英文单词数与中文汉字数之比极高，且 99% 以上列表项与英文逐字相同；人工抽查 `alioth.md`、`asteroids.md`、`sm-t970.md`、`oneplus13t.md` 确认正文为英文原文。
5. 所有结论均以本次源仓库 `75ae626a12764c706fc0b94c52a3eea09447dbaa` 的文档快照为准；若后续英文文档更新，需重新核对。
