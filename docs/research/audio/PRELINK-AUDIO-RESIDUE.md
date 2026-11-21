# 预链接残留里的音频：21 个槽，19 个目标

> 2026-11-21。音频线对 `gates:docs/research/ios27/PRELINK-RESIDUE.md` 做的逐条判定，不重复那份
> 205 项总审计。总表、复现脚本和 205→203 的口径都在 gates；这里只回答音频三个 bundle 的 21 个
> 槽是什么、stage 0 会不会碰、能不能用 PongAudioAmp/PongAudioGeniI2c 或补符号解决。

## 一、结论

1. 三个 bundle 一共 **21 个槽、19 个不同目标**：IOAudio2Family 1、AppleM2ScalerCSCDriver 4、
   IOAVFamily 16。其中 `0xfffffff00ac2534c` 与 `0xfffffff00ad714b8` 各被 Scaler 和 IOAV
   各引用一次，所以 21 个槽只对应 19 个函数起点。
2. 21 个槽全部是 **kext 持有的指针槽**，不是调用点：8 个 `__auth_got` 导入槽、13 个
   `__const` 表项。kext 不会 `bl` 到这些内核函数，它在方法里装载指针；因此不能用「找调用点」
   的办法证明它们不会被走到。口径见 `gates:docs/research/ios27/PRELINK-RESIDUE.md:7-14`。
3. **没有一项是 WCD938x/AW88261 的音频寄存器访问。** 13 个 `__const` 表项锚在
   `OSArray`、`OSSet`、`IOCommandGate`、`IOTimerEventSource` 这些通用内核对象的成员上；
   另外几个是机器例程、时钟、进程名和两个未定名的小辅助函数。bundle 名字带 AV，不等于目标是
   音频编解码。
4. **stage 0 的设计路径不会走到它们**：27 profile 的 board 没有 Pong 驱动树、没有 UFS、没有
   Adreno、没有 legacy display，也没有音频 client；stage 0 停在 `bsd_init`，到不了
   SpringBoard 的音频 client。这是设计路径的判定，**不是**「已经用 K60 日志证明它们不会执行」。
5. **PongAudioAmp/PongAudioGeniI2c 不能补这些符号**。它们是自己的 `pong_*` 驱动和
   `se_rd`/`se_wr` GENI 访问器，语义与 `OSArray::*`/`OSSet::*`/`IOWorkLoop::*` 无关；
   把自家函数塞进这些槽会满足签名却改变 Apple kext 对内核对象的假设，比 panic 更糟。

### 1.1 IOAudio2Family 的唯一槽

`com.apple.iokit.IOAudio2Family` 只贡献一个槽，和另外两个 bundle 的 20 个槽分开判：

| 项 | 值 |
| --- | --- |
| bundle | `com.apple.iokit.IOAudio2Family` |
| target | `0xfffffff00b36e788` |
| kind | `__auth_got` |
| site | `0xfffffff008273608` |
| 唯一 loader | `0xfffffff009f870bc+0x144` |
| 审计 verdict | `unreachable-before-console` |
| stage | post-SpringBoard (audio client) |
| baseline | false |

判据是三条，全部来自 `E:/k60-work/scratch/stubs/unreachable.toml:358-367`，不是从 bundle 名字推的：

1. 槽是 kext 持有的 `__auth_got` 指针，不是 `bl` 调用点；在 IOAudio2Family 里只有一个 loader，`0xfffffff009f870bc+0x144`。
2. 这条 loader 属于 post-SpringBoard 的 audio client 路径；审计把它标为 `unreachable-before-console`、`baseline=false`，不是上游已有基线。
3. console 前的结构证明：第一个 kext 入口是 `PE_init_iokit()`（`osfmk/kern/startup.c:689`），在 `console_init()`（`:478`）之后；205 个槽全在 kext 的 `__DATA_CONST`/`__const` 里，所以 console 前可达数为 0（`gates:docs/research/ios27/PRELINK-RESIDUE.md:19-25`）。

这条判据只证明「console 之前不会碰」，**不证明**「stage 0 全程不会碰」：stage 0 已经过 console，且 IOAVFamily 还有对象实例化窗口。要把这一条也关掉，需要以下任一可证伪观察：

- 在 stage-0/F3 日志里看到 IOAudio2Family 在 `bsd_init` 之前启动或加载。出现即按 `gates:docs/research/ios27/PRELINK-CLOSURE.md:36-41` 做函数配对或补实现，不能加 Pong 桩。
- 或者拿到 `0xfffffff009f870bc` 的调用者（当前只有 loader 关系，没有类/方法名），证明它只由 `IOAudio2Device`/`IOAudio2DeviceUserClient` 实例进入。在此之前，准确状态是「post-SpringBoard，stage-0 设计路径不到」。

反证入口：同一个 target `0xfffffff00b36e788` 还被 `com.apple.iokit.IOGPUFamily` 在 `0xfffffff00829c560` 引用（`E:/k60-work/scratch/stubs/unreachable.toml:369-377`）。它是通用内核例程，不是音频编解码寄存器访问；这也解释了为什么不能用 PongAudioAmp/PongAudioGeniI2c 补这个槽。

## 二、逐条表

缩写：`IOAudio2` = `com.apple.iokit.IOAudio2Family`，`Scaler` =
`com.apple.driver.AppleM2ScalerCSCDriver`，`IOAV` = `com.apple.iokit.IOAVFamily`。
`kind` 是槽的类型，`site` 是槽在 kext 里的地址；`size` 是目标函数在 24A446 参考里的字节数；
`ident` 是 gates 审计的识别度，`anchor` 是目标前一个已知符号（`unknown` 时只能给锚点）。

| bundle | target | kind | site | size | ident | anchor / 首次执行阶段 |
| --- | --- | --- | --- | ---: | --- | --- |
| IOAudio2 | `0xfffffff00b36e788` | `__auth_got` | `0xfffffff008273608` | 660 | unknown | 机器例程（中断）；post-SpringBoard 音频 client |
| Scaler | `0xfffffff00ab86b04` | `__auth_got` | `0xfffffff0080b55f8` | 12 | probable `_mach_absolute_time` | 时钟；display bring-up |
| Scaler | `0xfffffff00ac2534c` | `__auth_got` | `0xfffffff0080b5698` | 16 | unknown | 锚点 `_thread_set_cpuli…`；display bring-up |
| Scaler | `0xfffffff00ad714b8` | `__auth_got` | `0xfffffff0080b5630` | 116 | unknown | 锚点 `_qbt_transport_ac…`；display bring-up |
| Scaler | `0xfffffff00b0de1d8` | `__auth_got` | `0xfffffff0080b5620` | 132 | probable `_proc_name` | bsd proc；display bring-up |
| IOAV | `0xfffffff00ac2534c` | `__auth_got` | `0xfffffff008243b00` | 16 | unknown | 锚点 `_thread_set_cpuli…`；对象实例化（任意时刻） |
| IOAV | `0xfffffff00ad714b8` | `__auth_got` | `0xfffffff008243aa0` | 116 | unknown | 锚点 `_qbt_transport_ac…`；对象实例化（任意时刻） |
| IOAV | `0xfffffff00b24f1ac` | `__const` | `0xfffffff00823a988` | 68 | unknown | 锚点 `OSObject::it…`；对象实例化 |
| IOAV | `0xfffffff00b24f250` | `__const` | `0xfffffff00823a970` | 284 | unknown | 锚点 `OSArray::get…`；对象实例化 |
| IOAV | `0xfffffff00b24f4b8` | `__const` | `0xfffffff00823a960` | 204 | unknown | 锚点 `OSArray::rem…`；对象实例化 |
| IOAV | `0xfffffff00b2502cc` | `__const` | `0xfffffff00823a8a0` | 168 | unknown | 锚点 `OSArray::free…`；对象实例化 |
| IOAV | `0xfffffff00b250384` | `__const` | `0xfffffff00823a890` | 312 | unknown | 锚点 `OSArray::ge…`；对象实例化 |
| IOAV | `0xfffffff00b2581dc` | `__auth_got` | `0xfffffff008243790` | 172 | unknown | 锚点 `OSDictionary…`；对象实例化 |
| IOAV | `0xfffffff00b2869dc` | `__const` | `0xfffffff00823a700` | 80 | unknown | 锚点 `OSSet::setOp…`；对象实例化 |
| IOAV | `0xfffffff00b286bd8` | `__const` | `0xfffffff00823a688` | 168 | unknown | 锚点 `OSSet::free…`；对象实例化 |
| IOAV | `0xfffffff00b286c90` | `__const` | `0xfffffff00823a678` | 344 | unknown | 锚点 `OSSet::getM…`；对象实例化 |
| IOAV | `0xfffffff00b315dd8` | `__const` | `0xfffffff00823c568` | 204 | unknown | 锚点 `IOCommandGate…`；对象实例化 |
| IOAV | `0xfffffff00b316084` | `__const` | `0xfffffff00823c528` | 84 | unknown | 锚点 `IOCommandGate…`；对象实例化 |
| IOAV | `0xfffffff00b31a524` | `__const` | `0xfffffff00823ce58` | 112 | unknown | 锚点 `IOTimerEventSource…`；对象实例化 |
| IOAV | `0xfffffff00b31af40` | `__const` | `0xfffffff00823cd98` | 160 | unknown | 锚点 `IOTimerEventSource…`；对象实例化 |
| IOAV | `0xfffffff00b31afe0` | `__const` | `0xfffffff00823cd90` | 88 | unknown | 锚点 `IOTimerEventSource…`；对象实例化 |

**识别度**：这 21 行里 0 行是 `identified`。0xab86b04 与 0xb0de1d8 是 `probable`，其余 19 行
只有锚点；gates 的总审计也把 105/131 个目标列为无名字，26 个名字里 22 个只是与同构建 iPad
夹具比对出的「很可能」。不要把这里的 `OSArray`/`OSSet` 锚点当成已证实的函数名。

## 三、stage 0 为什么不会碰

四个静态事实：

- `gates:board.toml:352` 的 `remove` 含 `kernel.pong_native_driver_source`；stage 0 不建
  Pong 驱动树。
- `gates:board.toml:360` 的 `components.include` 只有 `ArmDTPlatform`、`ArmCpu`、
  `XnuPrelink`；没有 PongUfs，也没有显示/音频组件。
- `configs/mondrian_ios27_defconfig:20-22` 把 `CONFIG_XNU_NATIVE_UFS`、
  `CONFIG_XNU_NATIVE_ADRENO`、`CONFIG_XNU_NATIVE_LEGACY_DISPLAY` 都设成 `n`；因此没有
  UFS、Adreno、legacy display provider 去匹配这些 Apple kext。
- stage 0 的终点是 `bsd_init`；没有 SpringBoard，也没有音频 client。`IOAudio2Family` 的
  首次执行阶段就是 post-SpringBoard 音频 client。

但这四条只证明「没有设计路径」，不证明「运行时一定不会实例化」：

- `gates:docs/research/ios27/PRELINK-RESIDUE.md:19-25` 证明的是 **console_init() 之前没有
  kext 代码**；stage 0 已经过 console，所以这条不能直接推出「stage 0 不会碰」。
- `gates:docs/research/ios27/PRELINK-RESIDUE.md:34-51` 说 console 后最先咬的是 AMFI、apfs、
  sandbox、WatchdogTimer、IOStorage；音频三个 bundle 不在最前面。若 stage 0 在根挂载或首个
  launchd 就停住，音频槽没有机会成为第一故障。
- `IOAVFamily` 的阶段写的是「对象实例化（任意时刻）」，这是一个**尚未排除**的窗口。要么在
  F3/F4 给出一条「本 board 没有实例化 IOAV 对象」的可证伪观察，要么承认它仍开放；不要用
  「音频无关」把它标成已解决。

因此本文的准确说法是：**stage 0 的设计路径不会走到这 21 个槽；运行时无实例化这一句仍需
K60 日志或一次显式的 policy 证伪，当前没有。** 这不是把 205 项判成安全；总审计仍要求把
`prelink-map-unresolved` 保持 open。

## 四、能不能用 PongAudioAmp/PongAudioGeniI2c 补

不能。两边的符号形状和语义都不是一回事：

- Pong 侧是自家的 GENI I2C/音频功放驱动：`drivers/PongAudio/PongAudioAmp.c:418` 的
  `se_rd(void *ctx, uint32_t reg)` 和 `:425` 的 `se_wr(void *ctx, uint32_t reg, uint32_t
  value)` 读写的是 SE/GENI 寄存器；它们被填进 `PongGeniIo`（`drivers/PongAudio/PongAudioGeniI2c.h:66-70`）
  再交给 `pong_geni_prepare()`（`drivers/PongAudio/PongAudioGeniI2c.c:15`）。
- `PongAudioAmp.c:511-512` 的 `io.read = se_rd; io.write = se_wr;` 是**自家 io 表**的赋值，
  不是 Apple kext 的 `__auth_got` 槽。Pong 的 `pong_audio_amp_probe()`（`PongAudioAmp.c:944`）
  也不会导出 `OSArray`、`OSSet`、`IOWorkLoop` 的成员。
- 把 `se_rd/se_wr` 塞进 `OSArray` 的槽，参数个数可能凑巧一样，调用约定和行为完全不同；
  Apple kext 随后会把返回的「对象指针」当 `OSArray` 用。这比直接 panic 更难查。

真正的选项只有三类：

1. **函数配对**：本内核里已经有 `OSArray`、`OSSet`、`IOWorkLoop`、`IOCommandGate`、
   `IOTimerEventSource` 的实现（源码在 `libkern/c++` 与 `iokit/Kernel`），若目标确实是这些
   成员，应走 matcher 的 `functions` pair，用 reviewed 证书按签名/形状配对，而不是写 Pong 桩。
   当前 `gates:scripts/k60-fileset-pair.py:2-10` 只把 `[[pairing]]` 折进 `payload['data']`，
   `:49-60` 的 `reviewed()` 也只接受 data pairing；函数入口不在这个工具里。
2. **补内核实现**：若本内核根本没有那个函数（例如某个 Apple 私有辅助），先按
   `gates:docs/research/ios27/PRELINK-CLOSURE.md:36-41` 的处方补实现或 `.original` 适配器，
   再让 matcher 配；不能用一个返回 0 的 stub 让链接变绿。
3. **显式 policy**：只有在该 bundle 确实不会运行时，才在 allowlist/policy 登记「为什么这条
   路径不会走」并附可证伪观察。当前 allowlist 只登记 data/metaclass 的 16 条，没有函数 pair
   （`gates:docs/engineering/IOS27-PRELINK-ALLOWLIST.toml:88-180`）；函数槽不能借它消音。

## 五、可复现

总审计的 205/203/25 与逐目标表由 gates 记录的脚本复现：

```sh
cd /mnt/e/k60-work/scratch/stubs
python3 classify.py check       # 205 items / 203 keys / 25 bundles, check: OK
```

只看音频 21 行：

```sh
python3 - <<'PY'
import json
p='/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.json'
d=json.load(open(p))
audio={'com.apple.iokit.IOAudio2Family','com.apple.driver.AppleM2ScalerCSCDriver','com.apple.iokit.IOAVFamily'}
rows=[(b,t) for b in audio for t in d['stubbed'].get(b,[])]
print('slots',len(rows),'targets',len({t for _,t in rows}))
print('missing in audio',sum(len(d['missing'].get(b,[])) for b in audio))
assert len(rows)==21 and len({t for _,t in rows})==19
assert not any(d['missing'].get(b) for b in audio)
PY
```

读者若要核对单个目标，用参考表里的 `target/size/site` 对 `kernel.json` 的 `stubbed` 与
`PRELINK-RESIDUE` 的逐目标表；不要用本内核的 `llvm-nm` 邻接符号给目标命名——那是我们自己的
构建布局，不是 Apple 参考的函数身份。

## 六、这篇不证明什么

- 没有 K60 启动日志；stage 0 是否真的没有实例化 `IOAVFamily` 对象，仍未被运行时证据证明。
- 19 个目标里 17 个只有锚点，2 个是 `probable`；没有一个是 `identified`，所以「属于哪个
  函数」目前只能说到类族和锚点，不能说到具体成员。
- 没有编译、没有链接、没有设备；函数配对/补实现都还没做。
- 不是把 205 项判成安全，也不是给 F3/F4 的放行；`prelink-map-unresolved` 仍按
  `gates:docs/research/ios27/PRELINK-CLOSURE.md:49-78` 保持 open。
