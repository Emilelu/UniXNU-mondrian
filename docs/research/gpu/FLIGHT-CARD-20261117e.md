# 上机卡 2026-11-17e：把 addons 挂到 `/System/Library/Extensions`，让 Metal 发现插件

- 镜像标签：`gpu-addonmount-20261117`
- 分支/提交：`feat/gpu-metal-hw` @ 本卡之后的代码提交
- 新增 boot-arg：`gpu-addon=1`（`ALLOWED_ADDITIONS` 内的实验项；命令行 30→31 项、594→606 B，上限 607）

## 1. 目的

`gpu-loadmark-20261117` 已证明插件被 dyld 装进 backboardd（`:1288 Pong Metal: plugin loaded`），
但从未被实例化。读源码后确认设备发现路径是：
`PongAdrenoAccelerator.cpp:45` 给 IOService 设 `MetalPluginClassName=PongAdrenoMetalDevice`
→ Metal 框架到 **`/System/Library/Extensions/<name>.bundle`** 找插件
（`NativeAdrenoAccelerator.cpp:3` 注释、`drivers/PongMetal/README.md:19`）。

而 `zzy-native-gpu-addon-mount.patch` 正是把 `/private/var/ngpu/addons` 联合挂到
`/System/Library/Extensions` 的那一步 —— 它由 boot-arg 控制，**我们的命令行从来
没有这个参数**，所以挂载从未发生，`/System/Library/Extensions/PongAdrenoMetal.bundle`
不存在，Metal 自然找不到设备类。

本轮只做两件事：把该 boot-arg 改名成能放进 607 B 的 `gpu-addon=1`
（原名 `sheng-gpu-addon=1` 需 19 B，命令行只剩 13 B），并在挂载后打印一行结果。

## 2. 前提证据（上机前已具备）

| 类别 | 证据 |
| --- | --- |
| 静态 | `scripts/check-patch-apply.py` ✅（改名与新增打印后仍逐 hunk 可应用） |
| 单元 | `scripts/tests/test-metal-plugin-load-marker.py` 6/6 ✅；`scripts/tests/test-check-image-args.py` 全过（`gpu-addon` 已进 `ALLOWED_ADDITIONS`） |
| 产物 | `verify-boot-image: OK`；`image-arg-audit: OK (31 arguments, 606 bytes)` |

## 3. 抓取

- 复用 `scripts/flash.sh <boot.img> 240`，证据落 `E:/k60-work/evidence/usblog-<ts>/`。

## 4. 判据

### 成功判据（全部满足才算通过）

- **S1** 内核无异常：`K60KEXC` 出现 0 次（banner 不计）。
- **S2** 挂载成功：出现 `K60GPUADDON addons stage=5 status=0 daemons …`。
- **S3** 插件被实例化：出现 `Pong Metal: real Vulkan-backed device created`。
- **S4** 出帧：出现至少一行 `present #`。

### 失败判据（任一命中即 FAIL，并写明哪一条）

- **F1** 出现 panic / `K60KEXC`（除 banner）。
- **F2** 没有 `K60GPUADDON` 行：`native_gpu_addon_prepare()` 没被调用，或 boot-arg 没生效。
- **F3** 有 `K60GPUADDON` 但 `stage<5` 或 `status!=0`：联合挂载被拒（记录 stage/status 数值）。
- **F4** 挂载成功但没有 `real Vulkan-backed device created`：设备发现仍缺一环，
  下一步查 Metal 框架对 `/System/Library/Extensions` 的扫描时机与 `MetalPluginClassName` 的读取方。

## 5. 结果登记

（上机后填写。）
