# duo-bands

One modem firmware per phone with both the EU and the US LTE bands, for the Qin F21 Pro (before v3) and the Tiq M5. Flash it once and the phone works on both sides, with no more switching band sets. For the F21 there's also an app, F21 Duo Bands, that installs it in one tap, keeps your IMEI, Bluetooth and Wi-Fi addresses, and turns on VoLTE (4G calling) for Israeli networks.

**[Download the latest release](../../releases/latest)**

## What you get

| | LTE, EU bands | LTE, US bands | LTE total | 3G | 2G |
|---|---|---|---|---|---|
| Qin F21 | B1, B3, B5, B7, B8, B20, B28, B34, B38, B39, B40, B41 | B2, B4, B12, B13, B17, B66, B71 | 19 | B1, B5, B8 | GSM900, DCS1800 |
| Tiq M5 | B1, B3, B5, B7, B8, B20, B28, B38, B39, B40, B41 | B2, B4, B5, B7, B12, B13, B17, B29, B66, B71 | 20 | B1, B2, B5, B8, TD-SCDMA | GSM850, GSM900, DCS1800, PCS1900 |

## Install

### Qin F21: the app (easiest)

Needs a Qin F21 Pro from before v3, rooted with Magisk.

1. Download `F21DuoBands.apk` from the release and install it.
2. Open it, grant root when Magisk asks, and press **Install**.
3. Wait about 30 seconds without touching the phone. It reboots by itself.

It keeps your IMEI and your Bluetooth and Wi-Fi addresses, sets up VoLTE for Israeli networks, and refuses to run on any phone that doesn't have the F21 Pro's partition layout. The app doesn't make a backup, so back up `md1img_a`, `nvdata` and `nvram` first if you want a way back.

### Fastboot (Qin F21 or Tiq M5)

(This doesn't do what the app does on top: it won't keep your IMEI and addresses, and it won't set up VoLTE in Israel.)

Back up your current `md1img`, `nvdata` and `nvram` first.

Flashing `nvdata` and `nvram` replaces the phone's IMEI, Bluetooth MAC and Wi-Fi MAC with placeholder ones. Write yours down or back them up with [mtk-imei-switcheroo-app](https://github.com/flipphoneguy/mtk-imei-switcheroo-app) before flashing, then restore them with the same app afterwards.

Download the three files for your phone (prefixed `f21-` or `m5-`) and, from fastboot, on the active slot:

```sh
# F21 shown; the M5 is the same with the m5- files
fastboot flash md1img_a f21-md1img_a.duo.signed.bin
fastboot flash nvdata f21-nvdata.duo.img
fastboot flash nvram f21-nvram.duo.bin
fastboot reboot
```

## VoLTE in Israel

On the F21, calls in Israel usually drop to 3G because VoLTE never switches on. Two things block it. The phone's software turns VoLTE off for networks it doesn't know, and the modem has no IMS profile for most Israeli operators. The firmware fixes the modem side by listing Partner, Cellcom, Hot, 425-09 and 019 in the modem's operator table. The app fixes the phone side, by turning that blocking switch off and adding the IMS APN for those operators. Both only change things for Israeli SIMs, so a SIM from anywhere else behaves as before.

VoLTE also depends on your SIM plan having it enabled.

## Problems?

- **No service or "emergency calls only" after flashing with fastboot:** check the IMEI (`*#06#`) and restore yours with mtk-imei-switcheroo-app.
- **The app says the partition layout doesn't match:** it's not an F21 Pro from before v3 (or the partition table was changed). It didn't write anything.
- **The app stopped with an error:** the screen says whether anything was written, and the full log is in the app.

Ask on the [jtech forums thread](https://forums.jtechforums.org/t/10675).

## How it works

By comparing a working EU set against a working US set for the same phone, every place that decides band support was located: the band list, the per-slot RF routing and MIPI tables, calibration, power rules, and the carrier layer. The F21 duo is built on the US set and adds the EU bands into its empty slots. The M5 duo is built on the EU set and adds the US bands. Every edit keeps its size, so partition layouts are unchanged. The changes span `md1img` (the modem program `md1rom`: band list, RF routing, MIPI tables, PA control, power-rule defaults, and on the F21 the operator table) and `nvdata` (band indicator, per-slot calibration, MPR/A-MPR, MIPI bypass, self-calibration, and on the F21 the 3G B5 setup), plus the NVRAM backup.

The stock md1img chains to the public kaios test key from mtkclient, not a MediaTek production key, so after patching `md1rom` the cert chain is rebuilt to that same test root. The app writes the partitions from the running phone, using the eMMC write-protect trick from f21_bands_swap. The full write-up is in `docs/`.

| File | Contents |
|---|---|
| `docs/01-basics.md` | bands, the RF hardware chain, and how MediaTek modem firmware and NVRAM are laid out |
| `docs/02-qin-f21.md` | Qin F21: full EU-vs-US firmware comparison |
| `docs/03-m5.md` | M5: full EU-vs-US firmware comparison |
| `docs/04-f21-duo.md` | Qin F21 duo build: every change, the offline checks, and signing |
| `docs/05-m5-duo.md` | M5 duo build: every change and the offline checks |
| `docs/06-f21-volte.md` | Qin F21: what blocks VoLTE in Israel, the community fixes, and what this build does |
| `app/README.md` | the F21 Duo Bands app: what it does, step by step, and how to build it |

## Building it yourself

Needs Python with `cryptography`, and `e2fsprogs` (`e2fsck`, `debugfs`) for the ext4 steps. The stock firmware tars go in `tmp/tars/` as `{phone}-{eu,us}.tar.xz`. They, the extracted firmware and the built images stay out of git (`tmp/` and `duobands/` are ignored).

```sh
# one-time: unpack tmp/tars/*.tar.xz into tmp/{f21,m5}/{eu,us}/...
python3 scripts/setup_firmware.py

# per phone (f21 shown); the build/verify-stage scripts run from the work dir
mkdir -p tmp/f21_duo && cd tmp/f21_duo
python3 ../../scripts/f21/build_md1rom.py
python3 ../../scripts/f21/build_nvdata.py
cd ../..
python3 scripts/build_backup.py f21          # must run before verify_all
cd tmp/f21_duo
python3 ../../scripts/f21/verify_md1rom.py
python3 ../../scripts/f21/verify_all.py
cd ../..
python3 scripts/resign.py f21
python3 scripts/verify_signed.py f21

# the F21 app, from the verified F21 images
python3 scripts/build_app_assets.py
cd app && ./build.sh
```

`verify_md1rom.py` and `verify_all.py` re-derive every change from the EU and US firmware and print `ALL PASS`; `verify_signed.py` re-parses the signed image and walks the chain to the kaios root. The built images land in `tmp/{phone}_duo/`, and `duobands/{phone}/` holds copies of them.

```
docs/        the analysis and build write-ups (start at 01-basics.md)
scripts/     the build and verification scripts
  lib/       shared helpers (sdec, binregion, split_md1img, ext4blocks)
  f21/       per-phone build + verify for the F21
  m5/        per-phone build + verify for the M5
app/         the F21 Duo Bands app
keystore/    the public kaios test key (from mtkclient), used by resign.py
```

## Credits

- **ys770** for building the F21 duo on the US set, which is how the F21 build is made.
- **The-curious** for the F21 VoLTE patch for Israel that the VoLTE fix follows, and for the F21 used for testing.
- **farrict** for testing the M5 build.
- **ars18** for the eMMC write-protect trick in f21_bands_swap that the app uses to write the partitions live.
