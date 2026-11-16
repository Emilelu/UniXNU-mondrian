# backboardd 崩溃家族总表（A / B / C）

状态：离线分析已有上机记录；本轮未操作设备。更新 2026-11-16。仓库 E:/hackios/k60-display，分支 feat/display。
本轮只纠正文档证据边界与判读已有 d8，不修改硬件验证状态。§8 为最新回归记录，旧计数口径保留并注明。
本文件响应 Lead 2026-11-15 立项要求：把 backboardd 的崩溃按指纹分成家族，每族给出触发条件、
日志指纹（精确到格式串）、能否归因到我们的兼容钩子、以及「只用现有日志就能判」的判据。

## 0 结论摘要

| 家族 | 触发条件 | 日志指纹 | 归因 | 判据 |
| --- | --- | --- | --- | --- |
| A：NSURL nil 异常家族 | 触发源须逐进程、逐镜像核实；P-120 是历史子案例 | NSURL initFileURLWithPath: nil string parameter；有对应退出记录时再记 SIGABRT | 同文本不等于 Metal 根因；d8 的明确异常对象是 syncdefaultsd，pong_metal=2（§8） | 匹配异常行并绑定进程/PID、同次栈与退出对象；P-120 另需注入和因果证据（§1） |
| B：int-236 SIGSEGV | 发布 backlight-control=true 的新 IOService | K60 BACKLIGHT: published … control 1（旧格式）/ conformance=1 control=1（新格式）+ backboardd sig=11 | 发布层引入（brightness-4 control=1 崩 4 次，brightness-13 control=0 零崩） | python3 scripts/check-backlight-log.py <log> EXIT=0 |
| C：getBytes:range: 类型不匹配（**已结案**） | 新 IORegistry 内容把字符串属性发到 DT 平面（bt 线 0509 补丁） | -[NSTaggedPointerString getBytes:range:]: unrecognized selector + NSInvalidArgumentException + SIGABRT | 触发源由对照归到 bt 线 0509 的属性类型；具体读取者及私有帧归属仍未知（§3.3、§5.1）；ad49ff2 改 OSData 后消失，与 0511 四个 hunk 无关（§3.4、§7.4） | grep -c 'getBytes:range:' > 0 即 C 族；崩溃次数 ≈ (命中数+1)/2；结案判据见 §7.1 三档 |

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
保留这次 image-level 输出：C 族候选帧含 IOMobileFramebuffer + QuartzCore + libdispatch，A 族候选帧含
Foundation + libxpc。**18:06 证据边界更正**：这只是给定 slide 后的映射，不足以点名属性读取者、证明 Metal
根因或命名私有帧；跨进程 slide 绑定限制见 §5.1、§8。`.map` 不阻塞本轮只读判读。

共同风险：**向 IORegistry 发布此前不存在的内容，可能激活原先未触达的用户态路径**。
B 的 control 发布对照与 C 的属性类型修复对照各自成立，不据此认定两者是同一具体读取者。C 涉及**类型约定不匹配**
（DT 平面属性应为字节数组，发成了字符串）。这对 display 线是旁证：交付形态 A（默认不发
backlight-control）仍是正确终局，不是妥协。

## 1 家族 A：NSURL nil（异常签名；P-120 为历史子案例）

- 指纹：`NSInvalidArgumentException`，reason 含 `-[NSURL initFileURLWithPath:isDirectory:]: nil string parameter`
  （有的日志在 `-[NSURL` 前另有 `*** `）；SIGABRT 必须另有同一 PID 的 `sig=6` 退出记录支持。
- 历史子案例：gpu-20261114t（证据 E:/k60-work/evidence/usblog-20261114-235957）曾由 Lead
  2026-11-15 归为 P-120，与 int-236 分开。该历史解释涉及 `pong_metal=1` 与
  `userland/build.py:516` 的 PongAdrenoMetal 注入；**同文本或同一 boot-arg 不是独立因果证明**。
- 当前边界：软件渲染配置 `pong_metal=2` 的 d8 也有同指纹（§8），明确异常对象为 `syncdefaultsd`；
  不能把它改称 backboardd 崩溃，不能仅凭 Foundation/libxpc 帧把根因归到 Metal。
- 判据：先绑定 `进程名[pid:thread]` 的异常行、邻接的同次 backtrace 与该 PID 的退出记录；
  未带进程标签的碎片、`Too many corpses` 和首帧/桌面计数各自保留，不能互相替代。
  要进一步归 P-120，须另给该进程的实际注入及受控因果证据；否则只记 A 族签名，根因未知。

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
  (0x19b42148c 0x194775050 0x19b582424 0x19b436938 0x19b49897c 0x1c3831abc 0x1a21c3780 0x1a2193ddc 0x1c383197c 0x19c9de080 0x19cb12278 0x19cb1a8d8 0x1a21c3780 0x1a2193ddc 0x19cb1a824 0x10111f930 0x1a21c…。栈底私段帧（0x10… 段）每化身不同：pid 55 = 0x10111f930、pid 139 = 0x100b04930、pid 177 = 0x100aa9930（ASLR 滑动）；0x1a21c3780/0x1a2193ddc 出现两遍（重入形状）。这些地址未由该进程的加载映射绑定到任何私有 image/函数；单凭 0x10… 地址段不能命名为 backboardd 或 libpong-ui.dylib。§5 的缓存索引也不能解决缓存外私有帧归属。
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

### 3.3 归因：0509 属性类型对照成立，具体用户态读取者未定位

1. **我们的代码没有这个调用形状**：userland/ui_compat.c 的全部 ObjC 调用都是带类型的 objc_msgSend 强转（UIScreen mainScreen/nativeScale/nativeBounds :162-173；NSBundle :222-224；_productVersionStringFallback 带 isKindOfClass: 检查 :267-270；异常 description :367-368），全文件 grep getBytes|NSData|bytes]|data bytes = 0 命中；init.c 同样 0 命中。libpong-ui.dylib 确实被注入 backboardd（build.py:515 的注入名单），在上述源码搜索范围内未发现直接调用；这不能排除间接调用、未命名私有帧或全部兼容代码的影响。
2. **崩溃是类型不匹配的形状**：接收者是 NSTaggedPointerString（短字符串的 tagged 表示）——正是 setProperty(key, "短字符串") 在用户态读回时的类型；getBytes:range: 是数据型访问。这证明该消息的接收者类型不符；与 0509 的属性类型及修复对照共同支持根因判断，但日志没有直接点名被读的是哪一个 key。
3. **仓库自己的内核代码证明约定**：DT 平面的 device_type/compatible 必须以 OSData（原始字节）发布、以 OSDynamicCast(OSData,…) 读取——drivers/ArmCpu/ArmCpu.cpp:103（OSData *compatible = OSDynamicCast(OSData, gic->getProperty("compatible"))）、:302、:514（device_type 同）、drivers/ArmDTPlatform/ArmDTPlatform.cpp:192（device_type）、drivers/NativeUfs/NativeUfs.cpp:53-55。
4. **0509 违反了这个约定**：iokit/Kernel/MiniBluetooth.cpp（新文件）把 node->setProperty("device_type", "bluetooth")、compatible → "qcom,wcn7850-bt"、unixnu,adt-name → "bluetooth" 发成字符串（transport-encoding/speed 与 local-mac-address 倒是正确的原始字节）；同样的字符串属性也发到了 K60BluetoothRadio 服务上（radio->setProperty("device_type","bluetooth")），并且 registerService()；调用点在 iokit/Kernel/MiniIOSurface.cpp native_pong_ui_services_start（MiniAcceleratorPublishStub 之后加 MiniBluetoothPublishStub(provider);），门控 PE_parse_boot_argn("k60bt")。这与 k60bt=1 才崩、不设不崩的现场完全吻合。
5. **历史复核与已撤回假设**：Lead 2026-11-15 核对旧版 0509:185-187 的三处 C 字符串 setProperty
   （device_type / compatible / unixnu,adt-name），OSString 与 DT 平面 OSData 约定不符。当天提出的
   「0511 h2 删除冷启动 `return -EOPNOTSUPP` → 身份发布首次执行」假设已被 §7.4 的 h1/h34
   反证推翻（Lead 2026-11-16 02:11 更正）；保留它作历史，不再作为归因依据。
6. **springboard 线补充线索（Lead 2026-11-15 转达）**：userland/ui_compat.c:723-729 的 20G81 兼容层先验做法——`method_abi(setter,"v",3,"@B@")` + `strcmp(method_getTypeEncoding(setter),"v36@0:8@16B24@?28")` 在调用前断言精确类型编码；类簇（NSString/NSData）返回类型编码错标正是打出 unrecognized selector 的经典方式。该段可作 C 族修复后「宿主侧断言发布属性是 OSData」的参照（内核侧约定已是 OSDynamicCast(OSData,…)，ArmCpu.cpp:103）。springboard 线全链 grep getBytes=0，只说明该搜索没有发现直接 selector 调用，不足以排除全部兼容钩子。
7. **当前结论**：§5.1 已观察到 IOMobileFramebuffer / QuartzCore / libdispatch 的 image-level 候选帧，
   支持把调查范围收至显示提交相关路径，取代早先「最可能 HID/蓝牙事件路径、缺 cache」的猜测。
   这些帧不能独自证明具体属性读取者，也不能排除未出现在该栈上的所有代码。0509 的属性类型根因
   由 §3.4、§7.4 的修复对照支持；bt-s4c 未打印 K60 BACKLIGHT 服务行，不能把此现象混作 int-236。
   私有帧及跨进程 slide 绑定未闭环处保留未知，不再声称已排除全部显示钩子。

### 3.4 结案：C 族根因是 0509 的 OSString，修复与 h1–h4 无关（2026-11-16 定稿）

- device_type / compatible / unixnu,adt-name 改用 OSData 发布（模拟真实 FDT 的字节数组），与仓库内核读取侧（OSDynamicCast(OSData,…)）的约定一致；
- 或先只发 DT 节点、砍掉 K60BluetoothRadio 的 registerService()，确认 bluetoothd 能否只靠 DT 子节点工作；
- 验证：同一张镜像 k60bt=0 起飞（预期 0 崩）→ 修复版 k60bt=1（预期 0 崩 + bluetoothd 正常）。
- 修复后的宿主侧断言参照：仿 userland/ui_compat.c:723-729 的 method_abi + strcmp 精确类型编码断言，在用户态把读回的属性先按类型校验再用（内核侧读取约定 OSDynamicCast(OSData,…) 保持不变）。
- 进度（Lead 2026-11-15 22:10）：0509 OSData 修复已合入 bt 线分支（ad49ff2，三个属性改走 k60_bt_string_property()；test-k60-bt-0509-properties.py 25 例全过）；bt 下一张全量图带它，Lead 飞完即给本线实测判据。验证图由 Lead 直接排窗口上机（用户已放权 Lead 连续 boot，不再需要单独批准），本线只等实测结果、按 §3.5 判定表判。

**结案（2026-11-16 02:15，Lead 02:11 授权）**：

- **根因**：0509（`patches/xnu/0509-k60-bt-s3-identity-publish.patch`）把 `device_type` / `compatible` /
  `unixnu,adt-name` 三个 DT 平面属性发成 OSString，而 DT 平面约定是 OSData 原始字节（§3.3 第 3 条）；
  修复对照支持属性类型导致本族；用户态消息接收者为 NSTaggedPointerString，随后 SIGABRT。
  具体 key/读取函数未由 image-level 栈点名（§5.1），不把工程结案外推为函数级定位。
- **修复**：bt 线 ad49ff2 把三处（外加 radio 的 device_type）改走 `k60_bt_string_property()`
  （`OSData::withBytes(value, strlen(value)+1)`，带 NUL 结尾）。
- **修复与 0511 的四个 hunk 无关**：八格矩阵（§7.4）里带修复的三格 h12（h1+h2）/ h23（h2+h3）/
  h34（h3+h4，**既无 h1 也无 h2**）全部 getBytes 0 + SpringBoard ≥128 + first frame 1。
- **实测判据**：§7.1 的 C-alive 三条件（G=0、S≥100、F≥1），且步 0/1 的采集与身份审核通过；
  helper 名称命中只是一条旁证，不能单独完成同次镜像/修复身份认证。
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

命令 A（历史基线 broad-count，cwd = 证据目录，L=console.log；当前判读按 §7.1/§8 另记进程口径）：

```sh
grep -ac 'getBytes:range:' "$L"          # 基线 37（Lead 口径 36，同量级）
grep -acE 'KX!.*backboardd' "$L"         # 基线 1（健康 = 0）
grep -ac 'entered backboardd' "$L"       # 基线 19（健康 = 1）
grep -ac 'SpringBoard' "$L"              # 基线 13（健康 ≥ 100）
grep -ac 'first frame presented' "$L"    # 基线 0（健康 ≥ 1）
```

| 判定 | 条件（命令 A 的五个数） | 动作 |
| --- | --- | --- |
| 达到历史存活门槛 | 0 / 0 / 1 / ≥100 / ≥1 | 仍须 §7 的身份/覆盖审核；不自动修改硬件验证状态 |
| 症状下降仍在 | 0 < getBytes ≤ 18，且覆盖可比 | 第二个发布点待查：跑命令 B 抽 selector/实例类型，再核属性来源 |
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

命令 D（步 1 的身份审核，不能仅凭一个符号）：

```sh
sha256sum <boot.img> <build-manifest.json> <console.log>
jq -r '.repo.head, .series.file_sha256, .payload_args' <build-manifest.json
git merge-base --is-ancestor ad49ff2 <recorded-head>
git show <recorded-head>:patches/xnu/0509-k60-bt-s3-identity-publish.patch
```

将镜像哈希与同次 boot 记录、日志哈希与 capture 记录逐项核对，再核 recorded source 的 series 与
0509 内容（d8 实例见 §8）。这构成保存记录的来源链，不能替代镜像内二进制输入证明或设备内身份认证。
`llvm-nm <kernel.macho>` 命中 helper 可作补充；未命中也可能是内联/剥符号，不能直接判飞错镜像。

#### 3.5.1 未生效时的属性二分（三个镜像，均 k60bt=1）

| 镜像 | 发布方式 | 判据 |
| --- | --- | --- |
| H1 | 只把 device_type 改回 OSString，另两个 OSData | getBytes 命中回到 ≥19 → device_type 是触发点 |
| H2 | 只把 compatible 改回 OSString | 同上 → compatible 是触发点 |
| H3 | 只把 unixnu,adt-name 改回 OSString | 同上 → adt-name 是触发点 |

三个镜像都 0 崩 → 触发点不在这三个 DT 属性（radio 的 device_type 也在 ad49ff2 里改成了 OSData），
回到命令 B/C 找第二个发布点。

## 4 判据汇总（只用日志）

    grep -ac 'nil string parameter' log  # A 族候选；需绑定异常进程，不能据此归因 Metal/P-120
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
- **slide 来源与归属**：`K60SR26 t=75 start=0x1946b0000 slide=0x146b0000`（s4c console.log:1174）
  来自 `patches/xnu/0403-k60-pid26-slide.patch:31` 的 `proc_find(26)`，读取该 task 的 shared region；
  :45–49 的 `t` 是 `k60_hb_ticks * 15` 时间，**不是异常 PID 或线程号**。490 份历史 usblog 中
  119 份带探针（首份 `usblog-20261112-184616`）；没有它时脚本 exit 2。PID 26 的 slide 不能自动
  视作 backboardd / syncdefaultsd 的 slide，跨进程使用须另证 shared region 一致。
- 用法：

  ```sh
  python3 scripts/dyld-cache-index.py \
      --index /mnt/e/k60-work/caches/20G81/dyld-index-20G81.json \
      --log console.log --after 'getBytes:range:' --frame-limit 16
  ```

  退出码是机械覆盖率：0 全部地址落入索引 / 1 至少一帧未落入 / 2 索引、日志、slide 或目标 backtrace 缺失；
  **均不证明异常进程与 slide 已绑定，也不是 C 族判定码**。`--json` 给机器读；`--selftest` 11 项。
  `scripts/dyld-cache-index.py:159–187` 取全日志最常见 slide，再取 marker 后首条 ≥10 个 hex token 的行，
  不检查 PID/thread 或是否同次 backtrace；调用方须核对原始邻接行，无法绑定的保持条件性/未知。
  它给的是 **image 级**（dylib + 偏移）；`scripts/check-crash-symbols.py`（bb86175，吃 `.map`）可补符号，
  但匹配版本、进程加载映射和 slide 仍是前置，单份缓存 `.map` 也不能命名缓存外私有 executable。

### 5.1 两条 image-level 输出（02:45 记录；18:06 更正证据边界）

C 族（`--after 'getBytes:range:'`；将 s4c 的 `0x146b0000` / h1 的 `0x1eeac000` 作为 slide，
得到相同的 **image-level 候选映射**，机械覆盖 15/16；该输入来自 PID26 探针，异常进程的 slide 尚未独立绑定）：

    CoreFoundation+0x948c → libobjc.A.dylib+0x15050 → CoreFoundation+0x16a424 → CoreFoundation+0x1e938
    → CoreFoundation+0x8097c → IOMobileFramebuffer+0x7abc → libdispatch+0x64780 → libdispatch+0x34ddc
    → IOMobileFramebuffer+0x797c → QuartzCore+0x12b080 → QuartzCore+0x25f278 → QuartzCore+0x2678d8
    → libdispatch+0x64780 → libdispatch+0x34ddc → QuartzCore+0x267824 → 私有段

A 族（`--after 'nil string parameter'`；将 s4c 的 `0x146b0000` / h34 的 `0xa634000` 作为 slide，
得到相同的 **image-level 候选映射**，机械覆盖 10/12；不能据此认定 syncdefaultsd 与 PID26 共用该 slide）：

    CoreFoundation+0x948c → libobjc.A.dylib+0x15050 → Foundation+0x5ae2c → Foundation+0x5abdc
    → 私有段 ×2 → Foundation+0x99bd4 → Foundation+0x54df88 → Foundation+0x54f5ec → Foundation+0x54f0ec
    → libxpc+0xf788 → libxpc+0xfb68

读法：

- C 族输出含 **IOMobileFramebuffer / QuartzCore / libdispatch**，是显示提交相关路径的调查线索，
  取代旧的 HID/蓝牙路径猜测。image-level 帧不点名属性 key/读取函数；没有 IOKit/Bluetooth 帧
  也不能排除所有未出现在这条栈上的代码，更不能据此断言「CA 对象图就是读取者」。
- A 族输出含 **Foundation / libxpc**，支持在满足 slide 绑定后继续查这一路径；异常文本、libxpc 帧
  及进程名都不单独证明 URL 的来源或 Metal 注入根因。d8 明确异常对象为 syncdefaultsd（§8）。
- 未解地址 `0x10111f930` / `0x1007e8f48` / `0x1011eaf48` / `0x100f04930` 保持 **unresolved**：
  无进程加载映射和私有 image/symbol，不能把它们命名为 backboardd 或 libpong-ui 的函数。
- C 族工程结案依赖属性类型修复对照（§7.4），不依赖这些候选帧；A 族具体根因仍需逐样本核实。
  本轮不取 `.map`，不以缺符号为由扩大到设备操作。

## 6 0 字节日志的判决时效（跨线教训；Lead 2026-11-15 指派）

- 现象：console.log **0 字节**，部分样本另有 autoreset 回 fastboot。0 字节只证明该次未采得输出；
  内核停止、USB/主机连接未就绪或采集失败均需另证，不能单凭空文件定位停止阶段。
- 机制（adsp-e 实测 `E:/k60-work/evidence/usblog-20261115-223916/console.log`，3,312 行）：
  `K60 USBLOG: st=2 ev=0 cfg=0 dtr=0` 在 :248，直到 `K60 USBLOG: st=4 ev=595 cfg=1 dtr=1`（:477）主机才真正连上，
  紧接着 `K60DATA mounted ro=0 fstype=apfs` 在 :485。这个样本说明主机可在启动后才连上，
  更早的故障存在漏采可能；不能倒推每张 0 字节镜像都死在根挂载或 USB 之前。
- 历史数字保留：mhi3 / mhi4 / z0 / t2 / c0 五张 silent；加 c1/c2 后为 §7.1 的七张。
  **逐图边界以 refmine `ea7f72d:docs/research/wifi/DARWINBOOT-POOL.md:72–90` 为准**：
  c0 身份不符，属于 invalid-measurement，且没有同次 panic；mhi3/mhi4/z0/t2/c1 的逐图归档/停止路径
  未闭环，不能统一归为 seed UUID 或 P-215。c2/c3 对照与源码链支持的是 **c2/c3 对应配方**的 P-215。
- 配置风险仍需查：wifi defconfig 曾指名 seed UUID `6DCCF70A-6FD6-403E-ACED-95313CD7CBB8`
  （patches/wifi/0007-configs-mondrian-wifi-defconfig.patch:52），真机 UFS Data 是
  `1BCD69FF-24A5-48B1-94B6-8FE592B2F597`（configs/mondrian_defconfig:54，`CONFIG_XNU_OWNER_DATA_UFS=y` :47）。
  `drivers/NativeRamBlock/NativeRamBlock.cpp:443–447` 有 5 s 等待失败路径及
  `NativeRamBlock: Data UUID %.36s not published within 5s` 格式串；源码上的可能路径不是每张 silent 图的同次崩点证据。
- 判据（**先配置、后版式，别先造机制**）：
  1. 先确认它真是 0 字节：`find /mnt/e/k60-work/evidence -maxdepth 2 -name console.log -size 0`
     （目前 41 份，如 `usbcmd-test-210941`、`usblog-20261112-180735`）——0 字节与「全 0 命中」是两件事。
  2. 第一步 diff **构建配置**：`git -C /mnt/e/hackios/k60-display show <tag>:configs/mondrian_*_defconfig | grep -E 'OWNER_DATA_(MOUNT|UFS|VOLUME_UUID)'`，
     与 configs/mondrian_defconfig:43/47/54 对照；UUID 必须是真机已安装 UFS Data 的 `1BCD69FF-…`，不能是 seed 的 `6DCCF70A-…`。
  3. 第二步才 diff 内核版式（__TEXT/__DATA/payload 结构），第三步才怀疑某个驱动。
- 门禁：Lead 已在 main 落 `scripts/check-defconfig-uuid.py`（P-209）。本分支 rebase 到的 origin/main 2ce089a 里还没有这个文件，
  等它进 main 后本线门禁自动覆盖；此段按 Lead 口径记录，暂不引用行号。
- 与本族的关系：B/C 判读需覆盖 backboardd/桌面相关阶段，A 族还须绑定实际异常进程。0 字节时
  「getBytes=0、SpringBoard=0、first frame=0」是缺观测，统一 **INCONCLUSIVE**，不能证明没崩或更早停止。

状态（2026-11-16 00:10 更新）：Lead 23:59 指派 §7「C 族的判定顺序」已落地（三档 C-alive /
C-shadowed / C-alive-but-noisy + 一行判定命令 + 行号对格式）；复核发现已飞的 h12/h23 就是首批带 ad49ff2
的镜像，getBytes 0 / SpringBoard 132,128 / first frame 1 ⇒ C 族按 §7.4 判 C-alive，不必等 bt-late 图。

## 7 C 族的判定顺序（把症状写成流程；Lead 2026-11-15 23:59 指派）

§3.5 是「数哪五个数」，本节是「按什么顺序读、每档怎么落判」。判 C 族**不是先看崩溃次数**，
而是先排除「没活到能判」和「飞错镜像」两种假象，再看命中数与桌面存活度。顺序固定为四步：

    步 0  日志不存在/0 字节/采集失效？ → 是：INCONCLUSIVE（§6），不定位停止阶段
    步 1  同次镜像/日志与 0509 修复身份核实？ → 否或未知：只作基线或 INCONCLUSIVE，三档表作废
    步 2  数 getBytes 命中 + 桌面存活 → 三档之一（下表）
    步 3  抽签名                       → 只用来解释「被谁遮住」或「第二个发布点」

**所有计数一律加 `-a`**。真实日志里混有二进制字节（h23 的 console.log 就被 grep 判为 binary），
不加 `-a` 时 `grep -c` 仍给数字，但 `grep -oE`/`sed` 管道会输出 `binary file matches` 而静默变成 0 行——
本线在 23:57 就因为漏了 `-a` 得到过「h23 的 uncaught exception 抽不出来」的假结论。

### 7.1 三档判据（一行命令出结论）

先完成步 0/1，再运行计数；以下 `FIX_VERIFIED` 与 `COVERAGE_VERIFIED` 是人工审核结果，
不是由 G=0 或某个 helper 名称自动生成。命令示例未代替 §8 的实测工具回执；保留 grep 的错误码 2。

```sh
L=console.log
# 先核同次记录、修复身份、有效采集区间；未核实就保持 UNKNOWN
FIX_VERIFIED=${FIX_VERIFIED:-UNKNOWN}; COVERAGE_VERIFIED=${COVERAGE_VERIFIED:-UNKNOWN}
# S 改用显式进程标签；S_legacy 留作历史 broad-count 对照
if [ ! -s "$L" ] || [ "$FIX_VERIFIED" != YES ] || [ "$COVERAGE_VERIFIED" != YES ]; then
    echo INCONCLUSIVE
else
    G=$(grep -ac 'getBytes:range:' "$L"); RG=$?
    S=$(grep -acE 'SpringBoard\[[0-9]+:[0-9]+\]' "$L"); RS=$?
    S_legacy=$(grep -ac 'SpringBoard' "$L"); RL=$?
    F=$(grep -ac 'first frame presented' "$L"); RF=$?
    if [ "$RG" -gt 1 ] || [ "$RS" -gt 1 ] || [ "$RL" -gt 1 ] || [ "$RF" -gt 1 ]; then echo INCONCLUSIVE
    elif [ "$G" -eq 0 ] && [ "$S" -ge 100 ] && [ "$F" -ge 1 ]; then echo "C-alive G=$G S=$S S_legacy=$S_legacy F=$F"
    elif [ "$G" -eq 0 ] && [ "$S" -lt 100 ] && [ "${OTHER_FATAL_VERIFIED:-UNKNOWN}" = YES ]; then echo C-shadowed
    elif [ "$G" -gt 0 ] && [ "$G" -lt 19 ]; then echo C-alive-but-noisy
    elif [ "$G" -ge 19 ]; then echo C-not-fixed
    else echo INCONCLUSIVE; fi
fi
```

**本表只在步 1 为 YES 时适用；步 1 为 NO（镜像不带 ad49ff2）时本表整体作废，不要逐行套用。**
wifi 的 c0/c1/c2/z0/t2/mhi3/mhi4 **七张 0 字节数目保留**。旧命令在 G=S=F=0 时实际上会输出
C-shadowed（旧文字误写为 C-alive）；两种标签都没有证据，应在步 0 直接 INCONCLUSIVE。
P-215 的已证适用范围是 c2/c3 对应配方：受控对照加源码链支持 UFS 索取尚未分配的 Apps SMMU lease 锁，
0012 惰性分配后 c3 有 SpringBoard 132。c0 身份不符、无同次 panic；mhi3/mhi4/z0/t2/c1 的逐图
归档和实际停止路径未核，不能统包（refmine `ea7f72d:docs/research/wifi/DARWINBOOT-POOL.md:72–90`）。

| 档 | 条件 | 含义 | 落判动作 |
| --- | --- | --- | --- |
| **C-alive** | G=0 **且** 显式 SpringBoard 进程标签 S≥100 **且** F≥1 | 步 0/1 通过后，本次采集窗口未复现 C 族，满足既有回归门槛 | 记录五数、匹配定义、身份链和窗口；不自动升级其它硬件或验证状态 |
| **C-shadowed** | G=0、S<100，且有绑定进程的另一致命签名/退出证据 | 其它故障遮住本次 C 族观测，不能判断修复效果 | 给 A（§1）或 B（§2）等同次判据行；若只有低行数或缺 F 而无致命签名，改 INCONCLUSIVE |
| **C-alive-but-noisy** | 0<G<19，且采集窗口/路径覆盖可与基线比较 | 症状下降仍未消失；第二个 OSString 发布点只是待查假设 | 给下降前后行号、窗口和 PID 间隔（§7.2），再查 selector/实例类型；不由次数直接证明发布点 |
| （未生效） | getBytes ≥ 19，与基线 36/37 同量级 | 镜像没带修复或修复无效 | 先跑 §3.5 命令 D 确认镜像带 ad49ff2；确认后才按 §3.5.1 三属性二分 |

**注意：C-alive 不等于「修复生效」。** 不带 0509 的控制图（如 adsp-e `usblog-20261115-223916`，G=0 S=120 F=1）
用旧的未加身份/覆盖前置的命令也会输出 C-alive；原因是它没有发布那些字符串属性。
本版 §7.1 命令对未核实身份的输入返回 INCONCLUSIVE。所以**步 1 必须先过**：只有镜像真带 ad49ff2
且有效采集覆盖目标路径时，才可按既有修复结论记一次回归通过；否则不评价修复效果。

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
中位次只描述**命中在日志文本中的位置分布**：75–80% 表示命中一直延续到接近文件末尾。
它不证明进程没活下来，也不证明桌面存活；存活与否须另给进程活动/退出记录。修复后若降到 20% 以下，
只可表述为「命中的文本位置前移」，不能推断「之后桌面活下来了」。历史五表的首/末命中行保留为观测值。

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

A 族（`NSURL initFileURLWithPath:` nil 签名，未因此统一归 P-120）同法量过，**形状相同**：12–23 条命中几乎全部来自 `syncdefaultsd`
一个进程（只有 h3/base/adspe 各多出 1–2 条无进程名的行），桶分布同样是「<0.1 s 若干 + 9–12 s 若干」，
没有 1–9 s 的中间桶 —— 也是每次进程重生打一次，不是周期定时器。⇒ **A 族不需要按「周期性」单独立项**；
A/C 命中的时间桶形状相同，但 A 族命中在日志末尾前 580–990 行停止，C 族延续到末尾；
这只是观测到的文本分布差别。为什么 `syncdefaultsd` 不再打异常（放弃重试、进程退出或其它原因）
以及 C 族进程是否存活，均需同次活动/退出证据，不能由日志静默推断。

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

读法：签名排序只用于摘要，任何已绑定的 C 族命中都应记录，不能只看首位。getBytes=0 而 A 族签名
居首，说明本次日志没有 C 文本，不能单独证明修复生效或把残留归为 Metal/P-120。h12/h23/h34 的
历史 SpringBoard 132/128/128 与 F=1 说明该窗口有桌面活动，不说明发出 A 族异常的进程未退出。

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
   `[bluetooth] power=` 同样 0 次；h1/h12/h4 没有 h3。h13 的配方也含 h3（上表），
   旧说法「h1/h12/h13/h4 都无 h3」错误；不以这组不一致的文字替代逐图挂载路径核查。
   ⇒ h3 把早启动探针的挂载点整段拿掉，这是**可观测性副作用，不是失败**。所以「梯子不进」不能当判据，
   只能当「这张图不能用来判探针」的标记。
4. **C 族结案**：h12/h23/h34 三格都满足 §7.1 的 C-alive 三条件，其中 h34 无 h1 无 h2 ⇒ C 族的修复
   **不依赖任何 bt hunk，只依赖 0509**。残留的 16–22 次 NSURL nil 按 A 族签名处理，不能只凭文本归为 P-120（§1）。

**本节结论已定稿，不再需要补格。** 唯一还想复核的是 bt 线的全量图（bt-late / d 系列）在最终补丁集下
仍保持 C-alive；那只是回归确认，不改变归因。d8 的已存证据回归见 §8。

## 8 d8 已有证据的离线回归（2026-11-16，Lead 18:06 授权）

**判定：在保存记录对应的这次采集窗口内，满足 C-alive 回归门槛。** 历史口径
G/S_legacy/F/entered/crashed = **0/128/1/1/7**；显式 SpringBoard 进程标签 **S=121**，
同样满足 S≥100。七条 crashed 记录的对象均为其它 daemon，未记录 backboardd 的退出或 corpse。
此结论只评价 C 族本次未复现，不升级蓝牙、GPU、交互 UI 或亮度验证状态。

### 8.1 身份链与覆盖区间

证据目录为 `E:/k60-work/evidence/usblog-20261116-164726/`，镜像目录为
`E:/k60-work/artifacts/bt-d8-tlv/`（下表路径均相对此二目录）：

| 文件 | 字节数 | 本轮重算 SHA256（与 Lead 提供值一致） |
| --- | --- | --- |
| evidence/console.log | 255020 | 1ef1f5abf55f6036f36c729779aab3de53f667e782e9ba3492fb332109be7cd2 |
| artifact/boot.img | 201887744 | 0297012d47eb727bd52c164076bd60bdf90ee47d56eacdf19a89142f794fef2b |
| artifact/build-manifest.json | 2608 | 3dad0a5284896e7fe1cd649db67c604339ef7ec2c3baf17805a5804fe2f91db0 |

- 同次 `boot.json:2–8` 记录镜像路径/上述哈希、设备 6033dbec、captureArmed=true、
  bootAccepted=true、bootExitCode=0；`capture.json:2–17` 记录上述 console 路径/字节数/哈希，
  complete=true、portSeen/portOpened=true、openErrors=0、reopenCount=0，stopReason=budget。
  “complete”指采集预算完成，不是整次启动的功能验收；这两份本地记录将镜像与采集关联起来。
- manifest 的 source 为 `91dcd0761aeb035c15de743478851fb8ce0c0417`，dirty=0；series **235** 条，
  file_sha256=`9a2cfd416b5250854f8fda38d03ca095a631be296e0679bf9522ba445e73cbb8`。
  对该 source 的 `git show` 与 series 重算一致；series:229 含 0509，历史补丁:171–179 定义
  `k60_bt_string_property()`，:174 使用 `OSData::withBytes(value, strlen(value) + 1)`，
  :200–202/:255 用于 node 三属性与 radio device_type。`ad49ff2` 为其祖先，实际 git rc=0。
- manifest payload 含 `pong_metal=2 k60bt=1 pong_bt_late=1 k60_autoreset=300`，console:1351 的
  boot-args 可作旁证；:187 有 `K60 BT: published local address ee:98:c5:8a:6b:4e`，:492 有 Data 挂载。
  这是记录来源链与源码核验，**未解包 boot.img 证明 OSData helper 的二进制输入，日志也未提供
  设备内 image/source 哈希认证**；不将它描述为独立设备认证。
- 原始 console 为 **3749 行**。backboardd 进入 :1857，:2713 明确 swap client 为 PID55 backboardd，
  :2917 首帧；:3241 有 `44 frames in 32513 ms`，说明之后仍有 framebuffer 活动。
  采集到 :3732 的 `K60HB t=255` 和 :3749 的 USBLOG。capture 的 panicMarker/resetMarker 均 null，
  未记录退出的结论仅限这个窗口；首帧与行数不证明交互完整或 GPU 硬件加速。

### 8.2 精确计数定义、行号及退出码边界

计数单位为**区分大小写的物理匹配行**，不是出现次数，也不是唯一崩溃数。全文件 OPS regex 搜索均为
completed、scanComplete=true、pageComplete=true；对日志中的二进制字节保持文本模式（grep 示例需 -a）。
本轮工具不暴露原生 grep rc，以下明确记为“未提供”，没有把匹配数转换成实测退出码。

| 量 | 精确 regex | 匹配行数 | 首/末命中行 | 原生 grep rc |
| --- | --- | --- | --- | --- |
| G | `getBytes:range:` | 0 | 无 | 未提供 |
| S_legacy（历史口径） | `SpringBoard` | 128 | :1600 / :3045 | 未提供 |
| S（明确进程标签） | `SpringBoard\[[0-9]+:[0-9]+\]` | 121 | :2865 / :3045 | 未提供 |
| F | `first frame presented` | 1 | :2917 | 未提供 |
| entered | `entered backboardd` | 1 | :1857 | 未提供 |
| crashed（corpse 对象行） | `Process\[[0-9]+\] crashed:` | 7 | :2596 / :3583 | 未提供 |
| backboardd 退出记录 | `KX!.*backboardd` | 0 | 无 | 未提供 |

S_legacy 多出的 7 行是 :1600/:1816/:2133/:2720/:2885/:2886/:2887，包含启动路径、探针、注入入口、
激活门与类重复警告，不能全部叫 SpringBoard 自身日志。旧矩阵保留原口径，本次另记 S=121。
GNU grep 复跑时，无匹配通常 rc=1、有匹配 rc=0、错误 rc=2；这只是命令语义，**不是本轮测得的 rc**。

| 实际运行 | 原始 rc | 结果/含义 |
| --- | --- | --- |
| `git show <source>:patches/xnu/0509-k60-bt-s3-identity-publish.patch` | 0 | 内容可读，保留上述历史行号 |
| `git merge-base --is-ancestor ad49ff2 <source>` | 0 | 修复提交是祖先；仍检查实际补丁内容 |
| `dyld-cache-index.py --selftest` | 0 | 11 checks ok |
| 同脚本 `--after 'nil string parameter' --frame-limit 21` | 1 | 给定 PID26 slide 后 19/21 地址落入 image 索引；跨进程绑定未证 |
| 同脚本 `--after 'getBytes:range:' --frame-limit 21` | 2 | 无目标 backtrace；不是一次 C 族崩溃，也不是判定 FAIL |

### 8.3 异常、退出与 corpse 分别绑定对象

- NSURL 的明确异常行共 **18** 条，均带 `syncdefaultsd[pid:thread]`，首 :2280（111:1083），末 :3127；
  :2281/2282 紧邻的 first-throw/raw stack 有 21 帧，:2283–2285 为 PID111 另一线程同形栈，
  :2288 则为 `KX! 7 111 syncdefaultsd exit=0 sig=6 ...`。因此这组异常/栈/退出属于 syncdefaultsd111。
  :2578–2580 有交错碎片，未带标签的半行不能独立绑定进程；`libc++abi` 文本也不增加一条退出记录。
- 七条 corpse 对象：syncdefaultsd PID224(:2596)、231(:2719)、247(:2839)、255(:3072)、259(:3131)；
  mmaintenanced PID193(:3246)、295(:3583)。`Process[N] crashed: NAME` 的 NAME 是被报告对象，
  不是已知 logger；这七行未标明发出诊断的进程。`Too many corpses` 是这些行上的处理警告，
  不能另加七次退出，也不能据此计为 backboardd 崩溃。
- `KX!` 实际仅 10 条且序号有缺口；除上述 syncdefaultsd111，另有 mmaintenanced191 sig=5(:2396)、
  BlueTool128 exit=1 sig=0(:2746) 等，与七条 corpse 集合不同。ReportCrash(:2401) 和
  osanalyticshelper(:3639) 的日志也不能代替 crash subject。没有 backboardd 的记录不等于完整退出审计。
- A 族签名在 `pong_metal=2` 下存在，归类为 syncdefaultsd 异常/噪声；没有该进程 Metal 注入的因果证据，
  **不判为 P-120 金属注入根因**，也不以它遮蔽已经有首帧和进程日志的 C-alive 回归结果。

### 8.4 栈映射与蓝牙的独立未知项

console:1826 为 `K60SR26 t=75 start=0x183544000 slide=0x3544000`；记录 source 内
0403 补丁的 `proc_find(26)` 与时间格式串已核（git rc=0）。它只给 PID26 的 slide，
不是 syncdefaultsd111 的 shared-region 证明。:2282 栈在这个输入下机械映射到
CoreFoundation/libobjc/Foundation/libxpc/libdispatch/libsystem_pthread 等 **image-level 候选**，
两帧 `0x10021ff48` / `0x10021dd6c` unresolved。由于跨进程 slide 未绑定，候选名称/偏移均保持条件性，
不能升级为已确认的 syncdefaultsd 函数链；私有 image 与具体 URL/属性读取者也未知。

蓝牙在 :2778/:2803 报 `budget exhausted at op=0xfc00 waiting=1`，:2781/:2806 的 type=2 均 ret=-60，
:2807 明确 `QCA Failed to request file: qca/hpnv21g.bin (-60)`，最终 :2811：


```text
[bluetooth] power=1 result=-60 baud=3000000 firmware= tlv_sent=630 tlv_acks=28 tlv_final=1
```


显示 C 族回归达到门槛不改变这个 NVM 失败；本轮未修改 driver/patch/board、硬件验证状态或构建输入，
未同步共享树、重建、取 .map 或操作设备。剩余未知仅如上记录，不为补齐未知而扩大本轮授权。
