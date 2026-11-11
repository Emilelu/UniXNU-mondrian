# 环境事实权威表（用户反复交代过的，全部在此，勿再问）

> **这份文档是唯一权威来源。** 任何环境问题先查这里。
> 用户每次重复交代 = 流程缺陷 → 必须补进来。
> 最后更新：2026-11-10

---

## 1. 手机（K60 / mondrian）

| 项 | 值 |
|---|---|
| 序列号 | **`6033dbec`** |
| fastboot 设备名 | `6033dbec  fastboot` |
| **ADB 状态可切 fastboot** | ✅ **`adb reboot bootloader` 直接进，不用手动长按** |
| 串口（抓内核日志） | **COM5**（USB 侧），波特率按 boot-and-capture.ps1 |
| 自动复位 | `k60_selftest_reboot=300` — **有意设计**，300 秒后自己回 fastboot，供自动化调试循环 |
| 强制关机 | 长按电源 10 秒（仅当 ADB/fastboot 都不可用时）|

### 状态切换矩阵（每次操作前按此探活）

```bash
# 1) fastboot?
fastboot devices
# 2) 不在 → 试 adb
adb devices
# 3) 在 adb → 切 fastboot（首选！）
adb reboot bootloader && sleep 8 && fastboot devices
# 4) 都没有 → 才提示用户长按电源 10 秒
```

**自动化调试循环**（300s 复位是核心）：
```
fastboot boot <img> → 抓 300s 串口 → 内核自动回 fastboot → 刷下一个镜像
```

---

## 1b. git push 必须在 Windows 侧（重要）

| 项 | 事实 |
|---|---|
| **WSL 的 git** | **没有 GitHub 凭据** → push 静默挂起等密码，永不返回 |
| **Windows 的 git** | ✅ `gh auth git-credential` + 凭据管理器，push 正常 |
| push 命令 | `Set-Location '<repo>'; $env:GIT_TERMINAL_PROMPT='0'; git push --force --progress origin main` |
| 排查 | `ls-remote` 是 GET（能过），`push` 是 POST（需认证）→ **前者秒回后者卡死 = 认证问题** |

**WSL 只做 fetch / 构建 / 刷机。push 一律在 Windows 侧。**

## 2. Mac（构建 userland / GPU 用户态）

| 项 | 值 |
|---|---|
| 地址 | **`<user>@<mac-host>`** |
| 密码 | **`<password>`** |
| macOS | 26.7.3 |
| **只有 CommandLineTools，没有完整 Xcode** | ⚠️ **`xcrun --sdk iphoneos` 会失败** |
| 可用 SDK | 仅 `MacOSX*.sdk`（无 iPhoneOS SDK）|
| clang | `/Library/Developer/CommandLineTools/usr/bin/clang` |
| 构建目录 | `~/k60-build`（含 metal2vulkan, metal2vulkan-k60, mesa-k60, drivers, patches, scripts, tools, out）|
| 用户目录 | `/Users/emilelu` |

### SSH 用法

```bash
SSH="sshpass -p <password> ssh -o StrictHostKeyChecking=no <user>@<mac-host>"
$SSH 'command'
sshpass -p <password> scp -o StrictHostKeyChecking=no <local> <user>@<mac-host>:~/
```

### ⚠️ iPhoneOS SDK 在 Mac 上，不在标准位置（重要，别再找）

```
/Users/emilelu/ios-sdk/iPhoneOS16.5.sdk        ← 真实路径，完整可用
```

| 项 | 事实 |
|---|---|
| **SDK 路径** | **`/Users/emilelu/ios-sdk/iPhoneOS16.5.sdk`** |
| 完整性 | ✅ 有 `SDKSettings.plist`、`usr/lib/*.tbd`、`System/`、`Developer/` |
| **`xcrun --sdk iphoneos`** | ❌ **找不到**（SDK 不在 `/Library/Developer/CommandLineTools/SDKs/` 下） |
| **正确用法** | **必须显式 `-isysroot /Users/emilelu/ios-sdk/iPhoneOS16.5.sdk`** |
| Xcode | 未安装（也不需要，有这个 SDK 就够编 userland）|

**不要因为 `xcrun --sdk iphoneos` 失败就断定"Mac 没有 SDK"**——
它在自定义路径下，`xcrun` 只查标准目录。

### 编译 init 的正确命令（用这个 SDK）

```bash
SSH="sshpass -p <password> ssh -o StrictHostKeyChecking=no <user>@<mac-host>"
SDK=/Users/emilelu/ios-sdk/iPhoneOS16.5.sdk

$SSH "cd ~/k60-ul/userland && \
clang -target arm64-apple-ios16.6.1 -isysroot \"$SDK\" \
  -Os -static -nostdlib -ffreestanding \
  -fno-stack-protector -fno-stack-check -fno-builtin -Wall -Wextra \
  -Ilibmini -Wl,-e,_start \
  -Wl,-pagezero_size,0x100000000 -Wl,-no_fixup_chains \
  libmini/start.S libmini/mini.c init.c -o /tmp/init.new"
```

**验收判据（必须核对，见 P-94/P-95）**：
```bash
python3 -c "
import struct
d=open('/tmp/init.new','rb').read()
print('ncmds=%d sizeofcmds=%d size=%d' % (
    struct.unpack_from('<I',d,16)[0],
    struct.unpack_from('<I',d,20)[0], len(d)))"
# 编译产物（未签名）必须是  ncmds=9  sizeofcmds=1088  size=34704
```

---

### 旧内容：在 Mac 上构建 init（不需要 iPhoneOS SDK）

因为是 `-nostdlib -ffreestanding`，自带 syscall，**不用 SDK 也能编**：

```bash
cd ~/k60-ul/userland
clang -target arm64-apple-ios16.6.1 \
  -Os -static -nostdlib -ffreestanding \
  -fno-stack-protector -fno-stack-check -fno-builtin -Wall -Wextra \
  -Ilibmini -Wl,-e,_start \
  -Wl,-pagezero_size,0x100000000 -Wl,-no_fixup_chains \
  libmini/start.S libmini/mini.c init.c -o /tmp/init.new
# 会有一条 sysroot warning，正常
codesign --force --sign - --pagesize 4096 \
  --entitlements init-entitlements.plist /tmp/init.new
```

产物约 **53,728 字节**（签名后），Mach-O arm64。

---

## 3. WSL（主构建环境）

| 项 | 值 |
|---|---|
| 发行版数据 | `<android-sdk>\wsl`（ubuntu 24.04 vhdx）|
| **网关会变** | 历史值 `172.27.64.1` / 现 `198.18.0.2` → **git 代理写死会失效** |
| DNS | `github.com` → `198.18.0.150`（被代理软件 fake-ip 劫持）|

### git 代理（HR-41）

```bash
# 症状：Proxy CONNECT aborted
# 修法：清掉错误代理，实测直连可用
git config --global --unset http.proxy
git config --global --unset https.proxy
# 或跑 <workspace>/scripts/fix-git-proxy.sh 自动探测
```

### WSL 内重要路径

| 路径 | 内容 |
|---|---|
| `/opt/k60/trees` | 构建树（`k60build` 在此）|
| `/opt/unixnu-linux` | Xcode/LLVM 工具链副本 |
| `/root/linux-apfs-rw` | APFS 驱动（git 仓库）|
| `/home/emilelu/k60-work` | WSL 侧工作目录 |
| `<workspace>` | **主工作区**（Windows E 盘）|

---

## 4. 构建与刷机流程

| 步骤 | 命令/脚本 |
|---|---|
| 构建内核 | `<workspace>/scratch/buildv15.sh`（≈200 秒）|
| 打包镜像 | `<workspace>/scratch/packv15.sh` |
| 刷机+抓日志 | `<workspace>\usb-a-stage\scripts\boot-and-capture.ps1` |
| 构建树输出 | `/opt/k60/trees/k60build/out-baseline/mondrian/ipados-16.6.1-20G81/mondrian/` |
| 镜像输出 | `<workspace>\usb-a-stage\out\boot-v15-20261108.img` |

### 后台构建（避免超时）

```bash
setsid nohup bash /tmp/bNNNNN.sh > /tmp/bNNNNN.out 2>&1 < /dev/null &
```

### 验收标准

```
patches applied: 211    ← 补丁数
BUILD OK
kernel.macho sha256 <hash>
```

---

## 5. 仓库位置（详见 REPO-INVENTORY.md）

| 位置 | 仓库数 |
|---|---|
| `E:\hackios` | 15 |
| `<workspace>\references` | 23 |
| `<workspace>\forks-review` | 3 |
| `<android-sdk>\k60-ios` | 6 |
| WSL `/root` | 1 |
| **合计** | **48** |

**主仓**：`<repo>`（分支 `fix/k60-measured-high-window`）

---

## 6. 外部参考源

| 源 | 用途 |
|---|---|
| `<workspace>\UniXNU-zizhan` | **同 SoC SM8475 超集，第一优先参考** |
| `<workspace>\references\yibiya-upstream` | fork，`upstream-fix` 分支（采纳分析见 YIBIYA-PICK.md）|
| `<workspace>\impl\touch-protocol\refs\` | **完整官方 Goodix BerlinD 驱动源码** |
| `<workspace>\references\ruby-bringup` | GT9916R 触摸（K60 同款芯片）|

---

## 7. 用户反复交代过、必须记住的硬事实

1. **K60 = SM8475**，与 zizhan 同 SoC，与 ruby 同触摸芯片 GT9916R
2. **zizhan 触摸是 ST FTS 不是 Goodix** —— 只能参考总线/电源，协议层用 ruby
3. **300 秒自动复位是自动化调试设计，不要关**
4. **ADB 状态可以 `adb reboot bootloader`**
5. **Mac 可 SSH**（凭据见上），用于构建 userland/GPU 用户态
6. **WSL 网关会变**，git 代理要动态探测
7. **本仓库 `yibiya/UniXNU-mondrian` 是 fork 参考源**，需定期 cherry-pick
8. **每次开工先 pull 所有仓库到最新**（定时任务每日两次已建）
