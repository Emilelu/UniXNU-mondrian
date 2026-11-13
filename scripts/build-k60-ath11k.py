#!/usr/bin/env python3
"""Build Linux 7.0.14 ath11k PCI/MHI using UniXNU's shared Wi-Fi ABI.

Sources are local public Linux and UniXNU Ath12kWifi checkouts.
The driver is not replaced by success stubs. Missing core symbols fail the
link recipe; power/DMA/MSI remain the consuming Pong board's responsibility.
"""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import pong_paths

def adapt_dispatcher_timers(source):
    """Do not retain intrusive-list successors across reentrant callbacks."""
    old = """  u64 now = lx_now_ms();
  struct list_head *p, *n;
  for (p = g_timers.next; p != &g_timers; p = n) {
    n = p->next; struct delayed_work *d = container_of(p, struct delayed_work, work.entry);
    if (d->armed && now >= d->due && !is_running(&d->work)) {
      d->armed = 0; list_del_init(p); ran = 1; where(2, (const void *)d->work.func);
      g_running[g_nrunning++] = &d->work; d->work.func(&d->work); g_nrunning--; }
  }
"""
    new = """  u64 now = lx_now_ms();
  /* A callback may wait/pump recursively and remove any later timer. Never
   * keep next across that callback: list_del_init makes removed nodes self
   * linked. Restart selection after each callback and bound zero-delay work. */
  for (unsigned timer_budget = 256; timer_budget; --timer_budget) {
    struct delayed_work *d = 0; struct list_head *p;
    for (p = g_timers.next; p != &g_timers; p = p->next) {
      struct delayed_work *candidate = container_of(p, struct delayed_work, work.entry);
      if (candidate->armed && now >= candidate->due && !is_running(&candidate->work)) { d = candidate; break; }
    }
    if (!d) break;
    d->armed = 0; list_del_init(&d->work.entry); ran = 1; where(2, (const void *)d->work.func);
    g_running[g_nrunning++] = &d->work; d->work.func(&d->work); g_nrunning--;
  }
"""
    if source.count(old) == 1:
        return source.replace(old, new)
    # Ath12kWifi pin 28de7b91 already ships a bounded dispatcher loop that
    # selects `due` before each callback and never caches the list successor.
    # Accept that exact form as already-fixed; do not silently accept an
    # unrelated dispatcher (the unsafe cached-next pattern must be absent).
    already = """  for (unsigned budget = 0; budget < 64; budget++) {
    u64 now = lx_now_ms(); struct delayed_work *due = 0;
"""
    unsafe = 'n = p->next; struct delayed_work *d = container_of(p, struct delayed_work, work.entry);'
    if source.count(already) == 1 and unsafe not in source:
        return source
    raise RuntimeError('shared dispatcher timer ABI differs')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--linux', type=Path, required=True)
    p.add_argument('--shared', type=Path, default=pong_paths.sheng_root()/'drivers/Ath12kWifi')
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--jobs', type=int, default=4)
    a = p.parse_args(); linux = a.linux.resolve(); shared = a.shared.resolve(); out = a.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not (linux / 'drivers/net/wireless/ath/ath11k/pci.c').is_file(): raise RuntimeError('Linux ath11k PCI sources required')
    for file in ('include/nw_abi.h', 'shim/src/lx_rt.c', 'src/nw_sta.c'):
        if not (shared / file).is_file(): raise RuntimeError('UniXNU Ath12kWifi shared ABI required: ' + file)
    source = linux / 'drivers/net/wireless/ath/ath11k'
    gen = out / 'ath11k'; gen.mkdir(exist_ok=True)
    for f in source.glob('*'):
        if f.suffix not in ('.c', '.h') or f.name == 'trace.h': continue
        target = gen / f.name
        if target.exists() or target.is_symlink(): target.unlink()
        target.symlink_to(f)
    traces = sorted({v for f in source.glob('*.[ch]') for v in re.findall(r'\btrace_ath11k_[a-z0-9_]+', f.read_text())})
    (gen / 'trace.h').write_text('\n'.join('#define ' + n + '(...) ' + ('0' if n.endswith('_enabled') else '((void)0)') for n in traces) + '\n')
    spectral = out / 'spectral_common.h'
    if spectral.exists() or spectral.is_symlink(): spectral.unlink()
    spectral.symlink_to(source.parent / 'spectral_common.h')
    # A kernel variable-like jiffies macro cannot also name this statistics
    # member. Rename only the generated member/access, not time expressions.
    for name in ('core.h', 'dp_rx.c'):
        content = (source / name).read_text().replace('unsigned long jiffies;', 'unsigned long bp_jiffies;').replace('bp_stats->jiffies', 'bp_stats->bp_jiffies')
        (gen / name).unlink(); (gen / name).write_text(content)
    pc = (source / 'pci.c').read_text()
    for old, new in [('static int ath11k_pci_init(void)', 'int pong_ath11k_pci_init(void)'),
                     ('static void ath11k_pci_exit(void)', 'void pong_ath11k_pci_exit(void)'),
                     ('module_exit(ath11k_pci_exit);', 'module_exit(pong_ath11k_pci_exit);')]:
        if pc.count(old) != 1: raise RuntimeError('Linux 7.0.14 PCI entry differs: ' + old)
        pc = pc.replace(old, new)
    (gen / 'pci.c').unlink(); (gen / 'pci.c').write_text(pc)
    # Nothing CNSS2 selection, driven by actual QMI chip/board IDs. Linux's
    # board-2 container is not part of this phone's firmware partition.
    core = (gen / 'core.c').read_text()
    needle = '\tbd->fw = ath11k_core_firmware_request(ab, name);'
    replacement = r"""    char pong_bdf[48];
    if (!strcmp(name, ATH11K_DEFAULT_BOARD_FILE)) {
        u32 id = ab->qmi.target.board_id;
        const char *prefix = (ab->qmi.target.chip_id & 0x10) ? "bdwlang" : "bdwlan";
        if (id == 0xff) snprintf(pong_bdf, sizeof pong_bdf, "%s.elf", prefix);
        else if (id < 0xff) snprintf(pong_bdf, sizeof pong_bdf, "%s.e%02x", prefix, id);
        else snprintf(pong_bdf, sizeof pong_bdf, "%s%02x.e%02x", prefix, (id >> 8) & 255, id & 255);
        name = pong_bdf;
        ath11k_info(ab, "Pong: actual QMI board firmware %s\n", name);
    }
""" + needle
    if core.count(needle) != 1: raise RuntimeError('ath11k BDF request ABI differs')
    (gen / 'core.c').unlink(); (gen / 'core.c').write_text(core.replace(needle, replacement))
    # WMI's wait condition sends and transfers ownership of an skb on
    # success. The shared shim's generic wait evaluates that condition
    # again on exit, sending the same skb twice and replacing success with
    # -EAGAIN when the single HTC credit has already been consumed (g274).
    # Use its side-effect-safe wait for both WMI credit/descriptor paths.
    wmi = (source / 'wmi.c').read_text()
    if wmi.count('wait_event_timeout(') != 2:
        raise RuntimeError('ath11k WMI command wait ABI differs')
    (gen / 'wmi.c').unlink()
    wmi = wmi.replace('wait_event_timeout(', 'wait_event_timeout_once(')
    trace = '\ttrace_ath11k_wmi_cmd(ab, cmd_id, skb->data, skb->len);'
    if wmi.count(trace) != 1:
        raise RuntimeError('ath11k WMI submission trace ABI differs')
    wmi = 'extern void pong_ath11k_wmi_submitted(unsigned int);\n' + wmi.replace(
        trace, trace + '\n\tpong_ath11k_wmi_submitted(cmd_id);')
    (gen / 'wmi.c').write_text(wmi)
    # The cooperative shim cannot safely reenter full Linux firmware reset
    # work inside the failing MHI callback. Preserve the first fault and let
    # the board stop this optional worker with DMA storage retained.
    mhi_driver = (source / 'mhi.c').read_text()
    status = '\tstruct ath11k_pci *ab_pci = ath11k_pci_priv(ab);\n\n\tath11k_dbg(ab, ATH11K_DBG_BOOT, "notify status reason %s\\n",'
    if mhi_driver.count(status) != 1:
        raise RuntimeError('ath11k MHI status callback ABI differs')
    mhi_driver = 'struct mhi_controller;\nextern void pong_ath11k_mhi_failed(struct mhi_controller *, int);\n' + mhi_driver.replace(
        status, '\tstruct ath11k_pci *ab_pci = ath11k_pci_priv(ab);\n\n'
        '\tif (cb == MHI_CB_SYS_ERROR || cb == MHI_CB_FATAL_ERROR || cb == MHI_CB_EE_RDDM) {\n'
        '\t\tpong_ath11k_mhi_failed(mhi_cntrl, cb);\n\t\treturn;\n\t}\n\n'
        '\tath11k_dbg(ab, ATH11K_DBG_BOOT, "notify status reason %s\\n",')
    (gen / 'mhi.c').unlink()
    (gen / 'mhi.c').write_text(mhi_driver)
    # The shared station uses mac80211's split link/vif notifications.
    # ath11k still implements the unified bss_info_changed callback.
    # Route both notifications to that real implementation; a NULL split
    # callback caused g277's instruction-fetch panic on the first join.
    ath_mac = (source / 'mac.c').read_text()
    ops = 'static const struct ieee80211_ops ath11k_ops = {'
    bridge = '''static void pong_ath11k_vif_cfg_changed(struct ieee80211_hw *hw,
        struct ieee80211_vif *vif, u64 changed)
{
    ath11k_mac_op_bss_info_changed(hw, vif, &vif->bss_conf, changed);
}

'''
    if ath_mac.count(ops) != 1:
        raise RuntimeError('ath11k mac80211 operations ABI differs')
    ath_mac = ath_mac.replace(ops, bridge + ops)
    ath_mac, changes = re.subn(
        r'(\t\.bss_info_changed\s*= ath11k_mac_op_bss_info_changed,)',
        r'\1\n\t.link_info_changed = ath11k_mac_op_bss_info_changed,\n'
        r'\t.vif_cfg_changed = pong_ath11k_vif_cfg_changed,', ath_mac)
    if changes != 1:
        raise RuntimeError('ath11k BSS callback ABI differs')
    (gen / 'mac.c').unlink()
    (gen / 'mac.c').write_text(ath_mac)
    mac = (shared / 'src/nw_mac80211.c').read_text()
    mac += r"""
/* Linux ath11k still uses these mac80211 APIs; the shared station has one
 * hardware and an explicit active-vif list. Honour the supplied vif address. */
struct ieee80211_sta *ieee80211_find_sta_by_ifaddr(struct ieee80211_hw *hw, const u8 *addr, const u8 *local) {
    if (hw != g_hw || !g_sta || !ether_addr_equal(g_sta->addr, addr)) return 0;
    for (int i = 0; i < g_nvif; ++i) if (!local || ether_addr_equal(g_vif[i]->addr, local)) return g_sta;
    return 0;
}
void ieee80211_queue_work(struct ieee80211_hw *hw, struct work_struct *work) { if (hw == g_hw) lx_queue_work(work); }
"""
    (out / 'nw_mac80211_pong.c').write_text(mac)

    pinned = out / 'pinned'; pinned.mkdir(exist_ok=True)
    inputs = {'linux/mhi.h': 'linux/mhi.h', 'linux/ieee80211.h': 'linux/ieee80211.h',
        'linux/soc/qcom/qmi.h': 'linux/soc/qcom/qmi.h', 'net/cfg80211.h': 'net/cfg80211.h',
        'net/regulatory.h': 'net/regulatory.h', 'net/codel.h': 'net/codel.h',
        'net/ieee80211_radiotap.h': 'net/ieee80211_radiotap.h',
        'linux/nl80211.h': 'uapi/linux/nl80211.h', 'linux/rfkill.h': 'uapi/linux/rfkill.h',
        'uapi/linux/rfkill.h': 'uapi/linux/rfkill.h', 'net/mac80211.real.h': 'net/mac80211.h'}
    inputs.update({str(f.relative_to(linux / 'include')): str(f.relative_to(linux / 'include'))
                   for f in (linux / 'include/linux').glob('ieee80211-*.h')})
    for target, name in inputs.items():
        src = linux / 'include' / name
        if not src.is_file(): raise RuntimeError('Missing Linux public header: ' + str(src))
        dest = pinned / target; dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() or dest.is_symlink(): dest.unlink()
        dest.symlink_to(src)
    # tools/pin-headers.sh derives netdevice_enums.h from netdevice.h. The
    # shim's lx_skb.h includes that split header, so reproduce the exact
    # three upstream enum blocks instead of inventing definitions.
    netdev = (linux / 'include/linux/netdevice.h').read_text()
    blocks = []
    for enum_name in ('netdev_priv_flags', 'netdev_stat_type', 'netdev_cmd'):
        match = re.search(r'enum ' + enum_name + r'\s*\{.*?\};', netdev, re.S)
        if not match:
            raise RuntimeError('missing upstream netdevice enum: ' + enum_name)
        blocks.append(match.group())
    (pinned / 'linux/netdevice_enums.h').write_text(
        '/* SPDX-License-Identifier: GPL-2.0 */\n'
        '#ifndef NW_NETDEVICE_ENUMS_H\n#define NW_NETDEVICE_ENUMS_H\n'
        + '\n'.join(blocks) + '\n#endif\n')
    mhi = out / 'mhi'; mhi.mkdir(exist_ok=True)
    for name in ('init.c', 'main.c', 'pm.c', 'boot.c', 'internal.h'):
        dest = mhi / name
        if dest.exists() or dest.is_symlink(): dest.unlink()
        dest.symlink_to(linux / 'drivers/bus/mhi/host' / name)
    (mhi / 'trace.h').write_text((shared / 'shim/mhi/trace.h').read_text())
    common = out / 'common.h'
    if common.exists() or common.is_symlink(): common.unlink()
    common.symlink_to(linux / 'drivers/bus/mhi/common.h')
    env = dict(os.environ, DEVELOPER_DIR=str(pong_paths.developer_dir()))
    clang = os.environ.get('CROSS_CLANG') or subprocess.check_output(
        ['xcrun', '-f', 'clang'], env=env, text=True).strip()
    resource = subprocess.check_output([clang, '-print-resource-dir'], text=True).strip() + '/include'
    overlay = ROOT / 'drivers/PongWifi/ath11k/compat'
    flags = ['-target', 'arm64-apple-ios16.0', '-mkernel', '-O2', '-g0', '-ffreestanding',
        '-fno-builtin', '-fno-common', '-fno-strict-aliasing', '-fwrapv', '-fno-stack-protector',
        '-fno-delete-null-pointer-checks', '-mgeneral-regs-only', '-std=gnu11',
        '-Wno-incompatible-pointer-types', '-Wno-error', '-Wno-unused-value',
        '-nostdinc', '-isystem', str(shared / 'shim/libc'), '-isystem', resource,
        '-I', str(overlay), '-include', 'PongCompat.h', '-I', str(shared / 'shim/include'),
        '-I', str(linux / 'include'), '-I', str(linux / 'include/uapi'),
        '-I', str(shared / 'include'), '-I', str(pinned), '-I', str(shared / 'src'),
        '-I', str(gen), '-I', str(out), '-I', str(source.parent), '-DCONFIG_ATH11K_PCI=1',
        '-DLX_BOOT_SETTLE_MS=0']
    ath = 'core hal hal_tx hal_rx wmi mac reg htc qmi dp dp_tx dp_rx ce peer dbring hw pcic fw p2p mhi pci'.split()
    jobs = [(gen / (n + '.c'), out / ('ath11k_' + n + '.o'), []) for n in ath]
    jobs += [(mhi / (n + '.c'), out / ('mhi_' + n + '.o'), ['-I', str(mhi)]) for n in ('init', 'main', 'pm', 'boot')]
    # WPA station nonces use Darwin's entropy source, not a timer/counter.
    sta = (shared / 'src/nw_sta.c').read_text()
    begin = sta.index('static void make_nonce(u8 *out) {')
    end = sta.index('static void derive_ptk(void)', begin)
    sta = sta[:begin] + 'extern void PongWifiRandom(void *, size_t);\nstatic void make_nonce(u8 *out) { PongWifiRandom(out, 32); }\n' + sta[end:]
    # Darwin must see a real link-down for an explicit leave and for a
    # replacement join, including when down/up occurs within one daemon tick.
    join = 'static void start_connect(void) {\n  if (C.state != NW_STA_IDLE && C.state != NW_STA_SCANNING) return;'
    leave = 'else if (kind == REQ_DISCONNECT && C.state >= NW_STA_AUTH) { teardown(0, 0); C.state = NW_STA_IDLE; }'
    if sta.count(join) != 1 or sta.count(leave) != 1:
        raise RuntimeError('shared station transition ABI differs')
    sta = sta.replace(join, '''static void start_connect(void) {
  if (C.state == NW_STA_UP && C.ssid_len == g_req.ssid_len &&
      !memcmp(C.ssid, g_req.ssid, C.ssid_len) &&
      (!g_req.has_bssid || !memcmp(C.ap.bssid, g_req.bssid, 6))) return;
  if (C.state >= NW_STA_AUTH) {
    lx_cancel_delayed(&g_timer);
    teardown(C.state == NW_STA_UP, -1);
    C.state = NW_STA_IDLE;
  }
  if (C.state != NW_STA_IDLE && C.state != NW_STA_SCANNING) return;''')
    sta = sta.replace(leave, '''else if (kind == REQ_DISCONNECT && C.state >= NW_STA_AUTH) {
      lx_cancel_delayed(&g_timer); teardown(C.state == NW_STA_UP, -1); C.state = NW_STA_IDLE;
    }''')
    # ath11k caches the management rate after association, then reapplies it
    # when the next vdev starts (mac.c: ath11k_start_vdev). Rejoining from
    # 2.4 to 5 GHz must not carry a CCK rate into that start/authentication.
    # Use the same AP basic-rate selection as the shared station's later
    # association notification, but publish it before assign_vif_chanctx.
    rates_begin = '    const u8 *e = find_ie(C.ap.ie, C.ap.ie_len, WLAN_EID_SUPP_RATES);'
    rates_end = '    g_vif->bss_conf.assoc_capability = C.ap.caps;'
    assign = '  r = g_ops->assign_vif_chanctx(g_hw, g_vif, &g_vif->bss_conf, C.ctx);'
    if sta.count(rates_begin) != 1 or sta.count(rates_end) != 1 or sta.count(assign) != 1:
        raise RuntimeError('shared station basic-rate/channel-start ABI differs')
    rate_selection = sta[sta.index(rates_begin):sta.index(rates_end)]
    sta = sta.replace(assign, rate_selection +
        '  lx_log(6, "k60 station: pre-start band=%u basic_rates=0x%x", band, g_vif->bss_conf.basic_rates);\n'
        '  g_ops->link_info_changed(g_hw, g_vif, &g_vif->bss_conf, BSS_CHANGED_BASIC_RATES);\n' + assign)
    (out / 'nw_sta_pong.c').write_text(sta)
    (out / 'lx_rt_pong.c').write_text(adapt_dispatcher_timers((shared / 'shim/src/lx_rt.c').read_text()))
    common_sources = ['src/nw_crypto.c', 'src/nw_events.c', 'src/nw_mac80211.c', 'src/nw_net.c',
        'src/nw_netdev.c', 'src/nw_pci.c', 'src/nw_qrtr.c', 'src/nw_qrtr_mhi.c', 'src/nw_sta.c',
        'shim/src/lx_rt.c', 'shim/src/mhi_hook.c']
    jobs += [((out / 'nw_sta_pong.c') if n == 'src/nw_sta.c' else (out / 'nw_mac80211_pong.c') if n == 'src/nw_mac80211.c' else (out / 'lx_rt_pong.c') if n == 'shim/src/lx_rt.c' else shared / n, out / ('shared_' + Path(n).stem + '.o'), []) for n in common_sources]
    jobs += [(linux / ('drivers/soc/qcom/' + n + '.c'), out / (n + '.o'), []) for n in ('qmi_interface', 'qmi_encdec')]
    jobs += [(linux / 'lib/rbtree.c', out / 'rbtree.o', [])]
    jobs += [(ROOT / 'drivers/PongWifi/ath11k/PongAth11k.c', out / 'PongAth11k.o', [])]
    commands = []
    def compile(job):
        src, obj, extra = job; cmd = [clang, *flags, *extra, '-c', str(src), '-o', str(obj)]
        commands.append(cmd)
        r = subprocess.run(cmd, capture_output=True, text=True)
        (out / (obj.stem + '.log')).write_text(r.stdout + r.stderr)
        return obj.name if r.returncode else None
    with ThreadPoolExecutor(a.jobs) as pool: failed = [r for r in pool.map(compile, jobs) if r]
    (out / 'compile-commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    if failed: raise SystemExit('ath11k compile failures (retained .log): ' + ', '.join(failed))
    archive = out / 'libPongAth11k.a'
    linked = out / 'ath11k-combined.o'
    subprocess.run(['xcrun', 'ld', '-r', '-arch', 'arm64', *[str(o) for _, o, _ in jobs], '-o', str(linked)], env=env, check=True)
    nm = pong_paths.tool('llvm-nm', 'PONG_LLVM_NM', ('/opt/local/bin/llvm-nm-mp-18',))
    undefined = subprocess.check_output([nm, '-u', '-j', str(linked)], text=True).splitlines()
    (out / 'undefined-symbols.txt').write_text('\n'.join(undefined) + '\n')
    allowed = {'_PongWifiRandom','_bzero','_memcmp','_memcpy','_memmove','_memset','_snprintf','_strchr','_strcmp','_strlen','_strncmp','_strncpy','_strtoul','_vsnprintf'}
    if set(undefined) - allowed: raise RuntimeError('unimplemented ath11k imports: ' + repr(set(undefined) - allowed))
    # Export only the documented board/station boundary. Linux shims have the
    # same C names as XNU helpers, so namespace every other defined symbol.
    exports = {'_PongWifiRandom', '_nw_wifi_where'}
    defined = subprocess.check_output([nm, '--defined-only', '--extern-only', '-j', str(linked)], text=True).splitlines()
    renames = {n: '_pong11_' + n[1:] for n in defined if not n.startswith('_nw_wifi_') and n not in exports}
    mapping = out / 'symbol-map.txt'; mapping.write_text(''.join(k + ' ' + v + '\n' for k, v in renames.items()))
    namespaced = out / 'PongAth11k-linked.o'
    subprocess.run([pong_paths.tool('llvm-objcopy', 'PONG_LLVM_OBJCOPY',
                                    ('/opt/local/bin/llvm-objcopy-mp-18',)),
                    '--redefine-syms=' + str(mapping), str(linked), str(namespaced)], check=True)
    archive.unlink(missing_ok=True)
    subprocess.run(['xcrun', 'libtool', '-static', '-o', str(archive), str(namespaced)], env=env, check=True)
    (out / 'build-report.json').write_text(json.dumps(dict(linux='v7.0.14', shared=str(shared),
        guest='20G81', archive=str(archive), real_pci_mhi=True, wifi_operational=False,
        missing_symbols_policy='no fabricated-success stubs', image_verification='skipped by request'), indent=2) + '\n')
    print(archive)


if __name__ == '__main__': main()
