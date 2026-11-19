# 未合入 main 的分支清单（2026-11-19，供逐条确认）

main = `5d8a09a5`。`origin` 上未合入的分支 **49** 条，按线分组编号，你可以直接回「合 #13、#14；删 #26、#27」这样的编号。

**合并口径（用户 2026-11-19 明确）**：按官方文档标准没到 100%、但**能启动且主要功能可用**的也可以合（例如电池线能显示电量）；不需要等八步全绿。

**删除口径**：只有「已被别的分支完全包含」（git 祖先关系）或「树内容与 main 完全相同」才删；其余只归档不改内容。

| # | 分支 | ahead/behind | 文件 | 内容 | 证据 | 被谁包含 | 建议 |
|---|---|---|---|---|---|---|---|
| | **GPU / 显示 / 整合** | | | | | | |
| 1 | `feat/gpu-metal-hw` | 483/0 | 289 | GPU/Metal 主线：Metal 插件部署、扫出 presenter、IO coherence 探针、GMU 运行期调档（gperf）、35 张飞行卡，并且已经包含 consolidate/20261119 | 上机多次 PASS；present() 段已进 8.33 ms 预算（bench sum 5,907 µs、gpu 2,470 µs），但整机帧率未达标 | — | 合入 main（作为 GPU 与整合基线） |
| 2 | `consolidate/20261119` | 323/0 | 163 | 11-19 的整合分支：wifi tip + 电池 sample-dirty + 120 Hz 面板/背光，构建后上机 PASS | usblog-20261119-025400：te 55→120/s、backlight conformance=1 control=1 | feat/gpu-metal-hw | 已被 feat/gpu-metal-hw 包含，直接归档 |
| 3 | `feat/120hz-panel` | 93/9 | 32 | 面板三档切到 120 Hz + 12-bit 背光编码器 + 5 个门禁脚本 | 120hz-7 PASS（te 55→122）、brightness-19 两端 PASS | feat/gpu-metal-hw | 合入（若 gpu 分支已含则归档） |
| 4 | `feat/display` | 65/9 | 25 | 背光/面板早期实现（0620 补丁） | brightness-19 PASS | feat/gpu-metal-hw | 已并入 120hz-panel，归档 |
| 5 | `feat/springboard` | 39/137 | 20 | SpringBoard 壁纸/图标线 | 壁纸结案 PASS（catalogue size=772 resid=7420 修复） | — | 合入 |
| 6 | `feat/thermal-tsens` | 37/9 | 50 | tsens 采样 + 温控 level 发布 | thermal-20261115b：22 passed / 0 failed；⑧ 故意未做 | — | 合入 |
| | **触摸 / 按键** | | | | | | |
| 7 | `feat/touch-power` | 14/252 | 15 | 触摸上电/保留模块审计 | 触摸 8 触点 + 4 HID 已在真机证明（usblog-20261114-150931） | — | 合入 |
| 8 | `feat/buttons` | 8/160 | 9 | 按键 ADT 节点 + 三个 PMIC key | 真机 arbiter v7 power=1 up=1 down=1（234 次） | — | 合入 |
| | **电源 / 电池 / 充电 / ADSP** | | | | | | |
| 9 | `fix/power-doc-conformance` | 243/15 | 124 | 电源线的文档/门禁一致性 + 模式 1 控制台判据 | 文档性改动，随电源上机 | — | 合入（文档） |
| 10 | `fix/battery-sample-dirty` | 43/15 | 65 | 电池采样脏读修复（sample dirty 位） | 构建通过 + 真机未单独判读 | fix/power-doc-conformance | 待确认 |
| 11 | `feat/charge-auth` | 136/15 | 104 | 充电认证（PMIC-GLINK 认证状态机） | 用户明确说「不确定是否修好」 | — | 不合，继续 |
| 12 | `feat/charger` | 1/47 | 3 | 充电线早期脚架（1 提交） | 被 fix/power-doc-conformance 吸收 | — | 归档 |
| 13 | `feat/adsp-handoff-owner` | 39/15 | 62 | ADSP ownership 平台层（21 回调 + board 10 回调） | 已合入 gpu 分支；resources_cb 仍 -63（HR-01） | fix/power-doc-conformance | 归档（内容已在 gpu 分支） |
| 14 | `feat/adsp-carrier` | 33/9 | 25 | ADSP 载具（拷贝到固定地址） | 未上机 | — | 继续 |
| | **音频** | | | | | | |
| 15 | `feat/audio-adsp-merge` | 277/15 | 138 | 音频 + ADSP 合并线（codec probe、APR 探针） | 用户明确说「audio 那条线还没修好」 | — | 不合，继续 |
| 16 | `feat/audio-merge` | 104/149 | 76 | 音频早期合并（内核 HAL 部署） | 被 audio-adsp-merge 取代 | feat/audio-adsp-merge | 归档 |
| 17 | `feat/audio-codec` | 5/256 | 14 | codec 决策辅助函数（5 提交） | 宿主测试通过，未上机 | — | 并入 audio-adsp-merge 后归档 |
| | **WiFi** | | | | | | |
| 18 | `feat/wifi-ios27-abi` | 298/19 | 90 | 27 ABI 的 wifi 配置与 24A446 信道答案 | 离线配置，未上机 | — | 继续（27 迁移） |
| 19 | `test/wifi-he-scan` | 243/19 | 83 | wifi 线最新：HE 扫描 + 关联 + 状态栏内核侧关联 | 驱动跑起来、RSC 探针成立；网页仍打不开 | feat/wifi-ios27-abi | 待确认（wifi 未结案） |
| 20 | `feat/wifi6-wpa3` | 179/19 | 78 | WPA3/SAE 参数与预算 | 同上链 | — | 归档（被 test/wifi-he-scan 取代） |
| 21 | `feat/wifi-integration` | 40/234 | 45 | wifi 集成早期 | 被后续取代 | — | 归档 |
| 22 | `feat/wifi-bringup` | 103/19 | 72 | wifi 第一次跑起来 | 被后续取代 | — | 归档 |
| 23 | `fix/wifi-settings-wifid` | 173/19 | 70 | 设置页 wifid 扫描记录计数 | 被 wifi-he-scan 取代 | test/wifi-he-scan | 归档 |
| 24 | `fix/wifi-mission-timeout` | 169/19 | 68 | mission14 超时判据修正 | 被取代 | test/wifi-he-scan | 归档 |
| 25 | `fix/wifi-mission-poll` | 126/19 | 60 | mission3/轮询判据 | 被取代 | test/wifi-he-scan | 归档 |
| 26 | `fix/wifi-bhie-direct` | 105/19 | 59 | BHIe 直读候选 | 被取代 | test/wifi-he-scan | 归档 |
| 27 | `fix/wifi-bhi-execenv-wifi` | 100/19 | 58 | BHI_INTVEC 向量对比排除 | 被取代 | test/wifi-he-scan | 归档 |
| 28 | `feat/wifi-series-sync` | 81/9 | 101 | wifi 补丁序列与 k60-wifi 同步 | 被取代 | — | 归档 |
| 29 | `feat/wifi-patch-sync` | 2/9 | 5 | 补丁序列同步（2 提交） | 被取代 | — | 归档 |
| 30 | `feat/wifi-mhi-preload` | 101/19 | 60 | MHI 预载候选 | 被取代 | — | 归档 |
| 31 | `feat/wifi-ipa-rail` | 116/19 | 63 | IPA/rail 方向 | 被取代 | — | 归档 |
| 32 | `feat/wifi-dma-cache` | 97/19 | 58 | DMA cache 候选 | 被取代 | feat/wifi-mhi-preload | 归档 |
| 33 | `feat/wifi-ledger-fold` | 2/56 | 4 | wifi 账本折叠（纯文档） | 文档 | feat/wifi-final-conclusion | 归档 |
| 34 | `feat/wifi-final-conclusion` | 10/17 | 6 | wifi 结论收敛（纯文档） | 文档 | — | 归档 |
| | **蓝牙 / 27 基线** | | | | | | |
| 35 | `ci/ios27-kernel` | 82/0 | 191 | 27 内核 CI（push 触发 + 契约检查） | CI 通过一次 | — | 合入 27 基线 |
| 36 | `feat/bt-ios27-port` | 80/0 | 191 | 27 蓝牙端口 + 27 脚手架（39 提交，34 是 pedro 的） | 含 configs/mondrian_ios27_defconfig、profiles/os/ios-27.0.1-24A446、Darwin24/27 共存重命名 | ci/ios27-kernel | **作为 27 新基线 main 的来源** |
| 37 | `feat/bt-research` | 176/35 | 84 | 蓝牙研究工作（补丁 21 个 + 测试） | d5 梯子真机到 QCA version 0x12110201；用户态仍缺 | — | 合入（驱动部分已证明） |
| 38 | `test/bt-d8-timing-model` | 6/15 | 17 | BT d8 定时模型（宿主 34 场景/84 断言） | 宿主证据，未上机 | — | 归档（审计交付物） |
| | **蜂窝** | | | | | | |
| 39 | `feat/cellular` | 228/141 | 117 | 蜂窝/modem 载具（27 段固件、lzma 载具、IPA SCM） | 结构性构建，未上机；缺口 14 MB | — | 继续 |
| | **UFS / USB** | | | | | | |
| 40 | `feat/ufs-verified-table` | 16/9 | 25 | UFS 表读取按已拷字节推进 | 真机验证过表读 | — | 合入 |
| 41 | `feat/usb-console` | 35/137 | 21 | USB 控制台双模（mode-1 五 beacon / mode-2 回环） | 已结案 device-verified | — | 合入 |
| | **文档 / 审计 / 归档** | | | | | | |
| 42 | `docs/porting-gap-audit` | 169/9 | 113 | 移植缺口审计（169 提交、113 文件） | 文档/审计 | — | 合入（文档） |
| 43 | `feat/research-refindex` | 22/174 | 17 | 参考索引与 SOURCES.toml | 文档 | — | 合入 |
| 44 | `feat/judge-tools` | 17/174 | 19 | 判读器工具集（z0 对照判读） | 工具 | — | 合入 |
| 45 | `docs/reassess-bringup` | 3/15 | 12 | 11-16 复评报告 | 文档 | test/bt-d8-timing-model | 合入 |
| 46 | `docs/pitfalls-p227` | 3/17 | 7 | P-227 坑登记 | 文档 | — | 合入 |
| 47 | `feat/ios-profile` | 3/175 | 8 | OS profile 决策文档 | 文档 | — | 合入 27 基线 |
| 48 | `feat/first-frame-20261107` | 361/575 | 0 | 早期首帧分支（树与 main 完全相同） | 已吸收 | — | 归档 |
| 49 | `chore/archive-darwin24-main-20261103` | 208/575 | 0 | Darwin 24 归档分支（树与 main 相同） | 已吸收 | feat/first-frame-20261107 | 归档 |

## 其它 remote（不参与）

`yibiya/*` 13 条（remote `yibiya` = github.com/yibiya/UniXNU-mondromian 的镜像）、`yib/*` 13 条（本地镜像 `/mnt/e/k60-work/references/yibiya-upstream`）。这些是参考源，不合并、不改名、不删除。

共 49 条。