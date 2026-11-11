# init 历史版本（★ 重要：git 里 0391 的版本会 panic）

## 为什么有这个目录

`patches/xnu/0391-k60-embedded-init.patch` 的历史版本都是**另一条分支**的 init：
```
日志特征: Pong init: static 20G81 helper entered
          Pong init: HackiOS userland adapter / iOS 16.6.1 20G81 / static arm64
结果:     panic — Library not loaded: /usr/lib/libSystem.B.dylib
```

设备上**真正能启动**的是 `v10guard` 线：
```
日志特征: Pong init: HackiOS adapter [v10guard]
结果:     launchd 起来，进程到 pid 282（syncdefaultsd 崩溃）
```

这条线的源码原先只在 `/tmp/initbuild/`（临时目录），`0391` 一生效就永久覆盖丢失。
本目录把它保存到仓库里。

## 文件

| 文件 | 大小 | 说明 |
|---|---|---|
| `init-v10guard.bin` | 34,880 B | 已知能启动（实测 launchd pid 282）|
| `init-v10guard.c` | 15,683 B | 对应源码 |
| **`init-v24dp.bin`** | **34,904 B** | **v10guard 严格超集，当前 0391 用它** |
| `init-v24dp.c` | 24,815 B | 对应源码 |

`v24dp` 相对 `v10guard` 的增量只有两条日志（`disabled.plist open/wrote`），
其余 26 条日志完全相同，且含 `Pong init: native Metal entry enabled for backboardd`。

## 正确形态判据（必须同时满足）

```bash
# 1) 日志特征
strings init.bin | grep 'Pong init: HackiOS'
#    必须是 "HackiOS adapter [v10guard]"
#    不能是 "HackiOS userland adapter / ... static arm64"

# 2) Mach-O 结构
python3 -c "
import struct,sys
d=open(sys.argv[1],'rb').read()
n=struct.unpack_from('<I',d,16)[0]; off=32; cs=None
for i in range(n):
    c,s=struct.unpack_from('<II',d,off)
    if c==0x1d: cs=struct.unpack_from('<II',d,off+8)[1]
    off+=s
print('ncmds=%d cs=%s' % (n,cs))" init.bin
#    必须 ncmds=9，cs≈408-416
#    ncmds=10 + cs=19000 是 MacOSX SDK / macOS codesign 的产物，会 panic（P-94/P-99）
```

## 恢复步骤

```bash
# 用 v24dp 重新生成 0391 的 blob
python3 - <<'PY'
import io, re
INIT='/mnt/e/hackios/UniXNU-mondrian/userland/init-history/init-v24dp.bin'
P='/mnt/e/hackios/UniXNU-mondrian/patches/xnu/0391-k60-embedded-init.patch'
data=io.open(INIT,'rb').read()
lines=io.open(P,encoding='utf-8',errors='ignore').read().split('\n')
start=next(i for i,l in enumerate(lines) if 'k60_init_blob[K60_INIT_BLOB_LEN] = {' in l)
end=next(i for i in range(start+1,start+20000) if lines[i].strip()=='+};')
new=['+static const unsigned char k60_init_blob[K60_INIT_BLOB_LEN] = {']
for i in range(0,len(data),12):
    c=data[i:i+12]
    new.append('+    0x%02x,' % c[0] + ','.join('0x%02x' % b for b in c[1:]) + ',')
new.append('+};')
lines[start:end+1]=new
for i,l in enumerate(lines):
    if 'K60_INIT_BLOB_LEN ' in l and l.startswith('+#define'):
        lines[i]='+#define K60_INIT_BLOB_LEN %d' % len(data); break
io.open(P,'w',encoding='utf-8',newline='\n').write('\n'.join(lines))
print('done %d B' % len(data))
PY
```

## 关联坑

- **P-104**：能跑的 init 不在 git 里
- **P-94/P-99/P-100**：MacOSX SDK / macOS codesign 产出的 init 会 panic
- **P-21**：认 init 版本必须按日志字符串组合，不能按文件名或大小
