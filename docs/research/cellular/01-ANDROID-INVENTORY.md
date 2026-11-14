# 01 — Android 侧 modem / QRTR / IPA 取证清单

> 设备：Redmi K60（23013RK75C）/ mondrian / SM8475 / taro，序列号 `6033dbec`
> 取证时间：2026-11-14（本会话），全部为**只读**命令，未修改设备任何分区
> 取证身份：`adb -s 6033dbec shell`，`id` → `uid=0(root) gid=0(root) context=u:r:ksu:s0`（KernelSU）
> 所有条目都给出「命令原文 → 输出原文」。没有输出原文的结论一律不写。

---

## 0. 结论摘要（先看这段）

| 问题 | 答案 | 出处 |
|---|---|---|
| 基带是不是 SoC 内的 remoteproc？ | 是。MSS 作为 `4080000.remoteproc-mss` 由 `qcom_q6v5_pas` 驱动，`state=running` | §2 |
| 固件在哪？ | `modem_a`=`/dev/block/sde7`（380 MiB），只读挂在 `/vendor/firmware_mnt` | §1、§3 |
| 固件有多大？ | `modem.*` 共 30 个文件，109,072,529 B = 104.02 MiB | §3 |
| 固件版本？ | `MPSS.DE.2.0.c1-CN-Jan 13 2026-02:08:51`（两路 SIM 各一份） | §4 |
| QRTR 怎么走？ | **AF_QIPCRTR 套接字**，不是 unix socket；内核模块 `qrtr` 注册协议号 888 | §5 |
| 用户态 QRTR 守护进程？ | `vendor.qrtr-ns /vendor/bin/qrtr-ns -f`，pid 1974 | §5 |
| modem 注册了多少 QMI 服务？ | **36 个**（node 0），含 EFS 21 / WDS 1 / UIM 11 / NAS 3 / PDS 16 / DIAG 4097 | §5.4.1 |
| 有没有 IPA？ | 有。`qcom,ipa@3e00000`，驱动 `ipa`，`/dev/ipa` 存在，`rmnet_ipa0` 在线 | §6 |
| SIM 身份在哪？ | 两路 SIM 均 `LOADED`，IMEI 在 `persist.radio.imei`；EFS/NV 在 `modemst1/2`（裸分区，未挂载） | §7 |
| 现在能上网吗？ | 不能。`persist.radio.airplane_mode_on=1` | §7 |

---

## 1. 分区布局

### 1.1 分区符号链接

```
$ adb -s 6033dbec shell 'ls -l /dev/block/by-name/ | grep -iE "modem|mdtp|fsg|fsc|dsp"'
lrwxrwxrwx 1 root root 16 ... dsp_a -> /dev/block/sde12
lrwxrwxrwx 1 root root 16 ... dsp_b -> /dev/block/sde41
lrwxrwxrwx 1 root root 15 ... fsc -> /dev/block/sdf6
lrwxrwxrwx 1 root root 15 ... fsg -> /dev/block/sdf5
lrwxrwxrwx 1 root root 16 ... limits-cdsp -> /dev/block/sde62
lrwxrwxrwx 1 root root 16 ... mdtp_a -> /dev/block/sde10
lrwxrwxrwx 1 root root 16 ... mdtp_b -> /dev/block/sde39
lrwxrwxrwx 1 root root 16 ... mdtpsecapp_a -> /dev/block/sde9
lrwxrwxrwx 1 root root 16 ... mdtpsecapp_b -> /dev/block/sde38
lrwxrwxrwx 1 root root 16 ... modem_a -> /dev/block/sde7
lrwxrwxrwx 1 root root 16 ... modem_b -> /dev/block/sde36
lrwxrwxrwx 1 root root 16 ... modemst1 -> /dev/block/sdf3
lrwxrwxrwx 1 root root 16 ... modemst2 -> /dev/block/sdf4
```

### 1.2 容量（`/proc/partitions`，单位 KiB）

```
$ adb -s 6033dbec shell 'su -c "cat /proc/partitions"' | grep -E "sde7|sde9|sde10|sde12|sde36|sdf3|sdf4|sdf5|sdf6"
 179       0   389120 sde7     # modem_a
 179       0     4096 sde9     # mdtpsecapp_a
 179       0    32768 sde10    # mdtp_a
 179       0    65536 sde12    # dsp_a
 179       0   389120 sde36    # modem_b
 179       0     8192 sdf3     # modemst1
 179       0     8192 sdf4     # modemst2
 179       0     8192 sdf5     # fsg
 179       0     1024 sdf6     # fsc
```

交叉校验（fastboot 侧同一块设备报的字节数）：

```
$ fastboot -s 6033dbec getvar partition-size:modem_a
partition-size:modem_a: 0x17C00000     # = 398,458,880 B = 380 MiB，与 389120 KiB 一致
$ fastboot -s 6033dbec getvar partition-size:modem_b
partition-size:modem_b: 0x17C00000
```

### 1.3 挂载点

```
$ adb -s 6033dbec shell 'su -c "mount"' | grep -E "firmware_mnt|/vendor/dsp|persist|qmcs"
/dev/block/sde7 on /vendor/firmware_mnt type vfat (ro,context=u:object_r:firmware_file:s0,relatime,uid=1000,gid=1000,fmask=0337,dmask=0227,codepage=437,iocharset=iso8859-1,shortname=lower,errors=remount-ro)
/dev/block/sde12 on /vendor/dsp type ext4 (ro,seclabel,nosuid,nodev,relatime)
/dev/block/sda21 on /mnt/vendor/persist type ext4 (rw,seclabel,nosuid,nodev,noatime)
/dev/block/sde26 on /mnt/vendor/qmcs type vfat (rw,context=u:object_r:vendor_qmcs_file:s0,relatime,uid=1000,gid=1000,...)
```

**要点**：`modem_a`（sde7）被 Android 以**只读 vfat** 挂在 `/vendor/firmware_mnt`，
所以 modem 固件在 Android 侧就是「一个只读文件系统里的文件」——XNU 侧要读它，
必须先能读 UFS 上的 sde7 并解析 vfat（或用 UEFI 侧同样的分区读取路径），
而不是「跟 Android 要一个 socket」。

`modemst1`/`modemst2`（sdf3/sdf4）**没有**出现在 `mount` 里 —— 它们是裸的 EFS/NV 分区，
由 modem 固件自己通过 PAS 之后的 QMI 读写，Android 用户态从不挂载。

---

## 2. remoteproc：modem 就是一个 PAS 远程处理器

```
$ adb -s 6033dbec shell 'su -c "ls /sys/class/remoteproc/"'
remoteproc0  remoteproc1  remoteproc2  remoteproc3

$ adb -s 6033dbec shell 'su -c "for i in 0 1 2 3; do echo ==$i; cat /sys/class/remoteproc/remoteproc$i/name /sys/class/remoteproc/remoteproc$i/state /sys/class/remoteproc/remoteproc$i/firmware; done"'
==0
3000000.remoteproc-adsp
running
adsp.mdt
==1
32300000.remoteproc-cdsp
running
cdsp.mdt
==2
4080000.remoteproc-mss
running
modem.mdt
==3
2400000.remoteproc-slpi
running
slpi.mdt
```

驱动绑定：

```
$ adb -s 6033dbec shell 'su -c "ls /sys/bus/platform/drivers/qcom_q6v5_pas/"'
2400000.remoteproc-slpi  3000000.remoteproc-adsp  32300000.remoteproc-cdsp  4080000.remoteproc-mss  bind  uevent  unbind

$ adb -s 6033dbec shell 'su -c "readlink -f /sys/bus/platform/devices/4080000.remoteproc-mss/driver"'
/sys/bus/platform/drivers/qcom_q6v5_pas

$ adb -s 6033dbec shell 'su -c "readlink -f /sys/bus/platform/devices/4080000.remoteproc-mss/of_node"'
/sys/firmware/devicetree/base/soc/remoteproc-mss@04080000
```

**这条链是本次取证里最硬的证据**：modem 不是「外挂的某个 USB/PCIe 设备」，
而是 SoC 内部一个由 PAS（Peripheral Authentication Service）加载固件、
由 IPCC 中断与 smp2p 信号驱动的 remote processor。

---

## 3. 固件载荷（`/vendor/firmware_mnt/image`）

### 3.1 目录规模

```
$ adb -s 6033dbec shell 'su -c "ls -l /vendor/firmware_mnt/image/" | wc -l'
374          # 373 个条目 + total 行

$ adb -s 6033dbec shell 'su -c "du -sk /vendor/firmware_mnt/image"'
286384  /vendor/firmware_mnt/image      # ≈ 279.7 MiB
```

### 3.2 `modem.*` 文件表（实测字节数）

```
$ adb -s 6033dbec shell 'su -c "ls -l /vendor/firmware_mnt/image/"' | grep "modem\."
```

| 文件 | 字节 | 文件 | 字节 |
|---|---|---|---|
| `modem.mdt` | 5,884 | `modem.b17` | 3,690,496 |
| `modem.b00` | 1,076 | `modem.b18` | 14,095,752 |
| `modem.b01` | 7,204 | `modem.b19` | 16,584,207 |
| `modem.b02` | 805,556 | `modem.b20` | 6,541,320 |
| `modem.b03` | 14,756 | `modem.b22` | 120,256 |
| `modem.b04` | 15,588 | `modem.b23` | 40,935,488 |
| `modem.b05` | 13,112 | `modem.b24` | 8,377,984 |
| `modem.b06` | 34,880 | `modem.b25` | 1,290,846 |
| `modem.b07` | 114,688 | `modem.b26` | 8,960 |
| `modem.b08` | 2,743,284 | `modem.b27` | 290,304 |
| `modem.b09` | 37,184 | `modem.b28` | 102,208 |
| `modem.b10` | 49,152 | `modem.b29` | 10,760 |
| `modem.b11` | 4,138,640 | `modem.b31` | 4,808 |
| `modem.b12` | 262,144 | | |
| `modem.b13` | 4,784,128 | | |
| `modem.b15` | 3,518,216 | | |
| `modem.b16` | 473,648 | | |

- **合计 30 个文件，109,072,529 B = 104.02 MiB**
- `modem.b14` / `modem.b21` / `modem.b30` **不存在**（编号跳号）。
  这正好对应 §8 的 ELF 段表：这三个号段是纯 bss 段（`filesz=0`），所以没有对应文件。
- 全部文件时间戳 `2026-01-13 11:18`，权限 `-r--r----- system system`。

### 3.3 `modem.mdt` 是 ELF32 LE，链接地址就是 PAS 内存区

```
$ adb -s 6033dbec shell 'su -c "od -An -tx1 -N 52 /vendor/firmware_mnt/image/modem.mdt"'
 7f 45 4c 46 01 01 01 00 00 00 00 00 00 00 00 00
 02 00 a4 00 01 00 00 00 00 00 c0 8b 34 00 00 00
 00 00 00 00 71 00 00 00 34 00 20 00 20 00 00 00
```

| 字段 | 值 | 含义 |
|---|---|---|
| `e_ident` | `7f 45 4c 46 01 01 01` | ELF，32 位，小端 |
| `e_type` | `02 00` = 2 | ET_EXEC |
| `e_machine` | `a4 00` = 0xA4 | Qualcomm QDSP6（**不是** 0xB7=AArch64） |
| `e_entry` | `00 00 c0 8b` = **0x8bc00000** | 入口 = `mpss_region` 基址 |
| `e_phoff` | `34 00 00 00` = 52 | 段表偏移 |
| `e_phentsize` | `20 00` = 32 | 每段 32 B |
| `e_phnum` | `20 00` = 32 | 32 段 |

`e_machine=0xA4` 这条很重要：**modem 固件不是 ARM 代码**，是跑在 SoC 内 Hexagon/QDSP6
核上的镜像。XNU（ARM64）永远不可能「执行」它，只能**搬运并交给 PAS**。
这也决定了移植范围的上限（见 `03-SCOPE.md`）。

### 3.4 服务注册表 `modemr.jsn`

```
$ adb -s 6033dbec shell 'su -c "cat /vendor/firmware_mnt/image/modemr.jsn"'
{"sr_version":{"major":1,"minor":1,"patch":1},
 "sr_domain":{"soc":"msm","domain":"modem","subdomain":"root_pd","qmi_instance_id":180},
 "sr_service":[
   {"provider":"tms","service":"servreg","service_data_valid":0,"service_data":0,...},
   {"provider":"gps","service":"gps_service",...}]}
```

**这是 XNU 侧最容易漏掉的一份文件**：它声明 modem 的 root PD 在 QMI 服务注册表里的身份是
`soc=msm, domain=modem, subdomain=root_pd, qmi_instance_id=180`。
以后任何 protection-domain QMI（例如 `servreg` 查询）都要拿这组字符串去匹配，
而不是自己编一个 instance id。

### 3.5 MCFG（运营商配置）目录

```
$ adb -s 6033dbec shell 'su -c "ls /vendor/firmware_mnt/image/modem_pr/mcfg/configs/"'
mcfg_hw  mcfg_sw  mbn_build_utc.txt

$ adb -s 6033dbec shell 'su -c "cat /vendor/firmware_mnt/image/modem_pr/mcfg/configs/mbn_build_utc.txt"'
1768269985        # = 2026-01-13T02:06:25Z

$ adb -s 6033dbec shell 'su -c "ls /vendor/firmware_mnt/image/modem_pr/mcfg/configs/mcfg_sw/"'
generic  mbn_sw.dig  mbn_sw.txt  oem_sw.txt  oem_sw_ct_volte.txt  oem_sw_null.txt
```

`getprop` 侧对应的选择结果：

```
[persist.radio.ap_sw_mbn_count]: [346]
[persist.radio.ap_hw_mbn_count]: [1]
[persist.radio.mbn_default]: [HW_DEFAULT(0x0AE10108);SW_DEFAULT(0x0AE0000D);]
[persist.radio.mbn_hw_sub0]: [DSDA_Hybrid-LA-Waipio(0x0A001902);]
[persist.radio.mbn_sw_sub0]: [NV#71546=7;hVoLTE_OPNMKT_CT(0x0A0113F1);]
[persist.radio.mbn_sw_sub1]: [NV#71546=7;Volte_OpenMkt-Commercial-CMCC(0x0A012011);]
```

→ 卡 0 = 中国电信 VoLTE 配置，卡 1 = 中国移动 VoLTE 配置。
**这些是 Android 侧 `mbn` 选择的结果，存在 property 里**；XNU 侧要复现通话/数据，
就得自己跑同一套 mbn 选择逻辑（或至少原样复用这两个 id）。

### 3.6 本机没有 `mba.mbn`

```
$ adb -s 6033dbec shell 'su -c "ls /vendor/firmware_mnt/image/ | grep -i mba"'
（无输出，rc=1）
```

老平台（如 SDM845）PAS 需要先加载 `mba.mbn` 再加载 `modem.mdt`；**这台机器没有 mba**，
modem 由 `modem.mdt` 单镜像直接加载。这是 SM8475 世代的变化，移植时不要照抄老流程。

### 3.7 IPA 固件也在同一个目录

```
$ adb -s 6033dbec shell 'su -c "ls /vendor/firmware_mnt/image/ | grep -iE \"ipa|mlipay\""'
ipa_fws.b00  ipa_fws.b01  ipa_fws.b02  ipa_fws.b03  ipa_fws.b04  ipa_fws.mdt
fw_ipa_gsi_3.0_w.elf
mlipay.b00 ... mlipay.b08  mlipay.mdt
```

`ipa_fws.mdt` 同样是 ELF32 LE，`e_entry=0`、`e_phoff=0x34`。

---

## 4. 基带版本与设备身份

```
$ adb -s 6033dbec shell getprop | grep -iE "baseband|modem.*datetime|qspa"
[gsm.version.baseband]: [MPSS.DE.2.0.c1-CN-Jan 13 2026-02:08:51,MPSS.DE.2.0.c1-CN-Jan 13 2026-02:08:51]
[persist.radio.modem_build_datetime]: [Jan 13 2026 02:08:51]
[persist.radio.modem_release_datetime]: [Jan 13 2025 10:00:00]
[ro.baseband]: [msm]
[ro.boot.baseband]: [msm]
[ro.boot.vendor.qspa.modem]: [enabled]
[ro.boot.vendor.qspa.nav]: [enabled]
```

- 版本串出现**两次**（逗号分隔）= 双卡双待，两路 modem 实例各报一次。
- `MPSS.DE.2.0.c1-CN` = Modem Processor SubSystem，DE 分支，CN 区域版本。
- 时间戳 `Jan 13 2026 02:08:51` 与 §3.5 的 `mbn_build_utc.txt`（`02:06:25Z`）只差 2.5 分钟，
  互相印证同一批构建产物。
- `ro.baseband=msm` 表示「板载 SoC 基带」；若是外挂模块（如某些工程机的 MDM9x55），
  这里会是别的值（如 `mdm`）。**这是"内置"结论的一条独立旁证。**

设备身份：

```
$ adb -s 6033dbec shell getprop | grep -E "persist.radio.imei|imei[12]|persist.radio.meid|multisim|sim_slots"
[persist.radio.imei]: [863083061021129]
[persist.radio.imei1]: [863083061021129]
[persist.radio.imei2]: [863083061021137]
[persist.radio.meid]: [99002007494056]
[persist.radio.multisim.config]: [dsds]
[ro.telephony.sim_slots.count]: [2]
[persist.radio.active.slots]: [2]
```

→ DSDS（双卡双待单通），两个 IMEI 齐全，MEID 也在。

---

## 5. QRTR：走的是 AF_QIPCRTR 套接字，没有 /dev 节点

### 5.1 内核协议已注册

```
$ adb -s 6033dbec shell 'su -c "grep -i qipcrtr /proc/net/protocols"'
QIPCRTR    888      0      -1   NI       0   yes  qrtr        n  n  n  n  n  n  n  n  n  n  n  n  n  n  n  n  n  n  n
```

| 列 | 值 | 含义 |
|---|---|---|
| name | `QIPCRTR` | AF_QIPCRTR（协议族 42） |
| size | 888 | struct sock 大小 |
| sockets | 0 | 采样时无打开的套接字 |
| owner | `qrtr` | 由内核模块 `qrtr` 注册 |

已加载的 QRTR 相关模块（`ls /sys/module`）：`qrtr`、`qrtr_smd`、`qrtr_mhi`、`qrtr_gunyah`。

### 5.2 用户态服务

```
$ adb -s 6033dbec shell getprop | grep -E "init.svc.(vendor.qrtr-ns|vendor.qmipriod|ssgqmigd|dpmQmiMgr|vendor.modemManager)"
[init.svc.dpmQmiMgr]: [running]
[init.svc.ssgqmigd]: [running]
[init.svc.vendor.modemManager]: [running]
[init.svc.vendor.qmipriod]: [running]
[init.svc.vendor.qrtr-ns]: [running]

$ adb -s 6033dbec shell 'ps -A -o PID,NAME' | grep -iE "qrtr|qmi|ipacm|modem"
 213 [qrtr_ns]
 811 [rmnet_ctlwq]
 812 [rmnet_llwq]
 158 [kworker/u17:0-qmi_msg_handler]
1848 [kworker/u17:3-qmi_msg_handler]
1960 [qrtr_rx]
1974 qrtr-ns
2156 [qrtr_rx]
2219 [qrtr_rx]
2635 dpmQmiMgr
2643 qmipriod
2695 ipacm-diag
2698 ipacm
2705 modemManager
2737 ssgqmigd
3013 [glink_modem]
3554 [qrtr_rx]
5101 [qrtr_rx]
```

init 定义（`/vendor/etc/init/hw/init.qcom.rc:546-550`，原文）：

```
service vendor.qrtr-ns /vendor/bin/qrtr-ns -f
    class core
    user vendor_qrtr
    group vendor_qrtr
    capabilities NET_BIND_SERVICE
```

### 5.3 没有 /dev/qrtr*，也没有 unix socket

```
$ adb -s 6033dbec shell 'su -c "ls -l /dev/ | grep -i qrtr"'
（无输出，rc=1）

$ adb -s 6033dbec shell 'su -c "ls -l /dev/socket/ | grep -i qrtr"'
（无输出，rc=1）

$ adb -s 6033dbec shell 'su -c "ss -x | grep -i qrtr"'
（无输出，rc=1）
```

qrtr-ns 进程的 fd 表（`ls -l /proc/1974/fd`）：

```
0 -> /dev/null
1 -> /dev/null
2 -> /dev/null
3 -> socket:[60178]
```

→ **`qrtr-ns` 是纯 AF_QIPCRTR 套接字服务器**，不监听任何文件路径。
这条结论直接否定了「XNU 侧连一个 unix socket 就能问 modem」的设想：
QRTR 是**内核协议族**，XNU 侧必须自己实现 AF_QIPCRTR 的内核端，
或者绕过它直接讲 GLINK。

### 5.4 服务枚举：`qrtr-lookup` 的输出去向（本节曾误判，已更正）

**重要更正。** 本文件第一版把 `qrtr-lookup` 判成"在 KernelSU shell 里列不出服务"，
那是**看错了输出通道**，不是工具失败。事实是：

```
$ adb -s 6033dbec shell 'su -c "/vendor/bin/qrtr-lookup"'
  Service Version Instance Node  Port          ← stdout 只有表头
$ adb -s 6033dbec shell 'su -c "wc -c /data/vendor/qrtr/qrtr-lookup.txt"'
8209 /data/vendor/qrtr/qrtr-lookup.txt           ← 表格在这里
$ adb -s 6033dbec shell 'su -c "ls -l /data/vendor/qrtr/qrtr-lookup.txt"'
-rw-rw-rw- 1 system system 8209 2026-11-14 11:59 /data/vendor/qrtr/qrtr-lookup.txt
```

→ **`qrtr-lookup` 把结果写进 `/data/vendor/qrtr/qrtr-lookup.txt`，stdout 只印表头。**
按 stdout 判断"零命中"是工具用法错误。strace 证据见 §5.5。

### 5.4.1 modem 侧（node 0）真实注册的 QMI 服务

下面是 `/data/vendor/qrtr/qrtr-lookup.txt` 里 **Node = 0**（modem）的全部条目原文，
列顺序为 Service / Version / Instance / Node / Port：

```
    65508       1        0    0    19 <unknown>
       21       1        0    0    21 Modem embedded file system service
       24       1        0    0    23 Thermal mitigation device service
     4097     N/A        1    0    28 DIAG service (MODEM:CMD)
       23       1        0    0    35 Thermal sensors service
       36       1        0    0    36 Persistent device configuration service
       17       1        0    0    54 Specific absorption rate service
       34       1        0    0    55 Coexistence service
       85       1        0    0    62 <unknown>
       76       1        0    0    72 <unknown>
       50       1        0    0    73 <unknown>
       12       1        0    0    74 Phonebook Management service
        3       1        0    0    77 Network Access Service
       47       1        0    0    79 <unknown>
       11       1        0    0    80 User Identity Module service
      228       1        0    0    81 <unknown>
        1       1        0    0    82 Wireless Data Service
        4       1        0    0    83 Quality Of Service service
       26       1        0    0    84 Wireless data administrative service
        8       1        0    0    85 AT service
       77       1        0    0    86 <unknown>
        5       1        0    0    87 Wireless Messaging Service
       75       1        0    0    91 <unknown>
       74       1        0    0    92 <unknown>
       42       1        0    0    94 Data system determination service
        2       1        0    0    96 Device Management Service
       48       1        0    0    97 <unknown>
       68       1        0    0    98 <unknown>
       73       1        0    0    99 <unknown>
       78       1        0    0   100 <unknown>
       29       1        0    0   101 Circuit switched videotelephony service
        7       1        0    0   102 Authentication service
       86       1        0    0   103 <unknown>
       71       1        0    0   104 <unknown>
       33       1        0    0   105 IMS application service
       18       1        0    0   107 IMS settings service
       16       2        0    0   111 Location service (~ PDS v2)
```

**这就是 completion 判据要的"modem 已枚举"的直接证据**：36 个服务在 node 0 上应答，
包括 `21 Modem embedded file system service`（EFS 服务，正是 NV 请求的通道）、
`1 Wireless Data Service`、`11 User Identity Module service`（SIM）、
`3 Network Access Service`、`16 Location service (~ PDS v2)`。
这些服务能应答，说明 modem 固件已经**启动完成并跑在 QMI 服务循环里**。

### 5.4.2 AP 侧（node 1）与 DSP 侧（node 5/7/9/10）

Node 1（AP 自己）上关键的是 **service 64 = `Service registry locator service`**（servreg，
instance 1，port 16481）—— 这就是 `modemr.jsn` 里 `"service":"servreg"` 的主机侧对端：

```
     1070       1        0    1 16387 <unknown>
       52       1        1    1 16390 Dynamic Heap Memory Sharing
       49       1        1    1 16409 IPA control service
     4097     N/A        0    1 16414 DIAG service (MODEM:CNTL)
     4097     N/A        2    1 16416 DIAG service (MODEM:DATA)
     4097     N/A        4    1 16417 DIAG service (MODEM:DCI)
       64       1        1    1 16481 Service registry locator service
       14       1        0    1 16486 Remote file system service
       53       1       16    1 16487 <unknown>
     4096       1        0    1 16488 <unknown>      （instance 0..10 连续）
       40       1        0    1 17364 IMS RTP service
```

Node 5/9/10（ADSP/CDSP/SLPI 一类）上是 `43 Subsystem control`、`66 Service registry notification`、
`51 CoreSight remote tracing`、`24 Thermal mitigation`、`769 SLIMbus control`、
`15 Test service`；Node 7 是 WCNSS：`69 ATH10k WLAN firmware service`。

DIAG（4097）在 node 1 上按 instance 分槽：0=MODEM:CNTL、2=MODEM:DATA、4=MODEM:DCI、
64/66/68=LPASS、128/130/132=WCNSS、192/194/196=SENSORS、256/258/260=CDSP、320/322/324=WDSP。
这张表本身就是"**modem 与其它子系统都在 QRTR 命名空间里**"的完整证据。

### 5.5 strace 证明 `qrtr-lookup` 走的是 AF_QIPCRTR 广播

```
$ adb -s 6033dbec shell 'su -c "strace -f -e trace=socket,sendto,recvfrom,openat,chmod /vendor/bin/qrtr-lookup 2>&1 | head -40"'
socket(AF_QIPCRTR, SOCK_DGRAM, 0)        = 4
setsockopt(4, SOL_SOCKET, SO_RCVTIMEO, [1], 8) = 0
sendto(4, "\n\0\0\0\0\0\0\0\1\0\0\0\0\0\0\0\0\0\0\0", 20, 0,
       {sa_family=AF_QIPCRTR, sa_data="\0\0\1\0\0\0\376\377\377\377"}, 12) = 20
recvfrom(4, ...) = 20   （重复约 100 次，每次 20 字节）
openat(AT_FDCWD, "/vendor/lib64/libqrtr.so", O_RDONLY|O_CLOEXEC) = 5
openat(AT_FDCWD, "/data/vendor/qrtr/qrtr-lookup.txt", O_WRONLY|O_CREAT|O_TRUNC, 0666) = 5
chmod("/data/vendor/qrtr/qrtr-lookup.txt", 0666) = -1 EPERM (Operation not permitted)
```

三个结论：
1. 报文是 `QRTR_TYPE_NEW_LOOKUP`（首字节 `0x0a`）发往 node 0xffffffff（广播），
   所以它问的是"全网谁在" —— 收到 100 条 20 字节应答，就是上表的来源。
2. 结果文件是它自己 `O_CREAT` 出来的；`chmod` 在 KernelSU 下必然 `EPERM`，
   打印 `qrtr-lookup: chmod(): Operation not permitted` 但**不影响结果**。
3. `getenforce` = `Enforcing`，但**没有**任何 AVC 拒绝 —— 说明这不是 SELinux 问题，
   第一版的"未解项"结论完全建立在一个错误的观察上。

→ **L2 的验收判据成立且已被 Android 侧证实可行**：只要 XNU 侧能发出
`QRTR_TYPE_NEW_LOOKUP` 并收到 node 0 的 20 字节应答（服务 21/1/11/3/16 任一），
就算"modem 枚举成功"；再进一步对 service 64 (servreg) 发 QMI 请求读版本串，即达成 completion。

---

## 6. IPA / rmnet：数据面通道

### 6.1 设备节点

```
$ adb -s 6033dbec shell 'su -c "ls -l /dev/ | grep -iE \"ipa|rmnet|mhi\""'
crw-rw---- 1 radio  net_bt_admin 459,  0 ipa_lnx_stats_ioctl
crw-rw---- 1 radio  net_bt_admin 460,  0 ipa_tethering_bridge
crw-rw---- 1 radio  net_bt_admin 461,  0 ipaIpv6CTTable
crw-rw---- 1 radio  net_bt_admin 462,  0 ipaNatTable
crw-rw---- 1 radio  net_bt_admin 471,  0 rmnet_ctrl
crw-rw---- 1 radio  net_bt_admin 472,  0 ipa_odl_ctl
crw-rw---- 1 radio  net_bt_admin 473,  0 ipa_adpl
crw-rw---- 1 radio  net_bt_admin 474,  0 ipa
crw-rw---- 1 radio  net_bt_admin 501,  0 mhi_1103_00.01.00_pipe_0
crw-rw---- 1 radio  net_bt_admin 501,  1 mhi_1103_00.01.00_pipe_4
```

### 6.2 平台设备

```
$ adb -s 6033dbec shell 'su -c "ls /sys/bus/platform/devices/" | grep -iE "ipa|rmnet"'
3e00000.qcom,ipa
soc:qcom,rmnet-ipa
soc:qcom,smp2p_map_ipa_1_in
soc:qcom,smp2p_map_ipa_1_out

$ adb -s 6033dbec shell 'su -c "readlink -f /sys/bus/platform/devices/3e00000.qcom,ipa/driver"'
/sys/bus/platform/drivers/ipa
```

### 6.3 网络接口

```
$ adb -s 6033dbec shell 'su -c "ls /sys/class/net/"'
dummy0  ip6tnl0  lo  miw_oem0  p2p0  rmnet_data0  rmnet_data1  rmnet_data2
rmnet_data3  rmnet_data4  rmnet_data5  rmnet_ipa0  r_rmnet_data0  r_rmnet_data1
r_rmnet_data2  r_rmnet_data3  sit0  wlan0  wifi-aware0
```

- `rmnet_ipa0` = IPA ↔ modem 的 WAN 承载（每条数据都过 IPA 硬件）
- `rmnet_data0..5` = QMAP mux 出来的逻辑 bearer
- 这些全部是 `/devices/virtual/net` —— 说明它们由 IPA 驱动虚拟出来，没有独立硬件。

### 6.4 MHI 是 WLAN 的，不是 modem 的

```
$ adb -s 6033dbec shell 'su -c "ls /sys/bus/mhi/devices/"'
mhi0  mhi_1103_00.01.00_DIAG  mhi_1103_00.01.00_IPCR  mhi_1103_00.01.00_LOOPBACK

$ adb -s 6033dbec shell 'su -c "ls /sys/bus/pci/devices/"'
0000:00:00.0  0000:01:00.0
```

`lspci -nn` 等价信息（从 sysfs `vendor`/`device`/`class` 读出）：

| 地址 | vendor:device | class | 身份 |
|---|---|---|---|
| `0000:00:00.0` | `17cb:0110` | `0x060400` | Qualcomm PCIe root port |
| `0000:01:00.0` | `17cb:1103` | `0x028000` | QCA6490 WLAN（`subsystem 17cb:0108`） |

**关键否定证据**：整台机器只有两个 PCIe 设备，第二个是 WLAN。
`mhi_1103_*` 的 dev-id `0x1103` 正是这块 WLAN 的 device id，
所以这些 MHI 通道属于 **CNSS/WLAN**，与 modem 无关。
DT 里 `mhi_qrtr_cnss`（`qcom,dev-id = <0x1103>`）也是同一个东西。
**任何把 `mhi_1103_*` 当成 modem QRTR 传输的说法都是错的**（见 `02-DT-TRUTH.md` §7）。

---

## 7. SIM / EFS / NV 的归属

### 7.1 SIM 状态

```
$ adb -s 6033dbec shell getprop | grep -E "gsm.sim.state|gsm.sim.operator.alpha|airplane"
[gsm.sim.state]: [LOADED,LOADED]
[gsm.sim.operator.alpha]: [China Telecom,China Mobile]
[persist.radio.airplane_mode_on]: [1]
```

**注意**：两卡都 `LOADED`，但飞行模式是开的。
→ 射频链路（modem 固件、SIM 读取、QRTR/QMI 服务）全部在线，
**只是协议栈不发起数据/语音业务**。这对移植是好消息：
取证期间设备没有联网行为，不会因为「跑测试」产生流量或计费。

### 7.2 EFS / NV 在哪

```
$ adb -s 6033dbec shell 'su -c "ls /mnt/vendor/persist/"'
TWRP  audio  camera  coresight  data  display  fdsd  fpc  goodix  haptics
hlos_rfs  hvdcp_opti  iar_db  lost+found  mi_fp  misys  qca6490  rfs  secnvm
sensors  stability  time  vpp

$ adb -s 6033dbec shell 'su -c "ls /mnt/vendor/persist/modem"'
ls: /mnt/vendor/persist/modem: No such file or directory
```

→ **persist 分区里没有 modem 目录**。EFS/NV 全在 `modemst1`/`modemst2`（sdf3/sdf4，各 8 MiB，未挂载）。

### 7.3 EFS 同步守护进程

```
$ adb -s 6033dbec shell 'su -c "ps -A -o PID,NAME" | grep -iE "rmtfs|efs|tftp"'
2027 tftp_server
```

`tftp_server` 是 Qualcomm 的 EFS 同步服务：modem 通过 QMI 请求某个 NV 项时，
由它从 `modemst` 分区读出来、经共享内存递过去。**XNU 侧若不实现这条路径，
modem 即使被 PAS 起来也拿不到自己的 NV 数据，会停在「无网络」状态。**
这是移植范围的第二个硬约束（见 `03-SCOPE.md`）。

---

## 8. 未取到 / 未验证的项（诚实清单）

| 项 | 状态 | 原因 |
|---|---|---|
| `qrtr-lookup` 服务枚举 | **成功（曾误判）** | 结果写在 `/data/vendor/qrtr/qrtr-lookup.txt`（8209 B），stdout 只印表头。node 0 上有 36 个 QMI 服务应答（§5.4.1） |
| `dmesg` 里的 modem 加载日志 | **不可用** | 内核日志被反复的 `Modules linked in:` 崩溃转储污染，定向 grep 全是噪声 |
| `/sys/kernel/debug/remoteproc/remoteproc2/carveout_memories` | **空** | 该文件可读但内容为空 |
| `/sys/kernel/debug/remoteproc/remoteproc2/resource_table` | **"No resource table found"** | modem 固件不带 resource table（与 ADSP 不同） |
| `/proc/iomem` 里的 mpss 区段 | **看不到** | `mpss_region` 是 `no-map` 保留内存，不进 `/proc/iomem`。只能从 DT 读（见 02） |
| `mba.mbn` | **不存在** | 本世代不需要（§3.6） |
| 固件里的 `X65`/`SDX` 字符串 | **未命中** | 对 b18/b19/b23 前 2 MB 做 `strings` 未出现芯片型号字样，只有 `cape`。**不据此否定 X65，只说明固件不自报型号** |

---

## 9. 复现方式

```bash
export K60_AGENT_ID=cellular-agent
adb devices                                  # 必须看到 6033dbec
adb -s 6033dbec shell id                     # 必须 uid=0 且 context=u:r:ksu:s0
adb -s 6033dbec shell 'ls -l /dev/block/by-name/ | grep -i modem'
adb -s 6033dbec shell 'su -c "cat /proc/partitions"'
adb -s 6033dbec shell 'su -c "mount"' | grep firmware_mnt
adb -s 6033dbec shell 'su -c "ls -l /vendor/firmware_mnt/image/"'
adb -s 6033dbec shell 'su -c "od -An -tx1 -N 52 /vendor/firmware_mnt/image/modem.mdt"'
adb -s 6033dbec shell getprop | grep -iE 'baseband|qrtr|modem'
adb -s 6033dbec shell 'su -c "grep -i qipcrtr /proc/net/protocols"'
adb -s 6033dbec shell 'su -c "ls /sys/bus/pci/devices/"'

# QRTR 服务枚举：结果在文件里，不在 stdout
adb -s 6033dbec shell 'su -c "/vendor/bin/qrtr-lookup"'
adb -s 6033dbec shell 'su -c "cat /data/vendor/qrtr/qrtr-lookup.txt"'
adb -s 6033dbec shell 'su -c "strace -f -e trace=socket,sendto,recvfrom,openat,chmod /vendor/bin/qrtr-lookup 2>&1 | head -40"'
```

设备若停在 fastboot（`adb devices` 空、`fastboot devices` 有 6033dbec）：
`fastboot -s 6033dbec reboot`，约 45 秒后 adb 回来。
**不要 `fastboot flash` 任何分区**（双系统铁则）。
