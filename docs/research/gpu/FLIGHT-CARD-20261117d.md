# 上机卡 2026-11-17d：插件是否被 dyld 装载？—— 用构造函数标记一刀切开

- 镜像标签：`gpu-loadmark-20261117`
- 分支/提交：`feat/gpu-metal-hw` @ 本卡之后的代码提交
- 插件来源：`K60_METAL_PLUGIN_SRC` = `/mnt/e/iOS Port/Work/impl/gpu-mac-build/out/metal-plugin-20261117b`

## 1. 目的

`gpu-dualroot3-20261117` 已经证明部署与注入配置都成立
（`K60METAL deploy files=6/6 inject=6 error=0`；`console.log:530`
`Pong init: native Metal entry enabled for backboardd`），但全日志没有一行 `Pong Metal:`。

`PongMetalPlugin.mm` 的所有 `report()` 都在 Metal 入口之后，所以「没装载」和
「装载了但没有入口被调用」无法区分。本轮**只**加一个 dyld 构造函数
（`__attribute__((constructor))` → `report("plugin loaded",0)`），不改任何
Metal 逻辑、不改内核、不改 boot-arg、不改部署。

## 2. 前提证据（上机前已具备）

| 类别 | 证据 |
| --- | --- |
| 静态 | 新二进制 `strings -a | grep -c 'plugin loaded'` = **1**；`LC_RPATH` = **1**（`@loader_path`）；sha256 `6c2021b54e9993bd…`；95,600 B（比上一版 +48 B） |
| 单元 | `scripts/tests/test-metal-plugin-load-marker.py` 6/6 ✅（构造函数存在、调用共享 `report()`、构建脚本编译该文件且保留 `-Wl,-rpath,@loader_path`） |
| 产物 | `verify-boot-image: OK`；`image-arg-audit: OK (30 arguments, 594 bytes)` |

**更正**：上一份卡（17c）说「11-16 的插件没有 LC_RPATH」是**我的测量错误** ——
当时用 `--all-headers | grep -A3 … | head -30` 查看，`head -30` 在 8 条
`LC_LOAD_DYLIB` 之后截断，`LC_RPATH` 没被看到。重新用 `grep -c LC_RPATH` 计数，
11-16 与 11-17 两份二进制都是 **1**。因此「rpath 缺失」不成立，17c 未飞。

## 3. 抓取

- 复用 `scripts/flash.sh <boot.img> 240`，证据落 `E:/iOS Port/Work/evidence/usblog-<ts>/`。

## 4. 判据

### 成功判据（全部满足才算通过）

- **S1** 内核无异常：`K60KEXC` 出现 0 次（banner 不计）。
- **S2** 部署双根完成：`K60METAL deploy files=6/6 inject=6 error=0`。
- **S3** **插件被 dyld 装载**：出现至少一行 `Pong Metal: plugin loaded status=0x0`。

### 失败判据（任一命中即 FAIL，并写明哪一条）

- **F1** 出现 panic / `K60KEXC`（除 banner）。
- **F2** 没有 `K60METAL deploy ... inject=6`。
- **F3** 有 `S2` 但**没有** `Pong Metal: plugin loaded`：`DYLD_INSERT_LIBRARIES`
  对这个进程没有生效（或加载被 dyld 拒绝且没有打印）。下一步转为读
  `exec_inject_env()` 的名字匹配（`ip_ndp->ni_cnd.cn_nameptr` 与 `cn_namelen`）
  和 dyld 对平台二进制的插入策略，而不是继续改插件。
- **F4** 有 `plugin loaded` 但没有后续 `Pong Metal:`：插件确实在进程里，
  问题在 Metal 发现路径（`MTLCreateSystemDefaultDevice` 的 bundle 枚举）。

### 判定口径

`crashed: backboardd`、`software renderer fallback installed`、`present #` 一并记录，
但本轮判决只看 S1–S3：本卡只回答「装载了没有」。

## 5. 结果登记

**判决：PASS（S1/S2/S3 全部满足）。** 证据 `E:/iOS Port/Work/evidence/usblog-20261117-110349`
（`console.log` 3,064 行 / 190,081 B，抓取完整、未因 panic/复位中断，supervisor rc=0）。

| 判据 | 实测 | 结果 |
| --- | --- | --- |
| S1 `K60KEXC` | `grep -c` = **0** | ✅ |
| S2 部署双根 | `:480 K60METAL deploy files=6/6 inject=6 error=0` | ✅ |
| S3 插件装载 | `:1288 Pong Metal: plugin loaded status=0x0` | ✅ |

旁证：`crashed: backboardd` = **0**；`present #` = 0；`optional camera-filter GPU prewarm
skipped (software-only platform)` = 1（`:1670`）。

**本轮最重要的三个新事实**

1. **插件确实被 dyld 装进了 backboardd**（`:1288`，紧接 `:1276 Pong UI: 20G81 compatibility
   library entered backboardd` 之后）。「注入机制不生效」这一整类假设到此排除。
2. **但插件一次都没被实例化**：除构造函数那一行外没有任何 `Pong Metal:` 输出，
   特别是没有 `real Vulkan-backed device created` / `runtime refused device`。
3. **`:1282 Pong UI: 20G81 software renderer fallback installed (protection=0)` 不是
   「Metal 不可用」的证据** —— 读 `userland/ui_compat.c:943-951` 可知它只是把
   `renderer`/`framebuffer_format`/`display_ready` 等函数指针替换进 QuartzCore 的
   `install_renderer_hook()`，无论 Metal 是否可用都会打印。真正的 nil 信号是
   `:1670` 的 `software-only platform`。

**下一层（写死）**：查 `MTLCreateSystemDefaultDevice()` 的**设备发现路径** ——
插件里的 `PongAdrenoMetalDevice` 类如何被 Metal 框架找到并实例化
（`Info.plist` 的 `NSPrincipalClass`、`.clients`/`.publish` 的消费方、
以及 SpringBoard 进程根本没有注入插件这一事实：`:1658` 的 SpringBoard 只有
libpong-ui）。下一步要么在 SpringBoard 也注入插件，要么证明设备发现走的是
backboardd 发布的 Mach 服务。
