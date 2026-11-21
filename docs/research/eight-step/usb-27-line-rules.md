# usb27 线内规则（2026-11-22 Lead 广播，逐条落成做法）

来源：Lead 广播 2026-11-22T03:12（全体线）。这里只记「本线怎么用」，不复制原文。

## 1. 共享 RAG 库优先

- 库：`E:\k60-work\kb\kb.sqlite`（WSL `/mnt/e/k60-work/kb`），6,194 文档 / 142,260 块。
- 本线用法：断言「官方怎么写的」「别人实现到哪」之前先查库（本会话用 `kb_search`/`kb_rag`，
  `kb_root="E:/k60-work/kb"`；命令行等价入口是 `kb_engine.py search`，读到 JSON 里带 `file`/`section`）。
- 本线实测（2026-11-22，1 次 `kb_search`）：6,194 文档库中已收录 `F2-AFTER-INVALID.md`
  （「K60 唯一 console 是 USB CDC-ACM，`bsd_init` 之后才起」）、`IMAGE-ARGS-usb.fragment.md`
  （`k60_usbvend` 0/1/2 的描述符形状）、`BOOT-DEATH-SUSPECT.md`（`portSeen=false` = 设备从未枚举
  CDC-ACM，不是采集器故障）。这三条正好是 §1/§2/§9 的既有结论，可作交叉验证。
- 引用写法：命中写 `文件:节`；未命中才联网并附 URL；都没有写「未证」。

## 2. 环境坑

- `NO_PROXY=localhost,127.0.0.1,::1`（不带方括号）。
- `HF_ENDPOINT=https://hf-mirror.com`。

## 3. P-300 / P-307 / 冻结令

- P-300：27 无串口输出，0 字节日志 ≠ 内核没跑 ⇒ §9 的 INVALID 规则（`usb-27-export-surface.md` §9.3）。
- P-307：ramoops 在 DRAM，复位即归零 ⇒ 任何 ramoops 证据无效（§9.4）。
- 冻结：`docs/engineering/BOOT-FREEZE.md` `state = "frozen"` ⇒ §9 全部记 `unmeasured`，本线不排上机。

## 4. 门禁

- `scripts/check-channel-lifetime.py`：通道类文档必须回答 lifetime / read_moment / writer /
  loss_condition 四问。本线已在 §9.4 用表格满足；今后新增「读日志」类段落都按此四问写。
- `scripts/check-reply-freshness.py`：reply md 首行 `delivery:`、文末 `lead-reply:`；`K60_SCRATCH` 必须显式设。
