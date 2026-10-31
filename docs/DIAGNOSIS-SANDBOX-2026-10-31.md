# 诊断结论与修复方案：进度条卡 1/3 + SIGKILL 风暴（2026-10-31）

## 一、为什么一直在原地打转——根因其实早就在仓库里

对照源码逐行核实后确认：**这个仓库里本来就带着一套完整的 AMFI/Sandbox 替身**
（`zzzzzzz-pong-hackios-userland-abi.patch` 新增的 `bsd/kern/kern_minimac.c`，
已在我们正在编译的树里：`security/mac_base.c`、`osfmk/kern/startup.c:726` 均已挂上），
但它的启动被一个 **boot-arg 闸门** 拦住了：

```c
// kern_minimac.c:368-374（当前树内实文）
minimac_policy_init(void)
{
    uint32_t enabled = 0;
    if (!PE_parse_boot_argn("amfi_get_out_of_my_way", &enabled, sizeof(enabled)) || !enabled) return;
    mac_policy_register(&miniamfi_conf, &miniamfi_handle, NULL);   // "AMFI"
    mac_policy_register(&minisandbox_conf, &minisandbox_handle, NULL); // "Sandbox"
}
```

而现在的 kernel_args（payload.json 实读）：

```
-v native-ufs=1 pong_allow_unauthenticated_root=1 debug=0x144 cs_enforcement_disable=1
pong_software_keybag=1 disable_exc_resource=1 pong_ufs_readwrite=1 pong_data_mount=1
pong_data_rw=1 k60_fontscale=3
```

**没有 `amfi_get_out_of_my_way=1`。** 所以两个替身策略从未注册。

## 二、缺策略 → 用户态的确定性死亡路径（源码逐行核实）

1. `security/mac_base.c __mac_syscall():1587`：遍历 `mac_policy_list`，
   找不到名为 `"Sandbox"` 的策略 → `error = ENOPOLICY`（159）。
   libsystem_sandbox 的 `sandbox_init()` 拿到 159 → **profile 初始化失败**。
2. sweet 在**一模一样的状态**下记录的现象（NOTES.md:90-91，逐字）：
   - "launchd denies many mach lookups with `error = 159: Sandbox restriction`"
     （mediaserverd→com.apple.backboard.display.services、remoted、mobiletimerd→sleepd、
     identityservicesd→apsd）
   - "**tccd exits OS_REASON_SANDBOX "profile not found"** ... likely cause of many
     daemon crash loops"
   - 他们的修复就是 patch `0050-sweet-sandbox-policy.patch`：注册名为 `"Sandbox"` 的
     宽松 MAC policy（`mpo_policy_syscall` 默认返回 0，container/extension 返回 ENOENT）。
3. 同文件替身里还有 `mpo_priv_grant`（`kern_minimac.c:730-760`）：
   - `PRIV_WORK_INTERVAL` 无条件放行——注释明说：
     "UIKit does it as soon as anything scrolls, and takes a refusal for a programming
     error (**Failed to create work interval**): **SpringBoard died of it** on the first
     swipe"（sweet NOTES:22 同样记录）。
4. 现在日志里的受害者名单与这个机制完全吻合：
   `tccd / timed / ScreenTimeAgent / ptpd / securityd / usermanagerd`，
   `ex=3085 kx=1490 abn=1465`（98% 异常退出，全部 sig=9）。
   这些进程在 sandbox 初始化或 mach lookup 收到 159 后**自行 abort/exit**，
   由 `postsig` 合成 `OS_REASON_SIGNAL`/SIGKILL——这就是为什么 0238 的
   `K60 last bad` 全是 `sig=9`，且 victim 都是"无理由"的被杀。
5. 60fps→停的交替：backboardd 本身画 60fps 没问题（驱动 2.7µs、GPU 0µs），
   但它依赖的 mach 服务（mobilegestalt/iohideventsystem，159 同因）与
   SpringBoard 的 work-interval gate 拉不住 → UI 层周期性死掉又重启 → 屏幕在
   进度条（backboardd 单独存活时）与跑码（UI 死后只刷控制台）间切换。
   控制台与 UI 抢 framebuffer 的 `gc_enable` 问题（video_console.c:451-453）只是观感。

## 三、为什么之前"改一下再 boot"没命中

- ENOSPC、目录缺失、K60WATCH 刷屏都是**真实且必须修**的问题，修掉它们后
  日志才第一次走这么深——但现在挡路的已经是**下一个确定的闸门**：
  sandbox 策略缺失。之前每次修的都是更早的失败点，这是正常的 peel-the-onion，
  但确实该停掉"猜"：这次每个结论都有 file:line。

## 四、修复方案（一行 boot-arg，零代码改动）

### 立即做：payload 加 `amfi_get_out_of_my_way=1`

- 打开 `kern_minimac.c` 的两个替身策略，等价于 sweet 的 0050（且更完整：
  还有 container-path op 4、priv 表、AMFI dyld policy 0x5a/bootarg 0x60）。
- `cs_enforcement_disable=1` 已在 args 里，所以 AMFI 签名替身只是把
  ad-hoc 二进制标成 platform（这个替身本来就无安全意义，参考其注释）。
- **风险低**：这是 pong 板的原生路径（pong 用同一 boot-arg 起 hackios userland），
  不是新代码；0235-0239 诊断全部保留。

### 下一颗镜像的验证判据（照抄 sweet 的通过字符串）

| 判据 | 期望 |
|---|---|
| `minisandbox: request N (first seen …)` | 策略真的被注册并被调用 |
| `tccd`/`timed`/`securityd` 不再成批 sig=9 | abn 增速骤降 |
| 无 `error = 159` 类崩溃循环 | mach lookup 通了 |
| SpringBoard/UIKit 不再报 "Failed to create work interval" | priv_grant 生效 |
| 进度条 > 1/3 且不再回跳跑码 | UI 层存活 |

### 如果 boot-arg 打开后又出现新失败（预期内的两个）

- `minisandbox: privilege N refused` → 按 pong 表补 entitlement 映射（表已在源码里）。
- container-path 相关 abort → 已有 `zzz…-pong-container-path.patch` 的 ENOENT 语义
  （20G81 的 syncdefaultsd 修正），确认它是否在 series 里、是否被 0239 之前的顺序影响。

## 五、已排除/已修复项（不再回头查）

- 存储：2 GiB 已装+读回校验，ENOSPC 消失；旧卷备份在 PC。
- 目录：0239 建 28 个运行时目录（launchd.log/FeatureFlags/zoneinfo 三个实测 ENOENT 已覆盖）。
- 显示：CA 四前提（native canvas/Timing+Color/GetID=1/IOAcceleratorES）逐条核对过，全满足。
- K60WATCH：已默认关。
- fork 巡查：无未吸收的可用提交。

## 六、执行顺序（不再盲改）

1. 构建 `boot-amfi.img`：现有镜像 + `amfi_get_out_of_my_way=1`（唯一 delta）。
2. 刷入后只看上面六条判据 + `KX!` 的 `ns=/code=`（0238 已在线）。
3. 若 sandbox 通了但仍卡，下一个变量只从 `KX! ns=` 的实测值出发（jetsam ns=1
   还是 OS_REASON_SANDBOX 25 还是别的），不再从名字猜。
