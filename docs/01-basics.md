# Phone bands and MediaTek modem firmware: the basics

This file explains every term and idea needed to read the device notes (`02-qin-f21.md`, `03-m5.md`, `04-f21-duo.md`, `05-m5-duo.md`). It's general background and has no device findings in it.

## Part 1: radio and bands

### Frequency

Radio signals are waves, and frequency is how many times per second the wave repeats. It's measured in MHz (millions per second) or GHz (thousands of MHz). Phones use roughly 600 MHz to 6 GHz.

- **Lower frequencies** (600 to 900 MHz) travel far and get through walls well, but carry less data.
- **Higher frequencies** (1.7 GHz and up) carry more data but don't reach as far.

That's why carriers use a mix of low and high bands.

### Why the government is involved

Two transmitters on the same frequency in the same place drown each other out. So every country's government decides who may use which frequency range: TV, police, aircraft, GPS, Wi-Fi, mobile carriers and so on. Carriers buy rights to their ranges, usually at auctions. Every phone has to be tested and approved (FCC in the US, CE in Europe) to show it only transmits where it's allowed, at safe power.

### Bands

A **band** is a numbered frequency range set aside for mobile phones. The numbers are defined worldwide by **3GPP**, the standards body for mobile networks. For example:

| Band | Downlink (tower to phone) | Uplink (phone to tower) | Used mainly in |
|---|---|---|---|
| B3 | 1805–1880 MHz | 1710–1785 MHz | Europe, Asia |
| B20 | 791–821 MHz | 832–862 MHz | Europe |
| B12 | 729–746 MHz | 699–716 MHz | US |
| B71 | 617–652 MHz | 663–698 MHz | US |
| B40 | 2300–2400 MHz (shared) | same | Asia |

- **Downlink (DL)** is what the phone receives. **Uplink (UL)** is what the phone sends.
- **FDD** (frequency division duplex): separate frequency ranges for sending and receiving, used at the same time. Most bands are FDD.
- **TDD** (time division duplex): one range, with the phone and tower taking turns very quickly. B33 to B53 are TDD.
- **SDL** (supplemental downlink): download only, no uplink at all (such as B29, B32, B67, B69 and B252 to B255). These only work alongside another band.

Bands overlap. B4 and B66 both receive around 2110 MHz, and B12, B17 and B13 all sit around 700 MHz. A part built for one band can sometimes pass a neighbouring one.

### Generations and their band names

- **2G (GSM)** names bands by frequency: GSM850, GSM900 (also called EGSM900), DCS1800, PCS1900.
- **3G (UMTS/WCDMA)** uses numbered bands like LTE, written "UMTS Band 1". Engineer Mode on MediaTek phones also uses names: IMT-2000 = B1, PCS-1900 = B2, CLR-850 = B5, GSM-900 = B8.
- **4G (LTE)** uses numbered bands B1, B2, B3, and so on.
- **5G (NR)** uses n-numbers (n71, n78). Neither phone in these notes has 5G.

### Channel numbers (EARFCN)

Inside a band, a carrier uses a specific frequency, and LTE refers to it by a channel number called the **EARFCN**. Each band has an offset, and the frequency is `band's lowest frequency + 0.1 MHz × (EARFCN − offset)`. Example: B3 downlink starts at 1805 MHz with offset 1200, so EARFCN 1300 = 1805 + 0.1 × 100 = 1815 MHz.

### Networks: PLMN, MCC, MNC

Every mobile network has an ID called the **PLMN**, made of a country code (**MCC**) plus a network code (**MNC**). 310-260 is T-Mobile US. The SIM card says which network it belongs to, and the modem can change its behaviour based on that.

## Part 2: the hardware inside a phone

```
 SIM ─┐
      │   ┌──────────────── SoC (main chip) ─────────────┐
      └──►│  CPU (runs Android)   Modem (runs MOLY)     │
          └──────────────────────────┬───────────────────┘
                                     │ digital signal
                             ┌───────▼────────┐
                             │  Transceiver   │  turns data into radio waves and back
                             │  (MT6177M)     │  inputs: PRX1–10, DRX1–10
                             └──┬──────────┬──┘  outputs: LB1, LB2, MB1, MB2, HB1
                   transmit ►   │          │   ◄ receive
                             ┌──▼──────────▼──┐
                             │   Front end    │  amplifiers, filters, duplexers, switches
                             └──┬──────────┬──┘
                        main antenna     second (diversity) antenna
```

### SoC and modem

The **SoC** (system on chip) is the main chip. The ones in these notes are MediaTek MT6761 (Helio A22) and MT6768 (Helio G85 family). Inside it is a separate processor, the **modem** (also called the baseband), which does all the cellular work. It runs its own operating system, separate from Android. MediaTek's modem OS is called **MOLY**.

### Transceiver

A separate chip next to the SoC that converts between the modem's digital data and actual radio frequencies. Both phones in these notes use the **MT6177M**. It has numbered connection points (ports):

- **PRX1 to PRX10**: ten main receive inputs, fed from the main antenna
- **DRX1 to DRX10**: ten diversity receive inputs, fed from the second antenna (two antennas give better reception)
- **LB1, LB2**: low-band transmit outputs (roughly 600 to 960 MHz)
- **MB1, MB2**: mid-band transmit outputs (roughly 1.7 to 2.2 GHz)
- **HB1**: high-band transmit output (roughly 2.3 to 2.7 GHz)

The transceiver itself covers a wide frequency range. What decides which bands actually work is the front end.

### Front end

The parts between the transceiver and the antennas:

- **Power amplifier (PA)**: boosts the outgoing signal so it reaches the tower.
- **LNA** (low noise amplifier): boosts the weak incoming signal. The transceiver's PRX/DRX inputs contain LNAs, which is why firmware calls them "LNA ports".
- **Filter**: lets only a certain frequency range through. Filters are built for specific frequencies, and they're usually what limits which bands a phone can use.
- **Duplexer**: a pair of filters that lets an FDD band send and receive at the same time, keeping the two apart.
- **Antenna switch**: picks which filter path is connected to the antenna for the current band.

The firmware controls these parts in two ways:
- **Control pins (BPI)**: the modem sets output pins high or low to flip switches. MediaTek's firmware stores these pin patterns as **PDATA** values (fields named `pr0`, `pr1`… for receive and `pt0`, `pt1`… for transmit).
- **MIPI RFFE**: a small control bus. The modem sends commands over it (a device ID, a register address and a value) to front-end chips. Firmware stores lists of these commands per band.

A path through the front end only works for a band if its filters pass that band's frequencies.

### Calibration

No two radio chips come off the production line identical. At the factory, every single phone goes on a test machine that measures it on each band and stores correction values, such as "on this band, use setting X to get exactly 23 dBm out". These values are unique to that unit. Without them, the phone transmits too loud or too quiet and misjudges signal strength. Calibration only exists for bands the factory set up and tested.

### Power rules: MPR and A-MPR

- **MPR** (maximum power reduction): how much the phone must lower its maximum power when using certain modulation types. It's defined per band.
- **A-MPR** (additional MPR): extra power cuts that some bands need when the network asks for them, to protect neighbouring frequencies. The network sends an "NS" value that tells the phone which A-MPR rule to apply. US bands such as B13 have strict A-MPR rules.

### DPD

Digital predistortion: a technique that pre-shapes the signal so the power amplifier's output stays clean. It has nothing to do with which bands are enabled.

## Part 3: how the modem firmware is stored

A MediaTek phone keeps modem-related data in several partitions (named sections of the phone's storage).

### md1img: the modem firmware image

The `md1img` partition (two copies on A/B phones, `md1img_a` and `md1img_b`) is a container holding several parts one after another. Each part starts with a 512-byte header beginning with the magic bytes `88 16 88 58`, followed by the part's size and name. The parts:

| Part | What it is |
|---|---|
| `md1rom` | The modem program (MOLY) plus all its built-in data and default settings. This is the big one. |
| `md1dsp` | Firmware for the modem's signal-processing core. |
| `md1drdi` | Space for alternative per-board radio settings (DRDI). Can be empty. |
| `cert1`, `cert1md`, `cert2` | Signature certificates. They let the phone check that the firmware is genuine. |
| `md1_filter*`, `md1_emfilter` | Settings for the modem's debug logging. |
| `md1_mddb`, `md1_mddbmeta` | Debug databases used by MediaTek's log tools. |
| `md1_mddbmetaodb` | A gzip-compressed XML file describing every NVRAM record (see below). It's the decoder key for NVRAM. |
| `md1_mdmlayout` | Text describing log message layouts. |
| `md1_file_map` | A small text list of the original filenames of these parts. |

The build name inside `md1rom` describes the build. For example `TK_MD_BASIC/LWG_AGO1_6177M_T_R3_6761` means MediaTek's base modem project (`TK_MD_BASIC`), supporting LTE + WCDMA + GSM (`LWG`), with the 6177M transceiver, on the MT6761. `LWTG` adds TD-SCDMA (a Chinese 3G system).

### NVRAM: saved settings and calibration

MediaTek's modem keeps settings in **NVRAM records**. Each record type has:

- a numeric ID called the **LID** (for example 60436)
- a name (for example `NVRAM_EF_EL1_BAND_INDICATOR_LID`)
- a layout (which fields it has and their sizes)
- a version number and a record count

The name prefix shows which part of the modem it belongs to:

| Prefix | Meaning |
|---|---|
| `EL1` | LTE radio layer ("E" for E-UTRA, the LTE radio) |
| `UL1` | 3G radio layer |
| `L1` (without E or U) | 2G radio layer |
| `MML1` | Common radio parts shared by all generations |
| `ERRC`, `EMM` | LTE network protocol layers |
| `SBP` | Carrier customisation (see below) |

**Where records are stored.** The `nvdata` partition is an ext4 filesystem. Records live as files under `md/NVRAM/`, in these folders:

| Folder | Holds |
|---|---|
| `CALIBRAT` | Calibration and core radio setup |
| `NVD_DATA` | Settings and learned data (networks seen, APNs, …) |
| `NVD_IMEI` | IMEI and related identity data |
| `NVD_CORE` | Internal bookkeeping |
| `BACKUP` | Backup lists |

**Filenames** look like `EL03_001`: a four-character code, then the record version. The code itself doesn't say which record it is. The header inside the file does.

**File format.** Every record file starts with a 64-byte header:

```
4c 44 49 00   "LDI"      magic
xx xx         LID        which record type this is
xx xx         count      number of records
xx xx xx xx   size       bytes per record
...                      other header fields
```

After the header come the records. Each one is followed by an 8-byte checksum.

**Defaults.** If a record has no file in nvdata, the modem uses the default value built into `md1rom`. So a setting can live in two places: the built-in default in md1rom, and a saved copy in nvdata that overrides it. Some records are never saved to nvdata at all, and for those the md1rom copy is the only one.

**Encryption.** Most records are plain data. A few sensitive ones (IMEI, barcode, SBP settings) are encrypted with AES-128-ECB. The key is a fixed MediaTek key that public tools already use (it's in `mtk-imei-switcheroo-app`).

**The dictionary.** `md1_mddbmetaodb` (from md1img) lists every LID with its name, version and record layout, plus the meaning of every enum (named number). With it, any record file can be decoded into named fields. Each firmware version has its own dictionary.

**Other partitions:**

- `nvram`: a raw backup copy of the calibration records (and IMEI). The phone can restore nvdata from it. The same backup also exists as two files at the top of nvdata, `AllMap` and `AllFile` (see below).

### The NVRAM backup (`AllMap`, `AllFile`, nvram partition)

MediaTek's Android-side NVRAM library (`libnvram.so`) keeps a backup of the calibration and IMEI files, in two identical copies: as `/mnt/vendor/nvdata/AllMap` + `AllFile`, and inside the `nvram` partition.

- **`AllFile`**: all backed-up files packed one after another.
- **`AllMap`**: a 4-byte checksum, two file counts, then one entry per file (type, offset inside `AllFile`, size, full path).
- **`nvram` partition**: `AllMap` size, `AllFile` size, `ff ff ff ff`, then `AllMap` at offset 12 and `AllFile` at offset `0x20000`.

The checksum (read from `NVM_CheckData_OneFile` in `libnvram.so`) works like this:
1. Walk `AllFile` in 4-byte little-endian words.
2. Even-numbered words (0, 2, 4…) are XORed into the running value; odd-numbered words are added.
3. Any 1–3 leftover bytes are added as a zero-padded word.
4. The result is XORed with `AllFile`'s size.

The backup is only read when nvdata needs restoring. Phones run normally even when its checksum doesn't match, which happens after IMEI edits that change `AllFile` without updating `AllMap`.
- `nvcfg`: an ext4 filesystem with non-modem settings: GPS assistance config, battery fuel-gauge data, factory test results.

### Enums: names stored as numbers

Firmware stores names as numbers, and the dictionary maps them back. MediaTek's LTE band numbering is mostly the real band number, but not always. In the MT6761 firmware examined, `LTE_Band66 = 50` and `LTE_Band71 = 55`, because MediaTek's list skips unused numbers. A raw 50 in a band field means B66, not B50.

## Part 4: how band support is organised in MediaTek LTE firmware

### The generic band table

`md1rom` contains a table of every LTE band the modem software knows, with its frequency limits (stored in units of 100 kHz, so 18050 means 1805.0 MHz) and its EARFCN offsets. This table is the same for every phone using that firmware. Knowing a band doesn't mean the phone uses it.

### Slots

The phone's actual LTE setup is a list of **25 slots**. Each slot holds one band, or nothing. Every per-band LTE table is lined up with these slots: slot 3's wiring, slot 3's calibration and slot 3's front-end commands all belong to whichever band is in slot 3.

### The band indicator

Record `NVRAM_EF_EL1_BAND_INDICATOR_LID` (LID 60436) is that 25-slot list: 25 two-byte band numbers. A slot set to 0 is empty.

### Route tables

`NVRAM_EF_EL1_FE_TX_ROUTE_DATABASE_LID` and `NVRAM_EF_EL1_FE_RX_ROUTE_DATABASE_LID` describe the wiring for each slot:

- **TX entry** (48 bytes): band, transmit output (`txio`, such as LB2), power detector input, transmit control pin values (`pt0`–`pt3`), and which MIPI command table to use.
- **RX entry** (68 bytes): band, main receive input (`rxio`, such as PRX5), diversity input (`rxdio`, such as DRX8), receive control pin values (`pr0`–`pr3c`), MIPI command table, and external LNA settings.

### Calibration tables per slot

`NVRAM_EF_EL1_RSSIGAINTBL_TYPE1_LID` (receive gain), `NVRAM_EF_EL1_TXDAC_LID` (transmit power curve) and `NVRAM_EF_EL1_TXPAOCTLEV_LID` (amplifier levels) each hold one record per slot, in slot order.

### 3G and 2G

3G and 2G use their own simpler records:
- 3G: `NVRAM_EF_UL1_3G_RF_PARAMETER_LID` holds which 3G bands sit in which position, with their inputs and outputs.
- 2G: `NVRAM_EF_L1_CUSTOM_BAND_SUPPORT_LID` holds one on/off byte each for GSM850, GSM900, DCS1800 and PCS1900.

### The carrier layer: SBP

**SBP** (single binary platform) is how MediaTek fits many carriers' special rules into one firmware. The rules are named features like `SBP_DISABLE_LTE_BAND_BY_PLMN`, and the firmware picks a set of them based on the SIM's network or an ID set by Android. They can disable bands for certain networks even when the hardware and band list allow them. NVRAM has an SBP record too (`NVRAM_EF_SBP_MODEM_CONFIG_LID`, encrypted).

### Signing

Each md1img part has a matching certificate. On phones with secure boot enforced, the boot chain checks the signature before running the modem. A firmware signed with a different key would then be refused.

## Part 5: talking to the modem

### AT commands

A simple text command language for modems (dating back to 1980s dial-up modems; "AT" stands for "attention"). You send one line and get an answer plus `OK` or `ERROR`. Android's radio daemon (`rild`) talks to the modem this way all the time. Standard commands come from 3GPP (like `AT+CFUN`, radio on/off). MediaTek's own commands start with `AT+E`.

- `AT+CMD?` reads the current value
- `AT+CMD=?` lists what's supported
- `AT+CMD=...` changes something

### AT+EPBSE: band switches as bitmasks

`AT+EPBSE` reads or sets which bands the modem may use. Each group of bands is one number, and each bit of the number is one band:

```
AT+EPBSE=<gsm>,<umts>,<lte 1–32>,<lte 33–64>,<lte 65–96>,...
```

In the LTE fields, bit N of the first field is band N+1, bit N of the second field is band N+33, and so on. Example: `5` is binary `101`, so bits 0 and 2 are set, meaning B1 and B3.

These switches can only narrow down what the band indicator and routes already set up. Turning on a bit for a band with no slot, no route and no calibration does nothing useful.

### Engineer Mode

MediaTek's hidden test app (`com.mediatek.engineermode`, dial `*#*#3646633#*#*`). Its Band Mode screen shows the supported bands as checkboxes, and Telephony → AT Command Tool sends AT commands.

## Part 6: reading the numbers in these notes

- **Hex**: numbers written in base 16, like `0x1103f8c`. Offsets (positions inside a file) are given in hex.
- **Little-endian**: multi-byte numbers are stored lowest byte first. The bytes `6c 52` mean `0x526c` = 21100, which is 2110.0 MHz in 100 kHz units.
- **Bit / bitmask**: a number used as a row of on/off switches, one per bit.
