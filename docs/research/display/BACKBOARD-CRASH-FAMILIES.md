# backboardd 崩溃家族总表（A / B / C）

状态：离线勘察，未上机。日期 2026-11-15。仓库 E:/hackios/k60-display，分支 feat/display。
本文件响应 Lead 2026-11-15 立项要求：把 backboardd 的崩溃按指纹分成家族，每族给出触发条件、
日志指纹（精确到格式串）、能否归因到我们的兼容钩子、以及「只用现有日志就能判」的判据。

## 0 结论摘要

| 家族 | 触发条件 | 日志指纹 | 归因 | 判据 |
| --- | --- | --- | --- | --- |
| A：NSURL nil（P-120） | pong_metal=1 注入 PongAdrenoMetal 插件 | NSURL initFileURLWithPath: nil string parameter + SIGABRT | 已知坑 P-120，金属注入，非背光 | grep 'nil string parameter' > 0 且 manifest payload_args 含 pong_metal=1 |
| B：int-236 SIGSEGV | 发布 backlight-control=true 的新 IOService | K60 BACKLIGHT: published … control 1（旧格式）/ conformance=1 control=1（新格式）+ backboardd sig=11 | 发布层引入（brightness-4 control=1 崩 4 次，brightness-13 control=0 零崩） | python3 scripts/check-backlight-log.py <log> EXIT=0 |
| C：getBytes:range: 类型不匹配 | 新 IORegistry 内容把字符串属性发到 DT 平面（bt 线 0509 补丁） | -[NSTaggedPointerString getBytes:range:]: unrecognized selector + NSInvalidArgumentException + SIGABRT | 不在我们的钩子里；触发源是 bt 线 0509 补丁的字符串属性（§3.3） | grep -c 'getBytes:range:' > 0 即 C 族；崩溃次数 ≈ (命中数+1)/2 |

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

### 3.4 给 bt 线的修法建议（不在 display scope，未动手）

- device_type / compatible / unixnu,adt-name 改用 OSData 发布（模拟真实 FDT 的字节数组），与仓库内核读取侧（OSDynamicCast(OSData,…)）的约定一致；
- 或先只发 DT 节点、砍掉 K60BluetoothRadio 的 registerService()，确认 bluetoothd 能否只靠 DT 子节点工作；
- 验证：同一张镜像 k60bt=0 起飞（预期 0 崩）→ 修复版 k60bt=1（预期 0 崩 + bluetoothd 正常）。
- 修复后的宿主侧断言参照：仿 userland/ui_compat.c:723-729 的 method_abi + strcmp 精确类型编码断言，在用户态把读回的属性先按类型校验再用（内核侧读取约定 OSDynamicCast(OSData,…) 保持不变）。
- 进度（Lead 2026-11-15 22:10）：0509 OSData 修复已合入 bt 线分支（ad49ff2，三个属性改走 k60_bt_string_property()；test-k60-bt-0509-properties.py 25 例全过）；bt 下一张全量图带它，Lead 飞完即给本线实测判据。验证图由 Lead 直接排窗口上机（用户已放权 Lead 连续 boot，不再需要单独批准），本线只等实测结果、按 §3.5 判定表判。

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

## 5 缺口

- **20G81 dyld shared cache 缺失**，0x19cb…/0x1a21…/0x1c38… 与私段 0x10… 帧全部无法反推符号。Lead 2026-11-15 23:15 复核：**现在拉不了，原因不是窗口而是路径**——本机 `E:/k60-work/caches/` 不存在，
  `/mnt/e` 深度 4 内 `dyld_shared_cache*` 零命中；那 3.2 GB 在 unixnu 分区 `/dev/block/sda38` 的 SystemOS 窗口里，
  XNU 起来时它是根卷但 XNU 没有 adb；要取只能在 Android 侧对 sda38 做**只读** dd，并先用
  `drivers/NativeUfs/RootLayout.h` 的 SHNGROOT 窗口表算出偏移、读前算 sha256 对表（绝不写）。等队列空一轮由 Lead 执行。
  符号化脚本 `scripts/check-crash-symbols.py` 已待命，**不是阻塞项**——`.map` 只在「修完仍崩、需要点名 selector」时才真正需要。
  清单（将来取到后按此核对）：
  - /System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64e（iOS 16.6.1 完整版约 3.2 GB；设备上可能略小，以实际大小为准）
  - /System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64e.map（约 300–600 MB，若存在）
  - 可选 dyld_shared_cache_arm64e.symbols（设备上通常不存在，有则一并拉）
  - 目的地：E:/k60-work/caches/20G81/；符号化工具建议 ipsw（dyldsym 子命令）或 jtool2。
- 私段帧 0x10111f930/0x100b04930/0x100aa9930 归属（backboardd 主二进制 vs libpong-ui.dylib）同样依赖上述 cache；但即便归 backboardd 主二进制，也不改变 §3.3 的归因（我们无 getBytes 形状）。

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

| 档 | 条件 | 含义 | 落判动作 |
| --- | --- | --- | --- |
| **C-alive** | getBytes = 0 **且** SpringBoard ≥ 100 **且** first frame ≥ 1 | 0509 的 OSData 修复在真机生效，C 族结案 | 五数（G/S/F/entered/crashed）写进 HANDOFF 与 EIGHT-STEPS device 证据，§0 状态标 C 族 closed |
| **C-shadowed** | getBytes = 0 **但** SpringBoard < 100 | 不是生效也不是失败：C 族症状消失了，但桌面死在**别的族**手上 | 跑 7.3 抽签名，写明是哪个族（A 见 §1、B 见 §2），并把该族判据行抄进结论；不得记为「修复生效」 |
| **C-alive-but-noisy** | 0 < getBytes < 19（显著下降，如 36 → 3） | 部分生效：还有第二个 OSString 发布点 | 给**下降前后的行号对**（见 7.2 格式），跑 §3.5 命令 B 抽新 selector/实例类型，再跑命令 C 找漏网字符串属性 |
| （未生效） | getBytes ≥ 19，与基线 36/37 同量级 | 镜像没带修复或修复无效 | 先跑 §3.5 命令 D 确认镜像带 ad49ff2；确认后才按 §3.5.1 三属性二分 |

**注意：C-alive 不等于「修复生效」。** 不带 0509 的控制图（如 adsp-e `usblog-20261115-223916`，G=0 S=120 F=1）
用同一条命令也判 C-alive——因为它压根没发布那些字符串属性。所以**步 1 必须先过**：只有镜像真带 ad49ff2
（命令 D 非 0）时，C-alive 才等于「修复生效」；否则它只说明「这张图不涉及 C 族」。

### 7.2 C-alive-but-noisy 必须给的行号对

「次数下降」只有配上「第一次命中出现在第几行、最后一次在第几行」才是证据，否则无法与
「日志变短」区分。三张基线实测（`grep -an 'getBytes:range:' $L | head -1` / `tail -1`）：

| 日志 | 总行数 | 首命中行 | 末命中行 | 命中数 |
| --- | --- | --- | --- | --- |
| s4c `usblog-20261115-162553` | 3535 | :1303 | :3528 | 37 |
| h1 `usblog-20261115-211515` | 3558 | :1463 | :3527 | 36 |
| h4 `usblog-20261115-230627` | 3703 | :1384 | :3659 | 36 |

修复图若变成 3 次，就写成「37 → 3，首命中 :1303 → :xxxx，末命中 :3528 → :yyyy」，
并说明剩下的命中是集中在启动早期（第二个发布点只跑一次）还是贯穿全程（另有循环发布）。

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
剩下的是 P-120 金属注入的既有噪声——它不阻止桌面起来（h12/h23 的 SpringBoard 132/128 行就是证明）。

### 7.4 现成证据：h12 与 h23 已经满足 C-alive

Lead 23:59 说「要判的是 bt-late-20261115a（全量 0511 + 0512 + ad49ff2）」。本线复核发现
**已经飞过的 h12 / h23 就是首批带 ad49ff2 的镜像**，不必等新图即可给出 C 族结论：

```sh
git merge-base --is-ancestor ad49ff2 <head>                                # h12 364499d869 YES、h23 ba4afb2a4a YES
git show <head>:patches/xnu/0509-*.patch | grep -c k60_bt_string_property  # h12 5、h23 5；h1/h3/h13/h4/s4c 均 0
```

| 镜像 | 带 ad49ff2 | getBytes | SpringBoard | first frame | entered backboardd | crashed |
| --- | --- | --- | --- | --- | --- | --- |
| h12 `usblog-20261115-230047`（0EB30032F24A） | 是 | **0** | **132** | **1**（:2381） | 1（:1310） | 7 |
| h23 `usblog-20261115-235417`（9B308BAD875B） | 是 | **0** | **128** | **1** | 1（:1296） | 7 |
| h1 / h3 / h13 / h4（基线） | 否 | 36 | 12–13 | 0 | 18 | 30–45 |

h12 同日志还有 `:186 K60 BT: published local address ee:98:c5:8a:6b:4e` 与
`:762 [bluetooth] power=1 result=0 baud=115200 firmware=`——即「身份发布成功 + 类型正确 + 桌面起来」
三件事同时成立。按 7.1 判 **C-alive**：C 族（getBytes:range: 类型不匹配）在 ad49ff2 上已结案，
残留的 17–22 次 NSURL nil 是 A 族（P-120），按 §1 处理，不属本族。

仍建议 bt 线飞 bt-late-20261115a 时用本节复核一次（它是「全量 0511 + 0512 late-start」，
比 h12/h23 的二分底座更接近最终形态）；但 C 族的结论**不依赖**那张图。


