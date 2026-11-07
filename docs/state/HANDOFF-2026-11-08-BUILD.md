# HANDOFF — 进系统构建状态（2026-11-08）

## 目标
进系统（launchd 不再 SIGSEGV，SpringBoard 常驻）。

## 已完成
1. `patches/xnu/0391-k60-embedded-init.patch` — 内核内嵌 49,424 B init-stub，写 `/private/var/pong/init`（vnode_open + vn_rdwr + current_proc）。
2. `patches/xnu/0392-k60-weak-scanout-stubs.patch` — 三个 `__attribute__((weak))` scanout 符号，避免 bootstrap 链接找不到。
3. 用户态 `init-stub2.c`（无 libmini、raw svc）已编译 49,424 B，逻辑：mkdir boot-jobs/empty-xpc → 复制 stock LaunchDaemons（过滤 webBookmarks）→ bindfs 到 `/System/Library/LaunchDaemons` 与 `/System/Library/xpc` → exec `/sbin/launchd.ios`。
4. `k60_init_blob.h`（262 KB C 数组）在 `E:/k60-work/scratch/`。
5. ADT 触摸坐标修复已推送（`3ace22d`）。
6. TWRP 入口与 Windows-git 铁则已写入 `docs/state/`（`f09f360`）。

## 当前卡点
`unixnu build kernel` 在 bootstrap 阶段失败；`build-0392b.log` 无 sha，最近错误未捕获。
之前失败原因依次为：GPU `_pong_scanout_*` 未定义 → 子模块 `VerifiedRoot` 被杀 → 待查（0391/0392 是否应用成功未知）。

## 下一轮检查（按顺序）
```bash
L=/opt/k60/trees/k60build/out-baseline/mondrian/ipados-16.6.1-20G81/mondrian/logs/kernel-bootstrap.log
grep -nE '== kernel: patch 0391|== kernel: patch 0392' /tmp/build-0392b.log
grep -nE 'error:|Undefined symbols' "$L" | tail -10
tail -20 "$L"
```

## 若 0392 未生效
把 weak 定义放进新文件 `iokit/Kernel/k60_scanout_stubs.cpp` 并在 `bsd/conf/files` 增加一行（需要重新生成 patch 并在 series 中位于 0392 之前）。

## 设备
`6033dbec  recovery`（TWRP 已进入；进 TWRP 用 `fastboot reboot recovery`）。

## 构建命令
```bash
cd /tmp/k60build
./unixnu build kernel -D /tmp/usb-cdc-mainline/device --out /opt/k60/trees/k60build/out-baseline \
  --kernelcache /mnt/e/hackios/UniXNU/out/ipsw/20G81/kernelcache.decompressed
```
