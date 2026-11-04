# duo-bands

One modem firmware per phone that carries both the EU and the US LTE bands, for the Qin F21 and the M5.

**[Download the latest images](../../releases/latest)**

Each phone ships in regional variants with the same radio hardware but firmware that enables a different set of bands. Each duo build keeps the EU set intact and adds the US-only bands, so one firmware exposes both.

| | EU set | US-only additions | Duo total |
|---|---|---|---|
| Qin F21 | B1, B3, B5, B7, B8, B20, B28, B34, B38, B39, B40, B41 | B2, B4, B12, B13, B17, B66, B71 | 19 |
| M5 | B1, B3, B5, B7, B8, B20, B28, B38, B39, B40, B41 | B2, B4, B12, B13, B17, B29, B66, B71 | 20 |

The M5 build also keeps the EU set's 3G, 2G and TD-SCDMA; US 3G B4 is the only US radio not merged.

A release carries, per phone: `md1img_a.duo.signed.bin` (the modem image, re-signed), `md1img_a.duo.bin` (the same image unsigned), `nvdata.duo.img` and `nvram.duo.bin`.

## Flashing

From fastboot, on the active slot. Back up the stock `md1img`, `nvdata` and `nvram` first.

```sh
fastboot flash md1img_a md1img_a.duo.signed.bin
fastboot flash nvdata nvdata.duo.img
fastboot flash nvram nvram.duo.bin
fastboot reboot
```

Flashing `nvdata` replaces the IMEI and calibration with the build's.

## How it works

By comparing a working EU set against a working US set for the same phone, every place that decides band support was located: the band list, the per-slot RF routing and MIPI tables, calibration, power rules, and the carrier layer. The US-only bands go into the EU set's empty slots, with every edit kept the same size so partition layouts are unchanged. The changes span `md1img` (the modem program `md1rom`: band list, RF routing, MIPI tables, PA control, power-rule defaults) and `nvdata` (band indicator, per-slot calibration, MPR/A-MPR, MIPI bypass, self-calibration), plus the NVRAM backup.

The stock md1img chains to the public kaios test key from mtkclient rather than a MediaTek production key, so patching `md1rom` is followed by rebuilding the cert chain to the same test root. The full write-up, including the EU-vs-US comparison and the offline checks, is in `docs/` (start at `01-basics.md`).

## Layout

```
docs/        the analysis and build write-ups (start at 01-basics.md)
scripts/     the build and verification scripts
  lib/       shared helpers (sdec, binregion, split_md1img)
  f21/       per-phone build + verify for the F21
  m5/        per-phone build + verify for the M5
  setup_firmware.py   unpacks the tars into the tree the scripts read
  build_backup.py     rebuilds the NVRAM backup (AllFile/AllMap + nvram)
  resign.py           re-signs the duo md1img to the test root
  verify_signed.py    walks the re-signed cert chain
keystore/    the public kaios test key (from mtkclient), used by resign.py
tmp/         (gitignored) firmware tars, the extracted tree, and build artifacts
duobands/    (gitignored) the built images, per phone
```

The stock firmware tars live in `tmp/tars/` as `{phone}-{eu,us}.tar.xz`. They, the extracted firmware, and the built images stay out of git; the scripts and docs are what is tracked.

## Reproducing

Needs Python with `cryptography`, and `e2fsprogs` (`e2fsck`, `debugfs`) for the ext4 steps.

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
```

`verify_md1rom.py` and `verify_all.py` re-derive every change from the EU and US firmware and print `ALL PASS`; `verify_signed.py` re-parses the signed image and walks the chain to the kaios root. The built images land in `tmp/f21_duo/`; the copies in `duobands/f21/` are the same files.

## Documents

| File | Contents |
|---|---|
| `docs/01-basics.md` | bands, the RF hardware chain, and how MediaTek modem firmware and NVRAM are laid out |
| `docs/02-qin-f21.md` | Qin F21: full EU-vs-US firmware comparison |
| `docs/03-m5.md` | M5: full EU-vs-US firmware comparison |
| `docs/04-f21-duo.md` | Qin F21 duo build: every change, the offline checks, and signing |
| `docs/05-m5-duo.md` | M5 duo build: every change and the offline checks |
