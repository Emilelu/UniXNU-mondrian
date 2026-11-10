# K60 iOS16 内核构建配方（2026-11-08 验证成功）

## 产物
```
kernel.macho  53,628,928 B
sha256        a1b82ecb6326dab646da4db613d18788185363eb2bafe346a459f4a491defb84
位置          /opt/k60/trees/k60build/out-baseline/mondrian/ipados-16.6.1-20G81/mondrian/kernel/kernel.macho
```

## 唯一验证成功的配置组合

| 项 | 值 | 为什么 |
|---|---|---|
| patch 顺序 | **黄金 `xnu-patches.list`（191 条）+ 0391 追加** | `offline-owner-systemos-mount` 必须在 `pong-init-scratch-allocation`(53) 和 `pong-hackios-userland-abi`(54) 之后；文件名字母序会排错 |
| GPU 平台 | **`XNU_PONG_ADRENO_PLATFORM=0`** | 走软件 framebuffer；`=1` 会 force_load Adreno 栈，缺 `armcpu_spi_attach`（`libArmCpu.a` 里不存在） |
| 0392 weak stub | **不启用** | GPU 关闭后不需要 |
| 0391 头文件 | 完整 262,739 B new-file 段落 | 之前只写了 3 行头，导致 `use of undeclared identifier 'k60_init_blob'` |
| feeds | 旧 `out/feeds/` 复制 + `origin` 指向本地 | WSL 直连 GitHub 被 403 限流 |
| DriverKit 头 | 复制旧 `.cache/sources/xnu-driverkit-*.json` | 同上，`prepare-xnu-source.py` 要访问 api.github.com |
| SDK 头 | 从旧 fakeroot 复制 `usr/include`（`Availability.h` 等） | 清 `tree/` 会连 fakeroot 一起删 |

## 构建命令
```bash
cd /tmp/k60build
setsid nohup env XNU_PONG_ADRENO_PLATFORM=0 ./unixnu build kernel \
  -D /tmp/usb-cdc-mainline/device \
  --out /opt/k60/trees/k60build/out-baseline \
  --kernelcache /mnt/e/hackios/UniXNU/out/ipsw/20G81/kernelcache.decompressed \
  > /tmp/build.log 2>&1 < /dev/null &
```

## 打包命令
```bash
# payload（这份配方自己的 args；见下面「29 项的来历」一节，它与黄金镜像不同）
./unixnu payload -D /tmp/usb-cdc-mainline/device --out <out> --uefi /mnt/e/hackios/uefi-mondrian \
  --kernel-arg pong_allow_unauthenticated_root=1 --kernel-arg debug=0x144 \
  --kernel-arg cs_enforcement_disable=1 --kernel-arg pong_software_keybag=1 \
  --kernel-arg disable_exc_resource=1 --kernel-arg pong_ufs_readwrite=1 \
  --kernel-arg k60_console_export=1 --kernel-arg k60_usblog=2 \
  --kernel-arg pong_data_mount=1 --kernel-arg pong_data_rw=1 \
  --kernel-arg fb_threads=3 --kernel-arg k60_textonly=1 \
  --kernel-arg amfi_get_out_of_my_way=1 \
  --kernel-arg pong_init_path=/private/var/pong/init \
  --kernel-arg epoch=1793709100 --kernel-arg k60_fontscale=3 \
  --kernel-arg k60_init_blob=1 \
  --trust-cache /mnt/e/hackios/UniXNU-mondrian/prebuilt/20G81-trustcache.bundle

# boot 镜像
./unixnu bootimg -D <device> --out <out> --uefi /mnt/e/hackios/uefi-mondrian \
  --dtb <uefi>/Platforms/Xiaomi/mondrianPkg/FdtBlob/sm8475-xiaomi-mondrian.dtb \
  -o boot.img
```

## 上机
```
boot-0601-goldenargs.img  202,362,880 B
sha256 0d3ed4fe37fa601ac985b4635405d2255e5c81551e59761e0f3f94aa79140893
fastboot boot boot-0601-goldenargs.img
```

## 「29 项」的来历，与黄金镜像的实测差异（2026-11-09 复测）

**这份配方打包出来的镜像实际是 19 项、`debug=0x144`，不是 29 项。** 用只读 FAT 目录链
解析 `boot-0601-goldenargs.img` 的 payload（`ANDROID!` 头 `ksize=1,027,600`、payload 在
偏移 1,032,192 起）得到的 `/EFI/UniXNU/unixnu.toml`：

```
751 B  args tokens: 19   debug=0x144
-v native-ufs=1 pong_allow_unauthenticated_root=1 debug=0x144 cs_enforcement_disable=1
pong_software_keybag=1 disable_exc_resource=1 pong_ufs_readwrite=1 k60_console_export=1
k60_usblog=2 pong_data_mount=1 pong_data_rw=1 fb_threads=3 k60_textonly=1
amfi_get_out_of_my_way=1 pong_init_path=/private/var/pong/init epoch=1793709100
k60_fontscale=3 k60_init_blob=1
```

（19 项里的 `k60_init_blob=1` 就是 0391 的内嵌 init，黄金镜像没有它，所以 28 + 1 = 29 是
**当时的口径**，不是镜像内容。`docs/state/LEDGER.md:100` 的「29 项」沿用了这个口径。）

**黄金镜像 `boot-0442/0461-20261107.img` 实测是 28 项、`debug=0x140`**（同样只读 FAT 解析，
payload 在偏移 552,960；三份 console 捕获逐字回显同一列表）：

```
972 B  args tokens: 28   debug=0x140
-v native-ufs=1 pong_allow_unauthenticated_root=1 debug=0x140 cs_enforcement_disable=1
pong_software_keybag=1 disable_exc_resource=1 pong_ufs_readwrite=1 k60_console_export=1
k60_usblog=2 pong_data_mount=1 pong_data_rw=1 fb_threads=3 k60_textonly=1
amfi_get_out_of_my_way=1 pong_init_path=/private/var/pong/init epoch=1793709100
k60_fontscale=3 k60_skip_firmware_mount=1 k60_tolerate_cache_loader=1
launchd_unsecure_cache=1 xpcproxy_idversion=1 applog=1
applog_name=runningboardd,backboardd,lsd k60_entitlement_allow=1 k60_skip_iosurface=1
k60_panic_reset=1 k60_selftest_reboot=300
```

**逐项差异（19 项 → 28 项多了 10 项，少了 1 项）：**

| 项 | 0601（19 项） | 0442/0461（28 项） | 影响 |
|---|---|---|---|
| `debug` | `0x144` | `0x140` | `0x144` 含 `DB_NMI`，panic 卡在调试器里不复位；`0x140` 才走 0331/0334 的 IMEM `0x146AA65C=0x77665500` 自动回 fastboot（`docs/state/LEDGER.md:129-130`） |
| `k60_skip_firmware_mount=1` | ✗ | ✓ | launchd mount-phase bind mount 报 EPERM → PID 1 panic |
| `k60_tolerate_cache_loader=1` | ✗ | ✓ | `launchd_cache_loader` 崩溃被当成致命 |
| `k60_panic_reset=1` | ✗ | ✓ | panic 后不自动回 fastboot，要手动长按电源 |
| `k60_selftest_reboot=300` | ✗ | ✓ | 150 次 2 秒心跳后自复位回 fastboot（坑 133） |
| `launchd_unsecure_cache=1` | ✗ | ✓ | 内核不识别，无害；缺它时 launchd 读 cache 路径更严 |
| `xpcproxy_idversion=1` | ✗ | ✓ | xpcproxy 版本检查放宽 |
| `applog=1` | ✗ | ✓ | 用户态 applog 采集 |
| `applog_name=runningboardd,backboardd,lsd` | ✗ | ✓ | applog 只采这三个进程（args 预算，坑 124） |
| `k60_entitlement_allow=1` | ✗ | ✓ | 无 AMFI 时放行 entitlement |
| `k60_skip_iosurface=1` | ✗ | ✓ | 跳过 IOSurface duplicate class 卡点 |
| `k60_init_blob=1` | ✓ | ✗ | 0391 内嵌 init；黄金镜像用设备上 dd 写入的 init，**不需要它**，而且它的 `O_TRUNC` 会破坏那个 init（`docs/state/LEDGER.md:246` 坑 10） |

结论：**`boot-0601-goldenargs.img` 不是「带 golden args」的镜像**——它的文件名与内容不符，
19 项里的 `debug=0x144` 与坑 12 的硬规矩冲突。要用能上机的 args，请用 `boot-0442` 或
`boot-0461` 的 28 项 `debug=0x140`，`board.toml` 的 `[payload] kernel_args` 已按它改齐。

此外两代镜像的 boot 布局也不同（`ksize` 548,774 / payload@552,960 与 1,027,600 /
payload@1,032,192），`unixnu bootimg` 产出的头与能启动的布局不一致，见
`docs/state/LEDGER.md:135-143`。

## 关键教训（都是本会话实际踩的）

1. **两个仓库必须同步**：改 `E:\hackios\UniXNU-mondrian` 的 series 不会影响构建，构建读 `/tmp/usb-cdc-mainline/device`。这是本会话最长的弯路。
2. **清 `tree/` 会丢 fakeroot**：SDK 头必须从旧树复制回来。
3. **`Availability.h` 不在 AvailabilityVersions feed 里**，要单独从旧 fakeroot 拿。
4. **WSL 直连 GitHub 会被限流 403**：feed 与 DriverKit JSON 都要用本地缓存。
5. **patch 顺序按黄金构建的 `xnu-patches.list`**，不是文件名字母序。
6. **docs 生成时 new-file 段落必须完整**：`+++ b/path` 后每一行都要加 `+`。

## 上机后的判据日志
```
K60INIT: embedded helper write=0        ← 内核写入 stub 成功
Pong init: loading helper /private/var/pong/init
Pong stub: alive
boot-jobs copied (webBookmarks filtered)
LaunchDaemons view ok
xpc view ok
→ exec /sbin/launchd.ios
```
