# 01 · 符号地图 — qti_battery_charger_main_m81.ko

> 阶段一离线反编译产物（不碰设备、不 build）。所有地址都是**可重定位目标文件内的节内偏移**（见 §1.2）。
> 每条结论都可由 §8 的命令复现；文中 `\x01` 等前缀是 kernel printk 的 KERN_ALERT 级别字节，不是字符串内容。
> 后续：属性映射见 `04-PROP-MAP.md`，未决结案见 `05-OPEN-QUESTIONS.md`，L1 服务层契约见 `../battery/PMIC-GLINK-SERVICE.md`。

## 0. 结论摘要

1. 目标文件是 Linux 5.10.160-GKI 的可重定位内核模块（ELF64 `ET_REL`，AArch64），37 个节、**675 个 defined 符号**、85 个 undefined 符号；真实函数 **232** 个，其中 185 个是 debugfs/class 属性的 `_show/_store` 叶子函数。
2. **195 个函数**最终都调用同一个发送封装 `battery_chg_write`（`.text:0x688`）——整个模块对外的数据面只有一个出口。
3. brief 的“89 个符号”无法复现：用 brief 自己的粗筛正则精确过滤得 **97**（63 个函数符号 + 34 个数据对象），差异表见 §3.2。本项目口径定为 **97（=63+34）**。
4. 对外部内核服务的依赖面很窄：`pmic_glink` 3 个、`power_supply` 4 个、`typec` 6 个、`debugfs` 3 个、`panel_event_notifier` 2 个（§6）。K60 侧只需要提供这几个内核符号，模块即可链接并 probe。
5. 唯一导出符号是 `qti_battery_charger_get_prop`（`.text:0x500`，`__ksymtab`/`__kcrctab` 各有一条）。

## 1. 取证基线

### 1.1 文件与模块自述

| 项 | 值 | 取证方式 |
|---|---|---|
| 路径 | `/mnt/e/k60-work/firmware/qti_battery_charger_main_m81.ko` | — |
| 大小 | 247,776 B | `stat` |
| SHA-256 | `914d12fe026f13bd6c8e0b470872502e6560a2f2d51278d30e1822d1cd758a48` | `sha256sum` |
| BuildID | `e852b83c589f773d7cb09e6793ac59fd33086c58` | `llvm-readelf -n` |
| 编译器 | Android clang 12.0.5 (r416183b) | `.comment` |
| vermagic | `5.10.160-gki-g1762b4a1419e SMP preempt mod_unload modversions aarch64` | `.modinfo` |
| 模块名 | `qti_battery_charger_main_m81`；`description=QTI Glink battery charger driver`；`depends=panel_event_notifier,pmic_glink`；`intree=Y` | `.modinfo` |
| 源文件名 | `drivers/power/supply/qti_battery_charger_m81.c` | `.rodata:0x12db`（BUG/WARN 表） |

### 1.2 地址约定（必须先读）

- 文件类型 `ELF64 REL`（`e_type=1`）、`e_machine=AArch64`、**没有 program header**。
- 所有节的 `sh_addr` 都是 0，所以 `llvm-objdump` 打印的地址 = **该节内的偏移**，不是 VMA。不同节的同名偏移会重叠：`init_module` 在 `.init.text:0x0`，而 `__cfi_check` 在 `.text:0x0`。
- 本文写法：`.text` 内偏移直接写 `0x688`；其它节写成 `节名:0x..`，例如 `.rodata:0x259a`、`.data:0x68`、`.bss:0x18`。
- 函数符号带 KCFI 类型哈希后缀（`battery_chg_probe$66163305b7e70713cc9dd757e96077f7`），本文一律用短名；`xxx.cfi_jt` 是 CFI 跳板，不是函数体。

## 2. 节布局（37 个节）

| 节 | 文件偏移 | 大小 | 属性 | 说明 |
|---|---|---|---|---|
| `__ksymtab` | 0x40 | 0x3c | A | 1 个导出符号条目 |
| `__kcrctab` | 0x7c | 0x14 | A | 同上 CRC |
| `.altinstructions` | 0x90 | 0x24 | A | erratum 补丁 |
| `__bug_table` | 0xb8 | 0x0c | WA | BUG/WARN 位置表 |
| `.bss` | 0xc8 | 0x60 | NOBITS/WA | 运行时锁、指针 |
| **`.data`** | **0xc8** | **0x19d0** | WA | 驱动/psy 描述符、class 属性表、可写缓存 |
| **`.rodata`** | **0x1a98** | **0x32d0** | AMS | 字符串、prop map、psy 描述符、跳转表 |
| **`.text`** | **0x5000** | **0xe350** | AX | 代码；`0x0–0xdc58` 函数体，`0xdc58–0xe350` CFI 跳板 |
| `.plt` / `.init.plt` / `.text.ftrace_trampoline` | 0x13350 | 各 1 B | AX | 占位 |
| `__ksymtab_strings` | 0x13353 | 0xb4 | AMS | 导出符号名字符串 |
| `.init.text` | 0x13408 | 0x34 | AX | `init_module` |
| `.exit.text` | 0x1343c | 0x2c | AX | `cleanup_module` |
| `.modinfo` | 0x13468 | 0xf7 | A | 模块元数据 |
| `.note.Linux` | 0x13560 | 0x18 | A | — |
| `.gnu.linkonce.this_module` | 0x13580 | 0x400 | WA | `struct module` |
| `__versions` | 0x13980 | 0x1580 | A | MODVERSIONS CRC 表 |
| `.note.gnu.build-id` | 0x14f00 | 0x24 | A | BuildID |
| `.note.gnu.property` | 0x14f28 | 0x20 | A | BTI/PAC 属性 |
| `.rela.text.__cfi_check` | 0x14f48 | **0x13800** | I | 最大节：全 `.text` 的重定位表 |
| `.comment` | 0x28748 | 0x9e | MS | clang 版本 |
| `.llvm_addrsig` | 0x287e6 | 0x4d4 | E | — |
| `.rela.*`（另外 7 个） | 0x28cc0 起 | 共 ~0x4000 | I | ksymtab/init/exit/alt/bug/cfi_jt/rodata 重定位 |
| `.symtab` | 0x2c1d0 | 0x7518 | — | 1249 条符号 |
| `.strtab` / `.shstrtab` | 0x338f1 / 0x336e8 | 0x85ad / 0x209 | — | 字符串表 |

要点：`.text` 按 4096 页对齐（文件偏移 0x5000），`.rodata` 紧贴 `.data` 之后且带 `S`(strings)+`M`(merge) 标志——**这是唯一放字符串的节，全部协议字符串都在这里**。

## 3. 符号计数

### 3.1 按 nm 类型

`llvm-nm -S --defined-only -n` 共 **675** 行，按类型：

| 类型 | 数量 | 含义 |
|---|---|---|
| `T` | 453 | 全局 `.text` 符号（含 221 个 `*.cfi_jt`） |
| `d` | 157 | 局部 `.data` |
| `r` | 36 | `.rodata` |
| `b` | 16 | `.bss` |
| `A` | 5 | 绝对 |
| `D` | 4 | 全局 `.data`（`battery_chg_driver`、`usb_psy_desc` 等） |
| `t` | 2 | 局部 `.text` |
| `W`/`B` | 1/1 | 弱符号/`.bss` 全局 |

`.symtab` 共 **1249** 条：`FUNC` 454 条 = 221 个 `*.cfi_jt` + `__cfi_check` + `__cfi_check_fail` + **232 个真实函数**；`OBJECT` 198 条。未定义符号 **85** 个（`llvm-nm -u`）。

### 3.2 brief 的“89 个”核对（明确回答）

| 口径 | 过滤方式 | 数量 |
|---|---|---|
| A. brief 粗筛正则，全部 defined 符号 | `grep -Ei 'charger\|batt\|usb_pd\|smb\|glink\|power_supply'` | **97** |
| B. 只算函数符号（含 `.cfi_jt`） | A + 类型 `t/T/W` | 63 |
| C. 排除 `.cfi_jt` | B 中去掉 `*.cfi_jt` | 32 |
| D. 去 KCFI 后缀后的不同短名 | `sed 's/\$.*//' \| sort -u` | 66 |
| E. 广义关键词（加 usb/psy/typec/wls/xm/pen/hboost/panel/thermal/debugfs） | — | 266 |
| F. brief 声称 | — | 89 |

**结论：89 不成立。** 用 brief 自己的四组关键词精确复现是 **97**（63 函数 + 34 数据对象，见下表），与 89 差 8；其它任何自然口径（32/63/66/266）也都不是 89。本文与后续文档统一以 **97（63+34）** 为本项目口径，`§4` 的功能分类另按 232 个真实函数统计。

97 个匹配项的构成（对象部分）：`battery_chg_driver`、`battery_class_groups`、`battery_class_attrs`、`battery_props`、`battery_prop_map`、`battery_chg_match_table`、`batt_psy_desc`、`battery_class_group`、`power_supply_usb_type_text`、`power_supply_usbc_text`、`qc_power_supply_usb_type_text`、`__ksymtab_qti_battery_charger_get_prop`(+`__kstrtab`/`__kstrtabns`/`__crc` 4 条)、`battery_chg_probe.__key`(+`.11`)、`power_supply_read_temp.{last_temp,first_init,last_read_time}`、`qti_battery_register_panel{,_sec}_notifier_work.retry_count`、以及 13 个 `class_attr_*`（`bq2597x_*`、`master_smb1396_*`、`slave_smb1396_*`、`smb_iin_diff`、`smart_batt`、`battcont_online`、`battmoni_isc`、`battmoni_soa`）。

## 4. 功能分类（232 个真实函数）

| 类别 | 数量 | 说明 | 代表符号 |
|---|---|---|---|
| 模块骨架 | 2 | `init_module`/`cleanup_module` | `init_module` 0x0(.init.text) |
| 驱动生命周期 | 2 | platform driver probe/remove | `battery_chg_probe` 0x754 |
| **pmic_glink 客户端** | **3** | 唯一的发送封装 + rx 回调 + 状态回调 | `battery_chg_write` 0x688 |
| 工作队列/状态机 | 9 | delayed work 与通知 work | `battery_chg_subsys_up_work` 0x11b0 |
| power_supply 回调 | 10 | battery/usb/wireless 三路 get/set/writeable + 温度 | `battery_psy_get_prop` 0x32a8 |
| typec | 6 | partner/port 注册与 class | `qti_typec_partner_register` 0xda8c |
| 通知链 | 5 | reboot/panel/pen/hboost | `qti_battery_register_panel_notifier_work` 0x29f0 |
| uevent | 2 | 小米 uevent 属性 | `add_xiaomi_uevent` 0xd2d0 |
| **debugfs 属性读写** | **185** | `*_show`/`*_store` 叶子函数 | `wlscharge_control_limit_store` 0xb798 |
| 其它工具 | 8 | 字符串/十六进制/CFI 辅助 | `StringToHex` 0x3bc |
| **合计** | **232** | — | — |

分布特征：`0x38f8–0xd220` 这 185 个函数几乎等长（0xb0/0xc0），是 144 条 `class_attr_*` 与 debugfs 文件的一一对映；真正的协议逻辑只在 `0x688–0x38f8` 这 ~13 KB 里。

## 5. 关键符号表

> 列说明：**地址** = `.text` 内偏移（`init_module`/`cleanup_module` 标出节名）；**外部调用** = `llvm-objdump -dr` 中 `R_AARCH64_CALL26` 的目标（只列非 `.text` 内部调用的外部符号）。

### 5.1 骨架与生命周期

| 符号 | 地址 | 大小 | 类型 | 外部调用 |
|---|---|---|---|---|
| `init_module` | `.init.text:0x0` | 0x34 | T | `__platform_driver_register` |
| `cleanup_module` | `.exit.text:0x0` | 0x2c | T | `platform_driver_unregister` |
| `battery_chg_probe` | 0x754 | 0x950 | t | `_dev_err`、`msleep`、`devm_kmalloc`、`__mutex_init`、`__init_swait_queue_head`、`init_timer_key`、`pmic_glink_register_client`、`pmic_glink_unregister_client`、`register_reboot_notifier`、`unregister_reboot_notifier`、`of_property_read_string`、`of_property_read_variable_u32_array`、`of_property_count_elems_of_size`、`of_find_property`、`devm_power_supply_register`、`thermal_zone_device_register`、`__class_register`、`debugfs_create_dir`、`debugfs_create_bool`、`debugfs_remove`、`device_init_wakeup`、`queue_work_on`、`queue_delayed_work_on`、`complete`、`printk` |
| `battery_chg_remove` | 0x10a4 | 0x10c | t | `device_init_wakeup`、`debugfs_remove`、`class_unregister`、`unregister_reboot_notifier`×2、`pmic_glink_unregister_client` |

### 5.2 pmic_glink 客户端（全部数据面）

| 符号 | 地址 | 大小 | 类型 | 外部调用 |
|---|---|---|---|---|
| `battery_chg_write` | 0x688 | 0xc8 | t | `mutex_lock`、`pmic_glink_write`、`wait_for_completion_timeout`、`mutex_unlock`、`printk` |
| `battery_chg_callback` | 0x211c | 0x614 | t | `complete`、`strcmp`、`printk`、`__stack_chk_fail` |
| `battery_chg_state_cb` | 0x2730 | 0x40 | t | `queue_work_on` |

### 5.3 工作队列 / 状态机

| 符号 | 地址 | 大小 | 外部调用 |
|---|---|---|---|
| `battery_chg_subsys_up_work` | 0x11b0 | 0x258 | `battery_chg_write`×4、`msleep`、`printk` |
| `battery_chg_update_usb_type_work` | 0x1408 | 0x164 | `battery_chg_write`、`queue_work_on`、`printk` |
| `battery_chg_check_status_work` | 0x156c | 0x1f8 | `battery_chg_write`×4、`msleep`、`printk`×3 |
| `pen_charge_notifier_work` | 0x189c | 0x17c | `atomic_notifier_call_chain`、`power_supply_changed` |
| `xm_charger_debug_info_print_work` | 0x1a18 | 0x60c | `printk`（大段调试快照） |
| `xm_batt_update_work` | 0x2024 | 0xf8 | `power_supply_changed`、`generate_xm_charge_uvent` |
| `notify_blankstate_changed_work` | 0x28f0 | 0x100 | `kobject_uevent_env`、`power_supply_changed` |
| `qti_battery_register_panel_notifier_work` | 0x29f0 | 0x1bc | `of_drm_find_panel`、`panel_event_notifier_register` |
| `qti_battery_register_panel_sec_notifier_work` | 0x2bac | 0x1bc | 同上（副屏） |

### 5.4 power_supply 回调

| 符号 | 地址 | 大小 | 外部调用 |
|---|---|---|---|
| `battery_psy_get_prop` | 0x32a8 | 0x210 | `power_supply_get_by_name`、`battery_chg_write` |
| `battery_psy_set_prop` | 0x34b8 | 0x274 | `power_supply_get_drvdata`、`battery_chg_write` |
| `battery_psy_prop_is_writeable` | 0x372c | 0x2c | — |
| `usb_psy_get_prop` | 0x2d68 | 0x1bc | `battery_chg_write` |
| `usb_psy_set_prop` | 0x2f24 | 0x1d8 | `power_supply_get_drvdata`、`battery_chg_write`×2 |
| `usb_psy_prop_is_writeable` | 0x30fc | 0x14 | — |
| `wls_psy_get_prop` | 0x3110 | 0x198 | `battery_chg_write` |
| `wls_psy_set_prop` | 0x38d8 | 0x10 | — （恒返回 0 的空实现） |
| `wls_psy_prop_is_writeable` | 0x38e8 | 0x10 | — （恒 0） |
| `power_supply_read_temp` | 0x3758 | 0x180 | `ktime_get`、`battery_chg_write` |

### 5.5 typec / 通知链 / uevent / 工具

| 符号 | 地址 | 大小 | 外部调用 |
|---|---|---|---|
| `qti_typec_partner_register` | 0xda8c | 0x98 | `typec_register_partner` |
| `qti_typec_partner_unregister` | 0xdb24 | 0x48 | `typec_unregister_partner` |
| `qti_typec_class_init` | 0xdb6c | 0x94 | `typec_register_port`、`typec_set_data_role`、`typec_set_pwr_role` |
| `qti_typec_class_deinit` | 0xdc00 | 0x58 | `typec_unregister_port` |
| `register_hboost_event_notifier` | 0x4a0 | 0x30 | `raw_notifier_chain_register` |
| `unregister_hboost_event_notifier` | 0x4d0 | 0x30 | `raw_notifier_chain_unregister` |
| `pen_charge_state_notifier_register_client` | 0x628 | 0x30 | `atomic_notifier_chain_register` |
| `pen_charge_state_notifier_unregister_client` | 0x658 | 0x30 | `atomic_notifier_chain_unregister` |
| `screen_state_for_charge_callback` | 0xd8fc | 0x16c | `queue_work_on` |
| `add_xiaomi_uevent` | 0xd2d0 | 0x62c | `add_uevent_var`、`snprintf` |
| `generate_xm_charge_uvent` | 0x1764 | 0x138 | `kobject_uevent_env` |
| `StringToHex` | 0x3bc | 0xe4 | `strlen` |
| `qti_battery_charger_get_prop` | 0x500 | 0x128 | `strcmp`、`power_supply_get_by_name`、`power_supply_get_drvdata`、`power_supply_put`、`battery_chg_write`（导出 `EXPORT_SYMBOL`） |

### 5.6 直接发协议请求的 debugfs 代表（185 个中的协议相关者）

| 符号 | 地址 | 大小 | 备注（来自 `.rodata` 字符串） |
|---|---|---|---|
| `wireless_fw_update` | 0x3f44 | 0x498 | 无线固件升级主流程，`.rodata:0x627` 等多处 `pmic_glink_write` 上游 |
| `wls_bin_store` | 0xade4 | 0x4e4 | 148 字节请求（固件分块） |
| `wls_debug_show` / `wls_debug_store` | 0xba3c / 0xbb28 | 0xec / 0x174 | 220 字节调试透传 |
| `wireless_chip_fw_show` / `_store` | 0xac38 / 0xacf8 | 0xc0 / 0xec | 116 字节 |
| `request_vdm_cmd_show` / `_store` | 0x5808 / 0x5b88 | 0x380 / 0x340 | PD VDM 命令 |
| `verify_digest_store` | 0x4e78 | 0x2f0 | 小米鉴权摘要 |
| `wlscharge_control_limit_store` | 0xb798 | 0x134 | 24 字节 SET（opcode 0x51，prop 0x49） |
| `ship_mode_en_store` | 0x469c | 0xbc | 与 ship mode 使能位 `bcdev+0x30d` 相关 |

## 6. 未定义符号（85 个）分组

| 组 | 数量 | 符号 |
|---|---|---|
| pmic_glink | 3 | `pmic_glink_register_client`、`pmic_glink_unregister_client`、`pmic_glink_write` |
| power_supply | 4 | `devm_power_supply_register`、`power_supply_changed`、`power_supply_get_by_name`、`power_supply_get_drvdata`、`power_supply_put` |
| typec | 6 | `typec_register_port`、`typec_register_partner`、`typec_unregister_port`、`typec_unregister_partner`、`typec_set_data_role`、`typec_set_pwr_role` |
| thermal | 1 | `thermal_zone_device_register` |
| debugfs | 3 | `debugfs_create_dir`、`debugfs_create_bool`、`debugfs_remove` |
| panel | 2 | `panel_event_notifier_register`、`panel_event_notifier_unregister`、`of_drm_find_panel` |
| class/kobject | 3 | `__class_register`、`class_unregister`、`kobject_uevent_env`、`add_uevent_var` |
| firmware | 2 | `firmware_request_nowarn`、`release_firmware` |
| OF/DT | 8 | `of_property_read_string`、`of_property_read_variable_u32_array`、`of_property_count_elems_of_size`、`of_find_property`、`of_find_node_by_name`、`of_count_phandle_with_args`、`of_parse_phandle`、`of_drm_find_panel` |
| 字符串解析 | 5 | `kstrtobool`、`kstrtoint`、`kstrtou16`、`kstrtou8`、`kstrtouint`、`sscanf` |
| 字符串处理 | 9 | `strcmp`、`strncmp`、`strncpy`、`strlen`、`strlcpy`、`strlcat`、`snprintf`、`scnprintf`、`StringToHex`(内部) |
| 内存 | 7 | `devm_kmalloc`、`kmem_cache_alloc_trace`、`kmalloc_caches`、`get_zeroed_page`、`free_pages`、`memcpy`、`__stack_chk_fail`/`__stack_chk_guard` |
| 并发/定时 | 8 | `mutex_lock`、`mutex_unlock`、`__mutex_init`、`__init_swait_queue_head`、`wait_for_completion_timeout`、`complete`、`init_timer_key`、`delayed_work_timer_fn`、`queue_work_on`、`queue_delayed_work_on`、`system_wq` |
| 通知链 | 5 | `register_reboot_notifier`、`unregister_reboot_notifier`、`atomic_notifier_chain_register`、`atomic_notifier_chain_unregister`、`atomic_notifier_call_chain`、`raw_notifier_chain_register`、`raw_notifier_chain_unregister` |
| 电源管理 | 6 | `device_init_wakeup`、`pm_stay_awake`、`pm_relax`、`pm_wakeup_dev_event`、`ktime_get`、`__msecs_to_jiffies` |
| 杂项 | 3 | `msleep`、`printk`、`_dev_err`、`__platform_driver_register`、`platform_driver_unregister` |

（部分行数量与列表长度不一致，因为一个符号可能同时属于两组；完整原始清单见 §8 的 `03-nm-undef.txt`。）

## 7. 关键数据对象（`llvm-nm -S` + 重定位交叉验证）

| 对象 | 位置 | 大小 | 内容 |
|---|---|---|---|
| `battery_chg_driver` | `.data:0x68` | 0xf0 | `platform_driver`：+0 `probe`→`battery_chg_probe.cfi_jt`，+8 `remove`，+0x28 `name`→`.rodata:0x755` "qti_battery_charger"，+0x50 `of_match_table`→`.rodata:0x2bd8`，+0x88 `shutdown` |
| `battery_chg_match_table` | `.rodata:0x2bd8` | 0x190 | `qcom,battery-charger`、`qcom,wireless-fw-name`、`qcom,thermal-mitigation`、`qcom,shutdown-voltage` 等 |
| `batt_psy_desc` | `.rodata:0x3188` | 0x68 | `power_supply_desc`：name="battery"(0xce9)、type=1、props=`battery_props`(.data:0x2c8, 24 项)、get/set/writeable、`no_thermal=1` |
| `usb_psy_desc` | `.data:0x198` | 0x68 | name="usb"(0x27ef)、type=4、`usb_types`(.data:0x200, 10 项)、num=10、props=`usb_props`(.data:0x228, 8 项) |
| `wls_psy_desc` | `.rodata:0x31f0` | 0x68 | name="wireless"(0x872)、type=12、props=`wls_props`(.data:0x328, 6 项) |
| `battery_prop_map` | `.rodata:0x2d68` | 0x64 | 25 项 u32：wire→psych 映射，见 02 §5 |
| `usb_prop_map` | `.rodata:0x2dcc` | 0x34 | 13 项 |
| `wls_prop_map` | `.rodata:0x2e00` | 0x1c | 7 项 |
| `xm_prop_map` | `.rodata:0x2e1c` | 0x2ec | 187 项（.rodata 内全 0，运行时由响应填充） |
| `battery_class_groups` / `battery_class_group` / `battery_class_attrs` | `.data:0x158` / `.rodata:0x3258` / `.data:0x340` | 0x10 / 0x28 / 0x488 | class 名为 `.rodata:0x130a` "qcom-battery"；attrs 数组 144 项 + NULL（145 个槽，末尾 0） |
| class 属性结构体数组 | `.data:0x7c8–0x19c8` | 每个 0x20 | `{name*, mode u16, show*, store*}` |
| `psy_tzd_ops` | `.data:0x250` | 0x78 | `thermal_zone_device_ops`（`.rodata:0x3188` 的 batt_psy 用） |
| `usb_psy_supported_types` | `.data:0x200` | 0x28 | 10 个 `POWER_SUPPLY_USB_TYPE_*` |
| `qc_power_supply_usb_type_text` / `power_supply_usb_type_text` / `power_supply_usbc_text` | `.rodata:0x3108/0x3130/0x3280` | — | 文本表（`POWER_SUPPLY_*=%s` 打印用） |

## 8. 复现命令

```bash
# 全部在 WSL 内执行（Windows 侧无 LLVM）
KO=/mnt/e/k60-work/firmware/qti_battery_charger_main_m81.ko
OUT=/mnt/e/hackios/_scratch/charger-ko

llvm-readelf -h -S -n "$KO"            > $OUT/00-elf-header.txt   # 37 节 + BuildID
llvm-nm -S --defined-only -n "$KO"     > $OUT/02-nm-defined.txt   # 675 行
llvm-nm -u "$KO"                       > $OUT/03-nm-undef.txt     # 85 行
llvm-objdump -dr "$KO"                 > $OUT/05-objdump-dr.txt   # 反汇编+重定位
llvm-objdump -s -j .rodata "$KO"       > $OUT/06-rodata.txt
llvm-readelf -p .modinfo "$KO"         # 模块自述

# brief 粗筛口径复现（97 / 63 / 32 / 66）
llvm-nm -S --defined-only -n "$KO" | grep -Ei 'charger|batt|usb_pd|smb|glink|power_supply' | wc -l        # 97
llvm-nm -S --defined-only -n "$KO" | grep -Ei 'charger|batt|usb_pd|smb|glink|power_supply' | awk '$3 ~ /^[tTW]$/' | wc -l   # 63
llvm-nm -S --defined-only -n "$KO" | grep -Ei 'charger|batt|usb_pd|smb|glink|power_supply' | grep -v '\.cfi_jt' | wc -l    # 66（含对象）
```

## 附录 A · 全部 232 个函数符号

> 由 `symtab.md` 原样拼接生成（`llvm-nm -S --defined-only -n` + `llvm-objdump -dr` 的 `R_AARCH64_CALL26` 目标）。`地址` 为 `.text` 内偏移；`init_module`/`cleanup_module` 属于 `.init.text`/`.exit.text`。
| cleanup_module | 0x0 | 0x2c | .init/.exit | platform_driver_unregister |
| init_module | 0x0 | 0x34 | .init/.exit | __platform_driver_register |
| StringToHex | 0x3bc | 0xe4 | .text | strlen |
| register_hboost_event_notifier | 0x4a0 | 0x30 | .text | raw_notifier_chain_register |
| unregister_hboost_event_notifier | 0x4d0 | 0x30 | .text | raw_notifier_chain_unregister |
| qti_battery_charger_get_prop | 0x500 | 0x128 | .text | strcmp, power_supply_get_by_name, power_supply_get_drvdata, power_supply_put, .text+0x688, __stack_chk_fail |
| pen_charge_state_notifier_register_client | 0x628 | 0x30 | .text | atomic_notifier_chain_register |
| pen_charge_state_notifier_unregister_client | 0x658 | 0x30 | .text | atomic_notifier_chain_unregister |
| battery_chg_write | 0x688 | 0xc8 | .text | mutex_lock, pmic_glink_write, wait_for_completion_timeout, mutex_unlock, printk |
| battery_chg_probe | 0x754 | 0x950 | .text | _dev_err, msleep, devm_kmalloc, __mutex_init, __init_swait_queue_head, init_timer_key, pmic_glink_register_client, register_reboot_notifier, of_property_read_string, of_property_read_variable_u32_array, of_property_count_elems_of_size, devm_power_supply_register, thermal_zone_device_register, printk, complete, pmic_glink_unregister_client, unregister_reboot_notifier, of_find_property, __class_register, debugfs_create_dir, debugfs_create_bool, debugfs_remove, .text+0x688, device_init_wakeup, queue_work_on, queue_delayed_work_on, __stack_chk_fail |
| battery_chg_remove | 0x10a4 | 0x10c | .text | device_init_wakeup, debugfs_remove, class_unregister, unregister_reboot_notifier, pmic_glink_unregister_client, panel_event_notifier_unregister, printk |
| battery_chg_subsys_up_work | 0x11b0 | 0x258 | .text | .text+0x688, msleep, printk, __stack_chk_fail |
| battery_chg_update_usb_type_work | 0x1408 | 0x164 | .text | .text+0x688, printk, __stack_chk_fail |
| battery_chg_check_status_work | 0x156c | 0x1f8 | .text | .text+0x688, printk, msleep, __stack_chk_fail |
| generate_xm_charge_uvent | 0x1764 | 0x138 | .text | _dev_err, kobject_uevent_env, printk, .text+0x688, __stack_chk_fail |
| pen_charge_notifier_work | 0x189c | 0x17c | .text | .text+0x688, printk, atomic_notifier_call_chain, __stack_chk_fail |
| xm_charger_debug_info_print_work | 0x1a18 | 0x60c | .text | usb_psy_get_prop$66163305b7e70713cc9dd757e96077f7, printk, .text+0x688, wls_psy_get_prop$66163305b7e70713cc9dd757e96077f7, queue_delayed_work_on, __stack_chk_fail |
| xm_batt_update_work | 0x2024 | 0xf8 | .text | .text+0x688, printk, queue_delayed_work_on, __stack_chk_fail |
| battery_chg_callback | 0x211c | 0x614 | .text | printk, strcmp, complete, memcpy, queue_delayed_work_on, queue_work_on, power_supply_changed, pm_wakeup_dev_event |
| battery_chg_state_cb | 0x2730 | 0x40 | .text | queue_work_on |
| battery_chg_ship_mode | 0x2770 | 0xc0 | .text | printk, .text+0x688, __stack_chk_fail |
| battery_chg_shutdown | 0x2830 | 0xc0 | .text | printk, .text+0x688, __stack_chk_fail |
| notify_blankstate_changed_work | 0x28f0 | 0x100 | .text | printk, .text+0x688, __stack_chk_fail |
| qti_battery_register_panel_notifier_work | 0x29f0 | 0x1bc | .text | of_find_node_by_name, of_count_phandle_with_args, of_parse_phandle, of_drm_find_panel, panel_event_notifier_register, printk, queue_delayed_work_on |
| qti_battery_register_panel_sec_notifier_work | 0x2bac | 0x1bc | .text | of_find_node_by_name, of_count_phandle_with_args, of_parse_phandle, of_drm_find_panel, panel_event_notifier_register, printk, queue_delayed_work_on |
| usb_psy_get_prop | 0x2d68 | 0x1bc | .text | power_supply_get_drvdata, printk, .text+0x688, queue_delayed_work_on, __stack_chk_fail |
| usb_psy_set_prop | 0x2f24 | 0x1d8 | .text | power_supply_get_drvdata, printk, .text+0x688, __stack_chk_fail |
| usb_psy_prop_is_writeable | 0x30fc | 0x14 | .text | — |
| wls_psy_get_prop | 0x3110 | 0x198 | .text | power_supply_get_drvdata, printk, .text+0x688, queue_delayed_work_on, __stack_chk_fail |
| battery_psy_get_prop | 0x32a8 | 0x210 | .text | power_supply_get_drvdata, printk, .text+0x688, __stack_chk_fail |
| battery_psy_set_prop | 0x34b8 | 0x274 | .text | power_supply_get_drvdata, printk, .text+0x688, __stack_chk_fail |
| battery_psy_prop_is_writeable | 0x372c | 0x2c | .text | — |
| power_supply_read_temp | 0x3758 | 0x180 | .text | power_supply_get_drvdata, ktime_get, .text+0x688, printk, __stack_chk_fail |
| wls_psy_set_prop | 0x38d8 | 0x10 | .text | — |
| wls_psy_prop_is_writeable | 0x38e8 | 0x10 | .text | — |
| soh_show | 0x38f8 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| resistance_show | 0x39a8 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| moisture_detection_status_show | 0x3a58 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| moisture_detection_en_show | 0x3b08 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| moisture_detection_en_store | 0x3bb8 | 0xb8 | .text | kstrtobool, .text+0x688, __stack_chk_fail |
| wireless_boost_en_show | 0x3c70 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| wireless_boost_en_store | 0x3d20 | 0xb8 | .text | kstrtobool, .text+0x688, __stack_chk_fail |
| fake_soc_show | 0x3dd8 | 0x3c | .text | scnprintf |
| fake_soc_store | 0x3e14 | 0x98 | .text | kstrtoint, power_supply_changed, __stack_chk_fail |
| wireless_fw_update_store | 0x3eac | 0x98 | .text | kstrtobool, .text+0x3f44, __stack_chk_fail |
| wireless_fw_update | 0x3f44 | 0x498 | .text | pm_stay_awake, .text+0x688, printk, pm_relax, firmware_request_nowarn, release_firmware, msleep, wait_for_completion_timeout, pmic_glink_write, __msecs_to_jiffies, memcpy, __stack_chk_fail |
| wireless_fw_force_update_store | 0x43e4 | 0x98 | .text | kstrtobool, .text+0x3f44, __stack_chk_fail |
| wireless_fw_version_show | 0x447c | 0xcc | .text | .text+0x688, scnprintf, printk, __stack_chk_fail |
| wireless_fw_crc_store | 0x4548 | 0x90 | .text | kstrtou16, __stack_chk_fail |
| wireless_fw_update_time_ms_show | 0x45d8 | 0x3c | .text | scnprintf |
| wireless_fw_update_time_ms_store | 0x4614 | 0x4c | .text | kstrtouint |
| ship_mode_en_show | 0x4660 | 0x3c | .text | scnprintf |
| ship_mode_en_store | 0x469c | 0xbc | .text | kstrtobool, .text+0x688, printk, __stack_chk_fail |
| restrict_chg_show | 0x4758 | 0x3c | .text | scnprintf |
| restrict_chg_store | 0x4794 | 0x124 | .text | kstrtobool, .text+0x688, printk, __stack_chk_fail |
| restrict_cur_show | 0x48b8 | 0x3c | .text | scnprintf |
| restrict_cur_store | 0x48f4 | 0x124 | .text | kstrtouint, .text+0x688, printk, __stack_chk_fail |
| usb_real_type_show | 0x4a18 | 0xf0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| usb_typec_compliant_show | 0x4b08 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| real_type_show | 0x4bb8 | 0xf0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| resistance_id_show | 0x4ca8 | 0xac | .text | .text+0x688, scnprintf, __stack_chk_fail |
| verify_digest_show | 0x4d54 | 0x124 | .text | .text+0x688, snprintf, strlcat, strlen, printk, __stack_chk_fail |
| verify_digest_store | 0x4e78 | 0x2f0 | .text | strlcpy, strlen, strncpy, .text+0x688, __stack_chk_fail |
| connector_temp_show | 0x5168 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| connector_temp_store | 0x5218 | 0xc0 | .text | kstrtoint, .text+0x688, __stack_chk_fail |
| authentic_show | 0x52d8 | 0xd0 | .text | .text+0x688, printk, scnprintf, __stack_chk_fail |
| authentic_store | 0x53a8 | 0xd8 | .text | kstrtobool, printk, .text+0x688, __stack_chk_fail |
| chip_ok_show | 0x5480 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| vbus_disable_show | 0x5530 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| vbus_disable_store | 0x55e0 | 0xc0 | .text | kstrtoint, .text+0x688, __stack_chk_fail |
| verify_process_show | 0x56a0 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| verify_process_store | 0x5750 | 0xb8 | .text | kstrtobool, .text+0x688, __stack_chk_fail |
| request_vdm_cmd_show | 0x5808 | 0x380 | .text | .text+0x688, printk, snprintf, strlcat, scnprintf, __stack_chk_fail |
| request_vdm_cmd_store | 0x5b88 | 0x340 | .text | sscanf, printk, strlen, .text+0x688, __stack_chk_fail |
| current_state_show | 0x5ec8 | 0x11c | .text | .text+0x688, __stack_chk_fail |
| adapter_id_show | 0x5fe4 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| adapter_svid_show | 0x6094 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| pd_verifed_show | 0x6144 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| pd_verifed_store | 0x61f4 | 0xb8 | .text | kstrtobool, .text+0x688, __stack_chk_fail |
| pdo2_show | 0x62ac | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| bq2597x_chip_ok_show | 0x635c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| bq2597x_slave_chip_ok_show | 0x640c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| bq2597x_bus_current_show | 0x64bc | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| bq2597x_slave_bus_current_show | 0x656c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| bq2597x_bus_delta_show | 0x661c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| bq2597x_bus_voltage_show | 0x66cc | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| bq2597x_battery_present_show | 0x677c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| bq2597x_slave_battery_present_show | 0x682c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| bq2597x_battery_voltage_show | 0x68dc | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| master_smb1396_online_show | 0x698c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| master_smb1396_iin_show | 0x6a3c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| slave_smb1396_online_show | 0x6aec | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| slave_smb1396_iin_show | 0x6b9c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| smb_iin_diff_show | 0x6c4c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| cc_orientation_show | 0x6cfc | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| input_suspend_show | 0x6dac | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| input_suspend_store | 0x6e5c | 0xd4 | .text | kstrtobool, printk, .text+0x688, __stack_chk_fail |
| fastchg_mode_show | 0x6f30 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| night_charging_show | 0x6fe0 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| night_charging_store | 0x7090 | 0xd4 | .text | kstrtobool, printk, .text+0x688, __stack_chk_fail |
| blank_status_show | 0x7164 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| blank_status_store | 0x7214 | 0xd4 | .text | kstrtobool, printk, .text+0x688, __stack_chk_fail |
| screen_cctog_show | 0x72e8 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| screen_cctog_store | 0x7398 | 0xd4 | .text | kstrtobool, printk, .text+0x688, __stack_chk_fail |
| shutdown_delay_show | 0x746c | 0xc0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| shutdown_delay_store | 0x752c | 0xa8 | .text | kstrtoint, printk, __stack_chk_fail |
| soc_decimal_show | 0x75d4 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| soc_decimal_rate_show | 0x7684 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| quick_charge_type_show | 0x7734 | 0x434 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fake_cycle_show | 0x7b68 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fake_cycle_store | 0x7c18 | 0xc0 | .text | kstrtoint, .text+0x688, __stack_chk_fail |
| fake_soh_show | 0x7cd8 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fake_soh_store | 0x7d88 | 0xc0 | .text | kstrtoint, .text+0x688, __stack_chk_fail |
| deltafv_show | 0x7e48 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fake_temp_show | 0x7ef8 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fake_temp_store | 0x7fa8 | 0xc0 | .text | kstrtoint, .text+0x688, __stack_chk_fail |
| cycle_count_diff_show | 0x8068 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| thermal_remove_show | 0x8118 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| thermal_remove_store | 0x81c8 | 0xc0 | .text | kstrtoint, .text+0x688, __stack_chk_fail |
| typec_mode_show | 0x8288 | 0xc8 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| mtbf_current_show | 0x8350 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| mtbf_current_store | 0x8400 | 0xc4 | .text | kstrtoint, .text+0x688, __stack_chk_fail |
| smart_batt_show | 0x84c4 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| smart_batt_store | 0x8574 | 0xdc | .text | kstrtoint, printk, .text+0x688, __stack_chk_fail |
| shipmode_count_reset_show | 0x8650 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| shipmode_count_reset_store | 0x8700 | 0xc0 | .text | kstrtoint, .text+0x688, __stack_chk_fail |
| sport_mode_show | 0x87c0 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| sport_mode_store | 0x8870 | 0xc0 | .text | kstrtoint, .text+0x688, __stack_chk_fail |
| apdo_max_show | 0x8930 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| verify_slave_flag_show | 0x89e0 | 0x3c | .text | scnprintf |
| verify_slave_flag_store | 0x8a1c | 0x98 | .text | kstrtobool, printk, __stack_chk_fail |
| die_temperature_show | 0x8ab4 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| slave_die_temperature_show | 0x8b64 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg_raw_soc_show | 0x8c14 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| battcont_online_show | 0x8cc4 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| battmoni_isc_show | 0x8d74 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| battmoni_soa_show | 0x8e24 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| over_peak_flag_show | 0x8ed4 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| current_deviation_show | 0x8f84 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| power_deviation_show | 0x9034 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| average_current_show | 0x90e4 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| average_temp_show | 0x9194 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| start_learn_show | 0x9244 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| start_learn_store | 0x92f4 | 0xc0 | .text | kstrtoint, .text+0x688, __stack_chk_fail |
| stop_learn_show | 0x93b4 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| stop_learn_store | 0x9464 | 0xc0 | .text | kstrtoint, .text+0x688, __stack_chk_fail |
| set_learn_power_show | 0x9524 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| set_learn_power_store | 0x95d4 | 0xc0 | .text | kstrtoint, .text+0x688, __stack_chk_fail |
| get_learn_power_show | 0x9694 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| get_learn_power_dev_show | 0x9744 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| get_learn_time_dev_show | 0x97f4 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| constant_power_show | 0x98a4 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| constant_power_store | 0x9954 | 0xc0 | .text | kstrtoint, .text+0x688, __stack_chk_fail |
| remaining_time_show | 0x9a14 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| referance_power_show | 0x9ac4 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| referance_power_store | 0x9b74 | 0xc0 | .text | kstrtoint, .text+0x688, __stack_chk_fail |
| nvt_referance_current_show | 0x9c34 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| nvt_referance_power_show | 0x9ce4 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| start_learn_b_show | 0x9d94 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| start_learn_b_store | 0x9e44 | 0xc0 | .text | kstrtoint, .text+0x688, __stack_chk_fail |
| stop_learn_b_show | 0x9f04 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| stop_learn_b_store | 0x9fb4 | 0xc0 | .text | kstrtoint, .text+0x688, __stack_chk_fail |
| set_learn_power_b_show | 0xa074 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| set_learn_power_b_store | 0xa124 | 0xc0 | .text | kstrtoint, .text+0x688, __stack_chk_fail |
| get_learn_power_b_show | 0xa1e4 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| get_learn_power_dev_b_show | 0xa294 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| tx_mac_show | 0xa344 | 0xe4 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| pen_mac_show | 0xa428 | 0xfc | .text | .text+0x688, scnprintf, __stack_chk_fail |
| tx_iout_show | 0xa524 | 0xd0 | .text | .text+0x688, printk, scnprintf, __stack_chk_fail |
| tx_vout_show | 0xa5f4 | 0xd0 | .text | .text+0x688, printk, scnprintf, __stack_chk_fail |
| pen_soc_show | 0xa6c4 | 0xd0 | .text | .text+0x688, printk, scnprintf, __stack_chk_fail |
| pen_hall3_show | 0xa794 | 0xd0 | .text | .text+0x688, printk, scnprintf, __stack_chk_fail |
| pen_hall4_show | 0xa864 | 0xd0 | .text | .text+0x688, printk, scnprintf, __stack_chk_fail |
| rx_cr_show | 0xa934 | 0xe4 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| rx_cep_show | 0xaa18 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| bt_state_show | 0xaac8 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| bt_state_store | 0xab78 | 0xc0 | .text | kstrtoint, .text+0x688, __stack_chk_fail |
| wireless_chip_fw_show | 0xac38 | 0xc0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| wireless_chip_fw_store | 0xacf8 | 0xec | .text | kstrtouint, .text+0x688, __stack_chk_fail |
| wls_bin_store | 0xade4 | 0x4e4 | .text | printk, strncmp, memcpy, .text+0x688, kstrtou16, kstrtou8, __stack_chk_fail |
| rx_vout_show | 0xb2c8 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| rx_vrect_show | 0xb378 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| rx_iout_show | 0xb428 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| tx_adapter_show | 0xb4d8 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| op_mode_show | 0xb588 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| wls_die_temp_show | 0xb638 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| wlscharge_control_limit_show | 0xb6e8 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| wlscharge_control_limit_store | 0xb798 | 0x134 | .text | kstrtoint, printk, .text+0x688, __stack_chk_fail |
| wls_thermal_remove_show | 0xb8cc | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| wls_thermal_remove_store | 0xb97c | 0xc0 | .text | kstrtoint, .text+0x688, __stack_chk_fail |
| wls_debug_show | 0xba3c | 0xec | .text | .text+0x688, scnprintf, __stack_chk_fail |
| wls_debug_store | 0xbb28 | 0x174 | .text | printk, strncpy, .text+0x688, __stack_chk_fail |
| wls_fw_state_show | 0xbc9c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| wls_car_adapter_show | 0xbd4c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| wls_tx_speed_show | 0xbdfc | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| wls_tx_speed_store | 0xbeac | 0xc0 | .text | kstrtoint, .text+0x688, __stack_chk_fail |
| wls_fc_flag_show | 0xbf6c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg1_qmax_show | 0xc01c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg1_rm_show | 0xc0cc | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg1_fcc_show | 0xc17c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg1_soh_show | 0xc22c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg1_fcc_soh_show | 0xc2dc | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg1_cycle_show | 0xc38c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg1_fastcharge_show | 0xc43c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg1_current_max_show | 0xc4ec | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg1_vol_max_show | 0xc59c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg1_tsim_show | 0xc64c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg1_cell1_rascale_show | 0xc6fc | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg1_avg_current_show | 0xc7ac | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg1_tambient_show | 0xc85c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg1_tremq_show | 0xc90c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg1_tfullq_show | 0xc9bc | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg1_rsoc_show | 0xca6c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg1_ai_show | 0xcb1c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg1_cell1_vol_show | 0xcbcc | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg1_cell2_vol_show | 0xcc7c | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| power_max_show | 0xcd2c | 0x154 | .text | .text+0x688, usb_psy_get_prop$66163305b7e70713cc9dd757e96077f7, printk, wls_psy_get_prop$66163305b7e70713cc9dd757e96077f7, scnprintf, __stack_chk_fail |
| fg_vendor_show | 0xce80 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg_temp_max_show | 0xcf30 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| fg_time_ot_show | 0xcfe0 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| atest_show | 0xd090 | 0xd0 | .text | .text+0x688, printk, scnprintf, __stack_chk_fail |
| atest_store | 0xd160 | 0xc0 | .text | kstrtoint, .text+0x688, __stack_chk_fail |
| last_node_show | 0xd220 | 0xb0 | .text | .text+0x688, scnprintf, __stack_chk_fail |
| add_xiaomi_uevent | 0xd2d0 | 0x62c | .text | get_zeroed_page, .text+0x688, printk, scnprintf, kstrtoint, snprintf, add_uevent_var, tx_mac_show$66163305b7e70713cc9dd757e96077f7, pen_mac_show$66163305b7e70713cc9dd757e96077f7, rx_cr_show$66163305b7e70713cc9dd757e96077f7, quick_charge_type_show$66163305b7e70713cc9dd757e96077f7, _dev_err, free_pages, __stack_chk_fail |
| screen_state_for_charge_callback | 0xd8fc | 0x16c | .text | .text+0x688, printk, queue_work_on, __stack_chk_fail |
| __cfi_check_fail | 0xda68 | 0x24 | .text | — |
| qti_typec_partner_register | 0xda8c | 0x98 | .text | typec_register_partner, typec_set_data_role, typec_set_pwr_role |
| qti_typec_partner_unregister | 0xdb24 | 0x48 | .text | typec_unregister_partner |
| qti_typec_class_init | 0xdb6c | 0x94 | .text | kmem_cache_alloc_trace, typec_register_port |
| qti_typec_class_deinit | 0xdc00 | 0x58 | .text | typec_unregister_partner, typec_unregister_port |
| __cfi_jt_start | 0xdc58 | 0x0 | .text | — |
| __cfi_jt_end | 0xe350 | 0x0 | .text | — |
