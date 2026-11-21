# 坑位条目提案（P-??? 由 Lead 分配）

`k60-gates/docs/engineering/RULES.toml` 的 `[[rule]]` 逐字可用；本文件只是提案，
写 gates 不属于这条线（k60-gates 只读）。

```toml
[[rule]]
id = "P-???"
title = "板级 ADT 节点只在 board.toml 里「写对了」，没人核对它进没进 ADT 字节"
statement = "症状：内核驱动按精确名断言 PMIC/触摸节点的属性，打印 「Pong keys: DT node /arm-io/pong-buttons not found」或「Pong touch: … SKIP」，驱动整条不启动；而 board.toml 里那几行看起来是对的，静态检查也全绿。根因：board.toml 的 [adt.*] 表要经 scripts/unixnu/devicetree.py:311 generate() 才变成 payload 的 kernel.macho.adt（payload.py:232-236），中间没有任何一步把「表」与「字节」对起来；更糟的是这份表会被 pick/rebase 顺手改写——16 线 2026-11-12 的 97b84eb7 加了 [adt.arm-io.pong-buttons]，两分钟后 3b3ff9ce 以「never let a pick overwrite the board contract」把它删了，当时节点只活在 /opt 装配输入里（docs/research/EIGHT-STEPS.toml:406），仓里再也搜不到。判据怎么看见：①board.toml 结构检查（本 check）；②离线生成 ADT 后逐属性比对（scripts/gen-27-adt-buttons.py，docs/research/ios27/adt-27-buttons-check.md 有 PASS 表与反例）。修法：把节点写回 board.toml 的 [adt.buttons.*] / [adt.arm-io.pong-*.*]，并让 check 在 CI 里跑；改 pick 覆盖 board.toml 时，先看 god 表再看 ADT 字节，不做「先删后补」。"
check = '''python3 -c "import os,sys,tomllib,pathlib;t=tomllib.loads((pathlib.Path(os.environ.get('K60_XNEKOM_IOS27','../xnekom-ios27'))/'board.toml').read_text(encoding='utf-8')).get('adt',{});b=t.get('buttons',{});a=t.get('arm-io',{}).get('pong-buttons',{});g=lambda s,k:(a.get(s,{}) or {}).get(k);n=b.get('strings',{}).get('button-names',[]);s=b.get('string',{});bad=[m for m,c in ((' /buttons compatible',s.get('compatible')!='buttons'),(' /buttons device_type',s.get('device_type')!='buttons'),(' /buttons button-names',n!=['hold','voldown','volup'] or 'menu' in n),(' /buttons home-button-type',b.get('u32',{}).get('home-button-type')!=2),(' pong-buttons core-base',int(str(g('u64','core-base') or 0),0)!=0xc400000),(' pong-buttons cnfg-base',int(str(g('u64','cnfg-base') or 0),0)!=0xc42d000),(' pong-buttons observer-base',int(str(g('u64','observer-base') or 0),0)!=0xc440000),(' pong-buttons ee',int(str(g('u32','ee') or 0),0)!=0),(' pong-buttons pon-ppid',int(str(g('u32','pon-ppid') or 0),0)!=0x13),(' pong-buttons volume-up-ppid',int(str(g('u32','volume-up-ppid') or 0),0)!=0x18d)) if c];print(('FAIL:'+','.join(bad)) if bad else 'ok input-adt-nodes: /buttons 4 fields + /arm-io/pong-buttons 6 properties present in the 27 board.toml');sys.exit(1 if bad else 0)"'''
note = "2026-11-21 由 input27 线提出。check 已在 k60-gates 根目录双向验证：真 board.toml → `ok input-adt-nodes: /buttons 4 fields + /arm-io/pong-buttons 6 properties present in the 27 board.toml`、rc=0；删掉 home-button-type 与 pon-ppid 的副本当负例 → `FAIL: /buttons home-button-type, pong-buttons pon-ppid`、rc=1。check 刻意不依赖 dtc：宿主（Windows MSYS）没有 dtc，字节级核对留在 WSL 侧生成脚本里做；本 check 只守「表里必须有这十个字段」，防的是 pick 悄悄删节点这一类回归。号由 Lead 分配（P-293…P-296 已占用）。"
```

## 反例一（跑出来的）

把 27 board.toml 的 `home-button-type = 2` 与 `pon-ppid = "0x013"` 两行删掉，
再从 gates 根跑同一个 check：

```
FAIL: /buttons home-button-type, pong-buttons pon-ppid
rc=1
```

## 反例二（历史）

```
97b84eb7  2026-11-12 21:33  pick 88 commits                                → 加 [adt.arm-io.pong-buttons]
3b3ff9ce  2026-11-12 21:35  never let a pick overwrite the board contract → 删 [adt.arm-io.pong-buttons]
```

16 仓 `board.toml` 到 2026-11-21 仍只有 `[adt.buttons.*]`（:268 / :272 / :275）；
27 仓在 `board.toml:284-299` 补回，并在 :285-287 记着干净重建时驱动打印过
`Pong keys: DT node /arm-io/pong-buttons not found`。

## 验证记录

| 用例 | 环境 | 结果 |
| --- | --- | --- |
| 真 27 board.toml | cwd `k60-gates`，宿主 python3.14 | `ok input-adt-nodes: …`，rc=0 |
| 删两字段的副本 | 同上 + `K60_XNEKOM_IOS27=<副本目录>` | `FAIL: /buttons home-button-type, pong-buttons pon-ppid`，rc=1 |
| 字节级核对（dtc 路径） | WSL，`gen-27-adt-buttons.py` | `verdict: PASS (exit 0)`，见 `adt-27-buttons-check.md` |
