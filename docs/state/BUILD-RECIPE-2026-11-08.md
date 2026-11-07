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
# payload（args 必须与黄金镜像一致，只多 k60_init_blob=1）
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
