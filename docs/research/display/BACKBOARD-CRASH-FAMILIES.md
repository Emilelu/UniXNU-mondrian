# backboardd 崩溃家族总表（A / B / C）

状态：离线勘察，未上机。日期 2026-11-15。仓库 E:/hackios/k60-display，分支 feat/display。
本文件响应 Lead 2026-11-15 立项要求：把 backboardd 的崩溃按指纹分成家族，每族给出触发条件、
日志指纹（精确到格式串）、能否归因到我们的兼容钩子、以及「只用现有日志就能判」的判据。

## 0 结论摘要

| 家族 | 触发条件 | 日志指纹 | 归因 | 判据 |
| --- | --- | --- | --- | --- |
| A：NSURL nil（P-120） | pong_metal=1 注入 PongAdrenoMetal 插件 | NSURL initFileURLWithPath: nil string parameter + SIGABRT | 已知坑 P-120，金属注入，非背光 | grep 'nil string parameter' > 0 且 manifest payload_args 含 pong_metal=1 |
| B：int-236 SIGSEGV | 发布 backlight-control=true 的新 IOService | K60 BACKLIGHT: published … control 1（旧格式）/ conformance=1 control=1（新格式）+ backboardd sig=11 | 发布层引入（brightness-4 control=1 崩 4 次，brightness-13 control=0 零崩） | python3 scripts/check-backlight-log.py <log> EXIT=0 |
| C：getBytes:range: 类型不匹配（**已结案**） | 新 IORegistry 内容把字符串属性发到 DT 平面（bt 线 0509 补丁） | -[NSTaggedPointerString getBytes:range:]: unrecognized selector + NSInvalidArgumentException + SIGABRT | 不在我们的钩子里；触发源是 bt 线 0509 补丁的字符串属性（§3.3）；ad49ff2 改 OSData 后消失，与 0511 四个 hunk 无关（§3.4、§7.4） | grep -c 'getBytes:range:' > 0 即 C 族；崩溃次数 ≈ (命中数+1)/2；结案判据见 §7.1 三档 |

状态（2026-11-15 22:10 更新）：Lead 已收下本档案并离线复核确认 §3.3 归因；B 族口径终局——只认
brightness-4（control=1，4×SIGSEGV）对 brightness-13（control=0，0 崩）这一对，交付形态 A
（control=0 + 真 conformance）正式定稿；C 族的 0509 OSData 修复已合入 bt 线分支（ad49ff2：
三个属性改走 k60_bt_string_property()，OSData::withBytes(value, strlen(value)+1)；
test-k60-bt-0509-properties.py 25 例全过），bt 下一张全量图会带着它，Lead 飞完即给本线实测判据；
验证图由 Lead 直接排窗口上机（用户已放权 Lead 连续 boot，不再需要单独批准）；dyld 缓存由 Lead 在
队列空一轮、设备回 Android 有 adb 时拉取，拉完通知我做符号化（scripts/check-crash-symbols.py 已写好待命）；
springboard 线类型编码线索已收录 §3.3；§3.5 是本族判定表。

状态（2026-11-15 23:15 更新）：Lead 收下 04f965b（§3.5 判定表）与 97d6645（符号化脚本），
确认「以后按表判、不再口头判」。C 族现在还判不了，因为**能判的镜像一张都还没飞**：已飞的 h1/h3/h13
与负向 s4c 都不带 ad49ff2，只能当基线（§3.5 基线对照）；要判的是「全量 0511 + ad49ff2」那张，由 bt 线出图。
P-165/P-166 的 stale stamp 不为刷新而专门重建（P-207/P-208 教训：门禁只判本轮物证，为变绿造镜像不产生新知识）；
dyld 缓存暂时拉不了，原因是路径而非窗口（§5）。新增 §6「0 字节日志的判决时效」——跨线教训，判 C 族前必须先过这一关。

状态（2026-11-16 01:05 更新）：按 Lead 00:50 回复改三处——§7.1 表头加「步 1 为 NO 时本表整体作废」；
§7.2 补中位命中行，新增 §7.2.1「噪声还是周期性」间隔分布（C 族聚簇/事件驱动：同 pid 0.001–0.06 s 成对、
跨 pid 中位 10.3 s；A 族同形状 ⇒ A 族不需要按周期性单独立项）；§7.4 换成七格矩阵（补 s4c 与 h3），
并写下对 Lead「h2 是前置」的两条反证（h1 无 h2 但 :186 已发布、s4c 有 h2 仍 37 次）与缺格
「带修复、不带 h2」——该格从未飞过，是唯一能证成或证伪那条链的实验。

状态（2026-11-16 02:20 更新，C 族结案）：Lead 02:11 补飞了决定性的 h34（带 0509 修复、无 h1 无 h2），
getBytes 0 / SpringBoard 128 / first frame 1 ⇒ 「h2 是前置」的因果链作废，唯一变量是 0509 OSData 修复；
§7.4 从七格扩成八格并定稿，§3.4 写成结案。同时更正一条归因：「探针梯子不进」由 **h3 单独**造成
（h34 有 h3 无 h2，梯子同样不进），是可观测性副作用、不是失败，不能当判据。

状态（2026-11-16 02:50 更新，dyld 缓存不再需要设备）：§5 从「缺口」改写为「已取到」——
20G81 的 dyld shared cache 就在本地 IPSW 的 SystemOS cryptex（`096-56782-083.dmg`）里，
用 `scripts/dyld-cache-index.py` carve 出 2620 个 image 的索引（`E:/k60-work/caches/20G81/dyld-index-20G81.json`），
slide 直接取日志里我们自己打的 `K60SR… slide=0x…` 行。§5.1 给出已经解出的 C 族与 A 族两条栈：
C 族落在 IOMobileFramebuffer + QuartzCore + libdispatch（显示提交路径），A 族落在 Foundation + libxpc
（`syncdefaultsd` 的 XPC 取 URL 路径），两条路径独立，与 §1/§3.3 的归因一致。只有 backboardd 私有段
（`0x1011…`/`0x1007…`）仍解不出，那需要 `.map` 或设备 `.symbols`——**已从阻塞项降为可选项**。

结构性结论：B 与 C 是同一个根——「**向 IORegistry 发布此前不存在的内容，会激活 backboardd 里
一直死着的 Apple 代码路径**」。B 死在新路径本身，C 死在新内容与 Apple 代码的**类型约定不匹配**
（DT 平面属性应为字节数组，发成了字符串）。这对 display 线是旁证：交付形态 A（默认不发
backlight-control）仍是正确终局，不是妥协。

## 1 家族 A：NSURL nil（P-120，金属注入）

- 触发条件：pong_metal=1，userland/build.py:516 的 metal 段把 PongAdrenoMetal.bundle/PongAdrenoMetal 注入 backboardd。
- 指纹：*** Terminating app due to uncaught exception 'NSInvalidArgumentException', reason: '-[NSURL initFileURLWithPath:isDirectory:]: nil string parameter'，SIGABRT（sig=6）。
- 样本：gpu-20261114t（证据 E:/k60-work/evidence/usblog-20261114-235957）——已被 Lead 2026-11-15 更正确认是 P-120，与 int-236 无关。
- 归因：已知坑 P-120（docs/engineering/PITFALLS.md），不是背光发布层，也不在本线 scope。
- 判据：日志 grep 'nil string parameter' > 0，且对应 manifest 的 payload_args 含 pong_metal=1。

## 2 家族 B：int-236（backlight-control 发布后 SIGSEGV）

- 触发条件：IOService 发布 backlight-control=true（brightness-4，k60_backlight_control=1）。
- 指纹：旧格式 K60 BACKLIGHT: published level 2047 dbv 0xff control 1（brightness-4 console.log:183），新格式 K60 BACKLIGHT: published level … conformance=1 control=1；随后 backboardd 多次 sig=11（SIGSEGV），SpringBoard 只有几行，0 条 first frame、0 条 swap。
- 归因：发布层引入——同一镜像族 brightness-13（conformance=0 control=0）零崩溃（判定器 EXIT=0，证据 usblog-20261115-134638，SpringBoard 128 行、first frame 出现）。详见 INT-236-CHAIN.md 与 HANDOFF-20261114.md。
- 判据：python3 scripts/check-backlight-log.py <console.log>（旧形态加 --old-form）。脚本判 conformance/control、stats[0]、request[4]/[5]、sig=11 计数与 first frame。

## 3 家族 C：getBytes:range: 类型不匹配（新，bt-s4c-20261115c）

### 3.1 现场

- 证据：E:/k60-work/evidence/usblog-20261115-162553/console.log（3535 行）。
- 镜像身份（manifest）：series **229**、kernel_args_requested=['k60bt=1']、repo feat/bt-research head 5190337be6；boot.img sha256 dbf089c0ac0f5325f3661ae8e0d22e0d1b70fced1141234cb2c677b3b3a98d03。
- 崩溃节奏：entered backboardd 共 **19** 行（:1258,1331,1843,2081,2221,2359,2452,2532,2689,2752,2851,2974,3032,3103,3240,3287,3368,3438,3519）＝19 个 backboardd 化身**全灭**；~10.2 秒一次（04:32:41.482 → 04:35:38.112）；每次崩在 Pong UI 钩子装好约 1 秒后（pid 55：:1258 进入、:1260-1271 六个钩子 installed、:1303 崩）；线程号递增（376/749/1423/2168/2426/…）。KX! 只打第一次尸体（:1308 KX! 6 55 backboardd exit=0 sig=6 r=1 ns=2 code=0x6；:1310 KXPC pc=0x1d56f1198 lr=0x1e4bad5f8 sp=0x16ecfd350；:1311 KXP 55 /usr/libexec/backboardd），后续化身只留 Process[N] crashed 行（全日志 46 行）。
- 指纹行（:1303 / :1304，精确格式）：

    2026-11-03 04:32:41.482 backboardd[55:376] -[NSTaggedPointerString getBytes:range:]: unrecognized selector sent to instance 0xa591462ccf9314fd
    2026-11-03 04:32:41.511 backboardd[55:376] *** Terminating app due to uncaught exception 'NSInvalidArgumentException', reason: '-[NSTaggedPointerString getBytes:range:]: unrecognized selector sent to instance 0xa591462ccf9314fd'

- first-throw 栈形状（34 个栈全部同形，:1306 为例）：
  (0x19b42148c 0x194775050 0x19b582424 0x19b436938 0x19b49897c 0x1c3831abc 0x1a21c3780 0x1a2193ddc 0x1c383197c 0x19c9de080 0x19cb12278 0x19cb1a8d8 0x1a21c3780 0x1a2193ddc 0x19cb1a824 0x10111f930 0x1a21c…。栈底私段帧（0x10… 段）每化身不同：pid 55 = 0x10111f930、pid 139 = 0x100b04930、pid 177 = 0x100aa9930（ASLR 滑动）；0x1a21c3780/0x1a2193ddc 出现两遍（重入形状）。私段帧既可能是 backboardd 主二进制也可能是我们的 libpong-ui.dylib——两者同在 0x10… 段，无 20G81 shared cache 无法区分（§5 缺口）。
- 本日志 SpringBoard 只 13 行、0 条 first frame、0 条 swap（backboardd 全灭，桌面起不来）；另混有 1 个 NSURL nil 族栈（:1881，syncdefaultsd 形状 0x195873e2c 0x195873bdc），说明 A/C 可以共存。

### 3.2 与 brightness-13 的唯一差异（归因关键）

| | brightness-13（0 崩） | bt-s4c-20261115c（19 崩） |
| --- | --- | --- |
| series | 224 | **229（+0507/0508/0509/0510/0511）** |
| kernel_args | [''] | ['k60bt=1'] |
| payload_args / 注入列表 | pong_metal=2 … k60_skip_iosurface=1（逐字相同） | 逐字相同 |
| 背光服务 | conformance=0 control=0 | 无（0 条 K60 BACKLIGHT） |

payload 与注入完全一致、崩溃却又多 19 次 → 差异只在**内核补丁集**。五个 bt 补丁里只有
**0509-k60-bt-s3-identity-publish** 动了注册表（另四个只改 bsd/dev/qbt_k60.c 与 osfmk 的
BT 驱动/固件装载），所以注册表增量就是 0509。

### 3.3 归因：不在我们的钩子里，触发源是 bt 线 0509 的字符串属性

1. **我们的代码没有这个调用形状**：userland/ui_compat.c 的全部 ObjC 调用都是带类型的 objc_msgSend 强转（UIScreen mainScreen/nativeScale/nativeBounds :162-173；NSBundle :222-224；_productVersionStringFallback 带 isKindOfClass: 检查 :267-270；异常 description :367-368），全文件 grep getBytes|NSData|bytes]|data bytes = 0 命中；init.c 同样 0 命中。libpong-ui.dylib 确实被注入 backboardd（build.py:515 的注入名单），但它没有任何把 NSString 当 NSData 传的分支。
2. **崩溃是类型不匹配的形状**：接收者是 NSTaggedPointerString（短字符串的 tagged 表示）——正是 setProperty(key, "短字符串") 在用户态读回时的类型；getBytes:range: 是数据型访问。即某段 Apple 代码把「字符串属性」当「字节数组属性」读。
3. **仓库自己的内核代码证明约定**：DT 平面的 device_type/compatible 必须以 OSData（原始字节）发布、以 OSDynamicCast(OSData,…) 读取——drivers/ArmCpu/ArmCpu.cpp:103（OSData *compatible = OSDynamicCast(OSData, gic->getProperty("compatible"))）、:302、:514（device_type 同）、drivers/ArmDTPlatform/ArmDTPlatform.cpp:192（device_type）、drivers/NativeUfs/NativeUfs.cpp:53-55。
4. **0509 违反了这个约定**：iokit/Kernel/MiniBluetooth.cpp（新文件）把 node->setProperty("device_type", "bluetooth")、compatible → "qcom,wcn7850-bt"、unixnu,adt-name → "bluetooth" 发成字符串（transport-encoding/speed 与 local-mac-address 倒是正确的原始字节）；同样的字符串属性也发到了 K60BluetoothRadio 服务上（radio->setProperty("device_type","bluetooth")），并且 registerService()；调用点在 iokit/Kernel/MiniIOSurface.cpp native_pong_ui_services_start（MiniAcceleratorPublishStub 之后加 MiniBluetoothPublishStub(provider);），门控 PE_parse_boot_argn("k60bt")。这与 k60bt=1 才崩、不设不崩的现场完全吻合。
5. **Lead 2026-11-15 离线复核确认**：0509-k60-bt-s3-identity-publish.patch:185-187 正是这三行 C 字符串 setProperty（device_type / compatible / unixnu,adt-name），IOKit 语义下是 OSString 而非 DT 平面的 OSData 字节，引用准确；触发链闭合——0509 一直在，但 patches/bt/0005-k60-bt-s4-unblock.patch:8（镜像 patches/xnu/0511-k60-bt-s4-unblock.patch，series:209）的 hunk-2 删掉了 k60_bt_power_on() 的冷启动 `return -EOPNOTSUPP`，身份发布代码第一次真正执行 → 崩溃第一次出现（全仓库 30+ 份日志只有 bt-s4c 这一份命中）。
6. **springboard 线补充线索（Lead 2026-11-15 转达）**：userland/ui_compat.c:723-729 的 20G81 兼容层先验做法——`method_abi(setter,"v",3,"@B@")` + `strcmp(method_getTypeEncoding(setter),"v36@0:8@16B24@?28")` 在调用前断言精确类型编码；类簇（NSString/NSData）返回类型编码错标正是打出 unrecognized selector 的经典方式。该段可作 C 族修复后「宿主侧断言发布属性是 OSData」的参照（内核侧约定已是 OSDynamicCast(OSData,…)，ArmCpu.cpp:103）。springboard 线全链 grep getBytes=0，与本族「不在我们的钩子」归因不冲突。
7. **结论**：C 族崩的是 backboardd 里某 Apple 框架「把新出现的字符串属性当数据读」的路径（最可能是只有出现 bluetooth 设备时才会激活的 HID/蓝牙事件路径——HID 事件系统住在 backboardd 里）；具体是哪个系统帧，离线无法点名（缺 20G81 shared cache，§5）。可以肯定的是：**不在我们的显示钩子里**，且与本线的 K60Backlight 无关（bt-s4c 根本没有背光服务）。

### 3.4 结案：C 族根因是 0509 的 OSString，修复与 h1–h4 无关（2026-11-16 定稿）

- device_type / compatible / unixnu,adt-name 改用 OSData 发布（模拟真实 FDT 的字节数组），与仓库内核读取侧（OSDynamicCast(OSData,…)）的约定一致；
- 或先只发 DT 节点、砍掉 K60BluetoothRadio 的 registerService()，确认 bluetoothd 能否只靠 DT 子节点工作；
- 验证：同一张镜像 k60bt=0 起飞（预期 0 崩）→ 修复版 k60bt=1（预期 0 崩 + bluetoothd 正常）。
- 修复后的宿主侧断言参照：仿 userland/ui_compat.c:723-729 的 method_abi + strcmp 精确类型编码断言，在用户态把读回的属性先按类型校验再用（内核侧读取约定 OSDynamicCast(OSData,…) 保持不变）。
- 进度（Lead 2026-11-15 22:10）：0509 OSData 修复已合入 bt 线分支（ad49ff2，三个属性改走 k60_bt_string_property()；test-k60-bt-0509-properties.py 25 例全过）；bt 下一张全量图带它，Lead 飞完即给本线实测判据。验证图由 Lead 直接排窗口上机（用户已放权 Lead 连续 boot，不再需要单独批准），本线只等实测结果、按 §3.5 判定表判。

**结案（2026-11-16 02:15，Lead 02:11 授权）**：

- **根因**：0509（`patches/xnu/0509-k60-bt-s3-identity-publish.patch`）把 `device_type` / `compatible` /
  `unixnu,adt-name` 三个 DT 平面属性发成 OSString，而 DT 平面约定是 OSData 原始字节（§3.3 第 3 条）；
  backboardd 里某条 Apple 代码按数据读这些属性 → `-[NSTaggedPointerString getBytes:range:]` → SIGABRT。
- **修复**：bt 线 ad49ff2 把三处（外加 radio 的 device_type）改走 `k60_bt_string_property()`
  （`OSData::withBytes(value, strlen(value)+1)`，带 NUL 结尾）。
- **修复与 0511 的四个 hunk 无关**：八格矩阵（§7.4）里带修复的三格 h12（h1+h2）/ h23（h2+h3）/
  h34（h3+h4，**既无 h1 也无 h2**）全部 getBytes 0 + SpringBoard ≥128 + first frame 1。
- **实测判据**：§7.1 的 C-alive 三条件（G=0、S≥100、F≥1）且步 1（命令 D 非 0）为 YES。
- **回归确认**：bt 线最终补丁集（bt-late / d 系列）若仍满足 C-alive 即可；不满足则按 §3.5.1 三属性二分。
- 未做的一步：`registerService()` 是否也需要砍掉，从 h34 看不需要——三格都保留了它且桌面起来。

### 3.5 C 族判定表（可机判；P-204 形状）

基线日志 `E:/k60-work/evidence/usblog-20261115-162553/console.log`（3535 行，19 个 backboardd 化身全灭）。
下面每条都写明「哪一行日志、用什么命令数出来」，修复图落地后照表判即可。

基线对照（Lead 2026-11-15 23:15 提供，本线复核字节数与命中数）：四张已飞的 bt 二分图**都不带** ad49ff2，
只能当基线——h1 `E:/k60-work/evidence/usblog-20261115-211515/console.log`（245,272 B）、h3 `usblog-20261115-212105`（232,888 B）、
h13 `usblog-20261115-212643`（237,533 B），三张 `getBytes:range:` 各 **36** 次；负向 s4c 37 次。
非 bt 的两张对照 adsp-c `usblog-20261115-213413`（214,232 B）与 adsp-e `usblog-20261115-223916`（220,234 B）都是 **0** 次——
崩溃只在 bt 的 0509 身份发布链上出现，与内核版式无关（进一步支持 §3.3 归因）。判定仍以 §3.5 命令 A 的五数为准。

命令 A（数指纹，cwd = 证据目录，L=console.log）：

```sh
grep -c 'getBytes:range:' $L          # 基线 37（Lead 口径 36，同量级）
grep -cE 'KX!.*backboardd' $L         # 基线 1（健康 = 0）
grep -c 'entered backboardd' $L       # 基线 19（健康 = 1）
grep -c 'SpringBoard' $L              # 基线 13（健康 ≥ 100）
grep -c 'first frame presented' $L    # 基线 0（健康 ≥ 1）
```

| 判定 | 条件（命令 A 的五个数） | 动作 |
| --- | --- | --- |
| 修复生效 | 0 / 0 / 1 / ≥100 / ≥1 | C 族结案：把五数写进 HANDOFF 与 EIGHT-STEPS device 证据 |
| 修复部分生效 | 08 ≤ getBytes ≤ 18（显著下降但仍在） | 还有第二个 OSString 发布点：跑命令 B 抽新 selector/实例类型，再跑命令 C 找漏网字符串属性 |
| 未生效 | getBytes ≥ 19（与 37 同量级） | 先跑命令 D 确认飞的镜像真带修复；确认后再按 §3.5.1 三属性逐个二分 |

命令 B（部分生效时抽新 selector / 实例类型）：

```sh
grep 'unrecognized selector' $L | sed -E 's/.*-\[([^ ]+) ([^]]+)\].*/\1 | \2/' | sort | uniq -c | sort -rn
# 基线只有一行：37  NSTaggedPointerString | getBytes:range:
# 出现第二种组合（如 NSData | bytes 或 NSString | getBytes:length:）= 第二个发布点
```

命令 C（在 bt 线找未走 k60_bt_string_property() 的字符串属性）：

```sh
git -C /mnt/e/hackios/k60-display grep -n 'setProperty("[^"]*", *"' origin/feat/bt-research -- iokit bsd \
  | grep -v k60_bt_string_property
```

命令 D（确认镜像真带 ad49ff2 的修复）：

```sh
llvm-nm <kernel.macho> | grep -c k60_bt_string_property   # 新版 0509 才有；0 = 飞错镜像
jq -r '.repo.head, .series.sha256' <build-manifest.json   # 与 bt 分支 ad49ff2 之后的全量图对照
```

#### 3.5.1 未生效时的属性二分（三个镜像，均 k60bt=1）

| 镜像 | 发布方式 | 判据 |
| --- | --- | --- |
| H1 | 只把 device_type 改回 OSString，另两个 OSData | getBytes 命中回到 ≥19 → device_type 是触发点 |
| H2 | 只把 compatible 改回 OSString | 同上 → compatible 是触发点 |
| H3 | 只把 unixnu,adt-name 改回 OSString | 同上 → adt-name 是触发点 |

三个镜像都 0 崩 → 触发点不在这三个 DT 属性（radio 的 device_type 也在 ad49ff2 里改成了 OSData），
回到命令 B/C 找第二个发布点。

## 4 判据汇总（只用日志）

    grep -c 'nil string parameter'  log   # >0 且 manifest 有 pong_metal=1 → A 族（P-120）
    grep -c 'sig=11'                log   # >0 且 published 行 control=1 → B 族（int-236）
    python3 scripts/check-backlight-log.py log   # B 族正判器，EXIT=0 为 PASS
    grep -c 'getBytes:range:'       log   # >0 → C 族；崩溃次数 ≈ (命中数+1)/2（成对打）

C 族完整判定表（三档判据、命令 A–D、三属性二分）见 §3.5；**按什么顺序读、每档怎么落判**见 §7。

## 5 dyld 共享缓存：已从本地 IPSW 取到（2026-11-16，不再需要设备）

- **结论：20G81 的 dyld shared cache 不需要设备、不需要 adb。** 它在本地 IPSW 的 SystemOS cryptex 里：
  `E:/hackios/UniXNU/out/ipsw/20G81/096-56782-083.dmg`（Cryptex1,SystemOS，2,665,480,192 B，
  sha256 `bae1f451b77c17f8984980236ab577f89a8a4c5407bdc25c4242a34e11b0e7af`）。
  OS dmg（`096-57366-083.dmg`）里没有：单卷 `System/Library/Caches` 只有 apticket.der、com.apple.factorydata、
  com.apple.kernelcaches，全卷唯一的 dyld 相关文件是 `/usr/lib/dyld`（922,912 B）。
- **为什么不走文件系统**：SystemOS 卷是 sealed（incompat 0x28），`tools/apfs/apfs.py` 的 omap 缺项
  （root tree oid 1198 → 153489 全零，`bad Fletcher-64 checksum`），tree 元数据可读但 `iter_all()` 立刻炸。
  所以走 carve：内容确实在镜像里（全盘扫 `dyld_v1` 得 55 个命中、41 个 4096 对齐；
  独立佐证是全镜像里 `libSystem.B.dylib` 出现 2610 次）。
- **carve 方法**（`scripts/dyld-cache-index.py`）：按 8 MiB 块扫 `dyld_v1` 魔数，取第一个 imagesTextCount≥100 的
  对齐成员（本次 member `0x110a000`），读 header `0x88`=imagesTextOffset（`0x149f0`）、
  `0x90`=imagesTextCount（2620）；每条记录 32 字节：`uuid[16] | loadAddress u64 | textSize u32 | pathOffset u32`，
  路径串就在同一成员内。产物 `E:/k60-work/caches/20G81/dyld-index-20G81.json`（476,573 B，2620 images，0.36 s）。
- **slide 不用猜**：我们自己的服务扫描已经把它打进日志了——`K60SR26 t=75 start=0x1946b0000 slide=0x146b0000`
  （s4c console.log:1174）。490 份历史 usblog 里 119 份带这行（首份 `usblog-20261112-184616`），
  更早的图没有 K60SR 探针，脚本会 exit 2。一份日志里 A 族与 C 族各有一条 backtrace，用 `--after <marker>` 选。
- 用法：

  ```sh
  python3 scripts/dyld-cache-index.py \
      --index /mnt/e/k60-work/caches/20G81/dyld-index-20G81.json \
      --log console.log --after 'getBytes:range:' --frame-limit 16
  ```

  退出码 0 全解 / 1 有帧在缓存外 / 2 索引或日志缺失；`--json` 给机器读；`--selftest` 11 项。
  它给的是 **image 级**（哪个 dylib + 偏移）；`scripts/check-crash-symbols.py`（bb86175，吃 `.map`）给符号级，
  两者互补——没有 `.map` 时用本节，有 `.map` 时用那个。

### 5.1 已经解出来的两个栈（2026-11-16 02:45）

C 族（`--after 'getBytes:range:'`；s4c slide `0x146b0000` 与 h1 slide `0x1eeac000` 逐帧同形，15/16 帧解出）：

    CoreFoundation+0x948c → libobjc.A.dylib+0x15050 → CoreFoundation+0x16a424 → CoreFoundation+0x1e938
    → CoreFoundation+0x8097c → IOMobileFramebuffer+0x7abc → libdispatch+0x64780 → libdispatch+0x34ddc
    → IOMobileFramebuffer+0x797c → QuartzCore+0x12b080 → QuartzCore+0x25f278 → QuartzCore+0x2678d8
    → libdispatch+0x64780 → libdispatch+0x34ddc → QuartzCore+0x267824 → 私有段

A 族（`--after 'nil string parameter'`；s4c slide `0x146b0000` 与 h34 slide `0xa634000` 逐帧同形，10/12 帧）：

    CoreFoundation+0x948c → libobjc.A.dylib+0x15050 → Foundation+0x5ae2c → Foundation+0x5abdc
    → 私有段 ×2 → Foundation+0x99bd4 → Foundation+0x54df88 → Foundation+0x54f5ec → Foundation+0x54f0ec
    → libxpc+0xf788 → libxpc+0xfb68

读法：

- **C 族崩在显示提交路径，不是 BT 事件路径**：栈里是 IOMobileFramebuffer + QuartzCore + libdispatch，
  没有 IOKit / Bluetooth 帧。这与 §3.3 的「新发布的字符串属性被当字节读」一致——读它的是 CA 侧的对象图，
  所以补丁发的是属性、崩的是显示栈，两者不矛盾。
- **A 族栈底是 libxpc**，正是 `syncdefaultsd` 通过 XPC 取文件 URL 的路径，与 P-120（金属注入把 nil 传进
  `initFileURLWithPath:`）相符，进一步说明 A 族与 C 族是两条独立路径。
- 未解的帧全是 backboardd 私有段（`0x10111f930` / `0x1007e8f48` / `0x1011eaf48` / `0x100f04930`）。
  镜像级索引只能到 dylib 粒度；要指名 backboardd 内部的函数仍需 `.map` 或设备上的 `.symbols`。
  **P-120 与 C 族的归因都不依赖这一步**，所以 `.map` 已从阻塞项降为可选项。

## 6 0 字节日志的判决时效（跨线教训；Lead 2026-11-15 指派）

- 现象：console.log **0 字节** + 设备 autoreset 回 fastboot。看起来像「内核根本没跑」，实际最常见的是
  「内核跑了，但死在 USB 控制台把日志送出去之前」。
- 机制（adsp-e 实测 `E:/k60-work/evidence/usblog-20261115-223916/console.log`，3,312 行）：
  `K60 USBLOG: st=2 ev=0 cfg=0 dtr=0` 在 :248，直到 `K60 USBLOG: st=4 ev=595 cfg=1 dtr=1`（:477）主机才真正连上，
  紧接着 `K60DATA mounted ro=0 fstype=apfs` 在 :485。根挂载阶段及其之前的任何 panic 都留不下一个字节。
- 实测案例（Lead 2026-11-15 报告，wifi 线复核）：mhi3 / mhi4 / z0 / t2 / c0 五张 wifi 图全部 silent，
  真因不是内核版式，而是 wifi defconfig 指名的 Data UUID 是 32 MiB seed 的
  `6DCCF70A-6FD6-403E-ACED-95313CD7CBB8`（patches/wifi/0007-configs-mondrian-wifi-defconfig.patch:52），
  真机 Data 卷是 `1BCD69FF-24A5-48B1-94B6-8FE592B2F597`（configs/mondrian_defconfig:54，`CONFIG_XNU_OWNER_DATA_UFS=y` :47）；
  drivers/NativeRamBlock/NativeRamBlock.cpp:443-447 的 `waitForMatchingService(..., 5s)` 等不到就返回 0
  （日志 `NativeRamBlock: Data UUID %.36s not published within 5s`），根挂载随之失败并自 panic。
- 判据（**先配置、后版式，别先造机制**）：
  1. 先确认它真是 0 字节：`find /mnt/e/k60-work/evidence -maxdepth 2 -name console.log -size 0`
     （目前 41 份，如 `usbcmd-test-210941`、`usblog-20261112-180735`）——0 字节与「全 0 命中」是两件事。
  2. 第一步 diff **构建配置**：`git -C /mnt/e/hackios/k60-display show <tag>:configs/mondrian_*_defconfig | grep -E 'OWNER_DATA_(MOUNT|UFS|VOLUME_UUID)'`，
     与 configs/mondrian_defconfig:43/47/54 对照；UUID 必须是真机已安装 UFS Data 的 `1BCD69FF-…`，不能是 seed 的 `6DCCF70A-…`。
  3. 第二步才 diff 内核版式（__TEXT/__DATA/payload 结构），第三步才怀疑某个驱动。
- 门禁：Lead 已在 main 落 `scripts/check-defconfig-uuid.py`（P-209）。本分支 rebase 到的 origin/main 2ce089a 里还没有这个文件，
  等它进 main 后本线门禁自动覆盖；此段按 Lead 口径记录，暂不引用行号。
- 与本族的关系：A/B/C 三族都要求镜像至少活到 backboardd 起来；0 字节族死在更早阶段，
  用 §4 的判据会得到「getBytes=0、SpringBoard=0、first frame=0」的假健康。所以判 C 族前先过一遍本节。

状态（2026-11-16 00:10 更新）：Lead 23:59 指派 §7「C 族的判定顺序」已落地（三档 C-alive /
C-shadowed / C-alive-but-noisy + 一行判定命令 + 行号对格式）；复核发现已飞的 h12/h23 就是首批带 ad49ff2
的镜像，getBytes 0 / SpringBoard 132,128 / first frame 1 ⇒ C 族按 §7.4 判 C-alive，不必等 bt-late 图。

## 7 C 族的判定顺序（把症状写成流程；Lead 2026-11-15 23:59 指派）

§3.5 是「数哪五个数」，本节是「按什么顺序读、每档怎么落判」。判 C 族**不是先看崩溃次数**，
而是先排除「没活到能判」和「飞错镜像」两种假象，再看命中数与桌面存活度。顺序固定为四步：

    步 0  日志是不是 0 字节？        → 是：§6，先判「死在 USB 控制台之前」，与 C 族无关
    步 1  镜像真带 ad49ff2 吗？      → 否：只能当基线（§3.5 基线对照），不判 C 族
    步 2  数 getBytes 命中 + 桌面存活 → 三档之一（下表）
    步 3  抽签名                       → 只用来解释「被谁遮住」或「第二个发布点」

**所有计数一律加 `-a`**。真实日志里混有二进制字节（h23 的 console.log 就被 grep 判为 binary），
不加 `-a` 时 `grep -c` 仍给数字，但 `grep -oE`/`sed` 管道会输出 `binary file matches` 而静默变成 0 行——
本线在 23:57 就因为漏了 `-a` 得到过「h23 的 uncaught exception 抽不出来」的假结论。

### 7.1 三档判据（一行命令出结论）

```sh
L=console.log
G=$(grep -ac 'getBytes:range:' "$L"); S=$(grep -ac 'SpringBoard' "$L"); F=$(grep -ac 'first frame presented' "$L")
if   [ "$G" -eq 0 ] && [ "$S" -ge 100 ] && [ "$F" -ge 1 ]; then echo "C-alive  (G=$G S=$S F=$F)"
elif [ "$G" -eq 0 ];                                    then echo "C-shadowed (G=$G S=$S F=$F)"
elif [ "$G" -lt 19 ];                                   then echo "C-alive-but-noisy (G=$G S=$S F=$F)"
else                                                         echo "C-not-fixed (G=$G S=$S F=$F)"; fi
```

**本表只在步 1 为 YES 时适用；步 1 为 NO（镜像不带 ad49ff2）时本表整体作废，不要逐行套用。**
0 字节日志（wifi 家族 c0/c1/c2/z0/t2/mhi3/mhi4）用同一条命令会得到 G=0 S=0 F=0 的「C-alive」，
那是没采集到，不是没崩溃。那七张的死因现已查明是 UFS 抢在锁分配前要 Apps SMMU lease（P-215，
patches/wifi/0012 惰性分配后 c3 已进 SpringBoard 132），与 C 族无关——但它们作为「0 字节会被误判」的
例子仍然有效。

| 档 | 条件 | 含义 | 落判动作 |
| --- | --- | --- | --- |
| **C-alive** | getBytes = 0 **且** SpringBoard ≥ 100 **且** first frame ≥ 1 | 0509 的 OSData 修复在真机生效，C 族结案 | 五数（G/S/F/entered/crashed）写进 HANDOFF 与 EIGHT-STEPS device 证据，§0 状态标 C 族 closed |
| **C-shadowed** | getBytes = 0 **但** SpringBoard < 100 | 不是生效也不是失败：C 族症状消失了，但桌面死在**别的族**手上 | 跑 7.3 抽签名，写明是哪个族（A 见 §1、B 见 §2），并把该族判据行抄进结论；不得记为「修复生效」 |
| **C-alive-but-noisy** | 0 < getBytes < 19（显著下降，如 36 → 3） | 部分生效：还有第二个 OSString 发布点 | 给**下降前后的行号对**（见 7.2 格式），跑 §3.5 命令 B 抽新 selector/实例类型，再跑命令 C 找漏网字符串属性 |
| （未生效） | getBytes ≥ 19，与基线 36/37 同量级 | 镜像没带修复或修复无效 | 先跑 §3.5 命令 D 确认镜像带 ad49ff2；确认后才按 §3.5.1 三属性二分 |

**注意：C-alive 不等于「修复生效」。** 不带 0509 的控制图（如 adsp-e `usblog-20261115-223916`，G=0 S=120 F=1）
用同一条命令也判 C-alive——因为它压根没发布那些字符串属性。所以**步 1 必须先过**：只有镜像真带 ad49ff2
（命令 D 非 0）时，C-alive 才等于「修复生效」；否则它只说明「这张图不涉及 C 族」。

### 7.2 C-alive-but-noisy 必须给的行号对、中位次与间隔分布

「次数下降」只有配上「第一次命中在第几行、最后一次在第几行」才是证据，否则无法与
「日志变短」区分。五张不带修复的基线实测（`grep -an 'getBytes:range:' $L | head -1` / `tail -1`）：

| 日志 | 总行数 | 首命中行 | 末命中行 | 命中数 | 中位命中行（占全文） |
| --- | --- | --- | --- | --- | --- |
| s4c `usblog-20261115-162553` | 3535 | :1303 | :3528 | 37 | :2761（78%） |
| h1 `usblog-20261115-211515` | 3558 | :1463 | :3527 | 36 | :2810（79%） |
| h3 `usblog-20261115-212105` | 3355 | :1311 | :3319 | 36 | :2565（76%） |
| h13 `usblog-20261115-212643` | 3376 | :1252 | :3336 | 36 | :2545（75%） |
| h4 `usblog-20261115-230627` | 3703 | :1384 | :3659 | 36 | :2948（80%） |

修复图若变成 3 次，就写成「37 → 3，首命中 :1303 → :xxxx，末命中 :3528 → :yyyy」，
并说明剩下的命中是集中在启动早期（第二个发布点只跑一次）还是贯穿全程（另有循环发布）。
中位次给的是「命中在日志里的重心」：75–80% 说明崩溃一直持续到日志末尾（进程没活下来过），
若修复后降到 20% 以下，说明只在启动早期打过一次、之后桌面活下来了。

### 7.2.1 噪声还是周期性：相邻间隔分布（Lead 2026-11-16 00:50 要求）

判 noisy 档剩下的命中是「偶发噪声」还是「周期行为」，不能只看次数，要看**相邻命中的时间间隔落在哪个桶**。
两条命令就能把时间轴拉出来（`-a` 不能省，日志里有二进制字节）：

```sh
L=console.log
grep -an 'getBytes:range:' "$L" | grep -a 'unrecognized selector' | cut -d: -f1        # 行号序列
grep -a  'getBytes:range:' "$L" | grep -a 'unrecognized selector' \
  | grep -aoE '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:.]+'                                  # 时间戳序列
```

实测（C 族，四张不带修复的图；dt 由相邻两行时间戳相减）：

| 日志 | 命中 | 不同 pid | 同 pid 两次命中 dt（中位） | 相邻 pid 首次命中 dt（中位） | 桶 <0.1s / 0.1–1s / 1–9s / 9–12s |
| --- | --- | --- | --- | --- | --- |
| s4c | 37 | 19 | 0.009 s | 10.30 s | 18 / 0 / 1 / 17 |
| h1 | 35 | 18 | 0.023 s | 10.34 s | 17 / 1 / 0 / 16 |
| h13 | 35 | 18 | 0.023 s | 10.31 s | 17 / 0 / 1 / 16 |
| h4 | 35 | 18 | 0.024 s | 10.34 s | 17 / 1 / 0 / 16 |

读法：**聚簇、事件驱动，不是进程内定时器**。每个 backboardd 化身启动时在同一秒内打两条
（同一 pid 的两个线程，0.001–0.061 s 内），然后约 10.2–10.6 s 之后 launchd 才重生下一个化身。
那 ~10 s 是 launchd 的重生节流，不是我们的代码在定时发布。区分两种「等间隔」的判据是**同 pid 内有没有第二条**：

| 形状 | 判读 |
| --- | --- |
| 同 pid 成对（<0.1 s）+ 跨 pid 等间隔（~10 s） | 每次进程启动打一次 → 事件驱动（本次实测） |
| 同 pid 内等间隔重复（几秒一次，pid 不变） | 真定时器 / 轮询 |
| 间隔无结构（1–9 s 均匀分布，pid 混杂） | 噪声，与启动时机无关 |

A 族（P-120 `NSURL initFileURLWithPath:` nil）同法量过，**形状相同**：12–23 条命中几乎全部来自 `syncdefaultsd`
一个进程（只有 h3/base/adspe 各多出 1–2 条无进程名的行），桶分布同样是「<0.1 s 若干 + 9–12 s 若干」，
没有 1–9 s 的中间桶 —— 也是每次进程重生打一次，不是周期定时器。⇒ **A 族不需要按「周期性」单独立项**；
它和 C 族共用同一个 launchd 重生节流。唯一差别：A 族在日志结束前 580–990 行就停了
（`syncdefaultsd` 放弃重试），C 族一直打到日志末尾。

| 日志 | A 族命中 | 进程数 | 首命中行 | 末命中行 | 中位命中行（占全文） |
| --- | --- | --- | --- | --- | --- |
| s4c | 15 | 1 | :1880 | :2566 | :2250（64%） |
| h1 | 17 | 1 | :1712 | :2568 | :2259（63%） |
| h12（带修复） | 18 | 1 | :1746 | :2613 | :1906（60%） |
| h23（带修复） | 18 | 1 | :1869 | :2622 | :2055（61%） |

### 7.3 抽签名（解释 shadowed / noisy 用）

```sh
grep -aoE "uncaught exception '[^']+', reason: '[^']{0,40}" "$L" \
  | sed -E 's/0x[0-9a-f]+/0x../g' | sort | uniq -c | sort -rn | head -3
```

实测分布（同一命令跑出来的原始计数）：

| 日志 | 首位签名 | 次位签名 |
| --- | --- | --- |
| s4c / h1 / h3 / h13 / h4（不带 ad49ff2） | `-[NSTaggedPointerString getBytes:range:]` 18–19 次 | `-[NSURL initFileURLWithPath:isDirectory:]: nil string parameter` 11–22 次（A 族） |
| h12 / h23 / baseline / usb-d / adsp-c,d,e（getBytes = 0） | `-[NSURL initFileURLWithPath:isDirectory:]: nil string parameter` 13–22 次（A 族噪声） | 无 C 族签名 |

读法：**首位签名是 C 族**才算 C 族未修；首位签名是 A 族且 getBytes = 0，说明 C 族已消失，
剩下的是 P-120 金属注入的既有噪声——它不阻止桌面起来（h12/h23/h34 的 SpringBoard 132/128/128 行就是证明）。

### 7.4 八格矩阵：0509 的 OSData 修复与 0511 的四个 hunk，谁在起作用

Lead 2026-11-16 00:50 给了五格矩阵（h1/h13/h4/h12/h23），本线补上 s4c 与 h3；Lead 02:11 又补上决定性的 h34
（带修复、既无 h1 也无 h2），合成八格。hunk 编号按源文件行号：`bsd/dev/qbt_k60.c:1815` = 冷启动早退（**h2**）、
`:1996` = addon 门（**h1**）、`:2077` = stage 默认（**h3**）；`bsd/dev/qbt/btqca.c:761` = 固件日志（**h4**）。

| 镜像 | 证据目录 | head | 0509 OSData 修复 | h2 | h1 | h3 | h4 | getBytes | SpringBoard | first frame |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| s4c | `usblog-20261115-162553` | 5190337be6 | 无 | 有 | 有 | 有 | 有 | 37 | 13 | 0 |
| h1 | `usblog-20261115-211515` | e296d9ec4d | 无 | — | 有 | — | — | 36 | 13 | 0 |
| h3 | `usblog-20261115-212105` | 40cdafd045 | 无 | — | — | 有 | — | 36 | 12 | 0 |
| h13 | `usblog-20261115-212643` | 670e138c53 | 无 | — | 有 | 有 | — | 36 | 13 | 0 |
| h4 | `usblog-20261115-230627` | 3bcaac3acb | 无 | — | — | — | 有 | 36 | 13 | 0 |
| h12 | `usblog-20261115-230047` | 364499d869 | **有** | 有 | 有 | — | — | **0** | **132** | **1**（:2381） |
| h23 | `usblog-20261115-235417` | ba4afb2a4a | **有** | 有 | — | 有 | — | **0** | **128** | **1** |
| h34 | `usblog-20261116-014536` | f604d5f9da | **有** | — | — | 有 | 有 | **0** | **128** | **1**（:2486） |

复现这张表的三条命令：

```sh
git merge-base --is-ancestor ad49ff2 <head>                                # h12/h23/h34 为 YES
git show <head>:patches/xnu/0509-*.patch | grep -c k60_bt_string_property  # h12/h23/h34 为 5，其余 0
git show <head>:patches/xnu/series | grep -E '^0509|^0511'                 # 每格带了哪几个 hunk
```

h34 本线 02:15 独立复核（与 Lead 报的一致）：console 226,459 B / 3,314 行、getBytes **0**、SpringBoard 128、
first frame 在 :2486、entered backboardd 1、crashed 7（全是 `syncdefaultsd`/`mmaintenanced` 的
"Too many corpses being created"，无 panic）、`probe: armed` 0 次、`[bluetooth] power=` 0 次、
:186 `K60 BT: published local address ee:98:c5:8a:6b:4e`、:192 `addon: linked blob bytes=1027584 records=106`；
series 230 条（0509 + 0511j），0509 的 helper 计数 5，0511j 只含 `@@ -2077`（h3）与 `@@ -761`（h4）两个 hunk。

从表里能直接读出四条：

1. **把 {36,37} 与 {0} 分开的唯一变量是「0509 OSData 修复」这一列。** 带修复的三格全 0 且桌面起来，
   不带修复的五格全 36–37 且 first frame = 0。**h1/h2/h3/h4 四个 hunk 与 getBytes 计数没有因果关系**——
   h34 既无 h1 也无 h2，已经是 0。
2. **「h2 是前置」这条因果链作废（Lead 2026-11-16 02:11 自认）。** 三条反证：①h1 没有 h2 但 `:186` 照样打出
   published local address，探针梯子也跑完（`:762 probe: done`、`:763 power=1 result=0`）——发布点在
   `native_pong_ui_services_start`，与 `k60_request_power()` 的冷启动门不是同一条路径；②s4c 带全部四个 hunk
   仍 37 次；③h34 连 h1 都没有、照样 0 次。h2 与修复在这批图里共变是巧合。
3. **「探针梯子不进」的归因是 h3 单独造成的，不是 h2+h3 组合。** h34 有 h3 无 h2，`probe: armed` 与
   `[bluetooth] power=` 同样 0 次；h23 与 h34 都有 h3，h1/h12/h13/h4 都无 h3 且梯子都跑了。
   ⇒ h3 把早启动探针的挂载点整段拿掉，这是**可观测性副作用，不是失败**。所以「梯子不进」不能当判据，
   只能当「这张图不能用来判探针」的标记。
4. **C 族结案**：h12/h23/h34 三格都满足 §7.1 的 C-alive 三条件，其中 h34 无 h1 无 h2 ⇒ C 族的修复
   **不依赖任何 bt hunk，只依赖 0509**。残留的 16–22 次 NSURL nil 是 A 族（P-120），按 §1 处理。

**本节结论已定稿，不再需要补格。** 唯一还想复核的是 bt 线的全量图（bt-late / d 系列）在最终补丁集下
仍保持 C-alive；那只是回归确认，不改变归因。


