# 可复用操作流程（HR-49：走通一次就写下来）

> 每个 Playbook 都是「复制粘贴就能复现」的完整步骤。

---

## PB-1 构建内核

```bash
# 前提：改完补丁，且补丁名已加进 SERIES-FINAL.txt（P-90）
wsl -u root -e bash -c "tr -d '\r' < <workspace>/scratch/buildv15.sh > /tmp/bNNNNN.sh; \
  chmod +x /tmp/bNNNNN.sh; \
  pkill -9 -f 'unixnu build kernel'; sleep 2; \
  rm -f <workspace>/scratch/BUILD_V15.txt; \
  setsid nohup bash /tmp/bNNNNN.sh > /tmp/bNNNNN.out 2>&1 < /dev/null &"
```

**验收**：
```bash
wsl -u root -e bash -c "grep -aE 'BUILD OK|BUILD FAILED' <workspace>/scratch/BUILD_V15.txt | tail -1; \
  grep -a 'patches applied' <workspace>/scratch/BUILD_V15.txt | tail -1; \
  grep -a 'sha256' <workspace>/scratch/BUILD_V15.txt | tail -1"
```
期望：`BUILD OK` + `patches applied: <N>` + kernel sha256（≈200 秒）

---

## PB-2 打包 + 刷机 + 抓日志

```bash
# 打包
wsl -u root -e bash -c "tr -d '\r' < <workspace>/scratch/packv15.sh > /tmp/pv.sh; bash /tmp/pv.sh | tail -1"
```

```powershell
# 刷机（先确认设备）
$env:PATH='<android-sdk>\platform-tools;'+$env:PATH
fastboot devices        # 没有就 adb devices → adb reboot bootloader（HR-43）
& '<workspace>\usb-a-stage\scripts\boot-and-capture.ps1' `
  -Image '<workspace>\usb-a-stage\out\boot-v15-20261108.img' -Seconds 170 -WaitFastboot 90
```

**读日志**：
```powershell
$d = Get-ChildItem '<workspace>\evidence' -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content (Join-Path $d.FullName 'console.log') | Where-Object { $_ -match '<关键词>' }
```

---

## PB-3 从 Android 取权威硬件数据

**任何「硬件到底是不是好的」的疑问，先做这个再改代码。**

```powershell
$env:PATH='<android-sdk>\platform-tools;'+$env:PATH
# 1) 从 fastboot/内核回 Android
adb devices; adb reboot
Start-Sleep 45

# 2) regulator 全表
adb shell 'for i in $(seq 0 94); do r=/sys/class/regulator/regulator.$i; n=$(cat $r/name 2>/dev/null); if [ -n "$n" ]; then echo "$i $n $(cat $r/state 2>/dev/null) $(cat $r/microvolts 2>/dev/null)"; fi; done'

# 3) device-tree 属性（引脚）
adb shell 'ls /proc/device-tree/soc/spi@990000/xiaomi_touch@0/'
adb shell 'cat /proc/device-tree/soc/spi@990000/xiaomi_touch@0/goodix,avdd-gpio | od -An -tx1'

# 4) 子系统驱动状态
adb shell 'cat /sys/devices/platform/goodix_ts.0/chip_info'
adb shell 'cat /proc/bus/input/devices'
```

---

## PB-4 改补丁并验证

```bash
# 1) 改补丁（用 python 脚本做精确替换，保留 '+' 前缀）
# 2) 结构检查
python3 - <<'PY'
import io, re
P='<patch 路径>'
s = io.open(P, encoding='utf-8', errors='ignore').read()
body = '\n'.join(l[1:] for l in s.split('\n') if l.startswith('+'))
b2 = re.sub(r'//[^\n]*', '', body); b2 = re.sub(r'/\*.*?\*/', '', b2, flags=re.S)
print('braces {%d}/{%d} %s' % (b2.count('{'), b2.count('}'), 'OK' if b2.count('{')==b2.count('}') else 'BAD'))
print('parens (%d)/(%d) %s' % (b2.count('('), b2.count(')'), 'OK' if b2.count('(')==b2.count(')') else 'BAD'))
PY

# 3) 修 hunk 计数（必须，否则 git apply 会失败）
python3 <workspace>/scratch/fix_hunk_counts.py
python3 <workspace>/scratch/fix_bare_lines.py

# 4) 同步到构建树
cp -f "$E/patches/xnu/<name>.patch" /tmp/usb-cdc-mainline/device/patches/xnu/
```

---

## PB-5 往 payload.img 注入文件（方法一）

见 `DATA-VOLUME-DEPLOY.md` §方法一。核心命令：
```bash
mmd -i "$PAY" ::/DIR
mcopy -o -i "$PAY" local_file "::/DIR/file"
mdir -i "$PAY" -/ ::/DIR          # 验证
minfo -i "$PAY" ::                # 查剩余
```

---

## PB-6 构建 userland（Mac，无 iPhoneOS SDK）

```bash
SSH="sshpass -p <password> ssh -o StrictHostKeyChecking=no <user>@<mac-host>"

# 传源码
tar czf /tmp/k60-userland.tar.gz userland/
sshpass -p <password> scp /tmp/k60-userland.tar.gz <user>@<mac-host>:~/
$SSH 'cd ~ && rm -rf k60-ul && mkdir k60-ul && tar xzf k60-userland.tar.gz -C k60-ul'

# 编译（不需要 iPhoneOS SDK，因为是 freestanding）
$SSH 'cd ~/k60-ul/userland && clang -target arm64-apple-ios16.6.1 \
  -Os -static -nostdlib -ffreestanding \
  -fno-stack-protector -fno-stack-check -fno-builtin -Wall -Wextra \
  -Ilibmini -Wl,-e,_start -Wl,-pagezero_size,0x100000000 -Wl,-no_fixup_chains \
  libmini/start.S libmini/mini.c init.c -o /tmp/init.new'

# 签名
$SSH 'cd ~/k60-ul/userland && codesign --force --sign - --pagesize 4096 \
  --entitlements init-entitlements.plist /tmp/init.new'

# 取回并生成 blob
sshpass -p <password> scp <user>@<mac-host>:/tmp/init.new /tmp/init.new
# 然后按 scripts 里的模式生成 C 数组头文件
```

**产物 53,728 B（签名后）**，`strings` 应含你新加的路径/字符串。

---

## PB-7 重写 git 历史剔除大文件

```bash
cd <repo>
# 0) 备份
git bundle create <workspace>/rollback/<repo>-$(date +%Y%m%d-%H%M%S).bundle --all

# 1) 剔除
git filter-repo --path <大文件目录> --invert-paths --force

# 2) 恢复 remote（filter-repo 会删）
git remote add origin <url>

# 3) push 必须在 Windows 侧（HR-48）
```

```powershell
Set-Location '<repo>'; $env:GIT_TERMINAL_PROMPT='0'
git push --force --progress origin main
```

---

## PB-8 排查 "git push 卡住"

**先验认证，别先怀疑网络**（HR-48）：
```bash
GIT_TERMINAL_PROMPT=0 git push origin main 2>&1 | head -5
```
- 出现 `No anonymous write access` → 凭据问题 → **去 Windows 侧推**
- 认证能过但卡 → 才查 pack 大小 / 带宽

**判别**：`ls-remote`（GET，能过）秒回，`push`（POST，需认证）卡死 = 认证问题。

---

## PB-9 定位补丁应用失败

```bash
# 1) 看是哪个补丁失败
grep -a 'error: patch failed' /tmp/build-v15.log | head -5
grep -a '== kernel: patch' /tmp/build-v15.log | tail -5   # 最后成功的

# 2) 看补丁的 hunk 头
grep -n '^@@' <patch>

# 3) 看目标文件当前内容
sed -n '<行号范围>p' <构建树>/bsd/kern/xxx.c

# 4) 判断：上下文被别的补丁改过 → 重新生成该补丁，或并进已控制的相关补丁
```
**经验**：不要给不兼容的旧补丁打补丁；把逻辑并进同区域、且我们完全控制的补丁更稳。

---

## PB-10 手写 / 修改补丁的完整验证流程

**背景**：0404 因为跳过这些步骤返工 4 次（P-96）。**每次改补丁都按这个走。**

```bash
P=<patch 路径>
X=/opt/k60/trees/usb-cdc-mainline/out3/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work

# 1) 结构检查（C 代码括号平衡）
python3 - "$P" <<'PY'
import io, re, sys
s = io.open(sys.argv[1], encoding='utf-8', errors='ignore').read()
body = '\n'.join(l[1:] for l in s.split('\n') if l.startswith('+'))
b2 = re.sub(r'//[^\n]*','',body); b2 = re.sub(r'/\*.*?\*/','',b2,flags=re.S)
print('braces {%d}/{%d} %s' % (b2.count('{'),b2.count('}'),
    'OK' if b2.count('{')==b2.count('}') else 'BAD'))
PY

# 2) 自动修 hunk 行数 + 裸空行（通用脚本）
python3 <workspace>/scratch/fix_hunk_counts.py "$P"
python3 <workspace>/scratch/fix_bare_lines.py "$P"

# 3) 用构建同款判定验证
cd "$X" && git apply --check "$P"    # 必须无输出

# 4) 上下文不确定时，先读真实文件
sed -n '<from>,<to>p' "$X/<target>" | cat -A

# 5) 同步到构建树并构建
cp -f "$P" /tmp/usb-cdc-mainline/device/patches/xnu/
```

**三条硬性要求（git apply）**：
1. 新增文件段最后一行不能是裸 `+`
2. `@@ -0,0 +1,N @@` 的 N = 实际 `+` 行数
3. 上下文必须逐字匹配（含中间被跳过的行）

**注**：`patches/xnu/series` 是产物，真相源是
`<workspace>/scratch/SERIES-FINAL.txt`（P-90）。
