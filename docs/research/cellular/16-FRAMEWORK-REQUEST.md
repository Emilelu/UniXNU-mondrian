# 16 · 框架侧接口要求：ADT 占位与 MODEM/ 注入

> 收件人：Lead（在 k60-gates 侧统一改 `UniXNU` 并推 fork）。
> 本文只写**接口**，不改 `UniXNU`。固件侧已落地（`uefi-mondrian` `72e51ca` + `5d96806`），
> 契约见 `12-DXE-CONTRACT.md` §3.1/§3.7、载具实现见 `15-FIRMWARE-CARRIER-LOADER.md`、
> 验收断言见 `13-FIRMWARE-ACCEPTANCE.md` 表 A。
>
> **2026-11-16 19:32 已交付**：`UniXNU` fork 分支 `feat/modem-carrier`，
> `9198213`（实现：devicetree/payload/cli）+`ecc15f9`（文档），HEAD
> `ecc15f974770625496965650f487a148333291db`。本文此后作为**接口契约与验收依据**保留；
> 实现与本文的差异、以及交付实际覆盖到的范围见 §5 与 [17 号清单](17-OFFLINE-ACCEPTANCE-CHECKLIST.md)。

## 0. 一句话

两处改动，缺一不可，**必须同时打开或同时关闭**：

1. `devicetree.py` 的 `/chosen/memory-map` 多一条 16 字节全零的 `K60ModemImage`；
2. `payload.py` 往 stage 里放 `EFI/UniXNU/MODEM/` 的 27 个 `.lzma`。

只做 2 不做 1：固件发现载具目录存在、占位缺失 ⇒ `EFI_COMPROMISED_DATA`，黑屏。
只做 1 不做 2：固件打 `modem-image: no carrier in payload, skipped` 后照常启动（这条路径已经修好了，
见 `5d96806`），只是没有 modem。
所以两处用**同一个开关**，不能各自为政。

## 0.1 为什么先开目录再校验（固件侧 `5d96806` 的理由，改框架前必读）

`ImageCarrierLoad` 的第一版把顺序写反了：先查 `/chosen/memory-map` 里的 `K60ModemImage`
占位，占位缺失就 `EFI_COMPROMISED_DATA`；查到了才去 `Root->Open` 那个 `EFI/UniXNU/MODEM`
目录。这在只有 modem 镜像的世界里是对的，在真实世界里是把所有别的镜像变砖：

> payload 与 display/audio/wifi 共用，那些镜像 memory-map 只有 name ⇒ 先校验占位会全变砖。

这不是推测。抽一份共用的 `kernel.macho.adt`（`pong_adt_contract.parse_adt`）看
`/chosen/memory-map` 的属性名，结果只有 `['name']` —— 连 `PackedRAMDisk` 都没有，更不会有
`K60ModemImage`。也就是说：**只要 payload 里还没有 modem 载具，任何一份共用产物都过不了
占位检查**，而 `payload.py` 目前根本不注入载具（这正是本文要 Lead 补的第二处）。两条线一
起上，就会得到「所有镜像都黑屏」的结果，且原因只有一行 `placeholder missing`，看不出是
「这条线不需要 modem」。

修法（`5d96806`）是把顺序倒过来：**先开目录**，目录不存在 ⇒
`modem-image: no carrier in payload, skipped` + `EFI_SUCCESS` + `Files = 0`，继续启动；
目录存在才去校验占位，四条失败路径（缺失 / 长度≠16 / 非零 / memory-map 畸形）各自先
`Dir->Close` 再返回。判据因此变成「这个镜像声明了要装载具吗」，而不是「这个镜像的 ADT 里
有没有那条属性」。

形状：**同一份产物被多条线共用时，某一条线的强校验会变成所有人的硬门槛。** 共用产物上的
强校验必须绑定在「本条线自己的声明」上（这里是目录存在），不能绑定在「产物全局应该有什么」
上（这里是 ADT 里必须有一条属性）。同样的坑 modem / adsp / wifi 三条线都会再撞一次，
所以这条不只写给载具：改框架时如果新增了任何「产物里必须有 X」的检查，请同时给出
「本镜像不需要 X」的出口，并让它是一条明确的成功路径（有日志、有返回码），而不是注释。

## 1. `devicetree.py`：`K60ModemImage` 条目

### 1.1 位置

`scripts/unixnu/devicetree.py:291` 的 `generate()` 签名与 `:337-341` 的 mappings 构造：

```python
def generate(dtb, config, *, unique_chip_id=None, data=False, trust=False, addon=False, root_policies=False):
    ...
    mappings = [('PackedRAMDisk' if options.get('packed_data_ramdisk') else 'RAMDisk', bytes(16))] if data else []
    mappings += [('TrustCache', bytes(16))] if trust else []
    mappings += [('GpuAddon', bytes(16))] if addon else []
    mappings += [('RootPolicies', bytes(16))] if root_policies else []
    children = [node('chosen', chosen, [node('memory-map', mappings), node('manifest-properties')])]
```

### 1.2 改法

签名加一个关键字参数（默认 `False`，保持既有调用者不变）：

```python
def generate(dtb, config, *, unique_chip_id=None, data=False, trust=False, addon=False, root_policies=False,
             modem=False):
```

在 `:340` 的 `RootPolicies` 行之后、`:341` 的 `children =` 之前插入一行：

```python
    # K60 modem carrier: 16 zero bytes until ImageCarrierLib in DarwinBoot writes
    # the window it copied (base, span). Same shape as RAMDisk/TrustCache - a name
    # and 16 bytes, no length field, no type tag. The loader refuses to boot a
    # payload that ships EFI/UniXNU/MODEM without this placeholder, so it is
    # published exactly when the payload carries the carrier.
    mappings += [('K60ModemImage', bytes(16))] if modem else []
```

- `bytes(16)` = 16 个零字节 = **未发布**。运行期由固件用两次 `WriteUnaligned64` 写成
  `base=0x8bc00000, span=0x13200000`（`ImageCarrierLib.c` 的 `ImageCarrierLoad` 尾部）。
- 属性名 16 字符以内（`node()` 在 `:17-18` 拒绝 >31 B 的键名），`K60ModemImage` 名字长 14 B，安全。
  这里说的是**名字长度**；占位**值**必须是 16 B 全零，两者不能混。
- **不要**加长度字段或类型标签：`scripts/pong_adt_contract.py:83` 与 13 号 A5 都按「恰好 16 B」判。

## 2. `payload.py`：`generate()` 的实参

`scripts/unixnu/payload.py:231-236`：

```python
    if ctx.schema_version == 2:
        from .devicetree import compile_hardware, generate
        dtb = compile_hardware(ctx)
        (payloads / 'kernel.macho.adt').write_bytes(generate(
            dtb, ctx.board, unique_chip_id=seed, data=bool(data), trust=bool(trust), addon=bool(addon),
            root_policies=bool(policies)))
```

改成多传一个 `modem`（`modem` 的来历见 §3）：

```python
            root_policies=bool(policies), modem=bool(modem)))
```

**注意顺序**：ADT 先写（占位进 `kernel.macho.adt`），`MODEM/` 后拷（`write_volume` 才落盘）。
两者在同一次 payload 构建里完成，所以不存在「ADT 有占位、卷里没文件」的中间态产物。

## 3. `payload.py`：`EFI/UniXNU/MODEM/` 的注入位置

### 3.1 位置（这是关键，不是 mcopy 之后）

`write_volume()`（`:93-101`）只做一件事：`mformat` 建卷，然后
`for entry in sorted(stage.iterdir()): mcopy -i image -s -Q -m entry ::/`。
**`-s` 递归**，所以只要 `stage/EFI/UniXNU/MODEM/` 在调用 `write_volume` 之前存在，它就会随
`stage/EFI` 一起被拷进卷里。绝对不要在 `write_volume` 之后另起一次 `mcopy`——那会绕开下面三条既有保证。

正确插入点：`:283` 的 `(stage / 'EFI/UniXNU/unixnu.toml').write_text(config)` **之前**，也就是
`:260` 的 if/else（ADT 生成）之后、`:261` 的 `initrd = ...` 之后任意处。推荐紧贴 `:283`：

```python
    # The modem carrier: one LZMA stream per firmware segment, decompressed by
    # ImageCarrierLib straight into the modem window. Placed before the utime
    # pass and write_volume so the files get the same EPOCH timestamps as the
    # rest of the volume (reproducible image) and are counted by the size check.
    if modem:
        carrier = stage / 'EFI/UniXNU/MODEM'
        carrier.mkdir(parents=True)
        streams = sorted(path for path in modem.iterdir() if path.suffix == '.lzma')
        if not streams:
            raise Error(f'the modem carrier directory has no .lzma stream: {modem}')
        for stream in streams:
            shutil.copyfile(stream, carrier / stream.name)
        log(f'payload: modem carrier, {len(streams)} LZMA streams')

    (stage / 'EFI/UniXNU/unixnu.toml').write_text(config)
```

这样自动满足三条既有保证：

| 保证 | 位置 | 为什么重要 |
| --- | --- | --- |
| 时间戳归零 | `:284-285` `for path in [stage, *stage.rglob('*')]: os.utime(path, (EPOCH, EPOCH))` | 两次构建出同一个 sha256；`rglob` 会覆盖新目录 |
| 容量检查 | `:286-289` `content > size * 1024 * 1024 * 0.95` 即 raise | 载具 48,591,795 B 必须算进去，否则卷满才发现 |
| 一次性建卷 | `:290` `write_volume(...)` | 卷只 `mformat` 一次；后补文件要重开卷 |

### 3.2 `modem` 从哪来

三处，按优先级（与 `root_policies` 同形）：

1. `cli.py` 新选项 `--modem-carrier DIR`（§4）；
2. `board.toml [payload] modem_carrier = "<模板>"`，用 `policy_path.format(tree=ctx.tree, out=ctx.work)` 的同一套展开；
3. 都没有 ⇒ `modem = None` ⇒ 不注入、不发布占位，产物与今天逐字节相同。

取值代码放在 `:158-170`（`policy_path` 那一段）旁边：

```python
    modem_path = spec.get('modem_carrier')
    modem = expand(modem_path.format(tree=ctx.tree, out=ctx.work)) if modem_path else None
    if getattr(args, 'modem_carrier', None):
        modem = expand(args.modem_carrier)
    if modem is not None:
        if ctx.schema_version != 2:
            raise Error('The modem carrier handoff requires a format 2 device tree')
        if not modem.is_dir():
            raise Error(f'modem carrier directory not found: {modem}')
```

### 3.3 输入目录的形状（由设备仓库的打包脚本产出）

```text
<carrier-dir>/
    modem.b01.lzma
    modem.b02.lzma
    ...
    modem.b29.lzma        # 27 个；名字不是连号，见下
    modem-table.txt       # "<segment> <bytes>" 每行一段，27 行
```

段表 `K60ModemImageTable.h` 有 **30 行**，但只有 **27 行带文件名**：第 14、21、30 行是纯 bss 段
（`((const char *)0)`，bss 分别为 4096、163696640、15851520 字节）。所以 27 个名字是
`b01–b13, b15–b20, b22–b29`，**没有 b14/b21/b30**。按 `b01..b27` 或 `b01..b30` 连号生成会否定
真实输入：`b01..b27` 会拒绝 b28/b29 并索要不存在的 b14/b21/b30。`gen-modem-table.py --manifest`
只输出 filesz 非零的行，正好 27 行，方向是对的。

每个文件是 **LZMA-alone**（`xz --format=lzma`）流，且：

- 前 5 B 属性首字节 `0x5D`（`lc=3,lp=0,pb=2`）；
- 第 6..13 B 是 8 B 小端**未压缩长度**，必须改写成段表该行的 `bytes`
  （`xz` 流默认写 `0xFFFFFFFFFFFFFFFF`，不改固件会拒）；
- 13 B 头之后是压缩数据，固件按 `SourceSize - 13` 校验「正好消费完」。

这 27 个文件**不由框架生成**：它们来自设备仓库的打包脚本
（`k60-cellular` 侧，`gen-modem-table.py` 出表 + `xz --format=lzma` + 改写 8 B 字段）。
框架只负责「拷进 stage、数一数、记进 payload.json」。

### 3.4 记录进 `payload.json`

`:291-296` 的 `data_report` 加两个字段，让门禁和事后取证不依赖卷：

```python
                   'modem_carrier_files': len(streams) if modem else 0,
                   'modem_carrier_sha256': sha256_file(...) if modem else None,
```

`modem_carrier_sha256` 建议对「排序后的 `name:size` 列表 + 各文件 sha256」做一次哈希，不要只哈希目录名。

交付实现（`ecc15f9`）记录五个字段：`modem_carrier_files`、`modem_carrier_bytes`、
`modem_carrier_compressed_bytes`、`modem_carrier_sha256`、`modem_carrier_placeholder`。
关闭时前四个在 `payload.json` 里为 `null`，`_placeholder` 为 `false`，且 ADT 不出现该键。
本节的 `_files`/`_sha256` 是必须项，其余三个是增强项。

## 4. `cli.py`：新选项

加在 `common()`（`:17-50`），这样 `build payload`、`payload` 快捷命令都拿到：

```python
    p.add_argument('--modem-carrier', metavar='DIR',
                   help='directory of LZMA streams for the modem carrier (EFI/UniXNU/MODEM); '
                        'also publishes the K60ModemImage placeholder; or UNIXNU_MODEM_CARRIER')
```

- 默认 `None` ⇒ 行为完全不变。
- 环境变量 `UNIXNU_MODEM_CARRIER` 与其它路径选项一致（`--uefi`/`--kernelcache` 都这么做）。
- **不要**给 `bootimg` 子命令加（`:68-72`）：载具是 payload 的属性，不是 boot.img 的。

## 5. 改完之后怎么验证（全部离线，不依赖上机）

按顺序做，前一条不过就别做下一条。

实际验收的输入来源、真实退出码、OFF/ON 分组与随机控制前提见 [17 号离线验收清单](17-OFFLINE-ACCEPTANCE-CHECKLIST.md)。本节命令保留为接口示意；候选必须来自 Lead 交付的已提交框架和隔离严格构建，不执行下面带 `UNIXNU_SKIP_GATES=1` 的示意命令来宣称候选通过。

框架级子集已有可执行验收工具：`k60-cellular/scripts/verify-modem-carrier.py`（覆盖本节 5.1、
5.2 的卷与 5.3；全部输入参数化，写 `acceptance.json` 回执）。2026-11-16 在真实 `board.toml`、
`candidates/4g-quiet/hardware.dtb` 与 dxe-dryrun-d 的 27 个流上 `ACCEPTANCE PASS 11/11`、rc 0。
回执取自 `ecc15f974…` 的独立 `git clone`（本地 clone + checkout 该 SHA，HEAD 一致、dirty 0），
不是共享工作区当前内容；工具在载具实现三文件有未提交改动时以 rc 2 拒绝运行。
它不运行 `unixnu build payload`、不构建内核，因此只是框架级子集，不替代 17 号的整链验收。

> 本机注意：这台 WSL 的 `/tmp` 里留着 root 所有的旧文件，写会 `PermissionError`、
> `mcopy` 覆盖时会挂在确认提示上等输入（看起来像卡死）。下面所有 `/tmp/...` 路径请换成
> 自己的可写目录（例如 `/mnt/e/k60-work/artifacts/vfy/`）。

### 5.1 单元级：ADT 属性

```sh
python3 - <<'PY'
import sys, pathlib
sys.path.insert(0, 'scripts')
from unixnu.config import load_toml          # board.toml 是纯 TOML，不需要完整 ctx
from unixnu.devicetree import generate
board = load_toml(pathlib.Path('../UniXNU-mondrian/board.toml'))
dtb = pathlib.Path('out-baseline/mondrian/ipados-16.6.1-20G81/mondrian/device-tree/hardware.dtb')
kw = dict(unique_chip_id='0123456789abcdef')
on  = generate(dtb, board, modem=True, **kw)
off = generate(dtb, board, modem=False, **kw)
assert on != off
pathlib.Path('/tmp/adt-on.bin').write_bytes(on)
pathlib.Path('/tmp/adt-off.bin').write_bytes(off)
PY
```

（`generate()` 的 `config` 参数只读 `['payload']` 与 `['adt']` 两节，所以传 `load_toml()` 的裸 dict 即可，
不必构造 `ctx`；但 `random-seed` 每次不同，`on != off` 这条断言本身就恒真，**真正的判据是下面这条**。）

再用设备仓库的解析器核对（这一条是硬判据，不要只看「生成成功」）：

```sh
python3 - <<'PY'
import sys, pathlib
sys.path.insert(0, '/mnt/e/hackios/k60-cellular/scripts')
from pong_adt_contract import parse_adt
on  = parse_adt(pathlib.Path('/tmp/adt-on.bin').read_bytes())
off = parse_adt(pathlib.Path('/tmp/adt-off.bin').read_bytes())
assert on['/chosen/memory-map']['K60ModemImage'] == bytes(16), on['/chosen/memory-map']
assert 'K60ModemImage' not in off['/chosen/memory-map'], off['/chosen/memory-map']
print('placeholder ok')
PY
```

- `modem=True` ⇒ `/chosen/memory-map` 里有 `K60ModemImage`，值恰好 `b'\0'*16`；
- `modem=False` ⇒ 没有这个键（不是空值，是**不存在**）；
- `modem=True, data=True` ⇒ `RAMDisk` 与 `K60ModemImage` 同时存在，互不影响；
- 长度必须是 16，多一个字节都会被 `pong_adt_contract.py:83` 拒。

### 5.2 构建级：卷里有 27 个文件

```sh
UNIXNU_SKIP_GATES=1 ./unixnu build payload -D ../UniXNU-mondrian --out /tmp/vfy \
    --modem-carrier /mnt/e/k60-work/artifacts/dxe-dryrun-d/stage/EFI/UniXNU/MODEM

PL=/tmp/vfy/mondrian/*/mondrian/payload/payload.img
mdir -i "$PL" ::/EFI/UniXNU/MODEM | wc -l          # 27（不含 . 与 ..）
mcopy -o -s -i "$PL" '::EFI/UniXNU/MODEM/*' /tmp/vfy-modem
python3 ../k60-cellular/scripts/check-modem-lzma.py \
    --dir /tmp/vfy-modem --manifest /tmp/vfy-want.txt --sum
# 期望：failures=0；declared-total=109060761
stat -c %s "$PL"                                   # 201326592
```

- `payload.json` 里 `modem_carrier_files` = 27、`modem_carrier_sha256` 非空、`payload_sha256` 有值；
- `mdir` 的 27 行名字必须与 `gen-modem-table.py --manifest` 的名字列（各加 `.lzma`）diff 为空；
- `declared-total=109060761` 就是 13 号 C2 的 `copied`，两者对不上说明某个文件的 8 B 字段没改写。

### 5.3 回归级：不带载具时逐字节不变

```sh
./unixnu build payload -D ../UniXNU-mondrian --out /tmp/vfy0     # 不传 --modem-carrier
stat -c %s /tmp/vfy0/mondrian/*/mondrian/payload/payload.img     # 201326592
mdir -i .../payload.img ::/EFI/UniXNU                            # 只有 Payloads 与 unixnu.toml
```

- 这一条比 5.2 更重要：`modem=False` 必须让 display/audio/wifi 那几条线的产物**一个字节都不变**
  （sha256 与改动前一致）。`5d96806` 修的就是「别的镜像因为没有占位而黑屏」，框架侧不能把它改回来。

### 5.4 复现级：两次构建同 sha256

同一输入在受控离线 harness 下跑两次 5.2，`payload_sha256` 必须相同。需同时固定并记录 ADT 的测试随机输入、工具版本、时间戳与目录顺序；`:284-285` 的 utime EPOCH 与 `:100` 的 `sorted(stage.iterdir())` 只覆盖其中一部分。

`generate()` 使用 `os.urandom(256)`，固定 unique-chip-id 不会固定 random-seed。因此正常独立构建哈希不同不能直接归因于新增目录；5.3 的旧/新字节比较也需要相同的受控随机输入。harness 及其来源未交付时，两项字节结论均待验，不能删除 random-seed 后声称原始产物逐字节一致。详见 [17 号清单 §4.1](17-OFFLINE-ACCEPTANCE-CHECKLIST.md#41-随机输入不是-identity-seed)。

### 5.5 端到端（可选，需要 uefi-mondrian）

```sh
./unixnu bootimg -D ../UniXNU-mondrian --out /tmp/vfy \
    --uefi ../uefi-mondrian --fd ../uefi-mondrian/Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd \
    --dtb ../uefi-mondrian/Resources/DTBs/mondrian.dtb \
    --ramdisk /tmp/vfy/mondrian/*/mondrian/payload/payload.img -o /tmp/vfy/boot.img
# 13 号表 A 的 A1/A2/A2b/A3/A4/A6/A5 七行必须全绿
```

A2 是公式：`4096 + ceil(KSZ/4096)*4096 + 201326592 + 4096`，本交 `KSZ=555628` ⇒ 201,891,840。

## 6. 与固件侧的对应关系（改框架的人不必读固件代码，但要知道这几条）

| 框架做的事 | 固件侧读它的地方 | 不满足会怎样 |
| --- | --- | --- |
| 16 B 全零占位 | `ImageCarrierLib.c` `ImageCarrierLoad`：`AdtFindMemoryMapProperty("K60ModemImage")` 后判长度 16、内容全零 | 缺 ⇒ `modem-image: K60ModemImage placeholder missing` + `EFI_COMPROMISED_DATA`；长度≠16 ⇒ `placeholder is %d bytes, expected 16`；非零 ⇒ `range already published` |
| `EFI/UniXNU/MODEM/modem.bNN.lzma` ×27 | 逐段 `CarrierLoadSegment`：读 13 B 头、比对段表 `bytes`、`LzmaDecode` 到窗口 | 缺文件 ⇒ `modem-image: %a missing`；声明长度不符 ⇒ `%a header says %d, table says %d`；解压失败 ⇒ `%a did not decompress (%r)` |
| 两者都有 | 成功路径 | `modem-image: 30 segments, copied 109060761, zeroed 211012967, gaps 790528 untouched` |

失败一律 `goto Fail`（不启动），成功才把 `{0x8bc00000, 0x13200000}` 写进 ADT 副本并打
`modem-image: range 0x8bc00000..0x9ee00000 published as K60ModemImage`。

## 7. 引用

- `12-DXE-CONTRACT.md` §3.1（16 B 占位）、§3.7（构建期三条检查）
- `13-FIRMWARE-ACCEPTANCE.md` 表 A（A3/A4/A6/A5）与表 C（C1–C5）
- `14-DXE-REQUEST.md` §1（属性契约）、§5（夹具）
- `15-FIRMWARE-CARRIER-LOADER.md` §1.7/§1.8（路线 D）、§1.8.8（`LzmaDecode` 的 `*srcLen` 坑）
- 固件提交：`uefi-mondrian` `72e51ca`（拷贝与发布）、`5d96806`（目录先开、占位后查）
