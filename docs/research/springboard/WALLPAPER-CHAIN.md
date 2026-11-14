# WALLPAPER-CHAIN — 壁纸纯黑 / 换壁纸后进不去系统 / 桌面小组件加载不出来

- 线：springboard（工作树 `E:/hackios/k60-springboard`，分支 `feat/springboard`）
- 日期：2026-11-14
- 状态：证据链已闭合（host 侧）；设备判据未验证（按铁则禁止自行 boot，交 Lead）
- 适用范围：本文所有 `文件:行` 均可在工作树内直接检索；日志行号指 `docs/research/evidence/` 下文件的行号

---

## 0. 结论速览（TL;DR）

1. **OS 窗口里 `/Library/Wallpaper` 完整存在**（7z 实测 `/opt/k60/osroot/os.raw`：目录、9 个 `.wallpaperCollection`、Stills/iPad 下 17+ 个 `.wallpaper` bundle，含 7410 WWDC 2022）。"壁纸源从未部署"只说对了一半：真正缺的是 **Data 侧视图目标目录 `/private/var/pong/stock-wallpaper`**——设备上跑的 init 从不创建它。
2. **上机两行 SKIP 发生在 mount 之前**：init 的两道 guard（`userland/init.c@2101281:368-371`、`:373-378`）直接 `continue`，日志既不能证明 bindfs 可用、也不能证明不可用。bindfs 在密封只读根上 EPERM 另有独立证据（P-27）。
3. **纯黑的主因不是 SKIP，而是"没有任何代码去选壁纸"**：设备上的 `libpong-ui.dylib` 对应 `ui_compat.c@50f4644`（28 条 Pong UI 消息与嵌入 blob 完全匹配），**不含** `select_initial_wallpaper()` / `existing_wallpaper()`（HEAD 才有）。WallpaperKit 的默认目录又按设备名与精确 `logicalScreenClass` 筛选，phone 界面无法自动命中 iPad 素材（P-75）。修复 = 部署 HEAD 版 UI 库并在恢复镜像里带 `k60_wallpaper_reset=1` 启动一次（本文 §4 F1，已 host 编译并嵌入 0340）。
4. **桌面小组件加载不出来 = `com.apple.chronod` 被有意跳过**（`userland/build.py:40-45` BOOT_SKIP："widget extension discovery repeatedly times out before the first UI"，v80 REC），widget 扩展发现永不执行；PosterBoard 虽在 boot-jobs 里，但 Data 侧 `/private/var/mobile/Library/SpringBoard` 从未播种，首启为空。
5. **"换壁纸后进不去系统"缺当次日志**：本工作区穷尽搜索未找到 Lead 引用的 528-529/2241/2247/2257 行号的那份 `console.log`；现有唯一日志是 2026-11-03 的 `docs/research/evidence/springboard-truth.txt`（无任何 wallpaper 行）。本文给出两条候选机制与下次上机应抓的判据。

---

## 1. 完整链（init → SpringBoard / WallpaperKit → 纯黑）

```
内核（patches/xnu/0401-k60-embedded-init.patch，boot-arg k60_init_blob=1 门控）
  ├─ 写 /private/var/pong/var.pack      (:69-86, PONGJOB1, 14,526 B)
  ├─ 写 /private/var/pong/boot-jobs.pack (:62-67, 235,412 B)
  └─ 写并 exec /private/var/pong/init（52,376 B static Mach-O，PID 1 helper）
        init main(): console → prepare_var() → prepare_calendar() → prepare_runtime_paths()
                     → prepare_boot_services() → configure_ui_library() → execve("/sbin/launchd")
          ├─ prepare_var(): mount("apfs",…) Data → /private/var；read /pong/etc/var.skel 建目录树
          ├─ prepare_boot_services(): 6 条 bindfs views
          │     [i=4] source=/Library/Wallpaper          target=/private/var/pong/stock-wallpaper
          │     [i=5] source=/private/var/pong/Wallpaper  target=/Library/Wallpaper
          └─ configure_ui_library(): 把 /private/var/pong/libpong-ui.dylib 注入 SpringBoard/backboardd/…

launchd（boot-jobs 含 com.apple.SpringBoard.plist、com.apple.PosterBoard.plist）
  ├─ SpringBoard → libpong-ui.dylib present_initial_screen()
  │     ├─ 设备版（ui_compat.c@50f4644）：无壁纸选择代码 → 开机不选壁纸 → 黑
  │     └─ HEAD 版：select_initial_wallpaper() → WKWallpaperBundle initWithURL: + WKSystemShellWallpaperManager
  │                 setLockScreenWallpaperRepresenting:mirrorToHomeScreen:completion: → 7410 WWDC 2022
  └─ PosterBoard（119,520 B）→ 读 /Library/Wallpaper/ 与 /private/var/mobile/Library/SpringBoard/
```

链路要点：**壁纸像素来自 OS 窗的 `/Library/Wallpaper/Stills/iPad/*.wallpaper`**，由 WallpaperKit/PosterBoard 直接读取；init 的两条 wallpaper views 只是"把 stock 目录再暴露一份"的可选别名层，**不是壁纸可读的前提**。

---

## 2. 逐环证据

### 2.1 设备上跑的 init 是哪一版

- `patches/xnu/0401-k60-embedded-init.patch:122` `+#define K60_INIT_BLOB_LEN 52376`、`:123` `+static const unsigned char k60_init_blob[K60_INIT_BLOB_LEN] = {`；`:4503` bootjobs 数组；`:24132` varpack 数组。抽出三个 blob：init 52,376 B、boot-jobs 235,412 B、var.pack 14,526 B。
- 消息集比对（"Pong init:" 串）：与 `git show 2101281:userland/init.c` 相比 **src_only=0**（blob_only 仅 1 条 "Pong init: var.pack expand result=%d"，因源码跨行拼接导致漏匹配）；与 HEAD `userland/init.c` 相比 src_only=5（HEAD 新增的壁纸目录/别名消息全部不在 blob 里）。
- blob strings 同时含 `/private/var/pong/root` 与 `/private/var/pong/root/pong/etc/var.skel`（0406 var.pack 回退路径）⇒ 设备 init = **2101281 消息集 + 0406 回退路径**的手工混合版。
- **决定性**：该版本没有 `wallpaper_directory()`（HEAD `userland/init.c:368-375` 才有）⇒ `/private/var/pong/stock-wallpaper` 永远不会被创建。
- 为什么源码修了设备没变：`adbb047`（2026-11-12 22:20:14，"fix(init): keep the 52376-byte init the board can actually run"）刻意保留旧二进制；改 `userland/init.c` 不会自动更新 0401 的 blob。

### 2.2 两行 SKIP 的精确机制

日志原文 `docs/research/evidence/gpu-keys-notes.txt:19-20`：

```
Pong init: optional boot view SKIP /private/var/pong/stock-wallpaper (source/target unavailable)
Pong init: wallpaper aliases SKIP (stock view unavailable)
```

对应 `userland/init.c@2101281`：

- **i=4**（`:373-378`）：`lstat("/Library/Wallpaper")` 通过（目录/uid 0/无 022），但 `stat("/private/var/pong/stock-wallpaper")` 失败 → 打印 "optional boot view SKIP /private/var/pong/stock-wallpaper"（日志 :19 行）。
- **i=5**（`:368-371`）：`stat("/private/var/pong/stock-wallpaper/Collections/Collections~ipad.plist")` 失败 → 打印 "wallpaper aliases SKIP (stock view unavailable)"（日志 :20 行）。
- 两道 guard 都在 `mount()` 之前，因此这两行日志**不能**说明 bindfs 是否可用。P-27（`docs/ops/PITFALLS.md:325-341`）另有量测：`mount("bindfs","/System/Library/xpc",MNT_RDONLY,…)` result=-1 errno=1（密封根），30 秒判定"看到 `boot view … result=-1 errno=1` 就别再试 bindfs 变体"。

### 2.3 OS 窗事实（推翻"源未部署"假设）

- `/opt/k60/osroot/os.raw` = 5,096,079,360 B，APFS 卷 `SydneyG20G81.J120J121J207J208OS`，133,773 文件。
- 7z 列表实测存在：`Library/Wallpaper/DefaultWallpapers~ipad.plist`（150 B）、`Wallpapers~ipad.plist`（526 B）、`Collections/Collections~ipad.plist`（772 B）；Collections 下 9 个 `.wallpaperCollection`（iPadOS_16、Shoreline-J120-J121-J207-J208、iOS_15、iOS_14、Classic_Stripes、Stripe、Desert、Bokeh、Solid_Black）；`Stills/iPad/` 下 17+ 个 `.wallpaper` bundle，含 `400.Solid_Black-834w-1112h@2x~ipad.wallpaper`、`1770.Desert_Valley`、`1810.Lake_The_Desert`、`1890.WWDC_2021`、**`7410.WWDC_2022-1024w-1366h@2x~ipad.wallpaper`**、`7411.WWDC_2022_Light-834w-1112h`、`7412.WWDC_2022_Dark` 等。
- 7410 bundle 自洽性（与 `ui_compat.c:690`、`:707`、`:716-717` 的校验完全对应）：`Wallpaper.plist` 663 B（identifier=7410、logicalScreenClass=1024w-1366h@2x~ipad、thumbnailImageFileName=7410.WWDC_2022.thumbnail-1024w-1366h@2x~ipad.heic 179,004 B、default→7411 Light 5,549,889 B、dark→7412 Dark 5,141,459 B，实际文件均在）。
- 反证注释：`userland/init-v24dp.c:334-337` 的 "/Library/Wallpaper is absent from the OS window that is the primary reason this alias cannot apply"、`docs/reference/HISTORY-LEDGER.md:302` 的 "OS 窗 /Library/Wallpaper 本地无镜像离线不可核"——都是无镜像时代的推断，**已被 7z 实测推翻**。

### 2.4 谁读壁纸：SpringBoard / WallpaperKit / PosterBoard

- `System/Library/CoreServices/SpringBoard.app/SpringBoard`（112,528 B）：几乎无壁纸路径串，只有 entitlement `com.apple.private.wallpaperkit.service.migration` ⇒ 壁纸选择不在 SpringBoard 二进制里。
- `Applications/PosterBoard.app/PosterBoard`（119,520 B）：含 `/Library/Wallpaper/`、`/private/var/mobile/Library/SpringBoard/`、`com.apple.posterboardservices.dataModel`、选择器 `createPosterConfigurationForProviderIdentifier:posterDescriptorIdentifier:completion:`。
- `System/Library/PrivateFrameworks/WallpaperKit.framework` 在 OS 卷（含 PlugIns、Localizable.loctable 28,930 B）；主二进制在 dyld shared cache 内，静态不可见。
- boot-jobs blob（235,412 B）：`com.apple.PosterBoard.plist`、`com.apple.PosterBoard`、`com.apple.posterboardservices.services`、`com.apple.notificationcenter.widgetcontrollerconnection`、`com.apple.proactive.DefaultWidgetSuggester` ⇒ PosterBoard 与 widget 服务由 launchd 拉起。

### 2.5 设备 UI 库 = ui_compat.c@50f4644，无壁纸选择

- 0340 原嵌入 blob 113,904 B、28 条 "Pong UI:" 消息；与 `ui_compat.c@50f4644`（2026-11-11 "fix(k60): 从 yibiya 上游移植 UI/launchd 修复 + GTP 协议探针"）**完全匹配**（src_only=0 / blob_only=0）；与 HEAD 相比 src_only=11（壁纸选择、metal prewarm 等）。
- ⇒ 设备开机不会重选壁纸：**纯黑是"无选择"的必然**，不是 SpringBoard 崩。
- P-75（`docs/ops/PITFALLS.md:1132-1139`）：cand16 曾出现原生锁屏且 **stock-wallpaper bind 与 aliases=4 均成功**，但用户确认壁纸全黑；cand18 `existing-content=1` 说明原生设置未提交。结论："目录可见 ≠ 原生壁纸已选中"。

### 2.6 桌面小组件链

- `userland/build.py:40-45` BOOT_SKIP：`'com.apple.chronod': 'widget extension discovery repeatedly times out before the first UI'`（v80 REC 记录：急切发现会反复启动永不 check-in 的进程再被杀）；`:178` 打印 `Pong boot: …`。
- var.pack（14,526 B，count=133）无任何 SpringBoard/poster/wallpaper 条目；OS 窗 `/private/var/mobile/Library` 无 SpringBoard 目录 ⇒ PosterBoard 的 Data 侧状态目录首启为空、由进程现场创建。
- ⇒ 小组件加载不出来：**chronod 被跳过**是明确的一手原因；PosterBoard 状态目录缺失是第二因素。

### 2.7 "换壁纸后进不去系统"

- 现状：**没有当次日志**。已穷尽搜索 `/opt/k60`、`/mnt/e/hackios`、`/mnt/e/k60-work`（只有旧 `springboard-truth.txt`，全文无 wallpaper 行）；Lead 引用的 528-529/2241/2247/2257 行号无法复核，需提供文件路径。
- 候选机制 A（数据侧）：在设置里换壁纸 → WallpaperKit 写 Data 侧 store（`/private/var/mobile/Library/SpringBoard/`）；重启后 SpringBoard/PosterBoard 读新配置，若资产引用不可达则启动期卡住。
- 候选机制 B（挂载侧）：`userland/init.c@2101281:373-378` 的 guard 只挡"目录不存在"；一旦目录存在而 bindfs 失败/成功状态变化，会进入 `mount()`。历史教训 `docs/reference/ISSUES.md:325-327`：v7probe 把带 `mount` 的第 5 条放进 views 表导致 hang（"定住不重启"），修法是加 guard——说明"进不去系统"曾真实由 mount 阶段触发。
- 下次上机应抓：`Pong init: boot view %s -> %s result=%d errno=%d`（`:380-381`）、SpringBoard 崩溃前的 `Pong UI:` 序列、以及 `kern.pong_diagnostic`。

---

## 3. 判据对照（Lead 给的三条）

| 判据 | 当前 | 依据 |
|---|---|---|
| 上机日志不再有 wallpaper SKIP | ⏳ 待上机（F3 已实施：0617 让内核在 launchd 前建两目录并把 `Collections~ipad.plist` 写进目标目录；F2 被 0616 顶掉不生效，见 §4/§5.4） | `gpu-keys-notes.txt:19-20`、§4、§5.4 |
| SpringBoard 后壁纸可见 | ⏳ 待上机（springboard-20261114c 已把壁纸选择代码编进镜像，`strings boot.img` 自证；需 `k60_wallpaper_reset=1` 一次） | P-75 全黑；§5.1 |
| 换壁纸重启能进系统 | 未验证 | 无当次日志 |

---

## 4. 最小修复方案

### F1（已实施，host 验证通过）— 部署 HEAD 版 UI 库

- **改动**：`patches/xnu/0340-k60-uilib-deploy.patch` 的 `k60_uilib_blob` 由 113,904 B → 113,472 B（`ui_compat.c@HEAD` 的编译产物）；生成命令：
  `python3 userland/build.py ui --sdk /opt/k60/sdk/iPhoneOS16.5.sdk --out <K60_OUT>/ui`（`userland/build.py:416-423`）。
- **依据**：`userland/ui_compat.c:628-661` `existing_wallpaper()`（configuration 为 nil → -1）、`:669-741` `select_initial_wallpaper()`：`existing==-1` 或 boot-arg `k60_wallpaper_reset=1` 时，校验 7410 的 Wallpaper.plist、thumbnail/fullSize 资产、`WKWallpaperBundle initWithURL:` 与 `WKSystemShellWallpaperManager setLockScreenWallpaperRepresenting:mirrorToHomeScreen:completion:` ABI（`v36@0:8@16B24@?28`）后原生提交。
- **host 验证**：编译零错误；产出 113,472 B；`LC_CODE_SIGNATURE` superblob `fade0cc0` / CodeDirectory `fade0c02` / **pagesize shift 12（4K）**——满足 `userland/build.py:73-110` `native_init_signature`；嵌入数组与 dylib 逐字节相同（sha256 `8e37468e…`）。
- **上机**：刷入后需一次 **`k60_wallpaper_reset=1`** 启动强制重选（`porting.toml:90` 的 cand19 恢复镜像 args 即带此 arg，恰好一次）；后续启动 `existing!=0` 会保留用户已有壁纸（`ui_compat.c:689`）。判据日志：`Pong UI: wallpaper existing-content=… restore-stock=1` → `Pong UI: genuine wallpaper asset … present=1` → `Pong UI: submitting genuine wallpaper 7410 native lock+home path=…`。
- **风险**：HEAD 版比设备版多 11 条消息（metal prewarm 等）。若要求最小 diff，可只把 `:628-741` 两函数回移到 50f4644 基线（本文不展开）。

### F2（已实施，host 验证通过）— var.skel 建两个目录 + 0401 换 HEAD init

- **为什么必须成对**：只加目录只满足旧 init 的 `stat(target)` 守卫（`userland/init.c@2101281:373-378`），但旧 init 的 stock guard 检查的是**目标**目录里的 `Collections~ipad.plist`（`:368-371`），挂载前目标必空 ⇒ 仍打 `wallpaper aliases SKIP (stock view unavailable)`；而 HEAD init 把该 guard 改成检查**源** `/Library/Wallpaper/Collections/Collections~ipad.plist`（`userland/init.c:483-488`），并新增 `wallpaper_directory()`（`:368-375`）与 `wallpaper_aliases()`（`:383-443`）。
- **F2a 数据侧**：`scripts/gen-var-skel.py` 的 EXTRA 增加 `('pong/stock-wallpaper', 0o755, 0, 0)` 与 `('pong/Wallpaper', 0o755, 0, 0)`（`userland/build.py:50-64` 同步，两处必须一致）。重跑后 var.skel 129 行 / 6,498 B → 132 行 / 6,608 B（sha256 `151ce31c…`），两条目录行是 `d\t755\t0\t0\t/private/var/pong/{Wallpaper,stock-wallpaper}`，满足 `wallpaper_directory()` 的 uid0 / 无 022 校验。
- **F2b 内核侧**：`userland/build.py` 新增 `init_blob` 子命令（`:429-548`）：`split_boot_jobs`/`join_boot_jobs` 解析并重组 PONGJOB1 varpack、`embedded_blob`/`replace_embedded_array` 抽取并替换 0401 的数组与 `#define` 长度并重算 new-file hunk 行数、`compile_init_linux` 用 clang-18 + ld64.lld-18 编 `userland/init.c`。命令：`python3 userland/build.py init_blob --out /tmp/f2-init-out --sdk /opt/k60/sdk/iPhoneOS16.5.sdk --var-skel /tmp/f2-varskel/pong/var.skel`。
- **结果**：`k60_init_blob` 52,376 B → **52,456 B**（HEAD `userland/init.c`，ncmds=15，无 LC_CODE_SIGNATURE，与设备现状同为裸 Mach-O）；`k60_varpack_blob` 14,526 B → **14,636 B**（133 条不变，只换 var.skel）；hunk 头 `+1,4378` / `+1,1225` 与 `K60_INIT_BLOB_LEN 52456` / `K60_VARPACK_LEN 14636` 同步。
- ⚠ **上机预期**：i=4（stock 视图）若 bindfs 在 Data 目录上成功，则 `wallpaper_aliases()` 产出 4 条别名并打印 `genuine stock wallpaper aliases=4 result=0`；i=5 要覆盖 `/Library/Wallpaper`（密封 OS 根）仍可能 `result=-1 errno=1`（P-27），但这只是 `boot view` 行，不是 SKIP，且 OS 窗本身已有完整 `/Library/Wallpaper` 供 WallpaperKit 读取。
- **回滚**：`git revert` 本提交即可回到 52,376 B / 14,526 B 的旧 blob。

### F2 复查（2026-11-15，结论：不生效）

- **0616 把 0401 的 installer 调用整个换掉**：`patches/xnu/0616-k60-init-legacy-helper.patch:2967-2978` 把 `k60_install_embedded_init(&k60_init_resid)` 换成只写 `/private/var/pong/init` 的 `k60_install_legacy_init()`，其 `k60_init_legacy` = 34,904 B，与 `userland/init-history/init-v24dp.bin` 逐字节相同（sha256 `1671eb78…`，ncmds=9）。`docs/engineering/PITFALLS.md:4314-4351`（P-182）记录 52,320 B 新助手写进 Data 后任何镜像都 `initproc exited`，所以 0401 的 52 KB blob 被弃用。
- **后果**：0401 的 `k60_init_blob` 数组因无人引用被链接器丢弃（`grep -a -c "genuine stock wallpaper aliases" kernel.macho` = 0），`k60_varpack_blob` 也不再写盘 ⇒ **F2 的 52,456 B init 与 14,636 B varpack 在 springboard-20261114d 里是死代码**，上机日志仍会打 v24dp 的 `wallpaper aliases SKIP (stock view unavailable)`。F2 的 `init_blob` 工具链与测试保留（可复用），但**不能作为本问题的修复**。
- **不能把调用点改回去**：那会重演 P-182（新助手必须先在已有 Data 状态上验证两次启动）。

### F3（已实施）— 内核在 launchd 前预置壁纸视图（真正生效项）

- **机制**：新增 `patches/xnu/0617-k60-wallpaper-seed.patch`，在 `native_owner_data_prepare()` 的 `k60_mkdir_paths[]` 末尾加三条（`/private/var/pong/stock-wallpaper`、`…/Collections`、`/private/var/pong/Wallpaper`），并在 mkdir 循环后调用 `k60_wallpaper_stage()`：用 `vnode_open`/`vn_rdwr` 把真实的 `/Library/Wallpaper/Collections/Collections~ipad.plist`（772 B）复制到 `/private/var/pong/stock-wallpaper/Collections/Collections~ipad.plist`。
- **为什么这样就够**：0616 跑的 v24dp init 的两道壁纸守卫（`userland/init-v24dp.c:328-343`、`:344-348`）检查的正是这个目标路径上的 plist；文件存在后 i=4 的 stock 视图 bind 才能继续，i=5 的 `/Library/Wallpaper` 覆盖即使仍 `result=-1 errno=1`（密封根，P-27）也不再打印 SKIP。
- **判据**：日志出现 `K60WALL catalogue bytes=772 resid=0 error=0` 与 `Pong init: boot view /Library/Wallpaper -> /private/var/pong/stock-wallpaper result=0 errno=0`，且不再出现 `wallpaper aliases SKIP` / `optional boot view SKIP`。
- **不改 init**：完全避开 P-182 的 52 KB 助手风险；init 仍是那枚 34,904 B 的验证过二进制。

### F4（不建议现在做）— 删除 views 表 wallpaper 两条（改 init）

- 需重编 init blob（52,376 B）并重嵌 0401；host 可编译（HEAD 52,456 B / 2101281 52,320 B，LC 序列一致），但 WSL 的 `codesign` 是 no-op shim，`native_init_signature` 要求 4K 页签名 ⇒ **不能 host 完成**。上机风险最高，且对像素无帮助（PosterBoard 直接读 `/Library/Wallpaper`）。仅作为清理死代码的后续项。

### F5（小组件）— 恢复 chronod 需单独立项

- 去掉 `build.py:40-45` 的 BOOT_SKIP 会回到 v80 REC 记录的"反复启动、永不 check-in、被杀"循环；建议先修 widget 扩展发现超时再恢复，不在本线最小修复内。

---

## 5. host 验证记录（2026-11-14）

- 构建：`python3 userland/build.py ui --sdk /opt/k60/sdk/iPhoneOS16.5.sdk --out /tmp/k60-ui-out` → `libpong-ui.dylib -> patches/xnu/0340-k60-uilib-deploy.patch`；`ui-library.json`：`{bytes: 113472, signature: {code_directories: 1, page_bytes: 4096}}`。
- 补丁 diff：`patches/xnu/0340-k60-uilib-deploy.patch | 7782 +++---`（3,873 insertions / 3,909 deletions）；`git apply --numstat` 解析为 `9509 bsd/dev/k60_uilib.c / 6 bsd/kern/kern_exec.c / 1 bsd/conf/files`（后两个文件不在本仓库根，属 XNU 树）。
- 嵌入 blob 校验：113,472 B，sha256 `8e37468e…`（与 dylib 逐字节相同）；strings 37 条 "Pong UI:"，含 `Pong UI: wallpaper existing-content=%d restore-stock=%d (1=present -1=unavailable)`、`Pong UI: submitting genuine wallpaper 7410 native lock+home path=%s`、`/Library/Wallpaper/Stills/iPad/7410.WWDC_2022-1024w-1366h@2x~ipad.wallpaper`。
- 门禁：`PYTHONIOENCODING=utf-8 python3 scripts/check-blob-patches.py` → 警告 "0340 … 与最近一次上机基线的值不同（59b4900111c5 != 72371a041569）"，分支 `feat/springboard` 判 warning，**通过**。上机后需在 `docs/engineering/MAIN-BASELINE.toml` 更新 blob_sha256（铁则 9）。
- 构建产物只动了 `patches/xnu/0340-k60-uilib-deploy.patch`（`git status --porcelain` 仅 ` M` 一行）。

### 5.1 strict 构建（2026-11-14 21:46，springboard-20261114c）

- 命令：`K60_OUT=/opt/k60/trees/springboard-out K60_DEVICE_INPUT=/opt/k60/trees/springboard-device K60_EIGHT_STEP_ITEMS=springboard bash scripts/build-strict.sh springboard-20261114c --fd /mnt/e/k60-work/artifacts/fd/gpu-20261114n-cf4485712c29.fd`。
- 结果：`BUILD_EXIT=0`；kernel `95fe8809…` 105,480,192 B；payload kernel `e4f13116…`；`boot.img` `3ada9562…` 201,887,744 B；`verify-boot-image: OK`；`image-arg-audit: OK (29 arguments, 575 bytes)`；frozen-before/after 一致。
- **判据自证**：`strings -a boot.img | grep -c "Pong UI:"` = 39（旧 28）；命中 `Pong UI: wallpaper existing-content=%d restore-stock=%d`、`Pong UI: submitting genuine wallpaper 7410 native lock+home path=%s`、`/Library/Wallpaper/Stills/iPad/7410.WWDC_2022-1024w-1366h@2x~ipad.wallpaper` ⇒ **F1 的壁纸选择代码确实进了本次镜像**。
- 构建期间排除的两处跨树污染（都写进了仓库）：`scripts/tests/test-series-source.py` 的 P-194 假红（共享 artifacts 目录里最新的 224 补丁 manifest 把 223 补丁的树判红，改为"优先取与本仓库 series 一致的 manifest"）；`/opt/k60/trees/springboard-out` 从 lead-out `cp -a` 播种时带进来的 141 个引用 `/opt/k60/trees/lead-out` 的旧对象文件（`make[7]: No rule to make target …/lead-out/…/nx_netif_gso.c`），删除 `tree/build/{xnu,native-ufs,storage-abi}` 后重建通过。
- 产物：`/mnt/e/k60-work/artifacts/springboard-20261114c/boot.img`、`build-manifest.json`（components: kernel_built `95fe8809…`、boot_img `3ada9562…`、fd `cf448571…`）、`fd/springboard-20261114c-cf4485712c29.fd`。**未上机**（用户铁则：boot 由 Lead 执行）。

---

### 5.2 三条 SpringBoard 噪声的初查（低优先，逐个排）

| 噪声（原文） | 初查结论 | 证据 |
|---|---|---|
| `_applyBackdropViewSettings error: invalid size: (0.33 x 0.33)` | **未定位**。SpringBoard 二进制里没有该字符串（日志来自私框架或 UIKit 断言），0.33 = 1/3，像 point/pixel 比例或约束求解退化；需要带 `kern.pong_diagnostic` 的当次日志才能定位调用栈。 | `docs/research/evidence/springboard-truth.txt:109-113`；`/tmp/osx/System/Library/CoreServices/SpringBoard.app/SpringBoard` strings 无命中 |
| `Unbalanced calls to begin/end appearance transitions for <SBCoverSheetPrimarySlidingViewController>` | **未定位**。属锁屏/通知中心滑块的转场计数告警；与"进不去系统"无因果，但在 `present_home observe-only` 路径下出现（`:3502`），说明 cover sheet 在无人操作时也在跑转场——值得与锁屏策略一起查。 | `springboard-truth.txt:109-113`、`:3499-3502` |
| `Failed to Soft Linked: /System/Library/Frameworks/CarKit.framework/CarKit` | **已定位（路径不存在，非权限问题）**：20G81 OS 窗里 CarKit 只有 **PrivateFrameworks** 路径（55 条命中），`System/Library/Frameworks/CarKit.framework` **0 条命中**；backboardd 二进制里硬编码的 `/System/Library/PrivateFrameworks/CarKit.framework/CarKit` 存在，但 SpringBoard 侧按公开路径软链失败。可用 `ui_compat` 的 `dlopen` 钩子把公开路径重定向到私有路径消除噪声（不影响功能）。 | `7z l /opt/k60/osroot/os.raw`：`System/Library/PrivateFrameworks/CarKit.framework` 存在、`System/Library/Frameworks/CarKit` 计数 0；`strings backboardd` 命中私有路径 |

> 三条都**不是**壁纸纯黑的原因：壁纸链的断点在 §2.2（视图从未挂上）与 §2.5（设备 UI 库无选择代码），与本组噪声无交集。按用户指示记录后逐个排。

---

### 5.3 F2 host 验证（var.skel + 0401 重嵌，2026-11-14）

- `python3 scripts/gen-var-skel.py --os-image /opt/k60/osroot/os.raw --out /tmp/f2-varskel` → `entries=133 skeleton_bytes=6608 reg_files=13 bytes=514`；var.skel 132 行 / 6,608 B（旧 129 行 / 6,498 B），新增两条目录行 `d\t755\t0\t0\t/private/var/pong/stock-wallpaper` 与 `…/Wallpaper`。
- `python3 userland/build.py init_blob --out /tmp/f2-init-out --sdk /opt/k60/sdk/iPhoneOS16.5.sdk --var-skel /tmp/f2-varskel/pong/var.skel` → `init-blob.json`：`{bytes: 52456, ncmds: 15, varpack_bytes: 14636, var_skel_bytes: 6608}`；从补丁抽回的 init / varpack 与输入逐字节相同（init sha256 `079a087b…`）。
- `scripts/tests/test-init-blob.py`（新增，16 用例）全绿：三个数组长度与 `#define` 一致、PONGJOB1 split/join 往返逐字节、var.skel 唯一且含两条 0755 root:root 壁纸目录、改写数组后三个 hunk 头行数自洽、init 为 thin arm64 MH_EXECUTE ncmds=15。
- 环境注记：SDK `SDKSettings.json` 的 `Version` 是 16.4，`-platform_version` 第三段必须写 16.4；`ld64.lld-18` 对 `-static` 只告警不实现（加不加产物 sha 相同 `079a087b…`），因此 host 产物不保证与 macOS 产物逐字节一致，但 LC 序列与设备 blob 相同。

---

## 6. 未决问题 / 下一步

1. **找 Lead 引用的 console.log**（528-529/2241/2247/2257）——本工作区无此文件，需 Lead 提供路径；否则"换壁纸进不去系统"只能停留在候选机制。
2. 设备上 bindfs 的实际返回值需 `Pong init: boot view … result=` 行确认（P-27 是另一次量测）。
3. F2 复查：0616 把 0401 的 installer 调用换成 34,904 B 旧助手（P-182），F2 的 52,456 B init 与 varpack 是死代码（§4 F2 复查）。生效项是 F3（0617：内核预置目录 + 复制 catalog），与 F1 一起进 springboard-20261114e；上机后按 §3 三行判据核对，重点抓 `K60WALL catalogue …` 与 `Pong init: boot view …` 两组日志。
4. 上机（交 Lead，用户明确同意后执行）：刷 0340 新 blob + `k60_wallpaper_reset=1` 启动一次；抓 `Pong UI: wallpaper …` 与 `Pong init: boot view …` 两组日志。

---

## 7. 引用清单（文件:行）

- `userland/init.c@2101281:337-338` prepare_boot_services；`:343-344` unpack_boot_jobs；`:345-364` views 表（含 :361-362 注释）；`:368-371` stock guard；`:373-378` 通用 guard；`:379` mount；`:380-381` boot view 日志；`:108-146` prepare_var；`:126-133` d 行解析；`:385-402` configure_ui_library。
- `userland/init.c:368-375` wallpaper_directory；`:383-443` wallpaper_aliases；`:478-479` wallpaper views；`:483-488` stock guard。
- `userland/init-v24dp.c:317-357` 历史视图组；`:336` "absent from the OS window" 注释。
- `userland/ui_compat.c:628-661` existing_wallpaper；`:669-741` select_initial_wallpaper；`:690` 7410 路径；`:707/716-717` 资产校验。
- `userland/build.py:40-45` BOOT_SKIP chronod；`:73-110` native_init_signature；`:178` BOOT_SKIP 日志；`:251-341` data_seed；`:338` 65,536 上限；`:365-393` compile_ui；`:395-413` embed_ui_library；`:416-423` ui 子命令；`:429-548` init_blob（PONGJOB1 split/join、embedded_blob、replace_embedded_array、compile_init_linux）；`:50-64` EXTRA 与 `scripts/gen-var-skel.py:28-44` 必须一致。
- `patches/xnu/0340-k60-uilib-deploy.patch:22-24` 声明与 blob；`:9520` k60_uilib_deploy；`:9541-9546` vn_rdwr/日志；`:9557-9559` 调用点。
- `patches/xnu/0401-k60-embedded-init.patch:62-67` boot-jobs 写盘；`:69-86` var.pack 写盘；`:104-112` k60_init_blob 门控与 helper exec；`:122-123` `K60_INIT_BLOB_LEN 52456` 与数组；`:24138-24139` `K60_VARPACK_LEN 14636` 与数组（以上 blob 自 0616 起不再被调用，P-182）。
- `patches/xnu/0616-k60-init-legacy-helper.patch:5-6` `K60_INIT_LEGACY_LEN 34904`；`:2923` 头文件 include；`:2937-2961` `k60_install_legacy_init()` 只写 `/private/var/pong/init`；`:2967-2978` 把 0401 的调用点替换掉。
- `patches/xnu/0617-k60-wallpaper-seed.patch` 全文 88 行：`k60_wallpaper_stage()`（读 772 B catalog 写目标）、`k60_mkdir_paths[]` 三条壁纸目录、mkdir 循环后的调用。
- `scripts/tests/test-init-blob.py`（新增）16 用例：数组长度/hunk 行数/PONGJOB1 往返/var.skel 壁纸目录/init Mach-O 形态。
- `docs/research/evidence/gpu-keys-notes.txt:19-20` 两行 SKIP 原文。
- `docs/research/evidence/springboard-truth.txt:109-113` 三条 SpringBoard 噪声；`:116/121` launchd sig=11 / K60PANICARGS。
- `docs/ops/PITFALLS.md:325-341` P-27 bindfs EPERM；`:1132-1139` P-75 壁纸目录可见≠选中。
- `docs/reference/HISTORY-LEDGER.md:297/302` v9alias 守卫与离线核实；`docs/reference/ISSUES.md:325-327` v7probe 第 5 条 mount 导致 hang。
- `scripts/gen-var-skel.py:28-42/135-146/151-154`；`scripts/pack-boot-jobs.py` PONGJOB1；`scripts/check-blob-patches.py` blob 门禁。
- `porting.toml:90` cand19 恢复镜像 `k60_wallpaper_reset=1`；`docs/engineering/PITFALLS.md:1990-2016` P-104（能跑的 init 必须落仓库）。

---

## 8. 本次变更清单

| 文件 | 变更 | 说明 |
|---|---|---|
| `patches/xnu/0340-k60-uilib-deploy.patch` | `k60_uilib_blob` 113,904 B → 113,472 B | 部署 HEAD `ui_compat.c`（含壁纸选择）；host 重编并嵌入，签名 4K 页校验通过 |
| `patches/xnu/0401-k60-embedded-init.patch` | `k60_init_blob` 52,376 B → 52,456 B；`k60_varpack_blob` 14,526 B → 14,636 B | 换 HEAD `init.c`（`wallpaper_directory`/`wallpaper_aliases`）+ 新 var.skel；hunk 4378/1225 同步。**注意：自 0616 起该 blob 的 installer 不再被调用，本行改动不生效（P-182）** |
| `patches/xnu/0617-k60-wallpaper-seed.patch` | 新增 88 行 | 内核在 launchd 前建壁纸两目录并把 `Collections~ipad.plist` 复制进目标（生效项） |
| `patches/xnu/series` | +1 行 | 0616 之后追加 0617 |
| `scripts/gen-var-skel.py` | EXTRA +2 目录 | `/private/var/pong/{stock-wallpaper,Wallpaper}` 0755 root:root |
| `userland/build.py` | +130 行 | `init_blob` 子命令：PONGJOB1 读写、数组替换、Linux init 编译 |
| `scripts/tests/test-init-blob.py` | 新增 | 0401 三个 blob 与 hunk 的回归测试（16 用例） |
| `docs/research/springboard/WALLPAPER-CHAIN.md` | 新增/更新 | 本文 |
