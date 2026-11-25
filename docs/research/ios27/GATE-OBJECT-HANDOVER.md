# 移交单：让三处符号门禁报出「它量的是哪一份文件」

来源：2026-11-22 三次「读数与对象脱钩」（P-279 权限读不到、P-251 键从没存在过、`nm` 没拿到文件却报 `no symbols`）。
`scripts/check-kernel-console.py` 已经改好（提交 `887f5c7e`），照它的模板补剩下三处。

## 模板（照抄 check-kernel-console.py 的做法）

```python
stamp = hashlib.sha256(pathlib.Path(target).read_bytes()).hexdigest()[:12]
print(f"note symbols: {pathlib.Path(target).resolve()} sha256={stamp} "
      f"{len(defined)} defined; control {CONTROL}={CONTROL in defined}")
```

要点三条：

1. **绝对路径 + sha256 前 12 位** —— 事后能反推量的哪一份
2. **已定义符号总数** —— 为 0 就说明读取器没工作，不是内核没有符号
3. **对照符号** —— 一个已知必定存在的符号（27 内核用 `_kprintf`），它不命中 ⇒ 结论不可信

## 三处待改

| 文件 | 行 | 现状 | 要补 |
| --- | --- | --- | --- |
| `scripts/classify-prelink-targets.py` | `:57` | `llvm-nm -n --defined-only` 直接吃输出 | 打印对象行；`defined` 为 0 时退 2 |
| `scripts/k60-fileset-pair.py` | `:36` | 同上，另外 map 的 `native`/`reference` 是两份内核 | **两份各打一行**，并标哪份是 native、哪份是 reference（P-281 同族：混用会配错地址） |
| `scripts/xnu-symbolize.py` | `:61` | 同上 | 打印对象行；未命中时给出「换 `-n` / 去掉 `--defined-only` 重试」的提示而不是静默 |

## 验收（每条都要贴读数，不是「看起来对了」）

```bash
K=/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.macho
python3 scripts/classify-prelink-targets.py $K        # 期望：对象行 + 131 个 target 分类
python3 scripts/k60-fileset-pair.py …                 # 期望：native / reference 各一行对象行
python3 scripts/xnu-symbolize.py --find <insn> $K     # 期望：对象行 + 命中或明确的未命中提示
python3 scripts/tests/test-check-kernel-console.py    # 期望：TESTS OK: 8 cases
```

## 纪律

- 改完必须跑一次**真内核**，不能只跑单测：单测用的是合成符号集，量不到「读取器坏了」这件事。
- 三处都不许把「读不到」降级成 `set()` / `[]` / `0`——那是 P-279 的原始形态。
