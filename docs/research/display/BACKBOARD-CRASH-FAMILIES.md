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

状态（2026-11-15 晚）：Lead 已收下本档案并离线复核确认 §3.3 归因；B 族口径终局——只认
brightness-4（control=1，4×SIGSEGV）对 brightness-13（control=0，0 崩）这一对，交付形态 A
（control=0 + 真 conformance）正式定稿；C 族修复验证图等 bt 线出（本线不预建）；dyld 缓存已批准由 Lead 拉取（设备当前在 fastboot，
拉取需 adb，窗口由用户排，Lead 2026-11-15 18:59 回复）；springboard 线类型编码线索已收录 §3.3。

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

## 4 判据汇总（只用日志）

    grep -c 'nil string parameter'  log   # >0 且 manifest 有 pong_metal=1 → A 族（P-120）
    grep -c 'sig=11'                log   # >0 且 published 行 control=1 → B 族（int-236）
    python3 scripts/check-backlight-log.py log   # B 族正判器，EXIT=0 为 PASS
    grep -c 'getBytes:range:'       log   # >0 → C 族；崩溃次数 ≈ (命中数+1)/2（成对打）

## 5 缺口

- **20G81 dyld shared cache 缺失**，0x19cb…/0x1a21…/0x1c38… 与私段 0x10… 帧全部无法反推符号。Lead 2026-11-15 已批准下个上机窗口拉取，由 Lead 执行（设备只经 Lead 的手），拉完通知我，我再做符号化；Lead 会在窗口期顺带准备好 device 侧 adb 通道。清单：
  - /System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64e（iOS 16.6.1 完整版约 3.2 GB；设备上可能略小，以实际大小为准）
  - /System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64e.map（约 300–600 MB，若存在）
  - 可选 dyld_shared_cache_arm64e.symbols（设备上通常不存在，有则一并拉）
  - 目的地：E:/k60-work/caches/20G81/；符号化工具建议 ipsw（dyldsym 子命令）或 jtool2。
- 私段帧 0x10111f930/0x100b04930/0x100aa9930 归属（backboardd 主二进制 vs libpong-ui.dylib）同样依赖上述 cache；但即便归 backboardd 主二进制，也不改变 §3.3 的归因（我们无 getBytes 形状）。

