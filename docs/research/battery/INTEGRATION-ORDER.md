# ADSP handoff 集成顺序

> 2026-11-15；0619 仅留 feat/adsp-handoff-owner，不并 main。五阶段软件编排已实现并通过注入测试；真实 carrier/平台后端仍由 Lead/ADSP 接入，不证明 PAS1、GLINK、音频、电池或充电可用。

调用前置条件见 [HANDOFF-PUBLISH.md](HANDOFF-PUBLISH.md#调用点契约)，完整签名、返回码和 callback 责任见 [PAS1-PROVIDER-CONTRACT.md](PAS1-PROVIDER-CONTRACT.md)。编号保持 thermal0617、springboard0618、handoff0619；未改默认参数、白名单或其他线补丁，未做内核/镜像构建和设备操作。

## Boot 时间轴

本分支候选路径如下。同步调用必须在一次性 consumer 之前完成或失败；任一步失败停止交接并继续原有 IOBSD/battery 顺序，不制造属性。

~~~mermaid
flowchart TD
    A["bsd_init()"] --> B["bsd_autoconf(): kminit / pseudo devices"]
    B --> C["IOKitBSDInit()"]
    C --> G{"pong_handoff_publish 解析成功且 ==1?"}
    G -- 否 --> I["publishResource(IOBSD)"]
    G -- 是 --> P["runtime: claim / config overlap / chosen / OSData preflight"]
    P --> O["stages1–3: claim → stopped FIFO prepare → PAS auth/start"]
    O --> S["stage4: SMP2P ready/non-reset + short discovery lock"]
    S --> H["stage4 final TCSR: build_existing + self-parse"]
    H --> U["unlock; stage5 ready/epoch + atomic chosen commit"]
    U --> I
    I --> K["k60_physical_battery_start(): one-shot"]
    K --> R["return; setconf / IOFindBSDRoot"]
    R --> V["vfs_mountroot()"]
~~~

概念六步仍是 PAS1 → SMP2P ready/non-reset → 最终 TCSR → SMEM partition/build → 解锁 → /chosen。实际实现另有 stopped 准备和短 discovery 锁，不能把箭头误读为首次 SMEM 访问无锁，或在生产后端未就绪前先 map。

## 五阶段与六步对应的函数边界

| 顺序/概念 | 当前函数与边界 | 必须先满足 | 必须早于 |
|---|---|---|---|
| runtime preflight | k60_adsp_handoff_publish：永久 startup owner1 claim；生成配置、XNU RAM overlap、/chosen duplicate 检查；预分配 OSData。 | 默认关闭门控成功；电池宏启用。 | provider 有副作用、SMEM/TCSR map。 |
| 阶段1 claim | k60_owner_claim：完整 available/backend/reader、MDT验证、排他 cookie/epoch、资源和 stopped/live 证明，再 map 和短 TCSR probe。 | Lead 的早期 carrier/SCM/资源路径已经可用；不得等待 rootfs。 | FIFO 准备和任何 PAS 写操作；缺依赖 -1000 早于 mapping。 |
| 阶段2 stopped prepare | k60_owner_prepare_pas1：短 TCSR 下 partition 查找，fresh478/479/480分配32/4096/4096；拒绝旧 host items，不创建443。 | 逻辑排他 lease 持续；PAS stopped。 | AUTH/start。partial失败不可重试为fresh。 |
| 阶段3 / 六步1 PAS1 | k60_owner_auth_and_start：INIT metadata一次 → reloc MEM_SETUP → COPY/BSS/CACHE → AUTH_AND_RESET。 | stopped/资源/排他有效；reader bytes pin到load；实际物理装载和cache同步由后端完成。 | public Authenticated bit0、ready；此时仍无 native lease。 |
| 阶段4 / 六步2 SMP2P | k60_owner_build_handoff 调 ready；backend自己短锁发现443，再由core短锁复核partition/ready/restart/全零descriptor/items。 | PAS成功且public facts15；plan.required15/epoch匹配。 | 最终序列化锁；不通过则不build、不写chosen。 |
| 阶段4 / 六步3–5 | 解锁重验 live，再 lock；只 k60_handoff_build_existing + consumer self-parse；unlock后核对offsets/epoch/restart。builder本身不锁。 | discovery已解锁、逻辑lease仍pin；final TCSR成功。 | 内部build/self-parse bit1及native lease；公共bit1始终ResourcesHeld。 |
| 阶段5 / 六步6 | k60_owner_publish：registry root/exists、owner live、ready/restart和blob/epoch检查，runtime commit内append/self-parse并runPropertyAction原子无覆盖写104字节。 | final TCSR已释放；callback不执行于该临界区。 | 同步返回、IOBSD、physical battery，因此也早于setconf/root挂载。 |

生产 wrapper 的 k60_adsp_owner_acquire 顺序执行阶段1–4，并为stage4 plan先调用一次ready；k60_adsp_owner_publish执行阶段5。runtime不再自己map/ready，也不走旧aggregate k60_handoff_publish；不得外层持同一不可重入TCSR后调用阶段API。

## 逻辑所有权与短锁

软件排他 session 从claim持续覆盖阶段2–4和stage5 commit；copy配置/ops且context/reader持久，不能使用runtime栈寿命作为资源寿命。短TCSR分别用于probe、stopped allocation、ready discovery、core discovery和final build/parse；每次成功取得才恰好解锁一次。ready回调必须有界、只在解锁后sleep，未来硬件后端需落实时限，本轮没有可运行的真实polling实现。

最终TCSR区只包含build_existing+self-parse，不包含PAS/owner callback、日志、sleep、OSData或registry操作。核心stage诊断为 K60ADSP owner stage=%d rc=%d，解锁后才输出。TCSR不冻结DSP；逻辑平台排他契约必须覆盖所有解锁窗口，restart检查不能防止未来崩溃。

AUTH尝试后失败必须shutdown并独立证明stopped才释放；无法确认则Poisoned保留votes/exclusion/map/reader，不重试。成功commit与Published转换受同一非阻塞API gate保护；重入abort不能掉票或复位已发布DSP，成功后没有release路径。

## 电池入口与 root 挂载

- 检查的XNU顺序是bsd_init → bsd_autoconf → IOKitBSDInit，返回后才setconf/IOFindBSDRoot → vfs_mountroot。registry root指/chosen可用，绝不是rootfs已挂载。
- consumer先置attempted再读属性；无属性/无效属性返回后不会为晚到属性重试。Data-mount、root后文件读取或异步补发均太晚。
- 未安装backend时acquire=-1000，runtime前置检查通过后返回-42且不map；无属性consumer在transport之前blocked=-4。这是源码与host边界，不是设备观察。
- 早期启用尝试永久占用startup owner1，即使失败也排斥late owner2；gate关闭不取该claim，晚期诊断保留自身策略。原有属性提前duplicate退出并保留，不能据此证明其有效。

## 默认关闭和宿主断言

PE_parse_boot_argn必须返回成功且写入unsigned==1才调用；局部初值0。检查的XNU parser把裸pong_handoff_publish视为1，四字节还会截断4294967297为1，因此不是严格原始token字符串检查。缺参/解析失败（即使写1）或结果0/2/UINT32_MAX拒绝；电池宏0时连parser都编译掉。未修改board默认参数或镜像白名单。

[test-k60-handoff-integration.py](../../../scripts/tests/test-k60-handoff-integration.py) 将0619以fuzz0应用到临时predecessor fixture，提取应用后的真实IOKitBSDInit函数体，7场景×电池宏0/1=14。关闭路径publisher/SMEM/TCSR/PAS/claim spy为0；开启路径非空跑，且provider错误时仍保持publisher→IOBSD→battery。parser为stub，不覆盖原始boot-string或硬件，也不证明其他boot模块不访问SMEM。5补丁段/3 canonical mirrors通过；late fixture按当前0614重建，不是完整series重放。

新增五阶段host77场景（17/11/12/15/22）使用fake carrier/PAS/资源/registry和真实MDT/SMEM/build/parser。详见 [测试入口](../../../scripts/tests/run-k60-handoff-host.sh) 及provider契约。当前日志 E:/k60-work/artifacts/adsp-owner-stages-20261115/final-host/host-tests.log；不生成内核/镜像，不证明实际PAS启动或GLINK通信。

## 未来集成者检查清单

- [ ] 0619仅留分支；与Lead-owned carrier及真实平台后端共同评审，保持thermal0617/springboard0618。
- [ ] 逐项安装完整ops与reader，先available/stopped/排他证明再map；真实SCM序列化/resume/busy/coherence和COPY/BSS/cache到物理ADSP区域落实。
- [ ] 五阶段同步完成早于IOBSD/一次性battery/root挂载，入口均先过默认关闭gate，无提前claim/map旁路。
- [ ] 当前启动cookie/epoch、资源和逻辑lease跨越阶段2–4及stage5；不把内部build bit1当public ResourcesHeld。
- [ ] short锁配对；final只有build+selfparse；ready/日志/睡眠/registry均在final之外。
- [ ] stopped时仅fresh host478/479/480；不创建443、不清零活环；required精确15、epoch/几何/ready/restart一致。
- [ ] AUTH失败可安全shutdown+stopped；不确定Poisoned保留资源；原子发布成功后无abort/release/reset路径。
- [ ] 重跑77阶段/14dispatch/5段fuzz0/3mirrors，再单独授权完整series/kernel链接和产物核验。
- [ ] 只有用户与Lead明确授权才boot；以真实PAS1、持续资源、SMP2P、consumer发现和GLINK报文判定，不凭日志或合法blob。

## 检查的源码位置

本分支 [0619](../../../patches/xnu/0619-k60-adsp-glink-handoff.patch)、[runtime](../../../drivers/PongPower/K60HandoffRuntime.cpp)、[stages](../../../drivers/PongPower/K60AdspOwnerStages.c)、[builder](../../../drivers/PongPower/K60HandoffBuild.c) 与 [consumer](../../../drivers/PongPower/K60Battery.cpp)。只读缓存 /opt/k60/trees/k60build/out-baseline/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work 用于定位/fixture，不宣称整体等于分支。

缓存bsd/kern/bsd_init.c约908–909/1305–1321/983–994/1370–1375行对应autoconf/IOKitBSDInit/root顺序，SHA e75e23c6be6a60121e11bf9e5501c39ef0bd40e19898c223a5b48b02d2f50bdb；IOKitBSDInit.cpp SHA 9bb81ab81d076304e338e23ef294046276792ab8c6e3e56ea6441f5a5bc5df09。pexpert/gen/bootargs.c约140–144/378–379/485–486行对应数值copy/四字节截断/裸参数1，SHA1431f1f8aacae240b87bd29cd91905784c968f8014784201b3ed862bdb1b4ed9。
