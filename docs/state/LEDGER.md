# K60 进系统 · 压缩后必读账本

> 这份文件的唯一用途：**上下文被压缩后，第一眼读完它就能回到正确的状态**。
> 只写四类内容：已验证事实、已排除的假设、硬规矩、当前阻塞。
> 不写过程叙事。每轮结束更新。

---

## 一、硬规矩（违反过一次就会重犯旧错）

1. **只改 patch 文件，绝不手改 `tree/.cache/xnu-work/`**
   `tree/.cache/xnu-work` 是生成物。直接编辑会在下一次清树重建时丢失。
   我犯过：手改 `kern_exec.c` 补 `init_envp`、手改 `MiniIOSurface.cpp` 换 `reinterpret_cast`、手写 `k60_init_blob.h` —— 全部在重建后丢失并再次报错。

2. **两个仓库必须同步**
   - 构建读：`/tmp/usb-cdc-mainline/device`
   - Git 跟踪：`E:/hackios/UniXNU-mondrian`
   改 E 仓不影响构建；改 D 仓不入库。`0391` 曾来回同步 6 次以上。

3. **一次只改一个变量**，构建后固定输出三个判据再上机：
   - `patches applied` = 192
   - `ArmDTPlatform` 字符串数 = 38
   - `K60INIT` 字符串数 = 1

4. **禁止清 `tree/.cache/fakeroot`**；SDK 头丢失后从
   `/opt/k60/trees/k60build/out/mondrian/.../tree/.cache/fakeroot` 或 out3 复制
   （`Availability.h` 不在 AvailabilityVersions feed 里）。

5. **WSL 直连 GitHub 会被 403 限流**：feed 用本地缓存，DriverKit 用
   `.cache/sources/xnu-driverkit-*.json` 缓存。

6. **Git 提交/推送必须用 Windows git**，WSL 里的 git 永远推不上去。

7. **禁止 `fastboot flash`**，只用 `fastboot boot`。TWRP 已集成在 boot 镜像，用 `fastboot reboot recovery` 进入。

---

## 二、已验证事实（不要再重新推导）

### panic 解码
| 输出 | 含义 | 出处 |
|---|---|---|
| `namespace 9` + `code 0x1` | `OS_REASON_EXEC` + `EXEC_EXIT_REASON_BAD_MACHO` | `bsd/sys/reason.h:96,244` |
| `namespace 3` | `OS_REASON_CODESIGNING`（**不是** 9，我曾误判） | `reason.h:90` |
| `Unable to find driver for this platform: "J120AP"` | `IOPanicPlatform` 兜底，说明 `ArmDTPlatform` 未链入 | `IOPlatformExpert.cpp:2318` |

### 内核写文件的正确写法（照抄 `0340-k60-uilib-deploy.patch:7001-7013`，设备上已验证可用）
```c
ctx = vfs_context_current();
error = vnode_open(path, O_CREAT | O_WRONLY | O_TRUNC, 0644, 0, &vp, ctx);
error = vn_rdwr(UIO_WRITE, vp, (caddr_t)blob, (ssize_t)len, 0,
                UIO_SYSSPACE, IO_SYNC, vfs_context_ucred(ctx), &resid, current_proc());
vnode_close(vp, 0, ctx);          // <-- 必须是 0
```
**`vnode_close(vp, FWRITE, ...)` 会导致 `vnode_rele_ext kusecount 不平衡` panic**
（`vfs_subr.c:2693-2694`）。我曾用 `FWRITE` + `IO_SYNC|IO_NOCACHE` + `NOCRED`，触发 panic。

### init 必须的 Mach-O 形态（XNU `load_machfile` 接受的）
```
MH_EXECUTE, flags=0x1(NOUNDEFS)    不能有 DYLDLINK，不能有 LC_LOAD_DYLINKER
__PAGEZERO vmaddr=0 vmsize=0x100000000      (mach_loader.c:655 硬性要求 4 GiB)
LC_UNIXTHREAD 提供入口（不是 LC_MAIN）
LC_CODE_SIGNATURE 存在
```
参照物：`E:/k60-work/deliverables/pong-init/init`（35,160 B，pong 真实 init）。

### 我们的 stub 为什么曾被 `BAD_MACHO` 拒绝
`init-stub3`（我手工 clang 编的）：`flags=0x200085` = `DYLDLINK|TWOLEVEL|PIE`，
含 `LC_LOAD_DYLINKER`，无 `LC_CODE_SIGNATURE`。
原因：`ld64.lld 18` 的 `-static` **未实现**（`warning: Option '-static' is not yet implemented`），
产物只能是动态链接。**这条路走不通，不要再用手工编译的 stub。**

### 构建配方（唯一验证成功的组合）
```
cd /tmp/k60build
./unixnu build kernel -D /tmp/usb-cdc-mainline/device \
  --out /opt/k60/trees/k60build/out-baseline \
  --kernelcache /mnt/e/hackios/UniXNU/out/ipsw/20G81/kernelcache.decompressed
```
- patch 顺序 = 黄金 `xnu-patches.list`（191 条）+ `0391` 追加（共 192）
  不可用文件名字母序：`offline-owner-systemos-mount` 必须在
  `zzzzzz-pong-init-scratch-allocation` / `zzzzzzz-pong-hackios-userland-abi` 之后
- `.config`：`CONFIG_XNU_ARM_DT_PLATFORM=y`、`CONFIG_XNU_ARMCPU=y`、
  `CONFIG_XNU_PONG_ADRENO_PLATFORM=y`（与黄金完全一致，**不要改**）
- 构建脚本中**必须存在**两行（我曾误删，导致 `ArmDTPlatform` 不链接）：
  ```bash
  EXTRA_MAKE_ARGS+=("LD_KERNEL_ARCHIVES=$KERNEL_EXTRA_ARCHIVES")
  EXTRA_MAKE_ARGS+=("LD_KERNEL_ARCHIVES=$PLATFORM_ARCHIVES")
  ```

### boot args（与黄金镜像一致，仅多最后一项）
```
-v native-ufs=1 pong_allow_unauthenticated_root=1 debug=0x144
cs_enforcement_disable=1 pong_software_keybag=1 disable_exc_resource=1
pong_ufs_readwrite=1 k60_console_export=1 k60_usblog=2
pong_data_mount=1 pong_data_rw=1 fb_threads=3 k60_textonly=1
amfi_get_out_of_my_way=1 pong_init_path=/private/var/pong/init
epoch=1793709100 k60_fontscale=3 k60_init_blob=1
```
**缺 `k60_usblog=2` → CDC console 不枚举，设备静默。**
**`board.toml` B decision：不要传 `--trust-cache`**（多出 `kernel.macho.trustcache` + ADT 里多 `TrustCache` 节点，与黄金不符）。

### boot 镜像格式（`unixnu bootimg` 产出的**不可用**）
```
正确布局（取自 boot-0461，实测能启动）:
  [0,4096)        ANDROID! 头，u32@8 = kernel_size = 548,774，u32@16 = ramdisk_size = 0
  [4096,552960)   kernel 区（BootShim + UEFI FD + dtb）
  payload 放在偏移 552,960 起（header 不声明 ramdisk_size）
```
`unixnu bootimg` 会把 `ksize` 写成 1,027,600，payload 落到 UEFI 找不到的偏移 → 设备静默。
用 `splice4` 方式：保留模板 header/kernel 区，替换 552,960 起的 payload。

---

## 三、已排除的假设（别再试）

| 假设 | 为什么错 |
|---|---|
| "AMFI 拒绝未签名 init"（Round 15） | `namespace 9` 是 `OS_REASON_EXEC`，不是 CODESIGNING |
| "stub 缺 4 GiB pagezero"（Round 17） | 实测 stub **有** `__PAGEZERO vmsize=0x100000000` |
| "把 `PONG_ADRENO_PLATFORM` 从 1 改 0 能修 panic" | 黄金本身 `.config` 里就是 `=y`，ADRENO 不是变量 |
| "改 boot-args 能修" | 当前 panic 发生在 `stage=4` 之后、`loading helper` 之前，即写文件内部 |
| "用 `--trust-cache`" | `board.toml` 明确写 B decision 要 drop（与 pong 对齐） |

---

## 四、当前状态与阻塞

### 已确认可用
- 内核构建链（192 补丁，`ArmDTPlatform=38`，`K60INIT=1`）
- Data 卷挂载全成功：`K60DATA mount returned error=0 rw=1`、
  `K60UFS write#0..#7` 全 `result=0`、`K60UILIB deploy bytes=111328 resid=0 error=0`、
  `K60DATA mkdir ok=1/28`（全 EEXIST，正常）、
  `keybag/launchd policy/boot preferences err=0`、`attempt returned error=0 stage=4`
- CDC console 能枚举（COM5，VID_1209/PID_0001）

### 当前阻塞（Round 19 实测）
日志停在 `K60DATA attempt returned error=0 stage=4` 之后，**没有** `Pong init: loading helper`，
说明 panic 发生在 `k60_install_embedded_init()` 内部（写文件），即 `vnode_rele_ext kusecount` 不平衡。

**已做的修复（待验证）**：`0391` 已按 `0340` 的写法重新生成
（`vnode_close(vp, 0, ctx)` / `IO_SYNC` / `vfs_context_ucred(ctx)` / 带 `resid`），
`patches/xnu/0391-k60-embedded-init.patch` = 195,757 B，2 hunks。

### 设备侧重要事实
- **设备上的 `/private/var/pong/init` 曾被我的 0391（`O_TRUNC`）覆盖成坏 stub，现已损坏**
- 所以修复后的镜像**必须带 `k60_init_blob=1`** 才能把正确的 pong init 写回去
- 旧 pong init（35160 B）在 extent 36,864 B 内，放得下

### 抓取工具
- 常驻守护：`python E:/k60-work/scratch/capd.py --output <log> --stop-file <STOP> --status <status> --max-seconds 0 --idle 0 --wait-port 0`
  无限期等 1209:0001，逐块 flush，不自行停止
- UI 按钮：安装的 `@local/k60-console-buttons` 插件，路由
  `/k60-console/{start,stop,status,log}`，挂在 `conversation.composer.dock`
- **教训**：不要点“停止”再看——panic 后串口就没数据了。应保持守护常驻，直接读文件。
