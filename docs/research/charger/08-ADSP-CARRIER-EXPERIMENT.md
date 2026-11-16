# ADSP 载体实验：零售机第一次受控 PAS 上机

状态：产物已就绪（2026-11-17，tag `carrier-20261117c`），等 Lead 在用户同意后上机。
分支：`feat/adsp-carrier`（基于 `origin/main 74c0d24e`，不混 `feat/charger`）。
执行人：Lead（本线禁止自行 boot，见 m01673 与用户 m03715 铁律）。

## 0 这次上机只回答一个问题

**零售 K60 的 SCM 会不会放行 PAS（PIL）鉴权。**

不是"电池能不能用"，不是"GLINK 通不通"：那些都在 lease 之后。
所以判据钉在 `K60PAS auth ok` 这一行；到不了这一行就不是 PASS，
不论前面打印了多少行。

### 0.1 判据表（逐字，先写死）

| 判据 | PASS（全部满足） | FAIL | INVALID |
| --- | --- | --- | --- |
| C0 载体装载 | `K60PAS carrier begin` 与 `K60PAS carrier region base=0x9fd00000 span=0x3100000` 各 1 次 | 出现 `K60PAS carrier absent rc=` | 没有 `K60PAS carrier begin`（boot-arg 没进镜像，或 K60DATA mount 在本钩子之前失败；见 §3 前置） |
| C1 放置 | `K60PAS plan rows=24 copied=23494284 zeroed=25925684 link=0x86300000 base=0x9fd00000 window=0x3100000` 与 `K60PAS verify ok segments=24` 各 1 次 | `K60PAS verify mismatch` / `K60PAS verify bss not zero` / `K60PAS plan rc=` | 有 begin 无 plan 行 |
| C2 鉴权前步骤 | `K60PAS init ok` 与 `K60PAS mem_setup ok` 各 1 次 | `K60PAS init refused rc=` / `K60PAS mem_setup refused rc=` | init 行缺失 |
| C3 SCM 鉴权（本实验唯一结论点） | `K60PAS auth ok` 1 次，随后 `K60PAS carrier verdict PASS auth=ok base=0x9fd00000 span=0x3100000` | `K60PAS auth refused rc=` 或 `K60PAS carrier verdict FAIL rc=` | `K60PAS auth` 从未出现（提前 panic） |
| C4 系统存活 | auth 之后 60 s 内无 panic，控制台仍有心跳行 | 60 s 内 panic（贴 panic 首行 + `esr=`） | 无法判定（日志截断） |

规则：

- 一次 boot 只判一次；同一镜像重复 boot 不改变判决。
- 行号必须贴（`console.log:N`），不贴行号的判读不算证据（P-204 家族）。
- C3 为 FAIL 时先看 rc：`rc=-4` 是 SCM 拒绝（结论：零售机不放行）；
  `rc=-12`（EBUSY）要在 20 次重试后仍出现才算超时；`rc=1`（INTERRUPTED）
  要在 100000 次续会话后仍出现才是真中断。
- `K60PAS carrier verdict FAIL rc=` 是终态行，缺它而中途停住按 INVALID 处理。

### 0.2 止损线 D4（用户批准，m03755）

连续 2 次 boot 未到 `K60PAS auth ok` → 停止 ADSP 尝试，转 §6 的 ADC 兜底，
不再追加第三次"也许这次行"的镜像。

## 1 变更清单（每项：为什么 / 改在哪 / 静态证据）

### 1.1 carveout 真值（D1 = ③ 双来源）

- 事实：真机 FDT `/reserved-memory/adsp_region@9fd00000` reg=<0 0x9fd00000 0 0x3100000>
  （`E:/k60-work/scratch/power-work/assets/fdt-tree.json:286-291`），而固件按
  `0x86300000` 链接（pong SM8475 carveout）。旧代码把链接地址当目的地址：
  `drivers/PongPower/pong_adsp_table.h:3`、`drivers/PongPower/K60AdspPas.h:23`。
- 改法：三常量分开 —— `K60_ADSP_LINK_BASE 0x86300000`（固件链接）、
  `K60_ADSP_BOARD_BASE 0x9fd00000`（本板 carveout）、`K60_ADSP_WINDOW 0x3100000`；
  运行时可被 `/chosen` 的 `qcom,adsp-region` 覆盖（`patches/xnu/0613-k60-adsp-pas.patch:279`
  `k60_adsp_board_region()`）：2 cell = 32 位 base/span，4 cell = 64 位 base/span；
  device-tree cell 按 big-endian 解码（`k60_adsp_cell()`），对齐/范围校验。
- 静态证据：`scripts/tests/test-k60-adsp-loader.c` 断言 `plan.base == K60_ADSP_BOARD_BASE`、
  两者不等、`plan_at(0x9fd00800)` 必须 `K60AdspBadArg`；`scripts/tests/test-k60-adsp-image.py`
  从 `pong_adsp_table.h` 读回三个常量并与镜像表比对（`TESTS OK ... link 0x86300000 board 0x9fd00000`）。
- 产物证据：c 的 `kernel.macho` 保留 `K60PAS region from /chosen` 与
  `K60PAS ignoring region override` 两条诊断串（`strings` 复核，见证 `k60_adsp_board_region()` 被编入）。
- 结构测试：`scripts/tests/test-k60-adsp-region.py` 读 0613 patch，断言 `k60_adsp_cell()`
  按字节 big-endian 解码、`k60_adsp_board_region()` 支持 2/4 cell 且不退回 `const uint32_t *cells`
  （`TESTS OK region override parser uses big-endian cells (2 and 4 cell forms)`）。
- 回滚：一个 commit；改回 0x86300000 即恢复旧行为（不做）。

### 1.2 载体接线（D3 = ② 新 boot-arg）

- 为什么：`k60_adsp_reader_blob()` 早已存在但没有生产调用点
  （`drivers/PongPower/K60AdspImageReader.c:186`，过去只有单测在调）；旧 `pong_adsp`
  路径依赖 ramdisk FAT + Data mount，发布时机死锁（`docs/research/battery/HANDOFF-PUBLISH-SPEC.md` §7）。
- 改法：新 boot-arg `pong_adsp_carrier=1`（`patches/xnu/0613-k60-adsp-pas.patch:455`
  `k60_adsp_carrier_probe()`），走内嵌 blob；调用点插在
  `patches/xnu/0614-k60-adsp-call-site.patch:13-15` 的 `kern_exec.c` 块内，
  在 0619 的 `k60_adsp_startup_claim(2u)` 之前（不改 0619 一行，见 §5）。
- 静态证据：`scripts/verify-boot-image.py:85` `carrier_problems()` 只在该 boot-arg 有
  manifest `components.adsp_blob` + `adsp_blob_path` 且文件 sha256 一致时放行；
  自测 `scripts/tests/test-verify-boot-image.py` 6 例（缺 sha / 缺文件 / sha 不符 / 相符 /
  legacy 仍拒 / =0 允许），`14 cases, 0 failure(s)`。`scripts/check-image-args.py:44-55`
  的 `ALLOWED_ADDITIONS` 登记同名参数，`scripts/tests/test-check-image-args.py` 8 例全过。
- 可达性：carrier 块在 `native_owner_data_prepare()` 的 `if (error) goto done;`
  （K60DATA mount 成功）之后才执行（patched `bsd/kern/kern_exec.c:7892-7920`），不是函数入口。
  代码注释里的 "needs no filesystem and no Data mount" 指 carrier 自身不做文件系统 I/O，
  不表示钩子在 Data mount 之前；Data mount 失败时不会执行。这个前置写在 §3，失败形态按 C0 INVALID。
- 回滚：去掉 `--kernel-arg pong_adsp_carrier=1` 即完全不进这条路径（默认关闭）。

### 1.3 SCM 语义（D2 = ② 只补三点）

- EBUSY/INTERRUPTED 重试：`drivers/PongPower/K60AdspPas.c` `k60_scm_call()`，外层
  `K60_SCM_EBUSY_TRIES 20` × `IOSleep(30)`，内层 `K60_SCM_RESUME_TRIES 100000` 用
  `K60_SCM_INTERRUPTED` 续会话；x6 作为 in/out 寄存器显式声明（`k60_scm_raw`）。
- mem_setup 用表推导的 span（`plan.window` = 0x3100000）；pong 的 `qcom_mdt_span` 等价物
  记录为差异（§5 NOT-IN-SCOPE）。
- DTB PAS 36：**本次不启用**，只记差异（`PongAdsp.cpp:507-508` 成对 shutdown）。
- 寄存器声明：SMCCC 调用可改写全部 caller-saved 寄存器；`k60_scm_raw()` 把 x0–x7 全声明为
  in/out 并 clobber x8–x17 + memory（`a0547907`），否则编译器可能把活跃值留在 x4/x5/x7/x8+
  上，调用返回后读错栈/结构体。
- 静态证据：`scripts/tests/test-k60-adsp-pas.c` 断言三个重试常量与 `K60_ADSP_LOAD_BASE == 0x9fd00000`。

### 1.4 放置顺序与 cache（本次的 hard 证据）

- 顺序改成参考实现的 metadata → INIT_IMAGE → MEM_SETUP → copy → verify → AUTH_AND_RESET
  （旧 06xx 是 auth 先行、逐段 INIT_IMAGE、MEM_SETUP 最后，从未有过 `auth ok`）。
- 映射是 cacheable DDR（`0x2` = `VM_WIMG_DEFAULT` = `VM_MEM_COHERENT`，`osfmk/arm/memory_types.h:41-43`），
  所以 copy 后必须 clean 到 PoC：`k60_adsp_flush()`（`patches/xnu/0613-k60-adsp-pas.patch:229`）
  走同板已在用的 `flush_dcache64(pa,len,TRUE)`（0300 patch `:660` 先例；声明 `osfmk/arm/caches_internal.h:43`）。
- read-back：`k60_adsp_verify()`（`patches/xnu/0613-k60-adsp-pas.patch:317`）逐段 `memcmp` 窗口与
  blob 原文（零额外 49 MB），bss 逐字节扫 0；不等即 `K60PAS verify mismatch`，不进 auth。

## 2 构建与产物

| 项 | 值 | 证据 |
| --- | --- | --- |
| 构建命令 | `scripts/build-strict.sh carrier-20261117c --fd .../baseline-20261116a-cf4485712c29.fd --adsp-blob /mnt/e/k60-work/firmware/adsp --kernel-arg pong_adsp_carrier=1` | `k60-work/artifacts/carrier-20261117c/logs/` |
| 设备输入 | `/home/emilelu/charger-carrier/device`（共享树 2026-11-17 01:00 快照的私有镜像，789 文件与仓库同步） | `HEAD=70a1e4ca361a1116bc0ec1563bac74771c79f81c`、`git diff` sha256 `56697fe6a64b4e3f276f3d73ad240515a2db3fef369b1a8304d52ab26d1ca511` |
| ADSP 容器 | 26 个 adsp.* 文件，`sha256 663369461a9def3105884b34a574c119aaa2b95111c185a6f12de34158bcd319` | `artifacts/carrier-20261117c/adsp-carrier/k60_adsp_blob.bin` |
| kernel | `sha256 5bb7f4c8e6f64929a43395c282c9a8c50373bce51f07aaf9741723d828165099`，129,048,576 B（a `29a7097f…`、b `a77cbb76…`、c `5bb7f4c8…`；以 manifest 为唯一真值） | `build-manifest.json` `components.kernel_built` |
| kernel 字符串复核 | `K60PAS carrier` ×6、`K60PAS auth ok` ×1、`K60PAS carrier verdict` ×2、`pong_adsp_carrier` ×1（2026-11-17 04:12 对 c 的 kernel.macho 复核） | `strings -a /opt/k60/trees/k60build/out-charger-carrier/mondrian/ipados-16.6.1-20G81/mondrian/kernel/kernel.macho` |
| payload | kernel `020e79a64dd7c70ca947fb55adf8a99362b0d952cfb7ac8dbdaed7c2c43cad4f`、adt `1097f85c79886ee484ab0e5888a9781a0ce3df8b39864dd26b290bd7c20f40c9`、payload `9ab8b05cc55c2427f24a76042f8b42d893d87ee48cde4ba0c55f7f1c17ccfe4a` | `build-manifest.json` `components.payload*` |
| boot.img | `sha256 c484aa059309eea5459505c9e871779fc2aa2d23411a33762b4dbb076c802e78` | `build-manifest.json` `components.boot_img`；`verify-boot-image.py --manifest` 通过 |
| 电池存档 | `sha256 406942a1682d3f1141b827381ce442ebeb25547eda0789920bcef91363422e77` | 构建日志 `battery archive` |
| 八步门禁 | `build-strict: eight-step 通过 36 项检查`；冻结输入 `d408222162f4e3429b6a3eeb2cfd3a1a48c8b2bcf833787eef539a48649741db` | `logs/eight-step.log` |
| 镜像参数 | 30 args / 595 B，末项 `pong_adsp_carrier=1`；`image-arg-audit: OK (30 arguments, 595 bytes)` | `logs/image-arg-audit.log` |

`carrier-20261117a`（boot.img `149b0b0d…`）和 `carrier-20261117b`（`092a2d5f…`）均已被 c 取代：
a 的 SMC wrapper 缺 x4–x7 与 x8–x17 的 caller-saved 约束；b 的 `/chosen` 区域覆盖解析把
device-tree cell 按本机端序读，真实覆盖会被误读/忽略。c 包含 `d7fdff4d` 的 big-endian 修复，
manifest 的 `repo.head` 是 `d7fdff4d`。上机只用 c。

## 3 上机步骤（Lead 执行）

执行前置：0614 的 carrier 块位于 `native_owner_data_prepare()` 的 `if (error) goto done;`
（K60DATA mount 成功）之后（patched `bsd/kern/kern_exec.c:7892-7920`）。Data mount 失败时
carrier 不会执行，日志里只有 `K60DATA mount returned error=`，按 §0.1 C0 判 INVALID，
不计入 D4 的两次 ADSP 尝试（没有发生任何 SCM 调用）。

1. `bash scripts/k60-device.sh state` 确认识别到设备；`fastboot boot /mnt/e/k60-work/artifacts/carrier-20261117c/boot.img`，绝不 `flash`。
2. 采集：`record-boot.py`（console.log 落 `k60-work/evidence/usblog-<ts>/`）。
3. 判读：`python3 scripts/judge-battery.py --log <evidence dir>` 先跑 C1/C2 基础三态
   （契约就是 07-DEVICE-CRITERIA §0；本例会因无 lease 判 INVALID，那是预期的），
   然后按 §0.1 的表人工判 C0–C4 —— 判据行见本文件，不看别的。
4. 把 console.log 路径 + 判决贴回 reply md。

## 4 失败形态处置

| 日志行 | 含义 | 下一步 |
| --- | --- | --- |
| `K60DATA mount returned error=` 且无 `K60PAS carrier begin` | Data 未挂载，carrier 钩子未执行 | 按 C0 INVALID 记，不计 D4；先查 Data mount，不查 ADSP |
| `K60PAS carrier absent rc=` | 内核里没有 blob（0620 没进镜像） | 查 manifest `adsp_blob`，不是 ADSP 问题 |
| `K60PAS cannot map the carveout` | 0x9fd00000 不可映射 | 查 FDT adsp_region 是否被别的驱动占 |
| `K60PAS init refused rc=-4` | SCM 拒绝 INIT_IMAGE（PAS 不放行） | 立即记 FAIL，按 D4 止损 |
| `K60PAS auth refused rc=-4` | SCM 拒绝 AUTH_AND_RESET | 同上，这是本实验最可能的 FAIL 形态 |
| `K60PAS auth refused rc=-12` | EBUSY 用尽 20 次重试 | 查是否有别的 PIL 客户端在跑；可再给一次机会（D4 允许 2 次） |
| `K60PAS verify mismatch <part> at window+0x...` | 放置/读回不一致 | 我们的 bug，不是 SCM；修完再来 |
| `K60PAS metadata phys=` 后无 init 行 | kmem/PA 问题 | 把 rc 抄回来 |
| panic（`panic(cpu` 或 `esr=`） | 触碰了未映射页 | 贴首 20 行，按 D4 记一次失败 |

## 5 未闭合项清账表（上机前必须为空）

| # | 项 | 状态 | 依据 |
| --- | --- | --- | --- |
| 1 | 0613/0614 与 0619 的 hunk 关系 | 已闭 | 0614 的 carrier 块插在 0619 的 `{` 之前，0619 未改；`check-patch-apply` 全绿（227 patches applied） |
| 2 | boot-arg 只能被有容器 manifest 的镜像使用 | 已闭 | `verify-boot-image.py:85`；自测 6 例；`check-image-args.py` 已登记，自测 8 例 |
| 3 | 目的地址 = 板级 carveout 而非链接地址 | 已闭 | 三常量 + 单测 + `plan.base` 断言 |
| 4 | copy 后 cache 一致性 | 已闭 | `flush_dcache64` 先例（0300:660）与 cacheable 证明（memory_types.h:41-43） |
| 5 | SCM EBUSY/INTERRUPTED 语义 | 已闭 | 常量与调用形状来自 pong 工作实现；单测断言常量 |
| 6 | 旧 `pong_adsp` 路径仍可能被误开 | 已闭 | 门禁拒 `pong_adsp=1`；`pong_adsp_carrier` 独立 |
| 7 | DTB PAS 36 | NOT-IN-SCOPE | 本实验只回答 ADSP PAS 1；pong 的成对 shutdown 记录为差异 |
| 8 | SMEM TOC / SMP2P 就绪时间 / remote_restart_flag / tx-rx 4096 | NOT-IN-SCOPE | 属 lease 之后；HANDOFF-PUBLISH-SPEC §11 已列 |
| 9 | 采样器访问许可域 | NOT-IN-SCOPE | adsp-20261115e 之后由 adsp 线证明；本实验不读电池 |
| 10 | carrier 钩子的可达性（Data mount 前置） | 已闭 | `native_owner_data_prepare()` 在 `mount` 成功后才执行 0614 carrier 块（patched `bsd/kern/kern_exec.c:7892-7920`）；§3 前置与 §4 失败形态已写死 |
| 11 | `/chosen qcom,adsp-region` 覆盖的 cell 端序 | 已闭 | `k60_adsp_cell()` 按 big-endian 解码 2/4 cell（`patches/xnu/0613-k60-adsp-pas.patch:279`）；真机 FDT 无该属性时走默认 `0x9fd00000/0x3100000`（`d7fdff4d`） |

## 6 ADC 兜底预研（D5，只取证不写驱动）

结论摘要（全文 `E:/k60-work/scratch/charger-adc-fallback.md`，162 行）：

- 真机 FDT 有 `vadc@3100`（compatible `qcom,spmi-adc7`，FDT:16681-16690），电池通道齐全：
  `vbat_sns` reg 0x38f、`usb_in_v_div_16` 0x311、`ichg_fb` 0x3a1、`chg_temp` 0x310、`die_temp` 0x303。
- 端口已有真机验证过的 SPMI arbiter 读写（`patches/xnu/0308-...` / `0334-...`，
  `K60_SPMI_CORE_PA 0x0C400000`，observer/channel 窗口，`console.log:188/256` 的 restart-reason 写入成功）。
- FDT 全树无 fg/fuel/qg 节点；Android 的 SOC 来自 `[ADSP] fg_update_status`（dmesg:2）→
  无 ADSP 时 **SOC 必须标 unknown**，不得编造。UEFI 侧只有 ABL 二进制，无传给 XNU 的接口。
- 推荐两步：先做零写风险只读探针（PPID 0x031 的 apid + STATUS1/APP_SID/EN_CTL1，约 100–150 行），
  再实现 ADC7 配置/转换（vbat_sns + usb_in_v_div_16 为主，约 300–400 行）；
  代价与 4 个 not-proven（PPID 0x031 映射、EOC 轮询、ichg 换算、VADC 校准）见原文。

## 7 证据归档

- 构建：`/mnt/e/k60-work/artifacts/carrier-20261117c/`（manifest、logs、adsp-carrier/）。
- 上机：`/mnt/e/k60-work/evidence/usblog-<ts>/console.log`（Lead 采集）。
- 判读结果按 §0.1 表逐行贴回 `E:/k60-work/scratch/reply-charger-20261115.md`。
