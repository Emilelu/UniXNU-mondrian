# WPA3-Personal 在 27 线的移植边界

Status: blocked_by: F2/F3；offline plan accepted 2026-11-21; reference host gate added and passing 2026-11-21. 本轮没有构建、没有上机、没有改共享仓。WPA3 只在
`E:/hackios/UniXNU-t970` 的参考实现里存在；K60 当前仍是 WPA2-Personal，且
`pong_sae.c` 只是 SAE 帧形状探针，不是密钥协商。

## 0. 结论先行

1. t970 的 WPA3 不是用户态 supplicant，而是编进内核 ath11k 归档的 clean-room
   库：`T970WifiWpa3.c:1-8` 声明 WPA3-Personal、SAE Group 19、KDF-SHA256、
   AES-128-CMAC 与 BIP-CMAC-128；头文件只包含 `stddef.h`/`stdint.h`
   （`T970WifiWpa3.h:12-13`），没有 libc 或 OS 依赖。
2. 它通过生成期改写接到 station：`build-pong-ath11k.py:385-557` 的 edit 17
   把 `nw_sta.c` 复制成 `nw_sta_pong.c` 后注入库头、状态字段、SAE 状态机、
   RSN/RSNXE、PTK/CMAC/IGTK 与 PMF 过滤；库对象在
   `build-pong-ath11k.py:908` 加入归档。`build-t970-ath11k-link.py:216-217`
   只是调用这个生成器，本身不含 WPA3 代码。
3. K60 的 station 仍是同一套 legacy `nw_sta.c`，所以 t970 的库可以复用；但
   控制面不同：K60 的 Apple80211 join 在 `PongWifiNet.cpp:787-793` 只接受
   `auth_upper` 0、8、0x10，其他一律 `EOPNOTSUPP`。24A446 的 SAE
   `auth_upper` 值没有证据，不能猜。
4. 因此 WPA3 的移植分三层：库（可直接复用，BSD-2-Clause）、station 状态机
   （需要逐字段适配到 `nw_sta.c`）、Apple80211 控制门（能力缺失，等待真实
   join 请求或 wifid 证据）。只做前两层而没有第三层，WPA3 实际不会被发起；
   只放宽第三层而没有前两层，会得到一个假装支持 SAE 的 WPA2 连接。

## 1. 参考实现的层与调用关系

| 层 | t970 位置 | 作用 | K60 现状 |
|---|---|---|---|
| 密码学与 RSN | `T970WifiWpa3.c:46-437` | SHA-256、HMAC、HKDF、KDF、AES-CMAC、BIP、P-256、SSWU | 没有；`nw_crypto.h:8,16` 只有 HMAC-SHA1 与 PRF，`nw_sta.c:359-363` 只做 SHA1 PRF |
| SAE | `T970WifiWpa3.c:894-1128` | H&P/H2E PWE、commit/confirm、anti-clog、wipe | `pong_sae.c` 只生成固定填充的 commit 形状，`pong_sae.h:8-9` 明确说不是密钥协商 |
| RSN/关联 | `T970WifiWpa3.c:1148-1287` | 解析 AP RSN/RSNXE，构造 assoc RSN/RSNXE、commit/confirm 帧 | `nw_sta.c:112-123` 只接受 CCMP+PSK 且拒绝 MFPR；assoc RSN 是固定的 22 字节 |
| 4-way/PMF | `T970WifiWpa3.c:1380-1435` | SHA256 PTK、IGTK KDE、PMKID KDE、BIP 校验 | `nw_sta.c:359-383` 只做 SHA1 PTK、HMAC-SHA1 MIC、CCMP key；无 IGTK/PMF |
| station 接线 | `build-pong-ath11k.py:385-557` | edit 17 的字符串变换 | `build-k60-ath11k.py:546-730` 只注入 HE 与 SAE 探针，没有 WPA3 |

这里的“库”与 sheng 的用户态路线不是同一层。sheng 的
`drivers/ath12k-wifi` 页面描述的是 `wpa_supplicant 2.12` 做 SME/WPA
（`E:/hackios/UniXNU/docs/zh/drivers/ath12k-wifi.md:36-49`）；t970 的实现是
legacy 内核 station 自带的 SAE，不启动 supplicant。K60 现在飞的正是 legacy
`nw_sta.c`，所以本计划复用 t970；如果以后迁到 sheng 的 cfg80211/mac80211
路线，WPA3 应落在 supplicant，而不是把 t970 再塞进 mainline。

## 2. 字段对照：直接复制 / 需要适配 / 能力缺失

“直接复制”指字段语义与生命周期一致，只增加存储；“需要适配”指要改现有函数
或结构；“能力缺失”指当前 station/控制面没有对应入口，必须新增或等待外部证据。

| 参考字段或函数 | K60 位置 | 分类 | 精确改动 |
|---|---|---|---|
| `pw3_sae_ctx`（`T970WifiWpa3.h:24-41`） | `nw_sta.c:38-46` 的 `C` 无此成员 | 直接复制 | 在 `C` 增加 `pw3_sae_ctx sae;`；约 368 B，零初始化 |
| `pw3_rsn_info`（`T970WifiWpa3.h:96-103`） | `C` 无此成员；`C.ap.ie` 已保存完整 IE | 直接复制 | 增加 `pw3_rsn_info rsn;`，在 `start_connect` 解析 |
| `u8 pass[65]` + `pass_len`（edit 17:400） | `g_req.pass[65]` 在 `nw_sta.c:32`，但请求会被下一次 join 覆盖 | 需要适配 | 在 `C` 增加 `pass[65]`/`pass_len`，`start_connect` 从 `g_req` 复制；SAE 派生只用 `C.pass` |
| `pmkid[16]`、`have_pmkid`（edit 17:400） | 无 | 直接复制 | 增加字段；SAE confirm 后从 `C.sae.pmkid` 复制 |
| `sae_stage`、`sae_token[64]`、`sae_token_len`（edit 17:401） | 无 | 直接复制 | 增加字段；stage 0/1/2/3 与 t970 相同 |
| `igtk[16]`、`igtk_pn[6]`、`igtk_id`、`have_igtk`（edit 17:401） | 无 | 直接复制 | 增加字段；M3/组密钥更新时由 `pw3_find_igtk_kde` 填充 |
| `igtk_key`（edit 17:396） | `C.ptk_key`/`C.gtk_key` 在 `nw_sta.c:42` | 需要适配 | 增加 `struct ieee80211_key_conf *igtk_key;`，DISABLE_KEY 时释放 |
| `struct ieee80211_key_conf` 的 IGTK 用法（edit 17:501-510） | `install_key` 在 `nw_sta.c:376-383` 固定 `WLAN_CIPHER_SUITE_CCMP` | 需要适配 | 另写 `install_igtk`，cipher=`WLAN_CIPHER_SUITE_AES_CMAC`、iv_len=0、icv_len=8；`set_key` 返回正数表示硬件 key index，不能当失败 |
| `sta->mfp`（edit 17:468-469） | `nw_sta.c` 的 `add_station` 只设 `sta->wme` | 需要适配 | 在建立 station 时设 `sta->mfp = C.secure && C.rsn.use_mfp`；字段来自 pinned mac80211 头，t970 已编译通过 |
| `rsn_check`（edit 17:403-417） | `nw_sta.c:112-123` 只接受 CCMP+PSK，:122 拒绝 0x0040 | 能力缺失 | 用 `pw3_parse_rsn_ap` 替换；AKM 8 与 MFPR 不再被拒绝；解析 RSNXE H2E |
| `send_auth`（edit 17:450-459） | `nw_sta.c:132-136` 永远发 open-system | 能力缺失 | 先判 `C.rsn.akm == 8`；SAE 时按 stage 发 commit/confirm，不再发 open |
| `handle_sae_auth`（edit 17:563-600） | `nw_sta.c:458-466` 只处理 open auth 的 seq 2 | 能力缺失 | 增加 SAE auth 分支；处理 status 0、126、76 与 confirm；错误密码走 `NW_RES_BAD_KEY` |
| `eapol_ver_ok`（edit 17:475-479） | `nw_sta.c:415-418` 只接受 descriptor version 2 | 能力缺失 | AKM 8 接受 version 0 或 3；AKM 6 接受 3；WPA2 仍只接受 2 |
| `eapol_mic` / `sign`（edit 17:480-482, 489-492） | `nw_sta.c:374-375` 只做 HMAC-SHA1 | 能力缺失 | AKM>=6 用 `pw3_aes128_cmac`；WPA2 保留 HMAC-SHA1 |
| `derive_ptk`（edit 17:483-488） | `nw_sta.c:359-363` 只做 SHA1 PRF 384 | 能力缺失 | AKM>=6 用 `pw3_derive_ptk_sha256`；参数顺序按 t970 的 aa/spa |
| assoc RSN/RSNXE（edit 17:460-467） | `nw_sta.c` 的 assoc 里是固定 `rsn[22]` | 能力缺失 | 用 `pw3_build_assoc_rsn`（AKM 8 带 PMKID）与 `pw3_build_assoc_rsnxe`（H2E 0x20） |
| M1 PMKID 检查（edit 17:525） | 无 | 能力缺失 | AKM 8 且 `have_pmkid` 时，用 `pw3_find_pmkid_kde` 比较；不一致只告警，不静默接受 |
| M2 RSN（edit 17:527-533） | `nw_sta.c:423-427` 固定 RSN | 能力缺失 | M2 的 key data 改为 assoc RSN；descriptor version 用 `eapol_out_ver` |
| M3 IGTK（edit 17:540-542） | `nw_sta.c:450` 只取 GTK | 能力缺失 | `C.rsn.use_mfp` 时解析 IGTK KDE，保存 id/pn/key，M4 后安装 |
| PMF deauth（edit 17:601-630） | `nw_sta.c` 的 deauth 分支不检查 MFPC/MFP | 能力缺失 | broadcast 用 `pw3_bip_cmac128_verify` + IGTK；unicast 要求 protected 且 RX_FLAG_DECRYPTED；失败丢弃 |
| `IE_MAX`（edit 17:389-390） | `build-k60-ath11k.py:548-549` 已改成 2048 | 已适配 | 不新增改动；只要 RSNXE 在 `C.ap.ie` 内即可 |
| `nw_wifi_connect` 签名（`nw_abi.h:77`） | 只有 ssid/bssid/pass/plen | 不需要改 | SAE 由 station 在解析 AP RSN 后选择，不需要把 auth type 塞进 ABI |
| Apple80211 `auth_upper`（`PongWifiNet.cpp:787-793`） | 只允许 0/8/0x10 | 能力缺失 | 见 §3.3；在拿到 24A446 SAE 值前保持拒绝，不猜 |

## 3. 27 线的精确改动

### 3.1 库与构建

1. 源文件：把
   `E:/hackios/UniXNU-t970/drivers/T970Wifi/T970WifiWpa3.c` 与
   `T970WifiWpa3.h` 放到
   `drivers/PongWifi/ath11k/T970WifiWpa3.{c,h}`，保留文件头的 BSD-2-Clause
   与 `Copyright (c) 2026 PongWifi contributors`（`T970WifiWpa3.c:1-8`）。
   这是 clean-room 参考实现，不是 Linux 派生代码。
2. 在 `scripts/build-k60-ath11k.py:731` 的 `pong_sae` job 之后追加
   `jobs += [(ROOT / 'drivers/PongWifi/ath11k/T970WifiWpa3.c', out / 'T970WifiWpa3.o', [])]`。
   `-I drivers/PongWifi/ath11k` 已在 `:539`，不需要新 include 路径。
3. 不改 `libPongAth11k.a` 的导出规则：库函数会被 `:754` 的 namespace 重命名，
   只保留 `_nw_wifi_*` 与白名单；WPA3 内部符号不需要导出。
4. 不改 `scripts/build-k60-wifi-native.py:115-119` 的 stamp 检查；它只校验
   `ie_bytes=2048`，不校验 WPA3 符号。归档是否带 WPA3 库由 §4 的测试与
   `check-wifi-station-archive.py` 的成员检查补充。

### 3.2 station 生成器

在 `scripts/build-k60-ath11k.py` 的生成段（`:546-718`）按 t970 edit 17 的
顺序增加，而不是另写一套：

1. 在 `sta` 文本里插入 `#include "T970WifiWpa3.h"`，位置与 edit 17:387-388
   相同（`#include "nw_sta.h"` 之后）。
2. 在 `C` 结构（`nw_sta.c:38-46`）插入 §2 的字段；字段顺序按 edit 17:400-402，
   避免 packing 与初始化顺序变化。
3. 用 `pw3_parse_rsn_ap` 替换 `rsn_check`（edit 17:415-417）。**不要**保留
   `nw_sta.c:122` 的 `caps & 0x0040` 拒绝：SAE 必然要求 PMF。
4. 增加 `send_sae_commit`、`send_sae_confirm`、`start_sae`、
   `handle_sae_auth`（edit 17:424-449, 563-600）；`send_auth` 在 AKM 8 时
   调用它们，其他 AKM 保持 open-system 路径（edit 17:450-459）。
5. assoc 的 `rsn[22]` 替换为 `pw3_build_assoc_rsn`，再追加
   `pw3_build_assoc_rsnxe`（edit 17:460-467）。
6. `add_station` 设 `sta->mfp`（edit 17:468-469）。
7. `derive_ptk`、`sign`、EAPOL version、M1 PMKID、M2 RSN、M3 IGTK、
   `install_igtk` 与 PMF deauth 按 edit 17:475-630 的顺序替换。
8. `install_key` 的 `if (r)` 改成 `if (r < 0)`（edit 17:493-496）：
   `set_key` 的正返回值是硬件 key index，不是失败。这个改动同时修掉现有
   `install_key` 在硬件 offload 下误报的路径。
9. `IE_MAX` 不需要在生成器里再改；`:548-549` 已把 384 改成 2048。

### 3.3 Apple80211 控制门（唯一需要 boot-arg 的地方）

当前 `PongWifiNet.cpp:793` 的条件是：

```c
if (a.auth_upper && a.auth_upper != 8 && a.auth_upper != 0x10) { ... return EOPNOTSUPP; }
```

24A446 的 WPA3-SAE 使用哪个 `auth_upper` 没有证据；不改这一行去猜。精确做法：

1. 在 `PongWifiNet.cpp` 的全局状态增加
   `static uint32_t gSaeAuthUpper;`。
2. 在 `pong_wifi_net_start` 的 boot-arg 区（`:1390-1397`）增加
   `PE_parse_boot_argn("pong_wifi_sae_auth", &gSaeAuthUpper, sizeof gSaeAuthUpper);`。
   默认 0，表示不启用任何新值，现有行为不变。
3. `apple80211` 的 join 条件改为：
   ```c
   if (a.auth_upper && a.auth_upper != 8 && a.auth_upper != 0x10 &&
       (!gSaeAuthUpper || a.auth_upper != gSaeAuthUpper)) return EOPNOTSUPP;
   ```
   只有显式给出真实值时才放行；值从 24A446 的 join 请求或 wifid 反汇编取得。
4. 在放行日志里打印 `auth_upper=0x%x`，让 27 线第一次飞行能记录真实值；
   这个日志不是 WPA3 成功证据，只是下一次判断的输入。
5. 不改 `nw_abi.h:77` 的 `nw_wifi_connect` 签名。SAE 的选择发生在 station
   解析 AP RSN 之后（`C.rsn.akm == 8`），不需要把 auth type 穿过 ABI。
6. 现有 `sae=1/2` 探针 boot-arg（`PongWifiNet.cpp:1394-1397`）保留为
   帧形状实验；不要把它当 WPA3 开关。WPA3 的开关是
   `pong_wifi_sae_auth=<real value>`，它只允许 join，不改变 SAE 算法。

### 3.4 启动参数与默认值

| 参数 | 默认 | 作用 | 生效层 |
|---|---|---|---|
| `pong_wifi_sae_auth` | 0 | 允许指定的 Apple80211 `auth_upper` 进入 join；0 保持拒绝 | `PongWifiNet.cpp` |
| `sae` | 未设置 | 现有 SAE 帧形状探针，group 19（`sae=1`）或 20（`sae=2`） | `PongWifiNet.cpp:1394-1397` + `pong_sae.c` |
| `ieee80211w` | 不适用 | 本实现由 AP RSN 的 MFPC/MFPR 与 AKM 8 推导 `use_mfp`，不读用户态 supplicant 配置 | `nw_sta.c` |
| `wifi_operational` | false | 共享 station 仍报告未运营；WPA3 不改变这个状态 | `build-k60-ath11k.py:762-764` |

## 4. 主机测试：输入、命令、期望输出

### 4.0 本仓库的一条命令（2026-11-21 实测）

WPA3 只存在于 t970 参考树，所以先固定参考层的离线判据；它不是 K60 station 已接入的证据。
在仓库根目录执行（WSL；host-only，不构建内核、不生成 payload）：

~~~sh
cd /mnt/e/hackios/k60-wifi
/usr/bin/python3 scripts/tests/test-wpa3-reference.py
~~~

实测输出（2026-11-21，Ubuntu clang 18.1.3，t970 参考树只读）：

~~~text
reference t970: /mnt/e/hackios/UniXNU-t970
reference sha256: c=dfbf865b53abbfb6586741721a322ad4a589df91566bc868f2c09410c41646bf h=23510d2d40d76340885ce196dc913d4a28942979f729872c3f7fcaddb7df1312
compiler: /usr/bin/clang
PASS wpa3_test.c: ALL wpa3_test CHECKS PASSED
PASS sta_sim_wpa3.c: ALL sta_sim_wpa3 SCENARIOS PASSED
2/2 wpa3 reference checks passed
~~~

判据三件套（命令 / 期望 / 判定）：

| 检查 | 命令 | 期望 | 失败时 |
|---|---|---|---|
| 标准向量 | `scripts/tests/test-wpa3-reference.py` 内的 `wpa3_test.c` 编译并运行 | 输出含 `ALL wpa3_test CHECKS PASSED`，rc=0 | 任何 `FAIL`、缺失字符串或非 0 都是失败，不能当“参考库可用” |
| station/AP 模拟器 | 同一脚本内的 `sta_sim_wpa3.c` 编译并运行 | 输出含 `ALL sta_sim_wpa3 SCENARIOS PASSED`，rc=0 | 9 个场景未全过、错误密码场景未拒绝或非 0 都是失败 |
| 输入完整性 | 同一脚本 | t970 参考文件存在，clang 可执行 | 缺参考树或编译器时 rc=2 并打印 FAIL，必须失败而不是跳过 |

反例已实测：`--t970 /mnt/e/does-not-exist-t970` 返回 2 并打印 `FAIL reference: ... is not a directory`；`--clang /no/such/clang` 返回 2 并打印 `FAIL compiler: ... is not executable`；把参考测试的 `ALL wpa3_test CHECKS PASSED` 改成 `WRONG OUTPUT` 的 scratch 副本返回 1 并打印 `FAIL output wpa3_test.c: expected exactly ...`。

这个门禁只证明 t970 的参考库与协议模拟器在当前主机上可复现；它不证明 K60 的 `nw_sta.c` 已接线、27 归档已包含 WPA3，也不证明 24A446 的 `auth_upper`。K60 侧的接入判据仍是 §6 的第 2、3 条。

### 4.1 t970 标准向量

输入：

- `E:/hackios/UniXNU-t970/drivers/T970Wifi/T970WifiWpa3.c`
- `E:/hackios/UniXNU-t970/drivers/T970Wifi/T970WifiWpa3.h`
- `E:/hackios/UniXNU-t970/drivers/T970Wifi/tests/wpa3_test.c`

覆盖：SHA-256/HMAC RFC4231/HKDF RFC5869/KDF、AES-CMAC RFC4493、BIP-MMIE、
P-256、RFC9380 SSWU、H&P/H2E SAE、反射/错误 scalar/off-curve、错误密码、
RSN/RSNXE、IGTK KDE（`wpa3_test.c:120-402`）。

命令形态：

```sh
WORK=${WORK:-/mnt/e/k60-work/scratch/wpa3-host}
mkdir -p "$WORK"
clang -std=c11 -O1 -I drivers/T970Wifi \
  drivers/T970Wifi/T970WifiWpa3.c drivers/T970Wifi/tests/wpa3_test.c \
  -o "$WORK/wpa3_test" && "$WORK/wpa3_test"
```

期望：`ALL wpa3_test CHECKS PASSED`，rc=0。任何 `FAILED` 行或非 0 都是
失败；这是主机证据，不是设备证据。

### 4.2 t970 station/AP 模拟器

输入：同上的库，加
`E:/hackios/UniXNU-t970/drivers/T970Wifi/tests/sta_sim_wpa3.c`。

命令形态与 §4.1 相同，测试文件换成 `sta_sim_wpa3.c`：

~~~sh
WORK=${WORK:-/mnt/e/k60-work/scratch/wpa3-host}
clang -std=c11 -O1 -I drivers/T970Wifi \
  drivers/T970Wifi/T970WifiWpa3.c drivers/T970Wifi/tests/sta_sim_wpa3.c \
  -o "$WORK/sta_sim_wpa3" && "$WORK/sta_sim_wpa3"
~~~

覆盖 9 个场景：`wpa2_psk`、`wpa2_psk_sha256_pmf`、`wpa3_sae_hnp`、
`wpa3_sae_hnp_aclog`、`wpa3_sae_h2e`、`wpa3_sae_h2e_aclog`、
`wpa2_wpa3_mixed`、`wpa3_status126_fallback`、`wpa3_wrong_password`
（`sta_sim_wpa3.c:331-341`）。它断言 RSN 选择、PWE、commit/confirm、PMK/PMKID、
assoc RSN/RSNXE、PTK、IGTK、PMF deauth 丢弃/重放（`:293-328`）。

期望：`ALL sta_sim_wpa3 SCENARIOS PASSED`，rc=0；错误密码场景不得出现
`wrong pass rejected` 失败。

### 4.3 K60 侧接入测试（仍未实现）

`scripts/tests/test-wpa3-reference.py` 只覆盖参考库，不编译 K60 源码。K60 侧的 host 测试仍未实现；它应编译 K60 的
`drivers/PongWifi/ath11k/T970WifiWpa3.c` 与复制过来的
`tests/wpa3_test.c`（或直接引用 t970 的测试文件，保持只读参考）。期望输出与
§4.1 相同。station 的字符串变换仍由 `build-k60-ath11k.py` 完成，不要为了测试
把 WPA3 代码塞进生成器字符串；测试必须直接编译库源码。

注意：t970 的 `sta_sim_wpa3.c` 依赖 `nw_sta.c` 的 station 语义，K60 的
`nw_sta.c` 在 `E:/k60-work/impl/ath12kwifi27` 的 pin 上；如果 pin 与 t970 的
shared 源不同，先把 `C` 字段和函数签名对齐，再谈模拟器。不能把 t970 的
sim 结果直接当作 K60 station 已接入。

## 5. 与 27 线其他未决项的关系

- **C1（selector/ioctl）**：WPA3 join 最终仍走 Apple80211 selector；本计划只
  改 driver 内部的 auth 门，不证明 24A446 的 selector 27/254 路径。C1 仍 open。
- **C2（launchd/wifid）**：如果 24A446 使用用户态 wpa_supplicant，内核 SAE
  库不是正确层；本计划只覆盖 K60 当前 legacy station。C2 不因本文关闭。
- **C3（0x80 频道标志）**：与 WPA3 无关；不要拿 WPA3 的字段改动去关闭 C3。
- **B4/B5（导出与页大小）**：WPA3 库增加的是归档内部符号，不改变 93 MB 图的
  导出表；B4/B5 的判据仍按 `SBL-MISSION.md` §68.5。
- **构建验收**：本计划不产出 27 station 归档。真正编译前仍需要完整的
  arm64e `libPongAth11k.a`（含 `nw_wifi_power` 与
  `nw_wifi_scan_frequencies`），以及 §3.1 的库对象；否则只能停在源码与主机
  向量测试。

## 6. 关闭条件与不做的猜测

WPA3 的“已实现”至少需要三件事同时成立：

1. 参考层通过 §4.0（2026-11-21 实测），并且 K60 station 变换在主机上通过（§4.3，仍未实现）；
2. K60 归档包含库对象，且 `scripts/check-wifi-station-archive.py` 的成员
   架构/stamp 检查仍通过；
3. 24A446 的真实 join 请求给出 SAE 的 `auth_upper`，或者拿到 wifid 的
   selector 证据，使 §3.3 的 boot-arg 有值可填。

在 3 之前，`PongWifiNet.cpp` 保持拒绝未知 auth，WPA3 状态是“库可复用、
station 未接、控制面未证”。不得用 22H374 的 WPA2 personal 0x8 或 24A446 的
WPA2 personal 0x10 代替 SAE 值；也不得把 t970 的模拟器输出当成 K60 设备证据。

## 7. 复现清单

```
# 1. 读参考库与测试
E:/hackios/UniXNU-t970/drivers/T970Wifi/T970WifiWpa3.c:894-1128
E:/hackios/UniXNU-t970/drivers/T970Wifi/tests/wpa3_test.c:120-402

# 2. 看 t970 的接线
E:/hackios/UniXNU-t970/kits/PongPlatform24/build-support/merged-scripts/build-pong-ath11k.py:385-557

# 3. 看 K60 缺口
drivers/Ath12kWifi/src/nw_sta.c:112-123   # rsn_check
drivers/Ath12kWifi/src/nw_sta.c:359-383   # PTK / MIC / CCMP key
drivers/Ath12kWifi/src/nw_sta.c:415-455   # EAPOL version / M2
drivers/Ath12kWifi/src/nw_sta.c:458-466   # open auth only
    drivers/PongWifi/PongWifiNet.cpp:787-793  # auth_upper gate
    drivers/PongWifi/PongWifiNet.cpp:1394-1397 # sae probe, not SAE

# 4. 主机测试（只读参考，不构建 K60）
cd /mnt/e/hackios/k60-wifi
/usr/bin/python3 scripts/tests/test-wpa3-reference.py
```
