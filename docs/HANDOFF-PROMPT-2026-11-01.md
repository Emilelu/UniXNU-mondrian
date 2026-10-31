# 交接 Prompt（2026-11-01）

```markdown
你是 Redmi K60（mondrian / SM8475）移植 iOS 的主 agent，接手一次**路线迁移**：
从已经跑通的 **darwin22（iOS/iPadOS 16.6.1 / 20G81 / xnu-8796）**，迁移到
**darwin24（iPadOS 18.7.10 / 22H374 / xnu-11417）**。

## 背景：为什么迁移

darwin22 阶段**已经解决了所有影响启动的内核 panic**：8 核启动到 launchd、服务链拉起了
SpringBoard、`/private/var` 读写挂载成功、keybag 通过、watchdogd 禁用、**屏幕出现 iOS 启动进度条**。

唯一无法解决的是用户态 **sig=9 风暴**（约 98% 守护进程被 signal 9 杀掉）。已排除「无条件 Sandbox
策略」（补丁 0240）与「启动约束拒绝」（补丁 0241，`k60-no-lc=1`）两个假设，风暴均未停止。
用户因此决定放弃该分支（"问题依旧 不走16.6.1了"），转为 darwin24。

**所以：darwin22 的启动链经验全部有效、可复用；但 darwin22 的 sig=9 结论不要带过来重查。**

选 darwin24 的依据是 `UniXNU-pong` 用**同一颗 SM8475**。但请注意：
pong 的 `porting.toml` 只有 13 条 `kind="source"`、0 条 host、0 条 device 证据，
`migration-state.json` 里 `image_hashes_used: false`。
**pong 的 darwin24 从未提供过可复现的实机证据——它的 bug 很可能就是我们的 bug。**

## 第一件事：按顺序读完这几份，不要跳过

1. `~/hackios/UniXNU-mondrian/docs/ROUTE-A-18-HANDOFF-2026-11-01.md` ← **主线全文，最重要**
2. `~/hackios/UniXNU-mondrian/docs/ROUTE-A-18-STATE.md` ← 现在在哪、下一步
3. `~/hackios/UniXNU-mondrian/docs/PONG-FEASIBILITY.md` ← 为什么用 pong
4. `~/hackios/UniXNU-mondrian/docs/HANDOFF-2026-10-31.md` ← darwin22 时代历史（背景，不要照搬结论）
5. `~/hackios/UniXNU-mondrian/README.md` ← 状态表

读完再动手。

## ★ 铁律：先把新内核的改动彻底调研完，再开工、再发 boot

用户为这件事已经连续踩了三次同样的启动结果，明确要求：

> "已经连续两次这样了 你必须彻底解决问题再发boot"
> "你接下来别乱改了 没调研出真正解决方案前别浪费我时间"
> "你必须做充足的调研和研究…彻底解决这个问题，而不是总是靠猜测改一下再boot一下"

具体要求：

- **不要在没调研清楚前就改内核、打包、刷机。** 每一次盲刷都在消耗用户的耐心和设备寿命。
- 任何一处改动都要能回答三个问题：① 依据是什么（源码/产物/日志证据）② 预期现象是什么
  ③ 如果预期没出现，排除了什么、下一步查什么。
- **一次只改一个变量**，并在汇报里明确写出"这次改动的量"。
- 每轮上机前先把**校验**做完（哈希、结构、镜像布局），校验不过不上机。
- 关键结论必须落到文档并 push，不要只留在对话里。

## 当前卡点（一句话）

darwin24 内核已在 Linux 上完整构建、四道校验全过；loader 的 `boot_args` ABI 已从 Darwin 22
修正为 Darwin 24；最后一次上机**屏幕出现绿条**（证明 loader 跳板确实跳进了内核入口
PA `0xC74C04A0`），但内核仍**静默复位**。

**当前最大障碍不是缺补丁，而是观测盲区**：pong 的驱动栈里没有任何视频控制台驱动，
ramoops 控制台（K60 基址 `0xA7000000`）要到 `arm_vm_init()` **之后**才初始化，
所以那之前的任何死亡都是完全静默的。

## 已验证完成、不要重做的四件事

1. **平台层已补**：`libArmDTPlatform.a`(27,808 B) + `libArmCpu.a`(34,600 B) 已针对 darwin24 构建
   并用 `-Wl,-force_load` 链入。内核 20,872,376 B，sha256 `2f485593b3f7c2d35657f14d5e2e5804ca434fbf56df6f275c0802bf32a7e5cd`。
   没有这一层，`PE_init` 找不到 `IODTPlatformExpert`，内核没有控制台。
2. **`boot_args` ABI 已修**：`uefi-mondrian/.../DarwinBootPkg/Driver/BootArgs.h` 从
   Darwin 22（`sizeof 0x2e0`、命令行 608）改为 Darwin 24（`0x480`、1024，`BootFlags 0x470`、
   `MemorySizeActual 0x478`）。编译期 `STATIC_ASSERT` 全过，`DarwinBoot.obj` 含 `0x480 ×3`，
   FD 内 `0x2e0` 出现 0 次。**这是之前两次静默复位的根因。**
3. **loader 身份已确认**：`Entry.S` 与 pong 的 `DarwinBoot24` **sha256 完全一致**；
   `DarwinBoot.c` 只差我们加的 QR 调试行、前缀标签、ABI 字符串。
4. **镜像布局已解析并写成校验脚本**：`ANDROID!`@0；偏移 4096 = gzip(UEFI FD) 547,073 B
   + `hardware.dtb` 1,862 B = kernel_size 548,935；payload@557,056；总 201,887,744 B。
   FD 前有 **112 字节 BootShim**（`ARMd` 在 +56），所以解压后必须 `dec[112:] == fd` 才算对。

## 已排除的假设（别浪费时间）

| 假设 | 排除依据 |
|---|---|
| 入口点错误 | 我们 darwin24 的入口字 `140006EF 00000000 00000000 00000000` 与**能正常启动的** darwin22 **逐字节相同**；Apple 22H374 只是用 NOP 填充、落点一样 |
| xnu 侧 `struct boot_args` 变了 | xnu-8796 与 xnu-11417 的 13 字段 `struct boot_args` 与 6 字段 `Boot_Video` 完全相同 |
| `start.s:756` 的 `bne .` 死循环 | PONG 是 `NO_MONITOR=1`（KTRR 关），宏只 `msr` 不改 `x0`，`cmp x0,x1` 恒等，永不跳转 |
| `start.s:568` 的 `bne .` | 由 `tbz w1,#0x1f` 保护，非 kext 内核跳过 |
| 缺视频控制台驱动 | pong 驱动树只有 5 个（ArmCpu / ArmDTPlatform / NativeRamBlock / NativeUfs / PongAdreno），本来就没有；`pong_display`、`pong_software_ui` 全树无读者 |

## 下一个最值得查的线索

打包进内核的 FDT **是原始 `hardware.dtb`（1,862 B，14 个节点）**，不是
`devicetree.generate()` 生成的 ADT（14,620 B）。

- `unixnu bootimg` 的 `--dtb` 只跑 `patch_dtb()`（按 `board.toml [[bootimg.dtb_node]]` 加节点），
  **不会调用 `devicetree.generate()`**（已 grep 确认）
- 该 DTB 缺 **`/chosen`、`/arm-io`、`/defaults`、`/options`**——而这四项正是
  `ArmDTPlatform.cpp` 头注释里声明 `configure()` 必需的东西（"absent inputs make configure() fail"）
- payload 里 `adt_sha256 = 78f8ecd0…` 但 `adt.bin` 并不存在

`k60-work/adt-generate2.py` 已能生成 14,620 B 的 ADT（注意它头部 magic 是 `0x06000000`，
是**容器格式**，内部才嵌 FDT；`adt-walk.py` 假设裸 FDT 会报 `not an FDT`，需先修）。

## 建议的动作顺序

1. **先解决可观测性**（不要再盲刷）：在 `start.s` 的 `_start` 里加不依赖 MMU 的面包屑
   （`mov x20, x0` 之后、开 MMU 之前各画一条色条到 framebuffer；`x20` 是 boot_args PA，
   `Video[]`@+0x28，`v_rowBytes`@+0x38；XNU 的 bootstrap 页表含 V=P 块映射，开 MMU 后
   用 PA 写 framebuffer 仍有效）。或在 `arm_init()` 开头直接往 PA `0xA7000000` 写标记字，
   之后从 Android root `dd if=/dev/mem` 读回。
2. **核对 FDT 契约**：确认 darwin24 内核要的是 `hardware.dtb` 还是生成的 ADT；若是后者，
   要让 ADT 真正进 `bootimg`。
3. 越过 `arm_vm_init` 后读 ramoops carveout，看 `PONG DIAGNOSTIC v92` 是否出现。

## 构建命令（全部 Linux，不需要 macOS）

```bash
# 1) 平台驱动归档
wsl -d Ubuntu-24.04 -- python3 <workspace>/k60-work/build-k60-platform-archives.py

# 2) 内核（含 force_load 两个归档）
wsl -d Ubuntu-24.04 -- python3 <workspace>/k60-work/route-a18-platform-build.py
```

**坑（必读）**：
- `LD_KERNEL_ARCHIVES` 会**替换**默认列表 → 必须显式带 `-L$FAKEROOT/usr/local/lib/kernel -lfirehose_kernel`
- **make 不追踪命令行变量变化** → 改 `LD_KERNEL_ARCHIVES` 后必须先删
  `build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/mach.development.pong.unstripped.noctf` 才会重新链接。
  这条坑过一次：sha256 完全没变却以为链接成功。
- `MACHINE_CONFIGS=PONG`、`PLATFORM=iPhoneOS` 必须显式设

```bash
# 3) UEFI FD（不需要 nasm/iasl！）
cd ~/hackios/uefi-mondrian && python3 ./build_uefi.py -d mondrian -r DEBUG -c
# 结尾 "The Device DTB is Missing in Resources/DTBs!" 是无害的构建后失败

# 4) 打包
cd /tmp/k60build && ./unixnu bootimg -D ~/hackios/UniXNU-mondrian \
  --uefi ~/hackios/uefi-mondrian \
  --fd ~/hackios/uefi-mondrian/Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd \
  --dtb <OUT>/device-tree/hardware.dtb \
  --ramdisk <OUT>/payload/payload.img \
  -o /mnt/d/Android/k60-ios/<name>.img
# rc=1 + "boot image header does not match the requested parameters" 是已知误报，
# 必须用独立哈希校验（见 HANDOFF §5）
```

## ★ 用子 agent 提高效率

这份工作的调研面和开发面都很宽，**应该主动用子 agent 并行**，不要串行地一个人啃：

- **调研类**（可并行）：分别去读 pong 的驱动栈、xnu-11417 的早期启动路径、
  `devicetree.py` 的 ADT 契约、DarwinBoot24 与我们的 loader 差异、22H374 的 kext/prelink 需求。
  每个子 agent 给一个**明确的单一问题**和**要求的证据形式**（文件+行号、哈希、命令输出）。
- **验证类**（可并行）：镜像布局校验、FD 符号/常量校验、ADT 节点核对、
  patch series 是否干净应用——这些互不依赖。
- **反方审查**（强烈建议）：让一个子 agent 专门去**反驳**你当前的根因假设，
  要求它只输出"这个假设不成立的证据"。前几轮的教训就是假设过得太快。
- 子 agent **不要**取得刷机权限；刷机与不可逆操作只由你（主 agent）在向用户确认后执行。
- 子 agent 的结论必须附证据；没有证据的结论不要写进文档。

## 硬约束（违反会变砖）

- **只 `fastboot boot`，绝不 `fastboot flash boot`**（boot 分区属 Android，会毁双系统）
- **绝不 `fastboot flash persist`**（TEE 会 `deleteAllKeys`，密钥永久失效）
- 允许写 `unixnu` 分区；禁止碰 `persist` / `modemst*` / Android `userdata`
- 设备串号 `6033dbec`；用户可以随时"进 fb"，先用 `fastboot devices` / `adb devices` 自己探测，
  探测不到就轮询，不要反复追问
- 一次只改一个变量，并说明改动量
- 提交按文件拆分，**绝不 `git add -A`**；`mac-build/` 保持未跟踪
- 每个 push 的仓库，README 要及时跟进更新
- 每 6 小时左右抽查一次仓库的公开 fork，有用的 commit 吸收过来并保留作者/SHA 署名

## 汇报风格

用户是工程师，讨厌空话。直接给：改了什么、依据是什么、预期什么、没出现预期就排除了什么。
不要用"应该没问题""试试看"这类表述。
```

## 附：给接手者的产物清单

| 产物 | 大小 | sha256 |
|---|---|---|
| darwin24 内核 | 20,872,376 | `2f485593b3f7c2d35657f14d5e2e5804ca434fbf56df6f275c0802bf32a7e5cd` |
| payload.img | 201,326,592 | `632cb82961ab2ecd82c1e36a97a284ecd9ceec3e012078867450cb670ea20728` |
| UEFI FD | 3,145,728 | `a8a6f79c1d7705d96922c523c63c1cee24988788d29bfc97529e1cdbc67e4d4d` |
| `boot-darwin24-abi24.img`（已刷，出绿条） | 201,887,744 | `c249c547e6999a2722b5884733bda98af9c0d5a719ab575e4e921465df8c338a` |
| `boot-darwin24-abi24b.img`（未刷） | 201,887,744 | `6796e1479e5c5cd83fa37998b573d394e6b2b7a44ff2083353a153b9d04b35e0` |
