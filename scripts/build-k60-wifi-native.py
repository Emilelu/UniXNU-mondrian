#!/usr/bin/env python3
"""Link actual QCA6490 ath11k PCI/MHI and Pong-style Darwin 22 network/platform code.

Firmware is read from the user's local recovery extraction, embedded only in
ignored build output, never committed here. No images are hashed/read back.
"""
import argparse,importlib.util,json,os,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import pong_paths
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--tree',type=Path,required=True)
 p.add_argument('--ath11k',type=Path,default=pong_paths.wifi_build()/'libPongAth11k.a')
 p.add_argument('--firmware',type=Path,default=pong_paths.wifi_firmware())
 p.add_argument('--profile',type=Path,default=None,
                help='K60 board profile; defaults to ROOT/configs/mondrian-wifi-sm8475.json')
 p.add_argument('--output-dir',type=Path,default=None)
 a=p.parse_args();out=(a.output_dir.resolve() if a.output_dir else a.tree/'build/k60-wifi');out.mkdir(parents=True,exist_ok=True)
 shared=pong_paths.sheng_root()
 profile_path=a.profile or (ROOT/'configs/mondrian-wifi-sm8475.json')
 profile=json.loads(profile_path.read_text())
 if profile['board']!='mondrian' or profile['soc']!='SM8475' or profile['pci'].get('vendor')!=0x17cb or profile['pci'].get('device')!=0x1103:
  raise RuntimeError('mondrian QCA6490 profile required')
 hardware=os.environ.get('PONG_WIFI_DTB') or os.environ.get('PONG_HARDWARE_DTB')
 if hardware:
  spec=importlib.util.spec_from_file_location('k60_fdt',ROOT/'scripts/prepare-k60-wifi.py')
  fdt=importlib.util.module_from_spec(spec);spec.loader.exec_module(fdt)
  nodes=fdt.fdt_nodes(Path(hardware).read_bytes())
  host=next((v for v in nodes.values() if v.get('compatible')==b'qcom,pci-msm\0'),None)
  full=host is not None and 'qcom,phy-sequence' in host
  if not full:
   if os.environ.get('PONG_WIFI_DTB'):
    raise RuntimeError('PONG_WIFI_DTB is not a full live Wi-Fi DT')
   print('Wi-Fi: ADT hardware DTB omits live Wi-Fi fields; using the k60 live-DT board profile')
  else:
   live=fdt.describe(Path(hardware).read_bytes(),profile['pci'])
   for area in ('pcie','dma','msi'):
    for key,value in profile[area].items():
     if key=='target_link_speed':continue # Observed from Android PCIe runtime, not DT.
     if live[area][key]!=value:raise RuntimeError('k60 live DT changed: '+area+'.'+key)
   fields=('supply','resource','regulator','request')
   expected=[{key:r[key] for key in fields} for r in profile['rails']]
   actual=[{key:r[key] for key in fields} for r in live['rails']]
   if expected!=actual:raise RuntimeError('k60 live DT changed: WLAN rail requests')
 header='struct PongWifiPhyEntry {unsigned off,value,delay;};\nstatic constexpr PongWifiPhyEntry kPongWifiPhy[]={\n'+''.join('{%d,%d,%d},\n'%tuple(e) for e in profile['pcie']['phy_sequence'])+'};\n'
 header+='struct PongWifiRail {const char *name;unsigned mv,maxMv,ppid,type,subtype;};\nstatic constexpr PongWifiRail kPongWifiRails[]={\n'
 for e in profile['rails']:
  physical=e.get('physical',{})
  ppid=(physical.get('spmi_slave',0)<<8)|physical.get('peripheral',0)
  header+='{%s,%d,%d,%d,%d,%d},\n'%(json.dumps(e['resource']),(e['request'][0]+999)//1000,e['request'][1]//1000,ppid,physical.get('type',0),physical.get('subtype',0))
 for e in profile['pcie']['analogue_rails']:
  header+='{%s,%d,%d,0,0,0},\n'%(json.dumps(e['resource']),(e['microvolts']+999)//1000,e['microvolts']//1000)
 header+='};\n'
 domain=profile['pcie']['power_domain']
 if (domain['control'],domain['collapse_vote'],domain['collapse_bit'])!=(0x17b004,0x162128,0):raise RuntimeError('Pong PCIe0 power domain required')
 header+='static constexpr unsigned kPongPcieCollapseVote=%du,kPongPcieCollapseMask=%du;\n'%(domain['collapse_vote']-0x100000,1<<domain['collapse_bit'])
 pcie=profile['pcie']
 if pcie['clock_names'][8]!='pcie_phy_refgen_clk' or pcie['max_clock_frequency_hz'][10]!=100000000:
  raise RuntimeError('k60 pci-msm refgen clock plan changed; adapt its RCG before building')
 for name,value in (('kPongPciePhyStatus',pcie['phy_status_offset']),
                    ('kPongPciePhyStatusMask',1<<pcie['phy_status_bit']),
                    ('kPongPciePhyPowerDown',pcie['phy_power_down_offset']),
                    ('kPongPcieAuxMhz',pcie['aux_clock_mhz']),
                    ('kPongPcieEpLatencyMs',pcie['endpoint_latency_ms']),
                    ('kPongPcieTargetSpeed',pcie['target_link_speed']),
                    ('kPongPciePerstDelayUs',pcie['perst_delay_us'])):
  header+='static constexpr unsigned %s=%du;\n'%(name,value)

 (out/'PongWifiInputs.h').write_text(header)
 # Optional unattended association fixture. Only a local private file may
 # provide credentials; never put them in boot args, logs or source control.
 test_path=os.environ.get('PONG_WIFI_TEST_CONFIG')
 ssid=key=b''
 if test_path:
  test=json.loads(Path(test_path).read_text())
  ssid=test['ssid'].encode('utf-8');key=test['psk'].encode('utf-8')
  if not 1<=len(ssid)<=32 or not 8<=len(key)<=64 or b'\0' in ssid+key:
   raise RuntimeError('Wi-Fi test requires a valid SSID and WPA2 PSK')
  if len(key)==64 and any(c not in b'0123456789abcdefABCDEF' for c in key):
   raise RuntimeError('64-byte Wi-Fi test PSK must be hexadecimal')
 test_header='static constexpr unsigned kWifiTestSsidBytes=%d,kWifiTestKeyBytes=%d;\n'%(len(ssid),len(key))
 for name,data in [('kWifiTestSsid',ssid),('kWifiTestKey',key)]:
  test_header+='static const unsigned char %s[]={%s};\n'%(name,','.join(str(v) for v in data) or '0')
 test_file=out/'PongWifiTestInputs.h'
 fd=os.open(test_file,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
 with os.fdopen(fd,'w') as f:f.write(test_header)
 fw=sorted(f for f in a.firmware.iterdir() if f.is_file())
 if not all((a.firmware/n).is_file() for n in ('amss.bin','amss20.bin','m3.bin','regdb.bin')):raise RuntimeError('Actual Pong modem firmware required')
 entries=[];at=(8+len(fw)*40+4095)&~4095
 for f in fw:
  name=f.name.encode();size=f.stat().st_size
  if len(name)>31:raise RuntimeError('firmware name too long')
  entries.append((name,at,size,f));at=(at+size+4095)&~4095
 pack=out/'PongWifiFirmware.bin'
 with pack.open('wb') as f:
  f.write(b'PWF2'+struct.pack('<I',len(entries)))
  for name,off,size,_ in entries:f.write(struct.pack('<32sII',name,off,size))
  for _,off,size,path in entries:
   f.seek(off);f.write(path.read_bytes())
 asm=out/'PongWifiFirmware.s';asm.write_text('.section __TEXT,__const\n.p2align 12\n.globl _pong_wifi_firmware\n_pong_wifi_firmware:\n.incbin "'+str(pack)+'"\n.globl _pong_wifi_firmware_end\n_pong_wifi_firmware_end:\n')
 framework=a.tree/'.cache/fakeroot/System/Library/Frameworks/Kernel.framework/Versions/A'
 env=dict(os.environ,DEVELOPER_DIR=str(pong_paths.developer_dir()))
 sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],env=env,text=True).strip()
 flags=['-target','arm64-apple-ios16.0','-isysroot',sdk,'-mkernel','-ffreestanding','-fno-builtin','-fno-exceptions','-fno-rtti','-fno-stack-protector','-mgeneral-regs-only','-std=gnu++17','-fblocks','-O2','-DKERNEL=1','-DKERNEL_PRIVATE=1','-DXNU_KERNEL_PRIVATE=1','-DARM64_BOARD_CONFIG_PONG=1','-I'+str(framework/'PrivateHeaders'),'-I'+str(framework/'Headers'),'-I'+str(shared/'drivers/Ath12kWifi/include'),'-I'+str(shared/'package'),'-I'+str(out),'-Wno-deprecated-declarations']
 objects=[]
 for name in ('PongWifiPlatform','PongWifiNet'):
  obj=out/(name+'.o');cmd=['xcrun','clang++',*flags,'-c',str(ROOT/'drivers/PongWifi'/(name+'.cpp')),'-o',str(obj)]
  r=subprocess.run(cmd,env=env,capture_output=True,text=True);(out/(name+'.log')).write_text(r.stdout+r.stderr)
  if r.returncode:raise SystemExit(r.stderr)
  if name == 'PongWifiNet':
   # Register this owned object's network metaclasses after the radio starts.
   # Preserve all code/relocations; LLVM18 cannot globalize Mach-O symbols.
   raw=bytearray(obj.read_bytes());offset=32;symcmd=None
   for _ in range(struct.unpack_from('<I',raw,16)[0]):
    kind,length=struct.unpack_from('<II',raw,offset)
    if kind==0x19:
     for i in range(struct.unpack_from('<I',raw,offset+64)[0]):
      section=offset+72+80*i
      if raw[section:section+16].rstrip(b'\0')==b'__mod_init_func':
       raw[section:section+16]=b'__pong_init'.ljust(16,b'\0')
       section_flags=struct.unpack_from('<I',raw,section+64)[0];struct.pack_into('<I',raw,section+64,section_flags&~255)
    elif kind==2:symcmd=offset
    offset+=length
   if symcmd is None:raise RuntimeError('owned network object missing symbols')
   symoff,count,stroff,strsize=struct.unpack_from('<4I',raw,symcmd+8)
   if stroff+strsize!=len(raw):raise RuntimeError('unexpected network string table')
   for i in range(count):
    at=symoff+16*i;n=stroff+struct.unpack_from('<I',raw,at)[0];end=raw.index(0,n)
    if raw[n:end]==b'__GLOBAL__sub_I_PongWifiNet.cpp':
     new=b'_PongWifiNetStaticInit\0';struct.pack_into('<I',raw,at,strsize);raw[at+4]|=1
     raw.extend(new);struct.pack_into('<I',raw,symcmd+20,strsize+len(new));break
   else:raise RuntimeError('owned network constructor not found')
   obj=out/'PongWifiNet.late.o';obj.write_bytes(raw)
  objects.append(obj)
 obj=out/'PongWifiFirmware.o';subprocess.run(['xcrun','clang','-target','arm64-apple-ios16.0','-c',str(asm),'-o',str(obj)],env=env,check=True);objects.append(obj)
 obj=out/'PongQcomRpmh.o';subprocess.run(['xcrun','clang',*flags[:flags.index('-std=gnu++17')],'-O2','-I'+str(shared/'package'),'-c',str(shared/'package/QcomRpmh.c'),'-o',str(obj)],env=env,check=True);objects.append(obj)
 archive=out/'libPongWifiNative.a';archive.unlink(missing_ok=True)
 subprocess.run(['xcrun','libtool','-static','-o',str(archive),str(a.ath11k),*map(str,objects)],env=env,check=True)
 (out/'build-report.json').write_text(json.dumps(dict(board='mondrian SM8475 QCA6490',guest='20G81',backend='Linux v7.0.14 ath11k',archive=str(archive),firmware_from_local=str(a.firmware),firmware_files=len(entries),firmware_bytes=pack.stat().st_size,image_verification='skipped by request',runtime_observed=False),indent=2)+'\n')
 print(archive)
if __name__=='__main__':main()
