# 待应用：`0610` 双 root 部署（离线计划，未实施）

目标：让部署既写 `/private/var/ngpu/addons/…`（上游读法）也写 `/private/var/pong/…`
（`init-v24dp.c:366` 的注入点），从而使 `PongAdrenoMetal.bundle` 真被注入 backboardd。

## 1. 常量（`patches/xnu/0610-k60-metal-plugin-deploy.patch` 第 42 行附近）

```c
#define K60_METAL_ROOT   "/private/var/ngpu"
#define K60_METAL_INJECT "/private/var/pong"
```

## 2. 目录（第 137–140 行那组 `k60_metal_mkdir` 之后补两行）

```c
(void) k60_metal_mkdir(K60_METAL_INJECT, p, scratch);
(void) k60_metal_mkdir(K60_METAL_INJECT "/PongAdrenoMetal.bundle", p, scratch);
```

## 3. 写入（第 183–191 行路径改写之后）

容器里的相对路径有两种形态：`addons/PongAdrenoMetal.bundle/<file>` 与
`addons/PongAdrenoMetal.{publish,clients}`。写主路径成功后：
- 若 rel 以 `addons/PongAdrenoMetal.bundle/` 开头，再写一份到
  `K60_METAL_INJECT "/PongAdrenoMetal.bundle/" + basename`
- 若 rel 是 `addons/PongAdrenoMetal.publish` 或 `…clients`，再写一份到
  `K60_METAL_INJECT "/PongAdrenoMetal.<suffix>"`
- 两份都用相同 mode；第二份失败只打印 `K60METAL inject skipped <rel> err=%d`，不使整次部署失败

## 4. 必须同时给出的证据

| 类别 | 具体 |
| --- | --- |
| 静态 | `scripts/check-patch-apply.py` 通过（series 229 条逐 hunk） |
| 单元 | `scripts/tests/test-metal-dual-root.py`：断言补丁文本含 `K60_METAL_INJECT`、两行 mkdir、两处再写分支；并断言 `gen-k60-metal-blob.py` 未改动 |
| 产物 | 重建后 `K60METAL deploy files=6/6 error=0` 且新增 `inject=` 计数 |

## 5. 上机前

按仓规另写一张 `docs/research/gpu/FLIGHT-CARD-<date>.md` 预写 S/F 判据，
通过 `scripts/check-flight-card.py` 才允许 `fastboot boot`。
在此之前**禁止 boot**（用户 m35755）。判据应包含：用户态出现 `Pong Metal: …`
任一 NSLog 行（证明插件已被加载），这是本轮之后最小的可验证跃迁。
