# 可复用工具总表（HR-49：发现工具就登记，别让用户提醒）

> **两个 scripts 目录，别搞混：**
> - `<workspace>/scripts/` — 本地新增工具（inject-payload-files、sync-all-repos、fix-git-proxy）
> - `<repo>\scripts\` — **仓库内**工具（build-pong-*, data2g-*, reshuangroot, audit-*）

> 用法：要做某件事之前先在这里搜工具，不要重复造轮子或满盘 find。

---

## 1. 镜像 / 文件系统

| 工具 | 路径 | 用途 | 用法示例 |
|---|---|---|---|
| **mcopy / mdir / mmd** | 系统自带（mtools） | **读写 FAT 镜像，不用挂载** | `mcopy -o -i payload.img file "::/DIR/file"` |
| minfo | 同上 | 查 FAT 剩余空间 | `minfo -i payload.img ::` |
| **apfsck** | `/usr/sbin/apfsck` | APFS 卷检查 | `apfsck -q image.img` |
| **linux-apfs-rw** | `/root/linux-apfs-rw/` | **完整 APFS 读写内核模块**（含压缩） | `make && insmod apfs.ko` |
| Python APFS | `<workspace>/impl/bt-8step/_work/apfs.py` | 解析 APFS 结构 | `python3 apfs.py <img>` |
| reshuangroot | **仓库内** `scripts/reshuangroot.py` | 重建 unixnu 的 SHNGROOT 头 | 见 `docs/OPS-DATA-REBUILD.md` |
| diff-physical-vs-apfs | `k60-work/apps/diff-physical-vs-apfs.py` | 物理 vs 逻辑对比 | — |
| data2g-install.sh | **仓库内** `<repo>\scripts\data2g-install.sh` | Android 侧 dd 流式装 2 GiB Data | `sh data2g-install.sh /dev/block/by-name/unixnu` |
| data2g-stream.sh | **仓库内** `<repo>\scripts\data2g-stream.sh` | Data 种子流式写入 | — |
| **inject-payload-files.sh** | `<workspace>/scripts/inject-payload-files.sh` | **往 payload.img FAT 注入任意文件/目录**（自动建目录、查剩余空间） | `inject-payload-files.sh --src DIR --dest /METAL` |

## 2. APFS 校验器（4 个，用途不同）

| 脚本 | 检查什么 |
|---|---|
| `scripts/check-apfs-component-checkpoints.py` | 组件 checkpoint |
| `scripts/check-native-apfs-file-checkpoints.py` | native APFS 文件 |
| `scripts/check-original-apfs-checkpoints.py` | 原始 APFS |
| `scripts/check-original-apfs-root-checkpoints.py` | 原始 APFS 根 |
| `scripts/audit-pong-root-compression.py` | APFS 压缩审计 |

## 3. 构建 / 打包 / 刷机

| 工具 | 路径 | 用途 |
|---|---|---|
| **build-strict.sh** | `scripts/build-strict.sh` | **唯一允许的实验构建入口**（P-181）：先跑 `eight-step-gate.py --build`，红了直接停；再真实传 `unixnu` 退出码；`--fd` 必填并归档；要求 `kernel.macho` 新于本轮 marker；写 `build-manifest.json`。用法 `scripts/build-strict.sh <tag> --fd <file.fd> [--kernel-arg K=V]` |
| **verify-boot-image.py** | `scripts/verify-boot-image.py` | 构建后**实物校验**：从 boot.img 里读回 kernel/FD/DTB/payload kernel 并逐个比对 manifest 的 SHA；`--manifest <tag>/build-manifest.json`。自测 `python3 scripts/tests/test-verify-boot-image.py` |
| buildv15.sh | `<workspace>/scratch/buildv15.sh` | 构建内核（≈200s） |
| packv15.sh | `<workspace>/scratch/packv15.sh` | 打包 boot.img |
| **SERIES-FINAL.txt** | `<workspace>/scratch/SERIES-FINAL.txt` | **补丁顺序真相源**（P-90：改仓库 series 无效） |
| boot-and-capture.ps1 | `<workspace>\usb-a-stage\scripts\boot-and-capture.ps1` | 刷机 + 抓串口日志 |
| patch-armcpu-validate.py | 构建树 `tree/scripts/` | ARMCPU 校验补丁（P-24 强制） |
| build-pong-metal-plugin.py | `scripts/` | 构建 Metal bundle（**需 Mac + Xcode**） |
| build-pong-adreno-platform.py | `scripts/` | 构建 PongAdreno 静态库 |

## 4. 用户态构建（Mac 必需）

> **iPhoneOS SDK 在 `/Users/emilelu/ios-sdk/iPhoneOS16.5.sdk`** ——
> `xcrun --sdk iphoneos` **查不到它**，必须显式 `-isysroot`。
> 详见 ENVIRONMENT.md 与 P-95。

| 工具 | 路径 | 用途 |
|---|---|---|
| userland/build.py | 仓库 `userland/` | 编译 init + libpong-ui |
| **freestanding 编译命令** | 见 `ENVIRONMENT.md` §2 | **无 iPhoneOS SDK 也能编 init** |
| codesign | Mac 自带 | `codesign --force --sign - --pagesize 4096 --entitlements ...` |

## 5. 补丁维护脚本（scratch/）

| 脚本 | 用途 |
|---|---|
| **`fix_hunk_counts.py`** | 自动修正 `@@ -0,0 +1,N @@` 的 N（**默认扫 `patches/xnu/*.patch` 全部文件**，也可传路径） |
| **`fix_bare_lines.py`** | 把新增文件段里的裸空行改成 `+`，并重算 N（同样默认全扫） |

**手写或修改任何补丁后的固定流程**：
```bash
python3 <workspace>/scratch/fix_hunk_counts.py
python3 <workspace>/scratch/fix_bare_lines.py
cd <xnu-work> && git apply --check <patch>   # 必须无输出
```
**`patch --dry-run` 通过不算数** —— 构建用的是 `git apply`，判定更严（见 P-96）。

## 6. 环境 / 网络

| 工具 | 路径 | 用途 |
|---|---|---|
| fix-git-proxy.sh | `scripts/fix-git-proxy.sh` | HR-41：WSL 网关变化时自动修 git 代理 |
| sync-all-repos-v2.sh | `scripts/sync-all-repos-v2.sh` | 48 仓库分类同步（A 镜像/B 工作/C 三方） |
| git-filter-repo | `/usr/local/bin/git-filter-repo` | 重写历史剔除大文件 |

## 7. 设备交互

| 工具 | 用途 | 备注 |
|---|---|---|
| fastboot | 刷机 | `<android-sdk>\platform-tools` |
| adb | Android 交互 | **`adb reboot bootloader` 可进 fastboot**（HR-43）|
| TWRP | 分区级 dd | 慢，优先用 `DATA-VOLUME-DEPLOY.md` 的方法一 |
| sshpass | Mac SSH | `sshpass -p <password> ssh <user>@<mac-host>` |

## 8. Android 侧信息采集（宝贵的对照数据源）

```bash
# regulator 全表（判断电源是否正确）
adb shell 'for i in $(seq 0 94); do r=/sys/class/regulator/regulator.$i; \
  n=$(cat $r/name 2>/dev/null); [ -n "$n" ] && \
  echo "$i $n $(cat $r/state) $(cat $r/microvolts)"; done'

# device-tree（引脚/面板参数的权威来源）
adb shell 'ls /proc/device-tree/soc/*/'
adb shell 'cat /proc/device-tree/soc/spi@990000/xiaomi_touch@0/goodix,avdd-gpio | od -An -tx1'

# 触摸驱动内部状态（固件/配置真实值）
adb shell 'cat /sys/devices/platform/goodix_ts.0/chip_info'
adb shell 'cat /sys/devices/platform/goodix_ts.0/read_cfg'
```

**这些是判断"硬件有没有问题"的权威依据，比任何文档都可靠。**

## 9. 串口 / 日志

| 工具 | 用途 |
|---|---|
| COM5 | K60 内核串口（`boot-and-capture.ps1` 自动接） |
| `<workspace>\evidence\usblog-*\console.log` | 每次启动的日志 |

## 10. 反汇编 / 二进制

| 工具 | 用途 |
|---|---|
| `strings` | 查 Mach-O 里的符号/路径 |
| `nm -a` | Mach-O 符号表 |
| Ghidra | vendor .ko 反汇编（见 `LOCAL-ASSETS.md`） |

---

## init 版本库（★ 能跑的都在 /tmp，不在 git）

> **重要**：git 里 `0391` 的历史版本都是另一条分支（日志含 `static 20G81 helper`），
> **会 panic**。设备上能跑的是 `v10guard` 线，只存在于下面这些路径（`/tmp` 不是存储，
> 需要时先把它们落进仓库）。

| 路径 | 大小 | 说明 |
|---|---|---|
| `/tmp/init-v10guard/init-v10guard` | 34,880 B | 已知能启动（launchd 到 pid 282）|
| `/tmp/init-v10guard/init.c` | 15,683 B | 源码（362 行）|
| **`/tmp/initbuild/init-v24dp`** | **34,904 B** | **v10guard 严格超集，当前用在 0391** |
| `/tmp/initbuild/init-v24dp.c` | 24,815 B | 源码（646 行）|
| `/tmp/initbuild/init-v13..v23*` | ~34.9 KB | 中间迭代版本 |

**版本甄别（30 秒）**：
```bash
strings <init> | grep 'Pong init: HackiOS'
#   "HackiOS adapter [v10guard]"             → 能跑的线
#   "HackiOS userland adapter / ... static"  → git 里的线，panic

python3 -c "
import struct,sys
d=open(sys.argv[1],'rb').read()
n=struct.unpack_from('<I',d,16)[0]; off=32; cs=None
for i in range(n):
    c,s=struct.unpack_from('<II',d,off)
    if c==0x1d: cs=struct.unpack_from('<II',d,off+8)[1]
    off+=s
print('ncmds=%d cs=%s （正确形态：9 / ~408-416）' % (n,cs))" <init>
```

---

## 补丁生成：用 difflib，不要手写

手写 `@@ -old,count +new,count @@` 的四个数字会连续错（P-109，实测 6 轮返工）。
**固定做法**：

```python
import io, difflib
SRC = '<构建树>/bsd/kern/kern_exec.c'          # 必须是构建用的那棵树（P-110）
orig = io.open(SRC, encoding='utf-8', errors='ignore').read().split('\n')
new = list(orig)
i = next(i for i, l in enumerate(orig) if l.strip() == '<定位用的那一行内容>')
new = new[:i] + NEW_LINES + new[i:]
d = list(difflib.unified_diff(orig, new, fromfile='a/x', tofile='b/x', lineterm='', n=3))
io.open(PATCH, 'w', encoding='utf-8', newline='\n').write(
    '\n'.join(['diff --git a/x b/x'] + d) + '\n')
```

**验证（构建同款判定）**：
```bash
T=/tmp/diff-test; rm -rf $T; mkdir -p $T/bsd/kern
cp <构建树的 kern_exec.c> $T/bsd/kern/
cd $T && git init -q . && git add -A && git commit -qm init
git apply --check <patch>        # 必须无输出
```

**三棵树的区别（P-110）**：
```
B=  /opt/k60/trees/k60build/.../xnu-work         ← 真正构建用（9322 行）
D=  /tmp/usb-cdc-mainline/device                 ← 补丁输入目录
OLDSRC=/opt/k60/trees/usb-cdc-mainline/out3      ← 只给 fakeroot/sources（9236 行）
```

---

## Mach-O 签名：`scripts/sign-macho.py`

给 arm64 静态 Mach-O 打上 XNU 能加载的极简 ad-hoc 签名。

```bash
python3 <workspace>/scratch/sign-macho.py <macho> [identifier]
# 输出: <path>: <size> B, ncmds=9, signature=~412 B, magic OK
```

它做三件事（P-111）：
1. 删掉 `LC_DYLD_INFO_ONLY`（静态可执行里无意义，48 B）
2. `sizeofcmds += 16` 为 `LC_CODE_SIGNATURE` 留槽
3. 手写 `CodeDirectory(0x20400)` + `SuperBlob(0xFADE0CC0)` 追加到尾部

**不要用**：
- `codesign`（任何参数都产出 19 KB + ncmds=10 → 启动 panic）
- `ldid-lite.py`（逻辑对，但要求现成 16 B 空位，clang 产物没有）

---

## `userland/libmini/mini.h` 提供什么（写 init 前必查）

| 类别 | 可用 | **不可用** |
|---|---|---|
| 字符串 | `strlen` `strcmp` `strncmp` `strcpy` `strchr` | **`snprintf` `sprintf` `strcat` `strlcpy` `strlcat`** |
| 内存 | `memcpy` `memset` `bzero` | — |
| 文件 | `open` `close` `read` `write` `unlink` `mkdir` `chmod` `chown` `stat` `lstat` `getdirentries` | — |
| 挂载 | `mount(type, dir, flags, data)` | — |
| 常量 | `O_RDONLY` `O_WRONLY` `O_CREAT` `S_IFMT` `MNT_RDONLY` `SEEK_SET` | **`O_TRUNC` `S_IFREG` `S_IFDIR` `SEEK_CUR`** |

**拼路径要自己写**（P-112）：
```c
static void join_path(char *out, size_t cap, const char *dir, const char *name) {
    size_t d = strlen(dir), n = strlen(name);
    if (d + 1 + n + 1 > cap) { out[0] = 0; return; }
    memcpy(out, dir, d); out[d] = '/';
    memcpy(out + d + 1, name, n); out[d + 1 + n] = 0;
}
```
**判文件类型**：`(st.st_mode & S_IFMT) == S_IFREG` → 用 `S_IFMT` + 字面量
`0100000`（`S_IFREG` 未定义时）或自定义 `#define S_IFREG_ 0100000`。

---

## init 段表检查（★27，每次改 init 必跑）

```bash
python3 - init-signed <<'PY'
import struct, sys
d = open(sys.argv[1],'rb').read()
n = struct.unpack_from('<I', d, 16)[0]; off = 32
for _ in range(n):
    c, s = struct.unpack_from('<II', d, off)
    if c == 0x19:
        seg = d[off+8:off+24].split(b'\x00')[0].decode()
        fo, fs = struct.unpack_from('<QQ', d, off+40)
        if seg in ('__TEXT','__DATA','__LINKEDIT'):
            print('%-12s fileoff=%-6d filesize=%-6d' % (seg, fo, fs))
    off += s
PY
```

**`__TEXT` 必须 ≤ 16384。** 超了就是"日志 0 字节 + 自动复位"。
可用余量约 600 B（35.5 KB 版已占 15,751/16,384）。

---

## track-upstream-branches.py — 上游全分支追踪（★32）

```bash
python3 <workspace>/scripts/track-upstream-branches.py           # 报告 + 更新状态
python3 <workspace>/scripts/track-upstream-branches.py --dry-run # 只报告
python3 <workspace>/scripts/track-upstream-branches.py --json    # 机器可读
```

做三件事：强制全分支 refspec、`fetch --all --prune`、与
`.upstream-branches.json` 对比 SHA。

输出 `[新分支]` 或 `[更新]` 并列出提交。已接入 `sync-all-repos-v2.sh`。
