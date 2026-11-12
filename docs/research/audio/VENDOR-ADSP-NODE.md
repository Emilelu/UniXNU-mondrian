# 厂商 FDT 里的 ADSP/PAS 节点（官方来源，可直接抄）

来源：`E:\hackios\uefi-mondrian\Platforms\Xiaomi\mondrianPkg\FdtBlob\sm8475-xiaomi-mondrian.dtb`
（480,692 B，官方打包的完整板级 FDT），用 `dtc -I dtb -O dts` 解出。

这张表回答了 `docs/research/audio/GAP-ANALYSIS.md` 里长期悬着的那个问题：
**`K60AdspGlinkHandoff` 的 producer 该由谁提供**。答案不是"我们自己编一个"，
而是这块板上本来就有 `qcom,cape-adsp-pas` 远程处理器节点和
`qcom,pmic-glink` 的 `PMIC_RTR_ADSP_APPS` 通道，我们的 ADT 从来没收进去。

电池归档构建器的报错正是同一件事：
`Expected one enabled qcom,cape-adsp-pas, found 0`
（`scripts/build-k60-physical-battery.py` 要求 ADT 里存在该节点且 status 为可用）。

## 关键节点原文

```dts
		remoteproc-adsp@03000000 {
			compatible = "qcom,cape-adsp-pas";
			reg = <0x3000000 0x10000>;
			status = "ok";
			cx-supply = <0x93>;
			cx-uV-uA = <0x180 0x00>;
			mx-supply = <0x94>;
			mx-uV-uA = <0x180 0x00>;
			reg-names = "cx\0mx";
			clocks = <0x20 0x00>;
			clock-names = "xo";
			qcom,qmp = <0x8c>;
			interconnects = <0x5a 0x2b 0x46 0x200>;
			interconnect-names = "crypto_ddr";
			memory-region = <0x95>;
			interrupts-extended = <0x42 0x06 0x01 0x96 0x00 0x00 0x96 0x02 0x00 0x96 0x01 0x00 0x96 0x03 0x00 0x96 0x07 0x00>;
			interrupt-names = "wdog\0fatal\0handover\0ready\0stop-ack\0shutdown-ack";
			qcom,smem-states = <0x97 0x00>;
			qcom,smem-state-names = "stop";
			phandle = <0x33c>;

			glink-edge {
				qcom,remote-pid = <0x02>;
				transport = "smem";
				mboxes = <0x8f 0x03 0x00>;
				mbox-names = "adsp_smem";
				interrupt-parent = <0x8f>;
				interrupts = <0x03 0x00 0x01>;
				label = "adsp";
				qcom,glink-label = "lpass";
				phandle = <0x33d>;

				qcom,adsp_qrtr {
					qcom,glink-channels = "IPCRTR";
					qcom,intents = <0x800 0x05 0x2000 0x03 0x4400 0x02>;
				};

				qcom,msm_fastrpc_rpmsg {
					compatible = "qcom,msm-fastrpc-rpmsg";
					qcom,glink-channels = "fastrpcglink-apps-dsp";
					qcom,intents = <0x64 0x40>;
				};

				qcom,pmic_glink_rpmsg {
					qcom,glink-channels = "PMIC_RTR_ADSP_APPS";
				};

				qcom,pmic_glink_log_rpmsg {
					qcom,glink-channels = "PMIC_LOGS_ADSP_APPS";
					qcom,intents = <0x800 0x05 0xc00 0x03 0x2000 0x01>;
				};

				qcom,gpr {
					phandle = <0x4c8>;
					reg = <0x02>;
					qcom,intents = <0x200 0x14>;
					qcom,glink-channels = "adsp_apps";
					compatible = "qcom,gpr";

					spf_core {
						reg = <0x03>;
						compatible = "qcom,spf_core";
					};

					audio-pkt {
						reg = <0x17>;
						qcom,audiopkt-ch-name = "apr_audio_svc";
						compatible = "qcom,audio-pkt";
					};

					q6prm {
						phandle = <0x4c9>;
						reg = <0x07>;
						compatible = "qcom,audio_prm";
					};
				};
			};
		};

```

## 外围相关（同一份 FDT）

- `qcom,pmic_glink`（line 8555）：`qcom,pmic-glink-channel = "PMIC_RTR_ADSP_APPS"`，
  `qcom,protection-domain = "tms/servreg\0msm/adsp/charger_pd"` —— 这就是充电域。
- `qcom,pmic_glink_log`（8579）：`PMIC_LOGS_ADSP_APPS`，日志通道。
- `adsp_region@9fd00000`（177）与 `adsp_heap_region`（346）：与
  `dts/mondrian.dts` 里已修的 `adsp-base = 0x9fd00000` / `adsp-size = 0x03100000` 一致，
  互相印证。

## 下一步（按八步流程）

这不是推断出来的硬件：节点来自官方 FDT，属②官方 + ③反编译两步的直接产物。
要把 `remoteproc-adsp` + `pmic_glink` 落到我们的 ADT/DTS 里，先确认三件事：
寄存器基址与 `adsp_region` 不冲突、`glink-edge` 的 mbox 在我们的
`smem`/`ipcc` 映射里可解析、`status` 字段的取值。三者都有出处之后才动手。
## 构建器实际要求的完整依赖（`build-k60-physical-battery.py:56-80`）

`one('qcom,cape-adsp-pas')`、`one('qcom,smem')`、`one('qcom,ipcc')`、
`one('qcom,battery-charger')` 四个节点必须各存在一个，且：

- `glink-edge` 恰好一个，`qcom,remote-pid = 2`，`mboxes = <ipcc 3 0>`
- edge 下必须有子节点带 `qcom,glink-channels = "PMIC_RTR_ADSP_APPS"`
- `qcom,battery-charger` 的**父节点**必须带 `qcom,pmic-glink-channel = "PMIC_RTR_ADSP_APPS"`
- 还要有 `qcom,smp2p` 且 `remote-pid = 2`、`local-pid = 0`

## 厂商 FDT 里的实际取值（照抄即可）

| 节点 | 关键属性 |
|---|---|
| `ipcc` | `reg = <0xed18000 0x1000>`，`#mbox-cells = <2>`，`interrupt-controller`，`interrupts = <0 0xe5 4>` |
| `smem` | `memory-region = <…>`，`hwlocks = <… 3>` |
| `smp2p`（adsp） | `qcom,smem = <0x1bb 0x1ad>`，`mboxes = <ipcc 3 2>`，`interrupts = <3 2 1>`，`local-pid = 0`，`remote-pid = 2` |
| `battery-charger` | 父节点 `qcom,pmic_glink` 带 `PMIC_RTR_ADSP_APPS` + `protection-domain = "tms/servreg\0msm/adsp/charger_pd"` |

剩下两个未决依赖（下一轮必须先在仓库里找到出处，不能凭猜）：`smem` 的
`memory-region` 对应哪块保留内存、`hwlocks` 指向哪个 TCSR/hwspinlock 节点。这两项
在厂商 FDT 里是 phandle，必须解出指向的节点定义才能搬进我们的 ADT。

## ADT 已落地（2026-11-13）

`dts/mondrian.dts` 现在带有整套 GLINK 基础设施，全部取自官方 FDT，没有自造值：
`smem-region@80900000`（0x200000）、`syscon@1f40000`、`hwlock`（tcsr-mutex）、
`smem`、`mailbox@ed18000`（ipcc）、`remoteproc-adsp@3000000`（含 `memory-region = <&adsp_region>`
指向 `adsp-region@9fd00000`）、`smp2p-adsp`、`pmic-glink` + `battery-charger`。

验证方式不是"看起来对"，而是让构建器真正跑一遍：

```
$ dtc -I dts -O dtb -i <sm8475-common>/dts -o /tmp/m.dtb dts/mondrian.dts
（仅剩一条 warning：/mailbox@ed18000 Missing interrupt-parent）

$ python3 scripts/build-k60-physical-battery.py --output-dir /tmp/pbat \
    --framework /mnt/e/hackios/UniXNU --hardware-dtb /tmp/m.dtb \
    --battery-module /mnt/e/k60-work/firmware/qti_battery_charger_main_m81.ko
K60BatteryConfig.generated.c
K60BatteryProtocol.generated.h
captured-board-config.bin
Build the real Darwin22 Kernel SDK before this archive
```

四道节点检查（adsp / smem / ipcc / battery-charger）、glink-edge 的
`host0/ADSP2/IPCC3/0` 结构校验、smp2p 的 `remote-pid=2 local-pid=0` 全部通过，
构建器已经生成配置源文件，只差 Kernel SDK 才能编译成归档（`P-157` 的下一步）。
