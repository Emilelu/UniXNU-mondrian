import sys, struct, hashlib
sys.path.insert(0,'device/tools/apfs')
import apfs
BS=4096
o=apfs.Blocks.get
apfs.Blocks.get=lambda self,a,verify=True: o(self,a,verify=False)
ci=apfs.Container('ipsw/096-57366-083.dmg'); vi=ci.volumes()[0]
cw=apfs.Container('windows/os-window.img'); vw=cw.volumes()[0]
def fork(c,v,oid):
    xs=v.xattrs(oid)
    if 'com.apple.ResourceFork' not in xs: return None
    fl,xd=xs['com.apple.ResourceFork']
    if fl & apfs.XATTR_DATA_EMBEDDED: return None
    xoid,size=struct.unpack_from('<QQ',xd,0)
    buf=bytearray(size)
    for lg,ln,ph in v.extents(xoid):
        raw=c.blocks.raw(ph,(ln+BS-1)//BS)
        n=min(ln,size-lg); buf[lg:lg+n]=raw[:n]
    return hashlib.sha256(bytes(buf)).digest()
bad=[]; ok=0; n=0
for path,name,fid,dt in apfs.walk(vw, apfs.ROOT_DIR_INO_NUM):
    if dt!=8: continue
    n+=1
    try: d=fork(cw,vw,fid)
    except Exception: continue
    if d is None: continue
    r=vi.lookup(path)
    if not r: bad.append((path,'no source')); continue
    try: s=fork(ci,vi,r[0])
    except Exception: bad.append((path,'source error')); continue
    if s is None: continue
    if s==d: ok+=1
    else: bad.append((path,'differs'))
print('files',n,'matching',ok,'bad',len(bad))
for p,w in bad[:20]: print('  ',w,p)
