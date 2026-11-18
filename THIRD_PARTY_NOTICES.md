# Third-party source notices

This device repository contains or builds against these separately licensed projects:

- UniXNU core, DarwinBoot, NativePrelink, NativeUfs, NativeRamBlock, and the Adreno modules: retain their per-file SPDX identifiers and upstream repository licenses.
- HackiOS userland adapters, job policy and preference templates: retain the HackiOS license distributed with the source.
- NativeMetal, NativeAdreno, and ArmSmmu4K implementations: retain the upstream UniXNU module licenses.
- iOS 16.6.1 / 20G81 components are obtained from Apple's restore service by `scripts/fetch-ios16-assets.py`; no Apple restore binaries are included here.
- Linux v7.0.14 sources compiled into the kernel-side Wi-Fi archive: `drivers/soc/qcom/qmi_interface.c` and `drivers/soc/qcom/qmi_encdec.c` (SPDX GPL-2.0) and `lib/rbtree.c` (SPDX GPL-2.0-or-later), linked by `scripts/build-k60-ath11k.py:661-662`. A distributed kernel image that contains them is therefore subject to GPL-2.0 for those files. This repository does not yet carry the GPL-2.0 text; add it before any image containing the Wi-Fi archive is redistributed.
- The shared Ath12kWifi upper-stack sources compiled from `E:/k60-work/impl/wifi/work/src/UniXNU-sheng/drivers/Ath12kWifi` (`src/nw_sta.c`, `src/nw_crypto.c`, `src/nw_events.c`, `src/nw_mac80211.c`, the lx shim) carry no SPDX header. Treat them as all rights reserved until that project states a licence.

The device-level license does not replace a component's file-level license.
