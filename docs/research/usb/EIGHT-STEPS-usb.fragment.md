# EIGHT-STEPS.toml `[hardware.usb]` 段（待 Lead 合并）

本文件是**合并片段**，不是生效配置：`docs/research/EIGHT-STEPS.toml` 与
`scripts/render-eight-step-table.py` 都不在 USB 线写作用域（只允许
`docs/research/usb/`、`drivers/PongUsb/`、`patches/usb/`），所以这里给出可直接粘贴的块与三条合并步骤。

## 1. 粘贴到 `docs/research/EIGHT-STEPS.toml` 末尾

```toml

# ---------------------------------------------------------------- USB

[hardware.usb]
status = "active"
name = "USB（DWC3 device-mode / QMP PHY / UCSI）"

[hardware.usb.step.same_model]
done = true
evidence = "同 SoC SM8475 实机证据三份：references/UniXNU-pong/configs/pong-usb-sm8475.json 记录 ssphy@88e8000 的 qcom,qmp-phy-reg-offset 13 项与 qcom,qmp-phy-override-seq = <0x1580 0x0d 0x1614 0x38 0x1980 0x0d>；references/pong-usb/PongUsbDevice.h:123-145 是可直接对照的 CDC-ACM 设备实现；references/UniXNU-sheng/package/ShengBattery.cpp:30-91 是 UCSI 客户端。详见 docs/research/usb/RESEARCH.md §6 与 docs/research/usb/QMP-PHY.md §4。"

[hardware.usb.step.official]
done = true
evidence = "官方文档 https://unixnu.com/zh/porting/usb 全文（本地副本 E:/k60-work/references/UniXNU-upstream/docs/porting/usb.md，156 行）：bringUp 九阶段、AppleUSBXDCI/AppleUSBXHCI 的 OSKextLoadKextWithIdentifier 加载序列、qcom_dwc3_vbus/qcom_ucsi_start/qcom_ucsi_receive/qcom_ucsi_tick/qcom_ucsi_polling 五个板级入口（:90-105）、角色裁决原句（:100-101）、故障表六条。官方组件目录见 wide 步。"

[hardware.usb.step.decompile]
done = true
evidence = "Apple 20G81 kernelcache 与本仓 kernel.macho 的 USB kext 清单来自 strings -a 实测，34 个 USB kext 在 kc、本仓 macho 全 0（含 AppleUSBXDCI / IOUSBHostFamily / AppleUSBXHCI），见 docs/research/usb/IOUSBHOST-BINDING.md §1.1 表。UEFI 侧 sm8475-xiaomi-mondrian.dtb 用 dtc -I dtb -O dts 反编译为 21954 行文本（E:/k60-work/scratch/usb/mondrian.dts），ssphy 节点在 :16899-16917、pmic_glink 在 :8555-8578。"

[hardware.usb.step.wide]
done = true
catalog_checked = true
evidence = "UniXNU/components.toml（572 行、30 个组件）逐个核对：唯一 USB 组件是 QcomDwc3（:515-533，revision e4efe95c903a737e0f5955e5b50a8fb4d2a7d718，hardware 含 QMP USB3/DP PHY，source_files 含 QcomUcsi.h/QcomQmpUsb3.h，verified_devices=[sheng]，os_abi 只有 ipados-27.0.1-24A446，build_stage=embedded、build=[]）。其余 29 个组件无 USB 相关。结论见 catalog_result。"
catalog_result = """逐个核对 30 个组件里与 USB 相关的全部候选：
- QcomDwc3：【结构可参考，不能直接复用】它同时覆盖 device（AppleUSBXDCI 派生）与 host（AppleUSBXHCI 派生）两套栈，source_files 正是我们要做的四件（QcomDwc3.cpp / QcomEusb2Phy.h / QcomQmpUsb3.h / QcomUcsi.h），但 os_abi 只有 ipados-27.0.1-24A446，本机是 ipados-16.6.1-20G81；build_stage=embedded 且 build=[]，没有构建脚本也没有本机源码副本（ops_glob **/QcomDwc3/** 命中 0）。⇒ 只能按 docs/porting/usb.md 的结构自己实现，不能当组件引入。
- QcomGeniSpi / QcaBluetooth / Ath12kWifi：与 USB 数据通路无关。
- ArmSmmu4K：UCSI/DWC3 需要的 stage-1 SMMU context 与它同族，但 USB 的 stream id 与页表配置要单独写（官方 stream 0x40，本机实测 0x0，见 docs/plans/DOCS-PORTING-ALL.md:468-487）。
结论：USB 线没有可直接复用的官方组件，必须自写；QcomDwc3 的四文件结构是唯一权威参考。"""

[hardware.usb.step.plan]
done = true
evidence = "方案分三层，全部有实测依据：(1) 设备模式控制台已跑通（bsd/dev/k60_usblog.c，0405-0409 五个补丁，usb-20261114b 上机枚举成功）；(2) QMP SS PHY 上电顺序按主线 phy-qcom-qmp-combo.c:2548-2596 与下游 phy-msm-ssusb-qmp-sm8450.c:551-628 两套证据合并，寄存器表用 DT 自带 164 条而非主线 sm8550 表（QMP-PHY.md §3）；(3) UCSI 角色裁决挂在已有 GLINK 通道上，按 owner 32779 分流（UCSI.md §6）。详见 docs/research/usb/RESEARCH.md §22。"

[hardware.usb.step.deep]
done = true
evidence = "深挖得到三条会直接改变实现的结论：一，serdes 段 48 条里 24 条与主线 sm8550 不同（PLL/SSC/LOCK_CMP/BIN_VCOCAL），照抄主线会在第一步写错 24 个寄存器（QMP-PHY.md §3.1）；二，DT 的 13 项 reg-offset 与下游 enum qmp_phy_rev_reg 1:1 对应，唯一偏离是 clamp 0x1e00 vs 主线 0x1a0c（QMP-PHY.md §2）；三，K60 已有 GLINK 通道且 K60Battmgr.c:149 按 owner 32778 过滤，32779 的 UCSI 消息当前被静默丢弃，接入点是 K60Battery::receive() 分流而不是新开通道（UCSI.md §6）。"

[hardware.usb.step.verify]
done = true
local_verified = true
evidence = "三类本地核验齐全：qmp-phy-table.py --check 输出 RESULT: OK（13 项 reg-offset、164 条 init、block 分区全通过，见 docs/research/usb/QMP-PHY.md §9）；ucsi-host-selftest.c 编译零警告并输出 RESULT: PASS (0 failures)（docs/research/usb/UCSI-SELFTEST-OUTPUT.txt）；usb-20261114g 构建产物经 verify-boot-image.py --manifest → OK、check-image-args.py → image-arg-audit: OK (29 arguments, 575 bytes)，且 logs/kernel.log 证实 0405/0406/0407/0408/0409 五个补丁进镜像。"
static_check = "qmp-phy-table.py 对 DT 做五项一致性检查：reg-offset 条数等于下游枚举实项数、12 项非哨兵 offset 与主线 qmp_combo_offsets_v3 布局逐项相等、init 条目全部落在已知 block、无重复 offset、block 内递增。结果 RESULT: OK，唯一 note 是 clamp 0x1e00（以 DT 为真值）。"
unit_test = "docs/research/usb/ucsi-host-selftest.c：C11 零依赖，六组 40+ 断言覆盖消息长度、SET_NOTIFICATION_ENABLE 控制字、NOTIFY_IND→CCI、角色判定七种输入、ACK_CC_CI、GET_CONNECTOR_STATUS 全往返；RESULT: PASS (0 failures)。"
artifact_check = "usb-20261114g 的 kernel.macho 中含 0409 的两接口描述符（9,2,67,0,2,1,0,0xc0,50）且不含 98 字节描述符（grep '9, 2, 98' 命中 0）；boot.img sha256 3cba15c8a119606fd16125e2455b820c087e7ca3c4044711e0d4081e98faf695 与 build-manifest.json 一致。"

[hardware.usb.step.device]
done = false
evidence = "尚未完成本轮 QMP/UCSI 的上机验证：usb-20261114g 镜像与脚本已交 Lead，等待用户批准后执行（设备 6033dbec 停在 fastboot 未动）。历史状态：usb-20261114b 上机枚举成功但采集 0 字节；usb-20261114f 枚举正常、控制台 300 s 0 字节。"

[hardware.usb.step.device.prediction]
success = "K60 USBLOG 恢复 ≥250 行且不再出现 setup 80 06 0200 len 98；心跳每 2 s 一行且 tick ≈ 采集秒数÷2；若 QMP 已上电，另见 PHYSTATUS 清零后的 SS 枚举（connected, speed 4 = SUPERSPEED，DSTS bits[2:0]）"
failure = "采集 0 字节（控制台完全无声），或出现 K60PANIC/K60CACHE FAIL，或 GHWPARAMS3 的 NUM_EPS < 8 / NUM_IN_EPS < 4 导致 EP6/EP7 命令被拒"
```

## 2. `scripts/render-eight-step-table.py` 必须同时改

`UNTRACKED` 列表（:37-45）里的 `('USB', 'planned')` 必须删除，否则 README 表格会出现
**两行 USB**（P-148 记录过的事故：加进 EIGHT-STEPS.toml 的硬件同时留在 UNTRACKED）：

```diff
--- a/scripts/render-eight-step-table.py
+++ b/scripts/render-eight-step-table.py
@@ UNTRACKED = [
     ('CPU', 'device-verified'),
     ('电源', 'device-verified'),
     ('诊断', 'device-verified'),
     ('蓝牙', 'planned'),
-    ('USB', 'planned'),
     ('基带', 'planned'),
     ('DSP', 'planned'),
 ]
```

## 3. 重新生成 README 的八步表格

```sh
cd /mnt/e/hackios/k60-usb
PYTHONIOENCODING=utf-8 python3 scripts/render-eight-step-table.py --apply
PYTHONIOENCODING=utf-8 python3 scripts/render-eight-step-table.py --check
PYTHONIOENCODING=utf-8 python3 scripts/eight-step-gate.py --build
PYTHONIOENCODING=utf-8 python3 scripts/eight-step-gate.py --flash
```

预期新增行（中文表）：`| **USB（DWC3 device-mode / QMP PHY / UCSI）** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | 可刷机（⑦ 已核验） |`

## 4. 合并后的门禁影响

- `eight-step-gate.py --build`：新增 usb 段 ①–⑥ 都有 ≥30 字且带 file:line/URL/0x 引用的 evidence，通过。
- `eight-step-gate.py --flash`：⑧ 有 prediction.success/failure 即可，`done=false` 不阻断 flash。
- gate W（STATUS.md 覆盖）：`usb` 不在 `_MAP` 里，只会产生一条
  `EIGHT-STEPS.toml 有 STATUS.md 未列的硬件: usb` 的 **warn**，不是 bad。
