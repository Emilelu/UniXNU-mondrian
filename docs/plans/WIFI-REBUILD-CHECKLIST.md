# WiFi 对照镜像重出核对清单（4.5 GiB 窗口，从 origin/main）

> 状态：**清单稿（2026-11-15）**，只描述核对与重出的**判据**，不含新代码。
> 目标：从当前 `origin/main`（`97258d2`）按 `owned_memory_size = "0x120000000"` 重出一张
> WiFi 对照镜像，并与既有的 mhi3 / mhi4 两张镜像**逐字段**比对，判定「main 上的 wifi 栈
> 是否已经等价于 mhi4」。
>
> 结论先说：**从 main 直接重出复现不出 mhi4**。main 与 mhi4 之间隔着 5 条硬差异（§3），
> 其中第 1 条会让内核里**没有 PongWifi 驱动**。重出前必须先决定这 5 条各自怎么处理。

---

## 1. 两张基准镜像的口径

| 镜像 | 构建时间 | REPO head | 窗口 | 用途 |
|---|---|---|---|---|
| `wifi-20261116mhi3` | 2026-11-14 21:43:09 +08:00 | `feat/wifi-bringup` @ `aaec6375` | 4.75 GiB（`0x130000000`） | 对照组（旧窗口） |
| `wifi-20261116mhi4` | 2026-11-14 23:17:06 +08:00 | `feat/wifi-bringup` @ `f93c3404` | 4.5 GiB（`0x120000000`） | 实验组（新窗口） |

两张镜像之间只差 **2 个提交**（`git rev-list --count aaec637..f93c340` = 2）：

- `7a0fd50` `docs(wifi): record the MHI handshake logs and the strict-build repairs`
  —— 只加 `docs/research/wifi/LOCAL-VERIFICATION.md`（+172）与 `MERGE-REQUEST.md`（+61），**不碰代码**。
- `f93c340` `fix(board): drop the owned memory window to 4.5 GiB` —— 只改 `board.toml`（+5/−1）。

因此 **mhi3 与 mhi4 的唯一实质差异就是内存窗口**；其余 sha 差异全部由它级联
（ADT → payload → boot.img）。这一条是后面所有判据的前提。

main 上的等价窗口提交是 `3c69c80` `fix(board): drop the owned memory window to 4.5 GiB`
（同作者、同一时刻、同一改动，`git merge-base --is-ancestor 3c69c80 origin/main` = YES）。
→ **窗口这一项从 main 重出不需要任何补丁**，main 的 `board.toml:235` 已经是
`"owned_memory_size" = "0x120000000"`。

窗口如何进镜像（不是进内核）：`board.toml` 的 `[payload.adt] owned_memory_size`
→ `scripts/unixnu/devicetree.py:320-324` 写 `chosen` 的 `darwinboot-memory-size`
→ `scripts/unixnu/payload.py:239` 映射成 `--owned-memory-size` 交给 `make-pong-adt.py`（:157）。
kernel 步骤不读这个键（`scripts/unixnu/kernel.py` 只在 :260 读 `[kernel.prelink]`）
→ **改窗口不改内核，只改 ADT / payload / boot.img**。

---

## 2. 重出必须显式钉死的四个输入

`scripts/build-strict.sh` 的四个环境变量各自决定不同的东西，缺一个就会混线：

| 变量 | build-strict 里的位置 | 决定什么 | mhi3/mhi4 的值 |
|---|---|---|---|
| `REPO` | :36（脚本父目录，不可覆盖） | freeze 清单、`series` 计数、eight-step、manifest 的 `repo` 字段、`scripts/*` 工具 | `/mnt/e/hackios/k60-wifi` |
| `K60_DEVICE_INPUT` | :38 | `unixnu build kernel/payload/bootimg -D $DEV`（:135/:156/:189）；`board.toml`、`dts/`、`patches/xnu/series` **都从它读** | `/opt/k60/trees/k60-wifi-device` |
| `K60_BUILD_TREE` | :39 | `$BUILD/unixnu`（165 B 启动器）+ `$BUILD/out-*` | `/opt/k60/trees/k60build` |
| `K60_OUT` | :40 | 产物目录（`$OUT/mondrian/ipados-16.6.1-20G81/mondrian`） | `/opt/k60/trees/k60build/out-wifi` |

`patches/xnu/series` 的读取路径是 `board.toml:20` 的 `patch_series = ["device:patches/xnu/series"]`，
由 `scripts/unixnu/patches.py:11-31` 解析成 `$DEV/patches/xnu/series`。

---

## 3. 五条硬差异（阻断级，按影响排序）

### 3.1 0010 补丁在 main 上只加了一条装配路径 —— 重出会得到「没有驱动」的内核

`patches/wifi/0010-scripts-build-xnu-wifi-archive.patch` 在两边内容不同：

- **main 版**（blob `520f5d1e3b20897bee521bf8555e71843fe29461`）：只有 1 个 hunk
  `@@ -902,9 +902,15 @@`，往 `KERNEL_EXTRA_ARCHIVES` 加 `-Wl,-force_load,$PONG_WIFI_ARCHIVE`。
- **wifi 版**（blob `cb7723223da1df043a2f3fd110f947fa364e692a`）：2 个 hunk
  （`@@ -919,6 +919,12 @@` 与 `@@ -1134,6 +1140,12 @@`），同时往 `PLATFORM_ARCHIVES` 加一份。

补丁正文自己写了理由：

> The kernel is linked from one of two mutually exclusive archive sets.
> KERNEL_EXTRA_ARCHIVES belongs to the CONFIG_XNU_SOURCE_CORECRYPTO14 branch; the
> mondrian defconfig leaves that unset (the key is present twice, "y" first and "n"
> last, and the parser keeps the last one), so the kernel actually links through
> PLATFORM_ARCHIVES. Adding the archive to only one set silently yields a kernel
> without the driver, which is what the first version of this patch did. Both
> branches carry it.

实测印证：mhi4 的 `.config` 第 2 行 `CONFIG_XNU_SOURCE_CORECRYPTO14=y`、第 88 行 `=n`
（后者覆盖前者）→ 走 `PLATFORM_ARCHIVES`。而 `origin/main:scripts/build-xnu-4k-baseline.sh`
里 `grep PONG_WIFI` = **0 命中**。

**判据**：重出后必须能在 `kernel.macho` 里找到 `_pong_wifi_firmware` 与 `_pong_wifi_firmware_end`
两个符号（`llvm-nm`），span 恰为 11,067,094 B（见 `LOCAL-VERIFICATION.md:89-111`）。
找不到 → 走错装配路径，镜像作废。

### 3.2 `patches/xnu/series`：main 224 行，wifi 229 行，且 manifest 记的不是内核真正用的那份

| 树 | 行数 | sha256 |
|---|---|---|
| `origin/main` | 224 | `34cf51e4d10e46eb3514d798a3e3208c3ac7f124dd8a982585e9eea1e8b9c8c0` |
| k60-refmine HEAD（`feat/research-refindex`） | 223 | `5a18e92993e4af25ffd66597dc2398abb09c4efc52e14ce99cfa82e784f2e7f9` |
| k60-wifi（`feat/wifi-bringup`）与 k60-wifi-device | 229 | `0076aa20902ad3029628352093ab8c074f8a2db77e2079b840a32bd1658dcfdd` |

逐行差异：

- wifi 多 6 个 `zzzz…-pong-touch-{bitbang,frame,miso-pull,spmi,reset-level,pad-level}-probe.patch`；
- main 多 `zzy-native-gpu-addon-mount.patch`；
- `0610-k60-metal-plugin-deploy.patch`（main，218 行）↔ `0610-k60-metal-seeds.patch`（wifi，223 行）。

**口径错位**：`build-strict.sh:84-85` 的 `SERIES_COUNT`/`SERIES_SHA` 取 `$REPO/patches/xnu/series`，
而内核真正应用的是 `$DEV/patches/xnu/series`。mhi3/mhi4 两者恰好都是 229 所以看不出来；
从 main 重出时 `REPO`=224、若 `DEV` 仍指 k60-wifi-device=229，**manifest 会记 224 而实际应用 229**。

**判据**：重出后 manifest 的 `series.count` 必须与 `$DEV/patches/xnu/series` 的实际行数一致；
不一致就在报告里显式写明「manifest 记的是 REPO 的口径」。

### 3.3 `.config` 里有 `CONFIG_XNU_PONG_WIFI=y`，但两个 defconfig 都不带它

- mhi4 的 `out-wifi/.../mondrian/.config`（97 行）末尾有
  `# Trial build: mondrian_wifi_defconfig adds only this key (see configs/mondrian_wifi_defconfig).`
  + `CONFIG_XNU_PONG_WIFI=y`。
- `configs/mondrian_defconfig` **不含** `PONG_WIFI`；只有 `configs/mondrian_wifi_defconfig:71` 有。
- `unixnu build` **不会重写 `.config`**（只有 `unixnu defconfig` 写；build 只
  `config.py:195-200 need_config()` 读，缺文件才报 `no configuration`）。
- 工作目录名由 defconfig 名决定（`scripts/unixnu/config.py:164`
  `self.work /= selected.removesuffix('_defconfig')`）→ 选 `mondrian_wifi_defconfig` 会落到
  `mondrian_wifi/` 而不是 `mondrian/`，且 `OWNER_DATA_VOLUME_UUID` 会从
  `1BCD69FF-…` 变成 `6DCCF70A-…`。

与 main `configs/mondrian_defconfig` 的差集（除 `.config` 头部 27 行历史键外）：

| 开关 | main defconfig | mhi4 `.config` | 影响 |
|---|---|---|---|
| `CONFIG_XNU_PONG_WIFI` | 无 | `=y` | **驱动是否编进内核** |
| `CONFIG_XNU_GPU_ADDON` | `=y`（:27） | 无该键 | 触发 build-strict :99-116 的 Metal 插件 staging |
| `CONFIG_XNU_K60_PHYSICAL_BATTERY` | `=y`（:78） | `is not set` | 触发 :121-131 的 battery archive |

**判据**：重出前必须手写 `.config`（或改 defconfig 并接受目录/UUID 变化），
三者都要与 mhi4 对齐；重出后比对 `.config` 全文，只允许出现「与本次改动相关」的差异。

### 3.4 `board.toml` 两边不同：main 多 `[adt.buttons.*]`，`bitbang-pins` 也不同

| 项 | main（`34f47790…`，297 行） | wifi（`c63cd936…`，260 行） |
|---|---|---|
| `[adt.arm-io.pong-buttons.*]` | 有（:273-296，六值 + SPMI 三基址） | 无 |
| `[adt.buttons.*]` | 有（:289-296，`button-names = ["hold","voldown","volup"]`、`home-button-type = 2`） | 无 |
| `[adt.arm-io.pong-touch.bytes] bitbang-pins` | `10000000110000001200000013000000`（:264） | `11000000120000001000000013000000`（:260） |
| `owned_memory_size` | `0x120000000`（:235） | `0x120000000`（:235） |

**判据**：从 main 重出的镜像**会带 buttons 节点、且 bitbang-pins 是新表**，这两点与 mhi4 必然不同。
不是回归，但必须在报告里单列，避免把 ADT 差异误判成窗口差异。

### 3.5 `freeze()` 不覆盖 wifi 侧输入

`build-strict.sh:71-76`：

```sh
find board.toml dts patches/xnu scripts -type f -print0 | sort -z | xargs -0 sha256sum
```

- 只在 `$REPO` 里跑，**不哈希 `$DEV`**；
- **不含** `patches/wifi/`、`drivers/PongWifi/`、`configs/`、`.config`。

→ `frozen-before.txt` 与 `frozen-after.txt` 相同**不证明** wifi 侧没变。mhi3/mhi4 的
`frozen-before.txt` 都是 425 行（board.toml 记的是 `c63cd936…`，即 wifi 的 board.toml，
反过来印证 REPO=`/mnt/e/hackios/k60-wifi`）。

**判据**：重出报告里必须单独给出 `patches/wifi/` 与 `drivers/PongWifi/` 的清单 sha
（`git -C $DEV ls-tree -r` 或逐文件 sha256），不能拿 freeze 清单顶替。

---

## 4. 逐字段核对表

### 4.1 `boot.json`（由 `scripts/unixnu/bootimg.py:120-124` 的 verify() 写）

| 字段 | mhi3 | mhi4 | 从 main 重出的预期 | 判据 |
|---|---|---|---|---|
| `kernel_sha256` | `83b52b56…707c` | 同 | **同**（若 FD 与 DTB 相同） | 不同 → FD 或 DTB 换了 |
| `ramdisk_bytes` | 201326592 | 同 | 同 | 不同 → payload 尺寸变了 |
| `header_version` | 4 | 同 | 同 | — |
| `kernel_address` / `tags_address` | `0x0` / `0x0` | 同 | 同 | — |
| `image_sha256` | `615a05ce…` | `34688ecc…` | **必然不同** | 允许不同 |
| `image_bytes` | 201887744 | 同 | 同 | 不同 → 尺寸变了，要解释 |
| `fd_sha256` | `cf448571…` | 同 | **同**（复用同一个 FD） | 不同 → UEFI 侧变了 |
| `dtb_sha256` | `2d044eaa…` | 同 | **同**（main 的 `dts/mondrian.dts` = `491f784e…`，与 wifi 侧同一份） | 不同 → dts 或 dtc 变了 |
| `shim_bytes` | 112 | 同 | 同 | — |
| `hardware_tested` | false | false | false | 上机后由流程改写 |

**口径提醒（此前多次混淆）**：`boot.json` 的 `kernel_sha256` 是 bootimg verify() 里
`kernel = data[start:start+kernel_size]` 的 sha，即 **kernel 槽 = gzip(BootShim + UEFI FD) + 小 DTB**
的字节，**不是** payload 里的 XNU `kernel.macho`，也不是 build-strict 的 `components.kernel_built`。
mhi3/mhi4 的 fd 与 dtb 相同 → 该值必然相同，与 XNU 内核变没变**无关**。

### 4.2 `build-manifest.json`

| 字段 | mhi3 | mhi4 | 从 main 重出的预期 |
|---|---|---|---|
| `built_at` | 2026-11-14T21:43:09+08:00 | 2026-11-14T23:17:06+08:00 | 新时间 |
| `repo.branch` | feat/wifi-bringup | 同 | **main 或对照分支名** |
| `repo.head` | `aaec6375…` | `f93c3404…` | 重出时的 HEAD |
| `repo.dirty_files` | 0 | 0 | 必须 0 |
| `series.count` / `series.sha256` | 229 / `0076aa20…` | 同 | 见 §3.2，**必须与 `$DEV` 实际一致** |
| `frozen.list_sha256` | `ceb87e4e…` | `da44249e…` | 必然不同（board.toml 变了）；只作记录 |
| `components.adt` | `a78250ea…` | `a11085d3…` | **必然不同**（窗口 + buttons） |
| `components.boot_img` | `615a05ce…` | `34688ecc…` | 必然不同 |
| `components.dtb` | `2d044eaa…` | 同 | **同** |
| `components.fd` | `cf448571…` | 同 | **同** |
| `components.kernel_built` | `85e1fe17…` | `e18b77b6…` | 若内核输入相同则应等于 mhi4 的值；不同必须解释 |
| `components.payload` | `1e4b4f77…` | `4581a60d…` | 必然不同 |
| `components.payload_kernel` | `0addbb48…` | `e24a58f1…` | 随内核变 |
| `kernel_args_requested` | `["pong_wifi=1"]` | 同 | 同 |
| `payload_args` | 30 项、587 B（含 `pong_wifi=1`、`debug=0x140`、`epoch=1793709100`、`k60_usblog=2`） | 同 | 同 |
| `eight_step_sha256` | `67efa084…` | 同 | 若 eight-step 数据未变则同 |
| `eight_step_items` | **无此键** | **无此键** | **main 版 build-strict 会写这个键**（:227）→ 出现即证明用的是 main 版脚本 |

最后一行是「哪棵树的 build-strict 跑的」的指纹判据：main 版多
`scripts/check-build-env.py` 前置（P-185）、GPU addon staging、battery archive、
`check-metal-blob.py`（P-196）与 `eight_step_items` 字段；k60-wifi 版没有这些。

### 4.3 镜像自身自洽（fail-closed）

```sh
python3 scripts/verify-boot-image.py --manifest <build-manifest.json>
```

七步：ANDROID! v4 header_size 1584 → kernel 槽 gzip + 112 B BootShim + FV sha →
小 DTB（≤65536）→ ramdisk 与 `components.payload` 逐字节 → payload FAT 里的
`Payloads/kernel.macho` 与 `components.payload_kernel` → payload TOML 每条 `args =` →
策略 `pong_adsp`。需要 mtype（mtools）。mhi3 与 mhi4 当前都跑 **OK**，
重出的镜像必须同样 OK，否则不进上机队列。

另两条构建期门禁：`scripts/check-kernel-archives.py`（P-190，防止混进别线补丁）与
`scripts/check-image-args.py`（`DARWIN_BOOT_LINE_MAX = 607`；`pong_wifi`/`k60_wifi_rsc`/
`k60_wifi_stage`/`pong_wifi_dma_mib` 在 `ALLOWED_ADDITIONS`，`debug=1`/`epoch=1` 在 FORBIDDEN）。

---

## 5. 重出步骤（只列操作序列，不含新代码）

1. **钉死四输入**：`REPO` 指向 main 的检出、`K60_DEVICE_INPUT` 指向为本次准备的 device 树、
   `K60_BUILD_TREE` 与 `K60_OUT` 用新目录（不要复用 `out-wifi`，否则 `.config` 会沿用 mhi4 的）。
2. **补齐 wifi 侧输入**：main 上 `drivers/PongWifi/`、`configs/mondrian-wifi-*`、
   `scripts/{build-k60-ath11k.py,build-k60-wifi-native.py,prepare-k60-wifi.py,pong_paths.py}`
   **都不存在**，只能按 `patches/wifi/series` 顺序 `git apply` 十条落地（逐条 `git apply --check`
   会假失败，后一条依赖前一条已落地）。
3. **决定 §3.1 的 0010**：要么把 wifi 版 0010（双 hunk）取过来，要么接受「内核里没有驱动」并明说。
4. **决定 §3.3 的 `.config`**：手写 `.config`（PONG_WIFI=y、GPU_ADDON 无、PHYSICAL_BATTERY not set），
   或改用 `mondrian_wifi_defconfig` 并接受目录名与 UUID 变化。
5. **确认 archive**：`build-xnu-4k-baseline.sh` 默认 `PONG_WIFI_ARCHIVE=$ROOT/build/pong-wifi/libPongWifiNative.a`
   （当前 11,939,768 B，sha256 `bb258ff5…`）；另有 `$ROOT/wifi/native-real/libPongWifiNative.a`
   （sha256 `cda85a49…`）——**两个不同，必须显式确认链接的是哪一个**。
6. **确认固件**：`/mnt/e/k60-work/firmware/qca6490-wifi/` 四文件（amss.bin 5,470,128 B
   `a626cfc1…`、amss20.bin 5,296,128 B `903c378a…`、m3.bin 266,684 B `ad234ac8…`、
   regdb.bin 24,278 B `06810e85…`）；PWF2 头 4096 B，四条目 offset 0x1000/0x539000/0xa46000/0xa88000。
7. **复用 FD**：拿 `cf4485712c29` 那份（`/mnt/e/k60-work/artifacts/fd/wifi-20261116mhi{3,4}-cf4485712c29.fd`），
   这样 `boot.json` 的 `fd_sha256` 与 `kernel_sha256` 才有可比性。
8. **跑 build-strict**：`scripts/build-strict.sh <tag> --fd <fd> --kernel-arg pong_wifi=1`。
9. **按 §4 逐字段比对**，并单独产出 `patches/wifi` + `drivers/PongWifi` 的清单 sha（§3.5）。
10. **自洽校验**：`verify-boot-image.py` 必须 OK；`check-kernel-archives.py`、
    `check-image-args.py` 必须通过。

---

## 6. 「复现成功」的定义

重出的镜像算**复现 mhi4**，当且仅当同时满足：

1. `components.dtb` = `2d044eaa…`、`components.fd` = `cf448571…`、
   `boot.json.kernel_sha256` = `83b52b56…`；
2. `components.kernel_built` = `e18b77b6…`（内核输入逐字节相同）；
3. `kernel.macho` 里有 `_pong_wifi_firmware`/`_pong_wifi_firmware_end`，span 11,067,094 B；
4. `payload_args` 30 项、587 B，逐字相同；
5. `verify-boot-image.py` OK。

**允许不同**（并须在报告里逐条解释）：`built_at`、`repo.head`、`series.*`（口径差异）、
`frozen.list_sha256`、`components.adt`/`payload`/`payload_kernel`/`boot_img`、
`boot.json.image_sha256`，以及 §3.4 的 buttons 节点与 bitbang-pins。

**若第 2/3 条不成立** → 重出的不是 mhi4 的等价物，只能当「main 现状的对照组」，
不能用它去判「窗口是否是 MHI 0 字节的原因」。

---

## 7. 已知局限（写报告时必须带上）

1. `freeze()` 只哈希 `$REPO` 的 `board.toml dts patches/xnu scripts`，不含 wifi 侧输入（§3.5）。
2. `series` 在 manifest 里记 REPO 口径、内核用 DEV 口径（§3.2）。
3. `.config` 不是由 defconfig 重新生成，而是历史累积 + 手改的产物；今天跑 `unixnu defconfig`
   无论选哪个都复现不出 mhi4 的 `.config`（§3.3）。
4. `out-wifi/mondrian/ipados-16.6.1-20G81/mondrian/state.json` 里还写着
   `{"device": "/opt/k60/trees/usb-cdc-mainline/device"}`（旧值），与 `out-wifi/state.json` 不一致，属残留。
5. `board.toml` 之外，`$DEV` 树本身是脏的（`k60-wifi-device` HEAD `94d4a9ae`，
   有 3 个修改文件与 2 个未跟踪脚本）——重出前要记录 `git -C $DEV status --porcelain` 的完整输出。

---

## 8. 证据位置

- 两张基准镜像：`E:/k60-work/artifacts/wifi-20261116mhi3/`、`…/wifi-20261116mhi4/`
  （`boot.json`、`build-manifest.json`、`frozen-before.txt`、`frozen-after.txt`、`logs/`）。
- 静态判据：`docs/research/wifi/LOCAL-VERIFICATION.md`（k60-wifi 分支）§11-111。
- 上机时序与两道门：`docs/research/wifi/STAGE-BRINGUP.md`（k60-wifi 分支）。
- 板级真值与差异表：`docs/plans/WIFI-PORT-PLAN.md` §0、§2.1、§2.2、§4.0。
- 端点身份实测：`E:/k60-work/evidence/pci-id-20261114/`（17CB:1103 / 子系统 17CB:0108 / rev 1 /
  BAR0 0x60200000 2 MiB / Gen2 x1）。
