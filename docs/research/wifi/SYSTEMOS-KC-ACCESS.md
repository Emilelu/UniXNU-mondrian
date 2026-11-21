# 24A446 SystemOS 内核集合的解锁路径

Status: 可执行流程；C1/C2 仍未关闭。本文是给另一台机器上的人照着走的步骤，不是
「已经拿到 BootKernelExtensions.kc」的结论。2026-11-21 只完成了 AEA 解密，挂载与
提取没有完成，原因和原始报错见第 6 节。

## 1. 先读结论

要做的是把 24A446 的 SystemOS 层内核集合从
043-68526-711.dmg.aea 里取出来，再从集合里的 IO80211Family 和用户态的
/usr/sbin/wifid 找到 selector 0x3c30 / 容量 0x3c00 的调用链。它是
C1 的「24A446 真实调用者与信封」和 C2 的「launchd 启动的消费者与 ABI」的
共同输入，见 docs/plans/WIFI-IOS27-CHECKLIST.md:173-189。

目前能确定的文件身份：

| 项 | 值 |
| --- | --- |
| IPSW | /home/emilelu/ipsw/24A446.ipsw，12,314,041,166 B |
| 设备 | iPhone 16 Pro Max，iPhone17,2，D94AP，27.0.1 / 24A446 |
| SystemOS 成员 | 043-68526-711.dmg.aea，2,348,810,240 B |
| SystemOS 解密后 | 6,023,020,544 B，APFS 4096，卷名 Rave24A446.D94SystemCryptex |
| BuildManifest 声明 | Cryptex1,SystemOSSize = 5744 MiB |
| 根 OS 成员 | 043-69909-664.dmg.aea，8,858,370,048 B；解密后 10,223,616,000 B |
| AppOS 成员 | 043-69297-793.dmg，16,777,216 B |
| 内核缓存 | kernelcache.release.iphone17（不是 .kc，也不是本文目标） |

**不要**把根 OS 的 kernelcache 当成目标：它的 305 个 kext 里没有无线 kext；
**不要**把 7z 的「没列出 .kc」当成「不存在」：7z 对 APFS 只报
Unsupported method，必须挂载后再判断。

## 2. 在哪台机器上做

| 步骤 | Linux（本机 WSL） | macOS |
| --- | --- | --- |
| AEA 解密 | ipsw fw aea，已实测可用 | /usr/bin/aea decrypt，参考 UniXNU 的 ipsw.py |
| APFS 挂载 | 需要 apfs-fuse；没有就停在挂载前 | hdiutil attach，系统自带 |
| 读 .kc | apfs-fuse 挂载后 find | hdiutil 挂载后 find |
| 提取 kext | ipsw kernel kexts / extract | 同左 |
| 用户态 wifid | 需要从根 OS 或 dyld cache 取 | 同左 |

当前 WSL 有 ipsw 3.1.749、7z 23.01，没有 apfs-fuse、hdiutil、aea。
磁盘至少留 12 GiB：2.3 GiB AEA + 6.0 GiB APFS + 提取物。不要写 /tmp，
用 $WORK（例如 /home/emilelu/ipsw/24A446）。/tmp 会在下一次清理时消失。

## 3. macOS 路线（推荐）

~~~sh
export WORK="$HOME/k60/24A446"
export AEA="$WORK/043-68526-711.dmg.aea"
export IMG="$WORK/systemos/043-68526-711.dmg"
mkdir -p "$WORK/systemos" "$WORK/mnt"

# 1) 取 AEA 密钥并解密。--key 会访问 Apple 的 WKMS；需要网络，但不需要账号。
KEY=$(ipsw fw aea --key "$AEA")
/usr/bin/aea decrypt -i "$AEA" -o "$IMG" -key-value "$KEY"

# 2) 挂载。hdiutil 会打印实际卷名；确认是 Rave24A446.D94SystemCryptex。
hdiutil attach -readonly -nobrowse -mountroot "$WORK/mnt" "$IMG"

# 3) 找集合。找不到就停，不要把「没找到」改写成「不存在」。
find "$WORK/mnt" -name 'BootKernelExtensions*.kc' -print
~~~

如果 hdiutil 挂出多个卷，先看它打印的 /Volumes/... 或
$WORK/mnt/Rave24A446.D94SystemCryptex，再在对应卷上 find。

## 4. Linux 路线（本机可复跑）

~~~sh
export WORK=/home/emilelu/ipsw/24A446
export AEA="$WORK/043-68526-711.dmg.aea"
export IMG="$WORK/systemos/043-68526-711.dmg"
mkdir -p "$WORK/systemos" "$WORK/mnt"

# 1) 解密。ipsw 在 Linux 上用内置 Go AEA 实现，已实测输出 6,023,020,544 B。
ipsw fw aea "$AEA" --output "$WORK/systemos"

# 2) 挂载。没有 apfs-fuse 时，这一步的报错见第 6 节。
sudo apt-get install apfs-fuse
sudo apfs-fuse "$IMG" "$WORK/mnt"

# 3) 找集合。
find "$WORK/mnt" -name 'BootKernelExtensions*.kc' -print
~~~

如果不想用 apfs-fuse，可以试 ipsw 自带 mount：

~~~sh
ipsw mount sys "$WORK/24A446.ipsw" --device iPhone17,2 --mount-point "$WORK/mnt-ipsw" --detach
ls "$WORK/mnt-ipsw"
~~~

它是同一个 FUSE 依赖；没有 apfs-fuse 时同样失败，不要以为换命令就绕过。

## 5. 找到 .kc 之后

先列 kext，确认无线栈的 bundle 名；再提取。Bundle 名在不同版本可能变化，
所以先用 grep 查，不凭记忆写死：

~~~sh
KC=$(find "$WORK/mnt" -name 'BootKernelExtensions*.kc' -print -quit)
test -n "$KC" || { echo 'no .kc found; stop here'; exit 2; }

ipsw kernel kexts "$KC" -j > "$WORK/kexts.json"
grep -iE 'IO80211|AppleBCMWLAN|Airport|WLAN' "$WORK/kexts.json"

# 以实际列出的 bundle 名为准；下面是 24A446 上预期的常见名。
ipsw kernel extract "$KC" com.apple.iokit.IO80211Family -o "$WORK/kexts"
~~~

对提取出的 kext 做三件事，缺一不可：

1. llvm-nm 看它是否真的导出 selector 处理函数；
2. 在反汇编里定位 0x3c30 分支和 0x3c00 容量读取，记下文件、函数、偏移；
3. 在用户态 /usr/sbin/wifid 里找同一 selector 的发起处。

wifid 的启动项来自根 OS 的
System/Library/LaunchDaemons/com.apple.wifid.plist。该 plist 是 bplist，
Program 字段是 /usr/sbin/wifid，RunAtLoad 和 KeepAlive 为真，
POSIXSpawnType 为 Interactive；它还有 _LimitLoadToDeviceTree 和一组
com.apple.private.corewifi.* MachServices。7z 能读出 Program，但 7z 的
文件名列表里没有 /usr/sbin/wifid（它可能在 dyld shared cache 或被 APFS
视图隐藏），所以「launchd 说它在哪」和「实际能读到哪个文件」要分开记录。
不要把 plist 里的路径当成已提取的二进制。

## 6. 已经实测的失败（照抄，不要猜）

AEA 解密在 Linux 上成功；挂载和提取的失败原文如下。

没有 apfs-fuse 时，ipsw mount sys：

~~~text
failed to mount sys DMG: failed to mount /tmp/043-68526-711.dmg:
failed to find apfs-fuse: apfs-fuse not found in PATH or common locations:
Install apfs-fuse or set IPSW_APFS_FUSE_PATH environment variable.
(snap users: try 'sudo snap connect ipsw:system-files' if available)
~~~

ipsw extract --files --dmg sys 也走 FUSE；它会先把 SystemOS AEA 复制到
输出目录，然后去挂 AppOS，失败原文（临时目录名会变）：

~~~text
failed to extract files from AppOS 043-69297-793.dmg:
failed to IPSW FS dmg: failed to mount /tmp/ipsw_extract_dmg.../043-69297-793.dmg:
failed to find apfs-fuse: apfs-fuse not found in PATH or common locations:
Install apfs-fuse or set IPSW_APFS_FUSE_PATH environment variable.
~~~

把非 AEA 文件传给 ipsw fw aea：

~~~text
failed to parse AEA: invalid AEA header: found '????' expected 'AEA1'
~~~

7z 能打开 APFS 容器但只给出警告和部分视图：

~~~text
Open WARNING: Cannot open the file as [Dmg] archive; Type = APFS; Unsupported method.
~~~

它对 043-68526-711.dmg 列出 3,087 行 / 1,836 个文件，没有
BootKernelExtensions、KernelCollections 或 .kc。这个数字只能说明 7z 的
视图不完整，不能说明集合不存在；要挂载后再下结论。

## 7. 成功判据与停止条件

成功的最小证据链：

1. find 在挂载点上打印一个真实存在的 BootKernelExtensions*.kc；
2. ipsw kernel kexts 能列出至少一个无线相关 bundle（IO80211Family 或其
   24A446 的新名字），并且 extract 真的产生文件；
3. 处理函数里能定位 selector 0x3c30 / 容量 0x3c00，且 wifid 侧能定位
   同一 selector 的调用点；
4. 记录文件路径、kext bundle、函数名、偏移、二进制 sha256 和提取命令。

以下任一情况都停在 open：

- find 没有结果：说明 043-68526 这个视图里没有该 .kc，先记录实际卷名和
  文件列表，不要改写成「24A446 没有内核集合」，也不要转去 305-kext 的
  kernelcache 猜无线符号；
- 有 .kc 但 kexts 里没有无线 bundle：C1/C2 仍无消费者证据；
- 只有 16.6.1 或 22H374 的 wifid/IO80211：不能外推到 24A446；
- 只有 selector 常量、没有调用者：仍不能证明「关联前必须」。

## 8. 与 C1/C2 的关系

C1 要的是 24A446 真实调用者与 0x3c30/0x3c00 信封；C2 要的是 launchd
启动的消费者与 Apple80211 ABI 是否真走到那条路。本文只负责把两个二进制
取到可读状态。取到后：

- 在 IO80211Family 里找 selector 0x3c30 的 handler，确认 +8 的容量
  0x3c00 和 +0x3c08 的 40 字节请求是不是同一信封；
- 在 wifid 里找发起 selector 的调用点，确认它在关联前还是扫描后；
- 把证据写进 docs/research/wifi/IOS27-STATION-API-GAP.md 的 C1/C2 行，
  不要写进站归档的验收（站归档只认 scripts/check-wifi-station-archive.py）。

## 9. 不要做的事

- 不要用 7z 的「没有 .kc」当结论；
- 不要把 043-69909-664 根 OS 的 DriverKit WLAN 框架当成 IO80211Family
  内核驱动；它们是 DriverKit，和 kext 的 selector 不是同一条路径；
- 不要在 /tmp 里留下解密镜像；
- 不要为了拿这个文件去改共享 main、构建内核或上机；
- 不要把 AEA 密钥、Apple 账号、Mac 地址或密码写进仓库。
