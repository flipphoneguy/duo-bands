# Qin F21: VoLTE on Israeli networks

Why VoLTE doesn't come up on the F21 in Israel, where each piece of the fix lives, what the community patches change, and what the duo build does. Terms are in `01-basics.md`.

## Three gates

VoLTE needs all three of these. On a stock F21 with an Israeli SIM, the first one already closes it, so calls fall back to 3G.

### 1. The vendor's dynamic IMS switch (Android side)

The vendor build.prop sets `persist.vendor.mtk_dynamic_ims_switch=1`. With that on, rild (`mtkfusionrild`, `RtcImsConfigController`) looks up the SIM's MCC/MNC when the SIM loads and sets an "IMS resource capability" per operator:

```
RtcImsConfigController: processDynamicImsSwitch, currentMccMnc = 42512
RtcImsConfigController: setImsResourceCapability, volte:0, vilte:0, wfc:0, vonr:0, vinr:0
```

Android's ImsManager reads that capability and disables voice over IMS (`changeMmTelCapability ... mCapabilitiesToDisable={VOICE...}`), and rild passes it on to the modem as `triggerImsCfg volte:0` / `AT+EIMSCFG=0,...`. The modem then never tries to register IMS. The carrier config can say VoLTE is available (`carrier_volte_available_bool = true` for Partner) and it still won't happen.

With the switch at 0, the capability comes from the carrier config instead, and the same SIM gets `triggerImsCfg volte:1`. A persist prop set at runtime overrides the build.prop value.

In the logs the lookup ran when the SIM loaded at boot. A SIM inserted later without a reboot didn't trigger it again, and kept the previous capability.

### 2. The modem's operator table (md1rom)

`md1rom` has a table of 12-byte entries, `<u32 mccmnc><u32 mccmnc><u32 operator id>`, that maps a SIM's network to an IMS operator profile. The two F21 builds list different Israeli operators:

| Operator | US md1rom (`V142.4`) | EU md1rom (`V142.4.P2`) |
|---|---|---|
| Partner 425-01 | missing | 170 |
| Cellcom 425-02 | missing | 307 |
| Pelephone 425-03 | 233 | 233 |
| Hot 425-07 | missing | 310 |
| 425-09 | missing | 353 |
| 019 425-19 | missing | missing |

Without an entry the modem has no IMS profile for the SIM. In the US md1rom the table sits around `0xea2a80`–`0xea3d7c` (AT&T 310410 → 7, T-Mobile 310260 → 8).

### 3. An IMS APN

IMS registration runs over its own PDN, so the APN database needs a row of type `ims` for the SIM's MCC/MNC. The F21 ROM ships one for Pelephone (425-03) only.

## Where the modem keeps forced settings

`AT+ECFGSET="operator_code","<id>"` and `AT+ECFGSET="mncmcc_pass_flag","0"` are stored in nvdata, in record 0 of `NVD_DATA/IM79_081` (`NVRAM_EF_IMS_PROFILE_LID`):

| Offset in record 0 | Unset | Meaning |
|---|---|---|
| +138 (u16) | `ff ff` | forced operator code (232 = `e8 00`) |
| +1898 (u8) | `ff` | MCC/MNC check (0 = off) |
| +1672 | | last IMS network and cell, plus a timestamp (runtime data) |

Unset means the modem picks the profile from the operator table by the SIM. A forced code applies to every SIM, foreign ones included.

## The community fixes

All four were decompiled or read directly.

**The-curious's script, app and Magisk module** (jtech topic 5454). Root, run once:
- props: `persist.vendor.mtk.volte.enable 1`, `persist.vendor.radio.volte_state 1`, `persist.vendor.mtk.wfc.enable 1`, `persist.dbg.volte_avail_ovr 1`, `persist.vendor.radio.selfreg 1`, `persist.vendor.service.atci.pct.mode 1`, `persist.vendor.mtk_dynamic_ims_switch 0`
- an `ims` APN for the current SIM if none exists
- AT commands written to the rild pts that answers `AT`: `mncmcc_pass_flag 0`, `operator_code 232` (172 for Hot, MNC 07), a Cellcom-only SMS setting, `AT+EIMSCFG=1,0,0,0,1,1`, `settings put global volte_vt_enabled 1`, then `AT+CFUN=1,1`

This forces profile 232 (or 172) into nvdata for every SIM.

**The-curious's no-root patch** (topic 5455). Two Windows tools, both PyInstaller builds of short Python scripts:
- `patch_md1img.exe` rewrites five Malaysian entries in the operator table: 502-13 → 425-01 (232), 502-19 → 425-02 (232), 502-12 → 425-07 (172), 502-17 → 425-09 (232), 502-18 → 425-19 (232). It doesn't re-sign the image.
- `patch_superv2.exe` / `patch_super_v2adv.exe` flip `persist.vendor.mtk_dynamic_ims_switch=1` to `0` in the vendor build.prop inside `super`, and rewrite Malaysian IMS APN rows in `apns-conf.xml` into `mcc="425"`, `mnc` 01, 02, 07, 09, 19 (`apn="ims"`, `type="ims"`, `IPV4V6`), size for size.

With the operator in the modem's table, nothing has to be forced, which is why its guide says to turn MCCMNC CHECK back on.

**019's "019 VoLTE" app** (`com.meir.set.version` 3.0). A root wrapper around a variant of The-curious's script, hard-coded to 425-19. Next to the same props, APN and AT commands it adds `AT+ECFGSET="reg_gruu_support","0"`, an `xcap` APN (`hos`) and an `emergency` APN (`sos`), `persist.vendor.radio.mcfg_enabled`/`mcfg_auto_gen`, the `mtk_ims_support`/`mtk_volte_support`/`mtk_wfc_support` props and `wfc_ims_enabled 1`. It also checks iptables for DROP rules.

## What the duo build does

The same split as the no-root patch, with nothing forced:

1. **md1rom:** the five-entry operator table edit, the same mapping as `patch_md1img.exe` (`scripts/f21/build_md1rom.py`, step 8). A SIM from anywhere else keeps its own entry.
2. **nvdata:** `IMS_PROFILE` stays as in the US set, with the operator code and the MCC/MNC check unset.
3. **The app** (`app/README.md`) sets `persist.vendor.mtk_dynamic_ims_switch 0` and adds the `ims` APN for 425-01, 02, 07, 09 and 19 where one is missing. The APN rows only match Israeli SIMs.

With that setup a 019 SIM registers IMS without `reg_gruu_support 0`.

## Reading the logs

| Line | Means |
|---|---|
| `processDynamicImsSwitch, currentMccMnc = …` then `setImsResourceCapability, volte:0` | the vendor switch blocked this operator |
| `triggerImsCfg volte:0` / `volte:1` | what Android told the modem |
| `VoLTE REG: … resp = 401` then `resp = 200`, `Authenticating --> Registered` | SIP registration (from `volte_stack`) |
| `+CIREG: 2,1,5` | IMS registered, voice and SMS |
| `MtkImsCall: callSessionStarted … ESTABLISHED` | a call on IMS |
