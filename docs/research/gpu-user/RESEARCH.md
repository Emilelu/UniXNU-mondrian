# gpu-user 线研究记录：Metal 插件部署链

分支 `feat/gpu-user`（树 `/mnt/e/hackios/k60-gpu-user`），2026-11-14。
目标：让 `MTLCreateSystemDefaultDevice()` 返回设备，使合成器不再走 CPU 软件路径。

现状前提（已核实，不属于本线工作）：

- 内核侧 Adreno 22 步序列全部 result=0，GPU 硬件 bring-up 是好的
  （`PONG ADRENO: startup COMPLETE; hardware armed result=0 a=0x40000007 b=0x20010000`，
  `docs/engineering/STATUS.md:227`）。
- 用户态判 software-only 的唯一条件是 `MTLCreateSystemDefaultDevice()` 返回 nil
  （`userland/ui_compat.c:510`，dlsym 在 `:497` 与 `:508`）。
- 缺口在**插件文件部署**，不在内核 GPU 栈：`docs/engineering/STATUS.md:240-250`。

---

## ① 同型（same_model）

同型号 mondrian 的官方记录（unixnu.com/devices/mondrian-mzyxsl）GPU 从未出帧，
本移植的内核侧已超过该状态；用户态插件装载在参考实现里走的是
`MetalPluginName` → `/System/Library/Extensions/<name>.bundle` 这条固定路径，
本线沿用它。

## ② 官方（official）

官方 GPU 移植指南 https://unixnu.com/zh/porting/gpu 第四节要求把 Metal bundle 放进
系统扩展目录供发现；官方 AdrenoMetal 组件（`drivers/AdrenoMetal`，revision 454ff2ce）
同样是「插件被发现 → metal2vulkan 转发」的架构。本线不改架构，只补部署。

## ③ 反编译 / 真机取证（decompile）

真机日志 `/mnt/e/k60-work/evidence/usblog-20261114-150931/console.log`：

```
479: K60UILIB deploy bytes=113904 resid=0 error=0
480: K60METAL open /private/var/ngpu/addons/PongAdrenoMetal.bundle/Info.plist error=20
481: K60METAL deploy files=0/6 error=20
484: K60DATA mkdir ok=1/36 [ ... ngpu=17 ngpu/addons=17 ngpu/daemons=17 ... ]
```

三条读法：

1. `:479` 证明 `vnode_open + vn_rdwr` 写文件这套机制在 prepare 时机是好的。
2. `:480-481` 的 error=20 是 `ENOTDIR`：`PongAdrenoMetal.bundle` 被建成了**普通文件**，
   所以往它下面开 `Info.plist` 报「不是目录」。
3. `:484` 的 `K60DATA mkdir ok=1/36` 里 35 项是 EEXIST(17)——**mkdir 系统调用在同一点可用**，
   这正是 0398 的做法。

装载门禁（用户态，不在本线改动范围，但决定判据）：
`PongMetalPlugin.mm:165-192` 要求 `PongAdrenoMetal.publish` 与 `.clients`
都是普通文件、`st_uid==0`、`st_mode & 022 == 0`，publish 首字符为 `1`，
clients 逐行匹配 `getprogname()`；否则 `selectedClient()` 返回 false。

## ④ 广域（wide）

- mkdir 正宗模式：`patches/xnu/0398-k60-pong-runtime-directories.patch:5-18`
  往 `k60_mkdir_paths[]` 追加 `/private/var/ngpu`、`/addons`、`/daemons`；
  真正的 mkdir 循环在 0239/0215 引入，形如
  `copyout(path, scratch + 0x400, len + 1)` → `struct mkdir_args{path,mode}` →
  `mkdir(p, &args, &ret)`。
- 补丁锚点漂移：`zzy-native-gpu-addon-mount.patch` 被 `bf487cc` 移出 series，
  `git apply --check` 失败、`-C0` 才过 → 与 P-155
  （`docs/engineering/PITFALLS.md:3857`）同型，必须 `diff -u` 重新生成。
- 构建侧只认 series：P-190（`docs/engineering/PITFALLS.md:4441`）说明不在 series 的补丁
  会被静默跳过，这正是内核里 `native_gpu_addon_mount` 符号数为 0 的原因。

## ⑤ 方案（plan）

1. **修 `k60_metal_mkdir`**（`patches/xnu/0610-k60-metal-plugin-deploy.patch`）：
   放弃 `vnode_open(path, O_CREAT, 0755, ...)`（它建普通文件），改为
   `copyout(path, scratch + 0x400, len)` + `struct mkdir_args` +
   `mkdir(p, &args, &ret)`，EEXIST 视为成功；`k60_metal_deploy` 签名改
   `(proc_t p, user_addr_t scratch)`，由 `native_owner_data_prepare` 传入。
   上一版 `vnode_open(O_CREAT)` 误建的普通文件会挡住 mkdir，所以同一函数先用
   `unlink(p, &remove_args, &removed)` 清掉它并打印
   `K60METAL removed a stale file at …`。
   补丁行号：`:75` 签名、`:79` `scratch + 0x400`、`:88` copyout、`:99` unlink、
   `:105` mkdir、`:113` deploy 签名、`:137-140` 四个固定目录、`:196` 逐 `/` 前缀。
2. **保持 kern_exec.c 净 +9 行不变**（P-155）：0610 的 hunk 是
   `@@ -7820,8 +7820,17 @@`，只把 `extern` 与调用两行文本改成带参数版本
   （`:250`/`:252`）。0614 的 hunk 上下文逐字依赖这两行，其 hunk 为
   `@@ -7832,6 +7832,19 @@`，行号由 `diff -u` 算出而非手写。
3. **zzy 补丁重锚并入 series**：在「223 条中除 0610/0614 外全部应用」的树上，
   先 `git apply -C0` 应用旧 zzy，再逐文件 `diff -u` 生成新 zzy（168 行）。
   上游 `feat/gpu-yibiya` 合并后它落在 `patches/xnu/series:215`（0398 之后、0600 之前），
   而它改的 `osfmk/kern/startup.c` 与 `bsd/miscfs/bindfs/*` 的上下文补丁在
   series:26/49/54，都在它之前，故安全。
4. **打开开关**：`board.toml` 加 `sheng-gpu-addon=1`（zzy 的唯一运行时开关，
   `patches/xnu/zzy-native-gpu-addon-mount.patch:69`），并把 `pong_metal` 从 2 改成 1
   （P-144：`drivers/PongAdreno/PongAdrenoNativeGlue.cpp:30,44` 只在 ==1 时发布
   accelerator）。字节预算：30 项 593 B ≤ 608（`scripts/check-image-args.py:40` 用 607）。

## ⑥ 深挖（deep）

- `mkdir1at` 是 static（`bsd/vfs/vfs_syscalls.c:9827`），外部不可调用；
  `mkdir()` 包装（`:9988`）硬编码 `UIO_USERSPACE`，所以必须把路径 copyout 到**目标进程**
  的地址空间——这决定了 `k60_metal_deploy` 必须收 `proc_t p` 与 `scratch`。
- `scratch` 只有 1 页（`bsd/kern/kern_exec.c:8448-8452`，
  `mach_vm_allocate_kernel(map, &scratch_addr, map_page_size, ...)`，arm64 页 16 KB）。
  已占偏移：0x100-0x200（mount_args）、0x400（0398 的 mkdir 名字区，本线沿用）、
  0x400/0x600（zzy 的两次 union 挂载，每次占 offset..offset+0x100+size）、
  0x600-0x900（0600/0602 等路径与 body 区）。1 页 16 KB 内仍有 0xC00 以上的余量，
  但本线按 0398 的同型写法复用 `scratch + 0x400`（同一步骤内串行，不重叠）。
- 放弃 `VNOP_MKDIR` 手工 `componentname` 路线（先例 `bsd/vfs/vfs_xattr.c:1100-1185`）：
  include 依赖重、未上机验证；syscall 路线已被 0398 真机实证。
- `PongMetalPlugin` 的 `selectedClient()` 只认 `/System/Library/Extensions` 与
  `/private/var/pong` 两个目录；前者是 sealed 只读卷，所以必须有 zzy 的
  `MNT_RDONLY|MNT_UNION` bindfs overlay（`zzy` `:74`/`:78`）。
- zzy 挂载失败不 panic，只写 `native_gpu_addon_stage`/`native_gpu_addon_status`
  全局变量（`docs/plans/GPU-ENABLE-PLAN.md:540`）→ **串口日志看不到挂载结果**，
  判据只能靠后续 `Pong Metal:` 行。

## ⑦ 验证（verify）

本地（不刷机）能证明的：

- 干净 clone（xnu feed `1b191cb58250`）按 series 逐条 `git apply`：224/224 全过；
  重锚后的 zzy 单独 `git apply --check` rc=0，旧 zzy 在同树 rc=1（证明重锚必要）。
  这套改动已随上游 `feat/gpu-yibiya` 合入 main（0610 254 行、series 224 条、zzy 在
  `series:215`），本线不再重复携带。
- 终态断言：`bsd/dev/k60_metal.c` 含 `mkdir(p, &args, &ret)`、不含
  `vnode_open(path, O_CREAT, 0755`；`kern_exec.c` 含
  `native_gpu_addon_prepare(p, scratch)` 与 `(void)k60_metal_deploy(p, scratch)`；
  `bindfs.h` 含 `BINDM_FORCE_ROOT`。
- 仓库门禁：`scripts/check-patch-apply.py` ✅（P-162 四种翻车形状）；
  `scripts/check-boot-args.py` ✅ 30 config / 42 documented；
  `scripts/check-metal-blob.py` ✅（P-196：容器长度必须含 body 间 `.p2align 3` 填充，
  真机症状是 `deploy files=5/6 error=22` + `entry 5 body out of range`）。

只有上机能证明的：`K60METAL deploy files=6/6 error=0`、`MTLCreateSystemDefaultDevice`
非 nil（不再打印 `software-only platform`）、`Pong Metal: real GPU scanout worker ready status=0x0`。
P-196 之后还要确认不再出现 `K60METAL entry 5 body out of range` 与 `removed a stale file` 的循环重试。

## ⑧ 上机（device）

**未执行。** 用户铁则：禁止自行 boot；镜像就绪后交 Lead，由 Lead 在用户明确同意后执行。
构建与产物检查完成后在此补：tag、`boot.img` sha256、串口日志目录与关键行号。

上机判据（成功）：

1. `K60DATA mount returned error=0`
2. `K60METAL deploy files=6/6 error=0`（不再是 0/6 error=20）
3. `PONG METAL: real IOAcceleratorES provider published for20G81 discovery`
4. `Pong init: native Metal entry enabled for backboardd`
5. `Pong Metal: real GPU scanout worker ready status=0x0`
6. 日志中不再出现 `software-only platform`

失败分支：

- 仍 `deploy files=0/6 error=20` → mkdir 修复没进内核（查 series/device input 同步）。
- deploy 6/6 但无 provider published → `pong_metal` 不是 1，或
  `PongAdrenoCPReady`/`PongMetal20G81Enabled` 未置位（`PongMetalPlugin.mm:88-89`）。
- provider published 但 `selectedClient()` 拒绝 → publish/clients 的属主或 mode 不对
  （`PongMetalPlugin.mm:165-192`）。
- 只有 deploy 6/6、后续 `Pong Metal:` 行全缺 → overlay 没挂上（stage/status 全局变量，
  串口不可见），查 `sheng-gpu-addon=1` 是否真的进了 payload 的 `unixnu.toml`（P-159）。
