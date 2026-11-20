# 16 → 27 属性号对照（生成物）

由 `python3 scripts/check-prop-numbers.py --render` 生成，**不要手改**：改
`docs/research/charger/PROP-NUMBERS.toml`，门禁会在两者不一致时报 stale（P-259）。

三档结论只有 `same` / `differs-known` / `unknown`；`unknown` 的行同时进下面的待查清单。

| id | 属性 | 16 侧 | 27 侧 | 结论 | 谁改 |
| --- | --- | --- | --- | --- | --- |
| `iokit-current-capacity` | kIOPMPSCurrentCapacityKey | `kIOPMPSCurrentCapacityKey` | `kIOPMPSCurrentCapacityKey` | same | — |
| `iokit-max-capacity` | kIOPMPSMaxCapacityKey | `kIOPMPSMaxCapacityKey` | `kIOPMPSMaxCapacityKey` | same | — |
| `iokit-voltage` | kIOPMPSVoltageKey | `kIOPMPSVoltageKey` | `kIOPMPSVoltageKey` | same | — |
| `iokit-amperage` | kIOPMPSAmperageKey | `kIOPMPSAmperageKey` | `kIOPMPSAmperageKey` | same | — |
| `iokit-cycle-count` | kIOPMPSCycleCountKey | `kIOPMPSCycleCountKey` | `kIOPMPSCycleCountKey` | same | — |
| `iokit-time-remaining` | kIOPMPSTimeRemainingKey | `kIOPMPSTimeRemainingKey` | `kIOPMPSTimeRemainingKey` | same | — |
| `iokit-temperature` | kIOPMPSBatteryTemperatureKey | `kIOPMPSBatteryTemperatureKey` | `kIOPMPSBatteryTemperatureKey` | same | — |
| `iokit-fully-charged` | kIOPMFullyChargedKey | `kIOPMFullyChargedKey` | `kIOPMFullyChargedKey` | same | — |
| `iokit-adapter-details` | kIOPMPSAdapterDetailsKey | `kIOPMPSAdapterDetailsKey` | `kIOPMPSAdapterDetailsKey` | same | — |
| `iokit-adapter-family` | kIOPMPSAdapterDetailsFamilyKey | `kIOPMPSAdapterDetailsFamilyKey` | `kIOPMPSAdapterDetailsFamilyKey` | same | — |
| `iokit-adapter-amperage` | kIOPMPSAdapterDetailsAmperageKey | `kIOPMPSAdapterDetailsAmperageKey` | `kIOPMPSAdapterDetailsAmperageKey` | same | — |
| `iokit-adapter-watts` | kIOPMPSAdapterDetailsWattsKey | `kIOPMPSAdapterDetailsWattsKey` | `kIOPMPSAdapterDetailsWattsKey` | same | — |
| `literal-instant-amperage` | "InstantAmperage" 字符串属性 | `InstantAmperage` | `InstantAmperage` | same | — |
| `literal-nominal-charge-capacity` | "NominalChargeCapacity" 字符串属性 | `NominalChargeCapacity` | `NominalChargeCapacity` | same | — |
| `literal-design-capacity` | "DesignCapacity" 字符串属性 | `DesignCapacity` | `DesignCapacity` | same | — |
| `literal-raw-current` | "AppleRawCurrentCapacity" 字符串属性 | `AppleRawCurrentCapacity` | `AppleRawCurrentCapacity` | same | — |
| `literal-raw-max` | "AppleRawMaxCapacity" 字符串属性 | `AppleRawMaxCapacity` | `AppleRawMaxCapacity` | same | — |
| `wire-battmgr-table` | battmgr wire 属性下标（19 字段） | `19 fields` | `19 fields` | same | — |

## 待查（verdict = unknown）

- 无：每一行两侧都能打开并核对过。
