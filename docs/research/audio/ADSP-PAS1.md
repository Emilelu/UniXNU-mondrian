# ADSP PAS1 — 参数与调用序列（实测记录）

本文件记录实现 `K60AdspPas.c` 所需的全部外部知识，来源均为读源码所得，不在本仓库内可再推导。

## SCM 常量（来源 `E:\k60-work\references\pong-power\QcomScm.h`）

```
QCOM_SCM_SVC_PIL             0x02u   (:9)
QCOM_SCM_PAS_INIT_IMAGE      0x01u   (:10)
QCOM_SCM_PAS_MEM_SETUP       0x02u   (:11)
QCOM_SCM_PAS_AUTH_AND_RESET  0x05u   (:12)
QCOM_SCM_VAL                 0u      (:15)
qcom_scm_fn(svc, cmd)                (:21，位域拼装)
```

## 调用形状（来源 `E:\k60-work\references\pong-power\PongAdsp.cpp`）

```
:235  ScmResult scm(uint32_t command, uint32_t arginfo, uint64_t a, uint64_t b, uint64_t c)
:239    function = qcom_scm_fn(QCOM_SCM_SVC_PIL, command), session = 0
:244    __asm__ volatile("smc #0" : "+r"(x0) … "+r"(x7))
:259  bool scmOk(r) { return r.x0 == 0 && r.x1 == 0; }
```

成功判据是 **x0 与 x1 同时为 0**，只看 x0 会把失败当成功。

## 序列与参数

```
PAS_AUTH_AND_RESET  args(1, 0, 0, 0)             pas=1
PAS_INIT_IMAGE      args(2, QCOM_SCM_VAL, RW, 0) pas=1, phys=<每段物理地址>
PAS_MEM_SETUP       args(3, 0, 0, 0)             pas=1, base=0x86300000, span=0x3100000
PAS_SHUTDOWN        args(1, 0, 0, 0)             pas=1（仅用于回滚/重试）
```

顺序要点：`PAS_INIT_IMAGE` 需要**逐段**地址，因此必须先有段的 `(paddr, bytes)` 列表；`PAS_MEM_SETUP` 用整段跨度一次圈定。原计划的"先拷完再调 SCM"是错的。

## ADSP 镜像事实（实测，见 `VENDOR-ADSP-NODE.md`）

- 载入基址 `0x86300000`，跨度 `0x3100000`（= `adsp_region` 大小）
- `adsp.mdt` 为 ELF32，`e_phoff=52`、`e_phentsize=32`、`e_phnum=26`；有效 PT_LOAD 24 段
- `adsp.b10` 落在**非页对齐**地址 `0x86e0b2c0` → 必须逐字节拷贝
- `adsp.b24` 为纯 bss（7,245,824 B，无文件）
- 表由 `scripts/gen-adsp-table.py` 生成；`k60_adsp_plan()` / `k60_adsp_copy()` 已实现并有宿主测 6 项（`scripts/tests/test-k60-adsp-loader.c`）

## 尚缺

`K60AdspPas.c` 本身，以及 `K60AdspImage` 上"遍历 `(paddr, bytes)` 对"的接口（表内已有这两列，纯增量）。宿主可测部分：`qcom_scm_fn` 打包与 `args()` 编码，均不依赖设备。
