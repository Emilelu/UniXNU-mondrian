# springboard/RESEARCH.md —— 壁纸 / 换壁纸后进不去系统 / 桌面小组件（K60 mondrian）

> **结论层。** 证据行（`文件:行`）在 [WALLPAPER-CHAIN.md](springboard/WALLPAPER-CHAIN.md)；
> 本文只放**上机判读卡**：日志行原文 → 结论。八步进度以 `docs/research/EIGHT-STEPS.toml` 为准，本文不声明进度。
> 镜像对照：springboard-20261115a（验证镜像，带 `k60_wallpaper_reset=1`）与 springboard-20261114e（常规，无该参数），
> 两者都含 0340 新 UI 库 + 0618 内核种子；fd `cf4485712c29`。

## 0. 上机读日志顺序（照这个顺序抓，前一条不成立就别看后一条）

| # | 要抓的行 | 必须的结果 | 不成立时去哪 |
|---|---|---|---|
| 1 | `K60WALL catalogue bytes=… resid=0 error=0` | `bytes=772 resid=0` | §1 四类失败分支 |
| 2 | `K60WALL catalogue open/read/create error=…` | 一条都不出现 | §1 |
| 3 | `Pong init: optional boot view SKIP …stock-wallpaper` | **消失** | §2（目录/属主） |
| 4 | `Pong init: wallpaper aliases SKIP` | **消失** | §2（guard 二段） |
| 5 | `Pong UI: wallpaper existing-content=…` → `asset present=…` → `submitting genuine wallpaper 7410` | 三行依次出现 | §3 |
| 6 | 屏幕像素 | WWDC 2022 壁纸可见 | §4 半成功汇总 |

半成功（例如 1 成立但 3/4 仍在）走 §4，不要跳过前面的行直接看后面。

**不要手读**：`python3 scripts/judge-wallpaper-log.py <console.log>` 按上表六步逐条判（`PASS/FAIL/N-A/EYES` + `success/half/dead`），规则与本文表格同源。

## 1. 判定 —— 0618 内核种子（K60WALL）

| 日志行原文 | 结论 |
|---|---|
| `K60WALL catalogue bytes=772 resid=0 error=0` | **0618 全部生效**：772 B 的 `Collections~ipad.plist` 已从 /Library/Wallpaper 复制进 /private/var/pong/stock-wallpaper/Collections/；`K60DATA mkdir ok=N/M` 的 M 应比旧镜像多 3（0618 新增 stock-wallpaper、stock-wallpaper/Collections、Wallpaper 三条）。 |
| `K60WALL catalogue bytes=<非772> resid=<非0> rejected` | 源文件读到了但长度不对：源不是预期的 772 B plist（OS 镜像异常或被别的补丁改过）。把 actual bytes 与镜像 tag 一起报。 |
| `K60WALL catalogue open error=<errno>` | /Library/Wallpaper/Collections/Collections~ipad.plist 打不开（vnode_open 失败）。errno=2 ⇒ OS 窗没有该文件（与 §2.3 冲突，需重查镜像）；errno=13/30 ⇒ 权限/只读卷问题。 |
| `K60WALL catalogue read error=<errno>` | vnode_open 成功但 vn_rdwr 失败：极少见，报 errno。 |
| `K60WALL catalogue create error=<errno>` | 目标目录不存在或不可写：0618 的 mkdir 三条没生效（看 `K60DATA mkdir ok=N/M` 的 M 与清单），报 errno 与 ok 计数。 |
| 一条 K60WALL 都没有 | 0618 补丁没进内核：核对镜像 tag 是否 ≥ springboard-20261114e，再核对 boot.img 的 strings 里 K60WALL 计数（应 =5）。 |

**拷贝缓冲上限已核实（2026-11-15，回应 Lead m01914 a）**：0618 的 `static char k60_wall_buf[8192]` 是硬上限，读满时 `resid != 0` 走 `rejected`（fail-closed，不会截断写出）。
实测 20G81 的 `Collections~ipad.plist` 就是 **772 B**（`7z l -slt /opt/k60/osroot/os.raw` 的 `Size = 772`，Packed Size 也是 772），远低于 8 KiB ⇒ **本镜像不会命中 `size=… rejected`**；该分支只在换别的 OS 窗、且 catalog 涨过 8 KiB 时才需要改缓冲策略。
`vn_rdwr` 的 `resid` 语义已核（`/opt/k60/trees/springboard-out/feeds/xnu-c465a9f8/bsd/vfs/vfs_vnops.c:1013-1015`：`*aresid = uio_resid(auio)`，即未传输字节数），所以 `resid=0` 等价于「一次读完」，`bytes=772 resid=0` 是唯一成功形态。

## 2. 判定 —— v24dp init 的壁纸视图（0616 谱系）

| 日志行原文 | 结论 |
|---|---|
| `Pong init: wallpaper aliases SKIP (stock view unavailable)` **消失** 且 `Pong init: boot view /Library/Wallpaper -> /private/var/pong/stock-wallpaper result=0 errno=0` | stock 视图挂上。0618 的目标（catalog 落位 + 目录存在）达成，SKIP 链条第一环消除。 |
| `Pong init: boot view /private/var/pong/Wallpaper -> /Library/Wallpaper result=0 errno=0` | alias 视图挂上（壁纸别名入口）。 |
| `Pong init: optional boot view SKIP /private/var/pong/stock-wallpaper (source/target unavailable)` **仍在** | 目录仍没建成：0618 mkdir 没生效（对照 §1 的 K60DATA 计数）。 |
| `Pong init: boot view /Library/Wallpaper -> /private/var/pong/stock-wallpaper result=-1 errno=1` | **P-27 现身**：目录都在但密封根拒绝 bindfs。这一步**不在 0618 修复范围内**（init 在 mount 前就 SKIP 了，从来没量过这台板子的真实返回值）；若出现，走 WALLPAPER-CHAIN §4 F4（改 init），别再试 bindfs 变体。 |
| `Pong init: wallpaper alias SKIP (no target)` / `(no source)` | guard 二段：/Library/Wallpaper 不在 OS 窗（与 §2.3 矛盾）或 /private/var/pong/Wallpaper 没建（0618 mkdir 失效）。 |

**半成功形态（Lead 要求单列）**：

| 形态 | 判读 | 处置 |
|---|---|---|
| `K60WALL catalogue bytes=772 resid=0 error=0` 出现，但两条 wallpaper SKIP 仍在 | 0618 的复制与 mkdir 都生效，但 init 的 guard 仍在拒绝 —— 说明 SKIP 的真正卡点不是"目标目录缺 plist"。可能性：bindfs 在密封根 EPERM（P-27）被 guard 前的 stat 误判、或 0616 谱系 init 的 guard 检查路径与 0618 写入路径不一致。 | 抓 `Pong init: boot view … result= errno=` 行；若根本没打 boot view 行 ⇒ 卡在 guard 的 lstat/stat（目录存在性/属主/权限），查 `K60DATA mkdir ok` 计数与目录属主（应为 0:0、mode 0755）；若 result=-1 errno=1 ⇒ P-27，转 F4。**K60WALL 成功本身就是 OS 窗壁纸源可达的首次实证**，记录后转 F4 讨论，不回滚 0618。 |
| `K60WALL` 缺席但 SKIP 消失、boot view result=0 | 理论上不可能（SKIP 消失依赖 catalog 落位）；若真出现 ⇒ 0616 谱系判断有出入，报日志核对 init 版本（`Pong init: HackiOS` 首行）。 |
| boot view result=0 两条全过，但 `Pong UI:` 壁纸行缺席 | 视图挂上了但 UI 库没跑壁纸选择：核对 libpong-ui 是否新 blob（`Pong UI: 20G81 compatibility library entered` 后跟 img 行），再核对 k60_ui_springboard 未被关。 |

## 3. 判定 —— F1 UI 库壁纸选择（0340 新 blob，仅 k60_wallpaper_reset=1 时提交）

前提：`Pong UI: wallpaper existing-content=%d restore-stock=%d (1=present -1=unavailable)` 必须先出现（`ui_compat.c:686`）。
无 reset 参数时 `restore-stock=0` 且 `existing-content=1` ⇒ 直接保留用户壁纸，**后面整段不出现是正常行为**，不是失败。

| 日志行原文 | 结论 |
|---|---|
| `Pong UI: wallpaper existing-content=1 restore-stock=1 …` | 读到已有内容且 boot-arg 生效，进入重选流程（`ui_compat.c:686`）。 |
| `Pong UI: genuine wallpaper asset 7410.WWDC_2022.thumbnail-1024w-1366h@2x~ipad.heic present=1`（另两条 thumbnail/fullSize 同款） | 7410 bundle 三资产校验通过（`ui_compat.c:659`）——同时证明 stock 视图把 /Library/Wallpaper 透传成功。 |
| `Pong UI: submitting genuine wallpaper 7410 native lock+home path=/Library/Wallpaper/Stills/iPad/7410.WWDC_2022-1024w-1366h@2x~ipad.wallpaper` | 原生提交已发出（`ui_compat.c:738`）。 |
| `Pong UI: native wallpaper completion returned; visual pixels remain to be observed` | setter 回调返回，**像素是否上屏仍要靠眼睛确认**（`ui_compat.c:741`，P-75：回调不是像素判据）。 |
| `Pong UI: genuine wallpaper bootstrap SKIP (required 7410 metadata/assets unavailable)` | plist 或资产文件校验失败（`ui_compat.c:720`）：stock 视图没挂上或文件名不匹配。对照 §1/§2 的 K60WALL 与 boot view 行。 |
| `Pong UI: genuine wallpaper bootstrap SKIP (native 20G81 WallpaperKit ABI unavailable)` | WKWallpaperBundle/WKSystemShellWallpaperManager ABI 探测失败（`ui_compat.c:729`）：20G81 框架与预期 encoding 不符，报回后改 ABI 表，不动镜像。 |
| `Pong UI: genuine wallpaper bootstrap SKIP (native manager/URL unavailable)` | 管理器/URL 构造失败（`ui_compat.c:733`）。 |
| `Pong UI: genuine wallpaper bootstrap SKIP (native bundle rejected)` | WKWallpaperBundle initWithURL: 返回 nil（`ui_compat.c:737`）。 |

**像素级最终判据**：面板上出现 WWDC 2022 壁纸（Light/Dark 随外观）。
**排除项**：`existing-content=-1`（configuration 取不到，`ui_compat.c:636`）⇒ SBWallpaperController 尚未就绪，查 SpringBoard 是否真正起来了（`Pong UI: UIApplication _run entered`）。

## 4. 半成功汇总与升级路径

**判定器**：`python3 scripts/judge-wallpaper-log.py <console.log>` 按 §0 六步逐条输出 `PASS/FAIL/N-A/EYES` 与最终 verdict（`success` / `half` / `dead`），每条 FAIL 打印「去 §几」。纯读文件、无副作用；回归测试 `python3 scripts/tests/test-judge-wallpaper-log.py`（11 例，含两份真实旧日志作负样本）。

四种半成功形态（**按日志字面量匹配，判定器用的就是这些串**）：

| 形态 | 确切日志行 | verdict | 判读与处置 |
|---|---|---|---|
| A 种子生效但 guard 仍拒 | `K60WALL catalogue bytes=772 resid=0 error=0` + `Pong init: optional boot view SKIP /private/var/pong/stock-wallpaper (source/target unavailable)` | `half` | 复制与 mkdir 都生效，卡点在 init guard（目录属主/权限）或 bindfs。先看有没有 `Pong init: boot view /Library/Wallpaper -> /private/var/pong/stock-wallpaper result=… errno=…`：没有 ⇒ 卡在 guard 的 lstat/stat，查 `K60DATA mkdir ok=N/M` 与目录属主（应 0:0 / 0755）；有且 `result=-1 errno=1` ⇒ P-27，转 F4。K60WALL 成功本身就是「OS 窗壁纸源可达」的首次实证，不回滚 0618。 |
| B 目录被拒（缓冲/长度） | `K60WALL catalogue size=8192 resid=4096 rejected` 或 `K60WALL catalogue open error=2` / `read error=…` / `create error=…` | `half` | 772 B 实测不会命中 `size=… rejected`（§1 注记）；`open error=2` ⇒ OS 窗没有该 plist（与 §2.3 矛盾，重查镜像）；`create error` ⇒ 三条 mkdir 没生效。报 errno + `K60DATA` 计数。 |
| C 视图挂上但 UI 库跳过 | `Pong init: boot view /Library/Wallpaper -> /private/var/pong/stock-wallpaper result=0 errno=0` + `Pong UI: genuine wallpaper bootstrap SKIP (native 20G81 WallpaperKit ABI unavailable)`（或其余三种 SKIP） | `half` | 视图链通了，壁纸选择没跑：ABI 不符 ⇒ 改 ui_compat 的 ABI 表；`required 7410 metadata/assets unavailable` ⇒ 资产名不匹配（对照 §3）；`manager/URL unavailable` / `bundle rejected` ⇒ WallpaperKit 侧对象构造失败。 |
| D 全部通过但像素黑 | 无 SKIP、`submitting genuine wallpaper 7410` 与 `native wallpaper completion returned` 都在 | `success`（机器侧） | 机器判据已全过，剩下是 PosterBoard/compositing 层 —— 转 §5 与 WALLPAPER-CHAIN §2.6；像素只能靠截图确认。 |

**无 reset 参数的正常镜像**：`Pong UI: wallpaper existing-content=1 restore-stock=0` 之后整段不出现是**正确行为**（保留用户壁纸），判定器记为 `N-A` 而不是 FAIL。

**升级路径**：`success` + 像素可见 ⇒ 立即出常规镜像 springboard-20261115b（无 `k60_wallpaper_reset`），并把 0618 注释里「每次启动重选」改为「仅验证镜像使用」（Lead m01858）；`half` 按上表 A/B/C 分支处置；`dead` ⇒ 镜像没带 0618（先核 tag 与 `strings` 计数）。

## 5. 桌面小组件（挂账，不在本线）

`userland/build.py:40-45` BOOT_SKIP 有意跳过 `com.apple.chronod`（widget 扩展发现反复超时），加上 varpack/OS 窗都不含
`/private/var/mobile/Library/SpringBoard/`（PosterBoard 的状态目录），小组件首启必然缺失。
恢复 chronod 是独立项（WALLPAPER-CHAIN §4 F5），不与本线判据混判。

## 6. 三条 SpringBoard 噪声（低优先，逐个排）

记录于 WALLPAPER-CHAIN §5.2：backdrop invalid size (0.33 x 0.33)（未定位）、Unbalanced calls SBCoverSheetPrimarySlidingViewController（未定位）、
CarKit soft link（已定位：公开路径不存在，20G81 只有 PrivateFrameworks；可用 dlopen 钩子消噪）。均不是壁纸纯黑的原因。

## 7. 引用

- `patches/xnu/0618-k60-wallpaper-seed.patch:33/40/45/51/58` K60WALL 五条日志。
- `userland/init-v24dp.c:328-357` 两道 guard 与 boot view 日志（0616 部署谱系）。
- `userland/ui_compat.c:636/642/659/686/720/729/733/737/738/741` 壁纸选择日志与 SKIP 分支。
- `patches/xnu/0616-k60-init-legacy-helper.patch:2967-2978` installer 替换（P-182/P-197）。
- `docs/ops/PITFALLS.md:325-341` P-27；`:1132-1139` P-75；`docs/engineering/PITFALLS.md` P-197。
