# 线 → 检出 → 分支地图（LINE-MAP）

> 最后更新 **2026-11-17 02:20**。HEAD 是当天的快照，会漂移；它只用来回答「哪个检出的哪个分支有这条线的什么」。
> 研究文件的逐文件清单在 [docs/research/LINE-RESEARCH-MAP.md](../research/LINE-RESEARCH-MAP.md)；文档索引在 [docs/INDEX.md](../INDEX.md)。
> 检出所有权以 [TREE-OWNERS.toml](TREE-OWNERS.toml) 为准，本表只是它的阅读视图。

## 0. 一句话

main 只看得见 71 个 `docs/research/` 文件；16 个 `k60-*` 检出里另有 **97 个**只在分支上的研究文件。
一个能力结案时，应当**整目录搬回 main**（见 LINE-RESEARCH-MAP §1 的搬运规则），而不是在聊天里贴结论。

## 1. 逐线表

| 线 | 检出 | 分支 | HEAD（2026-11-17） | main 外的研究文件 | owner |
|---|---|---|---|---|---|
| 参考/取证 | `k60-refmine` | `docs/porting-gap-audit` | 本分支 | 0（写 main 文档） | `refmine-agent` |
| WiFi | `k60-wifi` | `feat/wifi-bringup` | `136f95c2` | 14 | `wifi-agent` |
| WiFi 集成 | `k60-wifi-lead` | `feat/wifi-integration` | `b4dbb3a0` | 3（全部是 k60-wifi 的副本） | `lead` |
| 蓝牙 | `k60-bt` | `feat/bt-research` | `ed93d189` | 10 | `bt-agent` |
| 蜂窝 | `k60-cellular` | `feat/cellular` | `7ee599e0` | 18 | `cellular-agent` |
| 热管理 | `k60-thermal` | `feat/thermal-tsens` | `c7b170b9` | 12 | `thermal-agent` |
| USB | `k60-usb` | `feat/usb-console` | `f5aa46de` | 7 | `usb-agent` |
| 音频 | `k60-audio` | `feat/audio-codec` | `5a8d8065` | 3 | `audio-agent` |
| 音频合并 | `k60-audio-merge` | `feat/audio-merge` | `81801af0` | 6 | **未登记**（见 §2） |
| ADSP handoff | `k60-adsp-handoff` | `feat/adsp-handoff-owner` | `161c4518` | 4 | `adsp-handoff-agent` |
| 显示 | `k60-display` | `feat/display` | `a322b587` | 6 | `display-agent` |
| 触摸 | `UniXNU-mondrian`（共享） | 当前 | — | 0（研究在 main） | `touch-agent` |
| 按键 | `k60-buttons` | `feat/buttons` | `71a067a2` | 3 | `buttons-agent` |
| SpringBoard | `k60-springboard` | `feat/springboard` | `9b8d78ad` | 3 | `springboard-agent` |
| GPU 用户态 | `k60-gpu-user` | `feat/gpu-user` | `042de9d9` | 2 | `gpu-user-agent` |
| iOS profile | `k60-ios-profile` | `feat/ios-profile` | `10deb6bb` | 1 | `ios-profile-agent` |
| 门禁 | `k60-gates` | `feat/gpu-metal-hw` | `786e96f9` | 1 | `lead` |
| 兄弟项目 | `UniXNU-zizhan` | `main` | `034a0b0` | 4 | **未登记**（见 §2） |

研究文件 0 个、但同样有主人的检出：`k60-charger`（`charger-agent`）、`k60-hygiene`（`hygiene-agent`）、`k60-lead`（`lead`）。

## 2. 两个未登记的检出

- `UniXNU-zizhan`：只读参考树（SM8475 + darwin24 的兄弟项目），有 4 份调研；若继续引用其结论，应先决定是否登记为 `lead` 的只读参考树。
- `k60-audio-merge`：有 6 份音频研究，其中 3 份与 `k60-audio` 重复；合并成功后建议以它为主副本，再登记 owner。

## 3. 读法

- **某条线在研究什么** → 本表找到检出的分支 → 打开 `docs/research/LINE-RESEARCH-MAP.md` 对应小节看逐文件一句话。
- **某个结论写在哪** → 先看 main 的 `docs/research/`；没有再看本表对应检出的分支。`docs/research/EIGHT-STEPS.toml` 里带 `k60-*:` 前缀的引用就是这个意思。
- **谁可以改这个树** → §1 的 owner 列 + `TREE-OWNERS.toml`；不要在没有主人的树上做不可逆操作（铁则 11 / P-184）。

## 4. 维护

新增或关闭一条线时改本表；搬完研究目录后同时改 `docs/research/LINE-RESEARCH-MAP.md`（删掉已搬的行）。
本表不设门禁：HEAD 每天都会变，硬校验只会制造假红。
