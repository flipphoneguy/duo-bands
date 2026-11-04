# M5 duo-band build (EU + US LTE)

A modem firmware set for the M5 that keeps every EU band and adds the US-only LTE bands. It's built from the two M5 sets described in `03-m5.md`, using the same method as the F21 duo (`04-f21-duo.md`, which explains the method and the background facts in more detail).

**Status: built and checked offline, never run on a phone.** The focus is 4G. 3G and 2G are left as in the EU set.

## What's in it

All built images are in `duobands/m5/`.

| Output | What it is |
|---|---|
| `md1img_a.duo.bin` | EU modem image, `md1rom` patched, certs left as EU (unsigned) |
| `md1img_a.duo.signed.bin` | the same image re-signed to the kaios test root |
| `nvdata.duo.img` | EU nvdata partition with 16 files patched |
| `nvram.duo.bin` | EU nvram backup partition, rebuilt from the duo backup (`AllMap` + `AllFile`) with a valid checksum |
| nvcfg | not changed (use the EU one) |

LTE bands, by slot:

| Slots | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | **12** | **13** | **14** | **15** | **16** | **17** | **18** | **19** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Band | B1 | B3 | – | B5 | B7 | B8 | B20 | B28 | B38 | B39 | B40 | B41 | **B2** | **B4** | **B12** | **B13** | **B17** | **B29** | **B66** | **B71** |

- US B5 and B7 weren't added: EU already has them, on identical paths (`03-m5.md`).
- **3G:** stays EU (B1, B2, B5, B8). US 3G B4 is not included.
- **2G:** stays EU (all four GSM bands, which covers US GSM850/PCS1900).
- **TD-SCDMA:** stays, since the EU build includes it.

## What's different from the F21 duo

- **Same modem version in both sets (V255):** EU and US use the same record layouts and signing keys, which makes pairing tables simpler.
- **B29 is download-only.** It has no transmitter, which affects several places:
  - its TX route says "not used"
  - its TX calibration records stay empty, as in the US set
  - in four transmit-side pointer tables, the US build points B29 at its "empty" entry, so the duo points it at EU's empty entry
  - the self-calibration lists treat it differently (next point)
- **Receive and transmit positions differ.** The self-calibration lists are ordered by filled slots, but the transmit list skips B29. `EL91` (IIP2) stores both positions. US B66 has (8, 7) in the US set, and (17, 16) in the duo.
- **More new data, less space:** in the M5, the TX MIPI events and two antenna tables have US-specific data, and the only free gap proven safe is smaller (12,968 bytes at `0x1284d58`–`0x1288000`, between the NVRAM descriptor table and code, with no pointers into it). The PA control data therefore only fits with its main half (see below).

## md1rom changes (366 writes, 4,435 bytes changed, 11,360 bytes of new arrays)

| What | EU md1rom location | Change |
|---|---|---|
| Band list (2 copies) | `0x1213cc4`, `0x1265624` | slots 12–19 = 2, 4, 12, 13, 17, 29, 50, 55 |
| CA support flags (2 copies) | `0x1213ca8`, `0x1265608` | slots 12–19 = 1 |
| Per-slot "2" flags (2 copies) | `0x121357c`, `0x126556c` | slots 12–19 = 2 |
| TX / RX route tables | `0x127c734` / `0x127ce54` | entries 12–19 = US entries, MIPI index set to own slot |
| 14 per-slot tables (2 blocks of 7) | block 1 `0x1212954`–`0x1213a90`, block 2 `0x12647e8`–`0x1266468` | entries 12–19 = US entries |
| Per-slot 112-byte antenna table | `0x127b694` | entries 12–19 = US entries, keeping EU's slot number at the end |
| A-MPR default | `0x126596c` | rows 4–7 = US rows (B2, B4, B13, B66) |
| 10 per-route pointer tables | `0x127a3f0`–`0x127ae1c` | routes 12–19 point at US data or EU-equivalent data |
| PA control (`MIPI_PA_TPC_SECTION_DATA`) | `0x127a190` (12-byte entries: normal half, CCA half) | routes 12–16, 18, 19: normal half = US data (920 B), CCA half = EU empty entry. B29 (route 17): whole entry EU empty (no TX) |
| New arrays | free gap from `0x1284e60` | TX MIPI data and events, RX MIPI data, two antenna MIPI tables, PA control main halves |
| Calibration defaults (RX gain `0x127b1ec`, TX `0x127b2ec`, `0x127b4c0`) | | **not added**: routes 12–19 keep EU's empty entry |

The 14 per-slot tables have entry sizes 42, 34, 38, 24, 24, 20 and 2 (band list) in each block. The 34-byte one fits `TX_MC_VCC_IDX_OFS` (850 ÷ 25).

**Pointer tables:** routes 12–19 resolve to US data in one of three ways:
- **reuse** an EU array where the US bytes are identical
- **EU empty entry** where US used its empty entry (B29 in transmit tables)
- **new array** otherwise (duplicates stored once)

**PA control, CCA half:** each PA control record has a normal half and a half used only for contiguous uplink carrier aggregation (CCA). Both halves for all 7 transmitting US bands would need 12.9 KB on top of the MIPI arrays, more than the gap holds. No uplink carrier aggregation is set up for the new bands (EU's CA linkage is kept, and it doesn't cover them), so the CCA half points at EU's empty entry. If the modem ever used CCA on a US band, it would find no PA commands for it.

**Calibration defaults** aren't added, for the same reason as on the F21 (`04-f21-duo.md`): they're fallbacks used only if nvdata calibration is missing, the duo's nvdata carries real calibration for every US band, and there's no safe space for them.

**Left as EU on purpose:**
- the generic band table
- the two band-independent pointer tables `0x127d938`/`0x127da28` (identical in EU and US for every route)
- the per-slot rows at `0x1213598` and `0x1213140` (identical in EU and US)
- EU's carrier-aggregation route entries
- 2G/3G defaults and TD-SCDMA data
- the split-band table (US lists its bands with zero splits, which equals not listing them)

## nvdata changes (16 files, 50 records)

| File | Record | Change |
|---|---|---|
| `CALIBRAT/EL03_001` | band indicator | slots 12–19 = new bands |
| `CALIBRAT/EA10_001` | RX calibration (per slot) | records 12–19 = US (B29 included) |
| `CALIBRAT/EA40_001`, `EA50_001` | TX calibration (per slot) | records 12–16, 18, 19 = US; B29's slot 17 stays empty |
| `NVD_DATA/EL01_001`, `EL0K_000`, `EL5C_000` | MPR, MPR CA, MPR HPUE CA (per slot) | rows 12–19 = US rows |
| `NVD_DATA/EL02_001` | A-MPR | rows 4–7 = US rows |
| `CALIBRAT/EL75_000`–`EL79_000` | MIPI bypass (per slot) | entries 12–19 = US entries |
| `CALIBRAT/EL90_001` | RX self-cal (receive list) | records 11–18 = US B2, B4, B12, B13, B17, B29, B66, B71 |
| `CALIBRAT/EL92_001` | TX self-cal (transmit list) | records 11–17 = US B2, B4, B12, B13, B17, B66, B71 |
| `CALIBRAT/EL91_001` | IIP2 self-cal | records 4–6 = B2 (11, 11), B4 (12, 12), B66 (17, 16) |

`EL93` (EU B40/B41 only) and `EL04` (CA linkage) stay EU. US-side carrier aggregation isn't merged.

**Backup:** as on the F21, the 12 backed-up copies inside `AllFile` were replaced with the duo versions, the `AllMap` checksum was recomputed (`0x125bdd2b` → `0xe9034482`), and `nvram.duo.bin` holds the same `AllMap` and `AllFile`. The M5 EU set's original backup was valid and consistent in all copies.

## Verified (offline)

**md1rom (27 checks):**
- same size, every changed byte inside a logged write, all writes inside the RF area or the gap
- `CHECK_HEADER` untouched
- both band lists correct
- route tables decode with the M5 dictionary, MIPI index = slot for all 25 entries
- new route entries equal the US ones apart from the MIPI index, and EU entries 0–11 are unchanged
- B29 has no TX output
- every pointer table: routes 12–19 resolve to the US bytes (or to EU's empty entry where US used empty), and routes 0–11 are unchanged
- PA control: normal halves byte-identical to US, CCA halves EU empty, B29 fully EU empty, routes 0–11 unchanged
- the calibration default tables still point routes 12–19 at EU's empty entry
- A-MPR rows correct

**md1img, nvdata, nvram (98 checks):**
- md1img same size, splits back into the patched md1rom, all other parts identical to EU
- `e2fsck` clean
- the 16 edited files match the intended content, all 266 other files byte-identical to EU, inode metadata unchanged
- every record checksum valid, LDI headers unchanged
- band indicator, calibration slots (with B29's TX left empty), the order of both self-cal lists, and the IIP2 indexes correct
- backup: `AllMap` checksum valid, only the checksum changed in `AllMap`, the 12 backed-up files equal the live duo files, nothing else changed in `AllFile`, and the nvram image holds exactly the duo `AllMap` and `AllFile`

The builders also asserted that every target was empty and that the free gap was all zeros before writing.

## Scripts and outputs

Build and verification scripts: `scripts/m5/` (`build_md1rom.py`, `build_nvdata.py`, `verify_md1rom.py`, `verify_all.py`) and `scripts/` (`build_backup.py`, `resign.py`, `verify_signed.py`), with shared helpers in `scripts/lib/`. Built images: `duobands/m5/` (`md1img_a.duo.signed.bin`, `md1img_a.duo.bin`, `nvdata.duo.img`, `nvram.duo.bin`).
