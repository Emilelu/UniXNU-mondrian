# 04 · Android 侧现场取证（K60 / mondrian / SM8475）

本文件记录**从运行中的 Android 系统与 vendor_boot 分区读到的现场证据**，用来补 ③（反编译）的
第二条腿：01 篇的证据是 UEFI 平台加载的那份 DTB，本篇的证据是设备 6033dbec 上真实跑着的东西。
每条都给可复现的采集命令与产物 sha256。厂商二进制里读到的事实，一律注明"偏移/行号"，不写推测。

设备侧采集由 Lead 执行（adb root，uid=0，SELinux `u:r:ksu:s0`），产物与原始 README 在
`E:/k60-work/evidence/thermal-android-20261114/`（WSL `/mnt/e/k60-work/evidence/thermal-android-20261114/`）。
本篇只引用该目录里已落盘的文件，不引用"当时看到过"的屏幕内容。

## 0. 产物清单与校验

| 文件 | 大小 | sha256 | 说明 |
|---|---|---|---|
| `zones.txt` | 84 行 | `08fa32b503dc8601628697ffeafbb507752a48213b1c9d6ea00a2465c64d08e5` | /sys/class/thermal 全部 zone 的 `zone\|type\|temp` |
| `drivers.txt` | 19 行 | `59ab39e9f1b57702f77c4eea455bcb9749238a191db7b2426a589066cc18bb47` | /sys/bus/platform/drivers + /proc/modules 节选 |
| `tsens-symbols.txt` | 60 行 | `318577190923a72b977bdc67a13385a47f58c6e7b8684649bf8e7f52be0da20f` | /proc/kallsyms 里 qcom_tsens 相关行 |
| `qcom_tsens.ko` | 77928 B | `22334f6d246cf1b67e238027a2d04ac19b588d47d73301bb7577c2dc9c6981a9` | 从 vendor_boot ramdisk 取出（§4） |
| `vendor_boot.dts` | 618636 B | `decf8fc5863aea74796df78ec484157c648a10e6077733c2cae0270d452fc897` | vendor_boot 里那份 DTB 的反编译 |
| `uefi-vs-vendorboot.dts.diff` | 465 B | — | 与 `/mnt/e/k60-work/scratch/mondrian.dts` 的差异（§7） |
| `thermal-engine.conf` | 84 B | `c32b39af7a19759a7db7f8b2d92d069a0534848aa7a195ca2cec24aa6c317cb3` | 明文，内容见 §6 |
| `thermald-devices.conf` | 2266 B | `d1b129f1ef37ac4efc584ee14cdff1e56c14a17e1cf70fbf04523407ad63df92` | 明文 |
| `thermal-map.conf` / `thermal-normal.conf` / `thermal-phone.conf` | 7504 / 4464 / 2176 B | `50e9f3f1…` / `53f2c122…` / `26ed2f35…` | 厂商加密二进制，未解（§6） |

采集命令（设备侧，只读；Lead 执行）：

```sh
for z in /sys/class/thermal/thermal_zone*; do
  printf '%s|%s|%s\n' "${z##*/}" "$(cat $z/type)" "$(cat $z/temp 2>/dev/null)"
done > zones.txt
cat /sys/bus/platform/drivers/*/uevent >/dev/null 2>&1   # 驱动名清单
ls /sys/bus/platform/drivers > drivers.txt
sed -n '1,200p' /proc/modules >> drivers.txt
grep -i tsens /proc/kallsyms > tsens-symbols.txt
```

## 1. 运行时有 84 个 thermal zone，而 DT 只描述 58 个 —— 两个数字不相等

`zones.txt` 共 84 行（`thermal_zone0` … `thermal_zone83`）。按数据来源拆分：

| 类别 | 个数 | zone 号 | 来源 |
|---|---|---|---|
| AP tsens 直读 | **32** | 24–55 | `qcom_tsens`（DT `thermal-sensor@c263000` / `@c265000`） |
| QMI 远端 | 25 | 0–23、56 | `qmi-ts-sensors`（DT phandle 0x5c，需 QRTR/GLINK） |
| PMIC（spmi-temp-alarm） | 6 | 57、58、62、69、70、71 | 来自 dtbo overlay，不在主 DTB |
| BCL | 8 | 59–61、63–67 | 同上（bcl_pmic5 / bcl_soc） |
| 小米虚拟（mi_thermal_interface） | 9 | 72–80 | 厂商私有 ko，非 DT |
| `socd` | 1 | 68 | 厂商私有，trip 单位是 100 不是 m°C |
| 电池/充电 | 3 | 81–83 | `vbat` / `battery` / `usb` |

即 **84 = 32 + 25 + 6 + 8 + 9 + 1 + 3**。DT 的 58 个 `thermal-zone` 里，`mx-pe`（`mondrian.dts:8335`）
在 DT 里就是 `status = "disabled"`（`mondrian.dts:8336`），运行时确实不存在；剩下 26 个运行时 zone
（PMIC/BCL/小米虚拟/电池）根本不在主 DTB 里，是 overlay 与厂商 ko 注册的。

> **结论（对 01 篇的补充）**：01 篇 §5 的"58 个 zone"是 **DT 描述数**，本篇的 84 是 **运行时注册数**。
> 两个数字都对，但不是同一个量，不能互相校验。可以互相校验的只有 AP tsens 的 32 个：
> DT §5.1 的 32 行索引表与 `zones.txt` 的 zone24–55 逐项一致（名字与顺序完全对应，见 §2）。
> 这条是 01 篇传感器索引表的**独立第二来源**。

## 2. 32 个 AP 传感器：zone24–55 与 DT 索引表逐项吻合

`zones.txt`（温度单位 m°C，采集时的静置值）：

| zone | 名字 | 温度 | 控制器 / DT 索引 |
|---|---|---|---|
| 24 | aoss-0 | 54900 | tsens0 idx 0 |
| 25–28 | cpuss-0..3 | 65300 / 60900 / 61300 / 60500 | tsens0 idx 1..4 |
| 29–37 | cpu-1-0..8 | 58100 / 67700 / 60500 / 65300 / 62500 / 70400 / 66100 / 67300 / 60500 | tsens0 idx 5..13 |
| 38–39 | gpuss-0/1 | 53700 / 53700 | tsens0 idx 14..15 |
| 40 | aoss-1 | 55500 | tsens1 idx 0 |
| 41–44 | cpu-0-0..3 | 60600 / 61400 / 60200 / 60600 | tsens1 idx 1..4 |
| 45–47 | nspss-0..2 | 53900 / 49100 / 51100 | tsens1 idx 5..7 |
| 48 | video | 55500 | tsens1 idx 8 |
| 49 | ddr | 52700 | tsens1 idx 9 |
| 50–53 | mdmss-0..3 | 51900 / 48300 / 49900 / 49500 | tsens1 idx 10..13 |
| 54–55 | camera-0/1 | 50300 / 50300 | tsens1 idx 14..15 |

两点直接后果：

1. **2 控制器 × 16 = 32 得到运行时确认**，不是靠 DT 单方面断言（`mondrian.dts:16441`、`:16451` 的
   `#qcom,sensors = <0x10>`）。任务书里"8 个传感器"是错的（01 篇 §9 已记）。
2. **DT 的 `thermal-sensor-cells` 参数就是控制器内的传感器序号**：zone 顺序 = tsens0 idx0..15 紧接
   tsens1 idx0..15，与 01 篇 §5.1 的表逐行一致。所以 `K60Tsens.c` 的静态表可以直接照这张表写。

## 3. 现场 trip 点：与 DT 完全一致（含一处常见误读）

从 `/sys/class/thermal/thermal_zone*/trip_point_*_temp` 读到的值：

- `aoss-0` / `cpuss-0` / `video`：trip0 = 125000、trip1 = 115000；
- `ddr`：trip0 = 125000、**trip1 = 90000**、trip2 = 115000；
- `zone68`（`socd`，非 tsens）：trip 读数是 `100`，**是它自己的单位，不是 m°C**，不能混进 tsens 表。

与 DT 对照（01 篇 §5.1）：`thermal-engine-config` = 125℃（`0x1e848`）、`reset-mon-cfg` = 115℃
（`0x1c138`）、`ddr0-config` = 90℃（`mondrian.dts:8009` 的 `0x15f90`）、CPU 的 `cpuX-emergN-cfg` = 110℃
（`0x1adb0`，见 `mondrian.dts:7239` 等 13 处）。**现场值与 DT 逐项相同**，说明 vendor_boot 的
fdt 与我们 UEFI 加载的 DTB 同源（§7 的反编译 diff 也独立证明了这点）。

需要纠正的一个说法：曾有"ddr 的中间那档其实是 110℃、Lead 记错了"的说法。DT 与现场都表明
**ddr 中间档是 90℃，而 110℃ 是 CPU 核的 emergN 档，两者并存**，不是同一个 trip。

## 4. 驱动是一个可加载模块，且不在 /vendor 里

`drivers.txt`：

- `/sys/bus/platform/drivers` 含 `qcom-tsens`、`thermal_pause`（另有 `hisi_thermal`、`qti_*` 等）。
- `/proc/modules`：`qcom_tsens 57344 0 - Live`，另有 `bcl_soc`、`bcl_pmic5`、`thermal_pause`、
  `mi_thermal_interface`。→ **tsens 驱动是 .ko，不是 built-in**。
- `/vendor` 与 `/vendor_dlkm` 共 314 个 .ko（erofs 只读）里都没有 `qcom_tsens.ko`；
  `find /` 只命中 `/sys/module`。→ 它在 **vendor_boot ramdisk** 的 `lib/modules/qcom_tsens.ko`。

取出路径（只读 dd，不写任何分区）：

```sh
dd if=/dev/block/by-name/vendor_boot_a of=/data/local/tmp/vb.img     # = sde25
# 100663296 B, sha256 e7d4febe3c5a6f614e0c5d1efbd2f4d7584dbe2a4a4f810b2c8e22f351d1f3a2
# VNDRBOOT v4, page 4096, header 2128, vendor_ramdisk_size 23714085,
# dtb_size 6443651 @ 23719936；ramdisk 是 legacy LZ4（magic 0x184c2102），7 块 → 54968576 B
# 解 cpio 必须在 /tmp 下做（drvfs 上解 55 MB 会卡到分钟级）
```

`/proc/kallsyms` 里 qcom_tsens 只有 `$d.N`/`$x.N` 局部符号（`tsens-symbols.txt`），
所以**不能**从 kallsyms 反推结构；但 ko 本体是 `not stripped` 的，符号齐全（§5）。

## 5. qcom_tsens.ko 逆向：三条硬结论

ko：77928 B，`ELF64 aarch64 relocatable`，**not stripped**，145 个已定义符号 / 49 个未定义符号，
BuildID `c304fa9cf3d125c8cd6a16c7c84616e950467bb6`，
`vermagic=5.10.160-gki-gf555d54c041a SMP preempt mod_unload modversions aarch64`，
`depends=qcom_ipc_logging`，描述 "QCOM Temperature Sensor driver"。

复现命令（WSL，llvm 工具链）：

```sh
llvm-nm --defined-only qcom_tsens.ko
llvm-objdump -s -j .rodata qcom_tsens.ko
llvm-objdump -d --no-show-raw-insn qcom_tsens.ko | sed -n '/<get_temp_tsens_valid>:/,/^$/p'
readelf -rW qcom_tsens.ko | grep -E 'qfprom_read|nvmem_cell'
strings -a qcom_tsens.ko | grep -E 'alias=of:'
```

### 5.1 它就是上游 Linux 驱动，没有小米私有改写

已定义符号里有 `init_common`、`tsens_probe`、`get_temp_tsens_valid`、`get_temp_common`、
`tsens_set_trips`、`tsens_read_irq_state`、`tsens_get_temp`、`tsens_get_trend`、`tsens_suspend`/`tsens_resume`、
`qfprom_read`、`compute_intercept_slope`、`calibrate_v1`、`calibrate_8916/8939/8960/8974/8976`、
`init_8960/enable_8960/disable_8960/suspend_8960/resume_8960`、`ops_generic_v2`、`data_tsens_v2`、
`tsens_v2_feat`、`tsens_v2_regfields`、`tsens_srot_config`、`tsens_config`、`tsens_table` ——
与 `/mnt/e/k60-work/scratch/refs/tsens.c`、`tsens-v2.c` 的符号集合一一对应。
modinfo 的 7 个 alias 只有 `qcom,msm8916/8939/8974/8976/8996-tsens`、`qcom,tsens-v1`、`qcom,tsens-v2`，
**没有 sm8475 专属 alias** → 本板走 `"qcom,tsens-v2"` fallback，与 02 篇 binding 的枚举一致
（`qcom-tsens.yaml:55-68` 里只有 sm8450/sm8550，没有 sm8475）。

### 5.2 寄存器表：厂商二进制里的独立第三来源

`.rodata` 的 `tsens_v2_regfields`（`:0xff0`）里，逐传感器的 `LAST_TEMP` 字段是
`(offset = 0xa0, 0xa4, 0xa8, 0xac, 0xb0, 0xb4, 0xb8, 0xbc, 0xc0, … , width = 0x0b)`：

```
 0ff0 00000000 1c000000 1f000000 00000000   <- 字段表头部（SROT 版本/使能）
 ...
 10a0 00000000 a0000000 00000000 0b000000   <- LAST_TEMP[sensor0] = off 0xa0, width 11
 10b0 00000000 00000000 a4000000 00000000   <- sensor1 = 0xa4
 10c0 0b000000 00000000 00000000 a8000000   <- sensor2 = 0xa8
```

即 **TM_Sn_STATUS = 0xa0 + 4n，位宽 12（[11:0]）**，与上游 `tsens-v2.c:94-101`
（`REG_FIELD_FOR_EACH_SENSOR16(LAST_TEMP, TM_Sn_STATUS_OFF, 0, 11)`、`VALID` 在 21、
`MIN/LOWER/UPPER/CRITICAL/MAX` 在 16..20）逐字段相同。这是**除了 DT 与上游源码之外的第三个独立来源**，
证明 02 篇 §2 的偏移表在本板厂商内核里也是这么用的。

`.data:0x100` 的 `tsens_v2_feat` 三个字 = `0x2 / 0x5 / 0x10`（hw_version = VER_2_X、字段位序、
`max_sensors = 16`），`.data:0x110` 的 `data_tsens_v2` 全零（不设 `num_sensors`，由 DT
`#qcom,sensors` 决定），与 `tsens-v2.c:31-40`、`:107-116` 一致。

### 5.3 读数路径：adc=0 分支，状态字直接 ×100

`get_temp_tsens_valid`（`.text:0x588`）反汇编的关键段：

```
 5f0: ldr  w8, [sp]            ; regmap_field_read(VALID)
 5f4: cbnz w8, 0x614           ; 已 valid 就不等
 5f8: mov  w0, #0x7d0          ; = 2000 → __const_udelay(2000)
 ...
 648: ldrb w8, [x8, #0x4]      ; feat 的第 5 个字节
 64c: tbnz w8, #0x1, 0x668     ; bit1 == adc
 650: sub  w8, w25, w24        ; resolution - ...  (12 位)
 654: add  w8, w8, #0x1f       ; 31
 658: lsl  w9, w9, w8
 65c: asr  w8, w9, w8          ; 符号扩展
 660: mov  w9, #0x64           ; = 100
 664: b    0x6b4               ; → mul w0, w8, w9  (×100)
 668: ...                      ; adc=1 分支才走 slope/offset (madd/sdiv)
```

即：本板 `adc = 0`，走"状态字按 12 位符号扩展后 ×100 = 毫摄氏度"，**与上游 `tsens.c:346-347` 的
`sign_extend32(temp, resolution) * 100` 完全同一条路径**。这也是 `K60Tsens.c` 里
`k60tsens_status_to_mc()` 的出处。

### 5.4 标定：代码在，但本板不走 —— 关键负结论

ko 里**确实带**完整的 Linux 标定机器：

- strings：`%s: calibration failed`、`calib`、`calib_backup`、`calib_sel`、`#qcom,sensors`；
- 未定义符号：`nvmem_cell_get` / `nvmem_cell_read` / `nvmem_cell_put`、`qfprom_read`；
- `readelf -rW` 里有 **9 处 `qfprom_read` 的 `R_AARCH64_CALL26` 重定位**（`:0x2210`、`:0x248c`、
  `:0x283c`、`:0x2858`、`:0x2a70`、`:0x2c94`、`:0x2cb0`、`:0x331c`、`:0x3334`）与
  3 处 `nvmem_cell_*` 调用（`:0x390`、`:0x3a8`、`:0x3b4`）。

**但本板没有标定源**：

- UEFI DTB 上 `grep -cE "qfprom|efuse|nvmem"` = **0**（`/mnt/e/k60-work/scratch/mondrian.dts`，21954 行）；
- 设备上活节点 `/proc/device-tree/soc/thermal-sensor@c263000/` 只有 `#qcom,sensors`、
  `#thermal-sensor-cells`、`compatible`、`interrupt-names`、`interrupts`、`name`、`phandle`、`reg`
  八个属性，**没有 `nvmem-cells`，也没有 `qcom,tsens-calibration`**；
- 上游 binding 里 nvmem 也**不是必需项**（`qcom-tsens.yaml:222-227` 的 required 只有
  compatible/interrupts/interrupt-names/#thermal-sensor-cells/#qcom,sensors）。

**结论**：这份 ko 是为 8916/8939/8960/8974/8976/8996/v1/v2 一锅端编的同一个驱动（alias 就是证据），
标定代码在本板上根本没被走到（没有 cell 可解析）。而 v2 IP 在 `adc=0` 时的读数路径本身不需要
标定系数（§5.3），所以：

> **只读 PongThermal 驱动不需要任何标定系数。** 需要标定的只有"我们自己去写硬件阈值"那条路
> （`tsens_set_trips` → `degc_to_code()`，`tsens.c:290-315`），本阶段明确不做。

这条同时解释了 01 篇 §4 的"DT 无标定属性"为什么不是阻塞项。

## 6. 厂商用户侧热管理（仅背景，不是移植目标）

`/vendor/etc` 下 36 个 `thermal-*.conf`：

- `thermal-engine.conf` 84 字节，内容 `# File empty by default` → **本机不用 thermal-engine，用 thermald**；
- `thermald-devices.conf`（2266 B）是明文，已落盘；
- `thermal-map.conf` / `thermal-normal.conf` / `thermal-phone.conf` 是厂商加密二进制
  （xxd 头 `01f8 9f93…`，无 gzip 头，strings 无明文）→ **记为未解，不再投入**。移植不依赖它们。

## 7. vendor_boot 的 DTB 与 UEFI 的 DTB 实质相同

把 vendor_boot 里的 dtb（6443651 B @ 偏移 23719936）单独反编译后与
`/mnt/e/k60-work/scratch/mondrian.dts` 做 diff，**只有一个 15 行的 hunk，全在根节点**：

```diff
-model = "Qualcomm Technologies, Inc. Cape SoC";
-compatible = "qcom,cape";
-qcom,msm-id = <0x212 0x10000>;
+model = "Qualcomm Technologies, Inc. Cape LTE Only SoC";
+compatible = "qcom,cape-v2";
+qcom,msm-id = <0x21c 0x10000>;
```

其余全部相同：`thermal-sensor@c263000` 在 `:16438`、`thermal-sensor@c265000` 在 `:16448`、
`aliases` 的 `tsens0`/`tsens1` 在 `:21890`/`:21891`、`thermal-zones` 命中 33 次 —— 与
`vendor_boot.dts` 的行号逐行一致。

**后果**：01 篇基于 UEFI DTB 得出的全部 thermal 事实，对运行中的 Android 系统同样成立；
Android 侧的 DT **不是**更丰富的来源，也无法回答标定问题（§5.4）。

## 8. 这些证据让哪些"未解"变成了"已解"

| 之前的缺口 | 现在的状态 |
|---|---|
| vendor tsens 驱动本体（③ 缺的第 1 项） | **已取得**：`qcom_tsens.ko`，not stripped，符号/寄存器表/读数路径全部可引（§5） |
| 标定属性有无 | **已确认无**，且证明 v2 只读路径不需要（§5.4） |
| 32 个传感器是否真在跑 | **已确认**：zone24–55 全部有非零读数（§2） |
| DT 的 trip 是否就是现场 trip | **已确认**：逐项相同（§3） |
| Android 侧 DT 是否与 UEFI 不同 | **已确认**：只差根节点 model/compatible/msm-id（§7） |
| `/vendor/etc/thermal-engine*.conf`（③ 缺的第 2 项） | **部分**：`thermal-engine.conf` 为空（本机不用它）、`thermald-devices.conf` 明文已取；`thermal-map/normal/phone.conf` 厂商加密未解 |

## 9. 仍然缺什么（③ 因此保持 done = false）

1. **SROT 的现场值**：`SROT_HW_VER`（`0xc222000+0x0`）与 `SROT_CTRL`（`+0x4`，bit0 = TSENS_EN）从未被读过。
   上游 `tsens.c:974-979` 在 `TSENS_EN == 0` 时直接 `-ENODEV`，所以这是上机第一条要确认的事实。
   读它需要内核态 MMIO（Android 上没有现成接口），只能等 ⑦⑧ 阶段由我们自己的代码读。
2. **32 个 STATUS 的 VALID 位现场快照**：Android 侧只给了换算后的温度，没给原始状态字，
   因此"bit21 是否全为 1"仍属未验证。
3. **厂商加密的三份 thermal-*.conf**：未解，且判定为与移植无关（§6），不再投入。
4. 本阶段仍**禁上机**，上述 1、2 都只能等 Lead 批准 ⑦⑧ 之后做。

## 10. 与本阶段代码的对应关系

- `drivers/PongThermal/K60Tsens.h` / `K60Tsens.c`：只读驱动，偏移出自 §5.2 与 02 篇 §2，
  换算出自 §5.3 与 `tsens.c:346-347`，传感器表出自 §2（= 01 篇 §5.1）。
- `scripts/tests/test-k60-thermal-tsens.c`：纯函数 + 假 TM 窗口的主机单测（16 组断言全过），
  覆盖 VALID 缺失、越界拒绝、负温度符号扩展、`0xa0+4n` 字索引、表长/名字/zone 号。
- 驱动**不写任何寄存器**、不开中断、不碰 SROT —— 与 Lead 给的边界一致，也与
  `hakios.thermal.c:5-13`、`ThermalProbe.cpp:5` 两个同族实现的做法一致。
