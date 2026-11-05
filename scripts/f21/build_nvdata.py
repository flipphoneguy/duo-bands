#!/usr/bin/env python3
# Build duo-band F21 nvdata and nvram images: US base plus EU LTE records in slots 7-18 and EU 3G B5.
import struct, hashlib, shutil, json, sys

import os
_R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_R, 'scripts', 'lib'))
from ext4blocks import write_file
from sdec import Dict
F21 = os.path.join(_R, 'tmp', 'f21')
USN, EUN = f'{F21}/us/nvdata/md/NVRAM', f'{F21}/eu/nvdata/md/NVRAM'
NEW = list(range(7, 19))
EU_SLOT = [0, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13]
EU_BANDS = [1, 3, 5, 7, 8, 20, 28, 34, 38, 39, 40, 41]
log = []

def mx(b):
    h = hashlib.md5(b).digest()
    return bytes(h[i] ^ h[i + 8] for i in range(8))

class LDI:
    def __init__(self, path):
        self.raw = bytearray(open(path, 'rb').read())
        assert self.raw[:4] == b'LDI\0'
        self.lid, self.n = struct.unpack_from('<HH', self.raw, 4)
        self.size = struct.unpack_from('<I', self.raw, 8)[0]
    def off(self, k): return 0x40 + k * (self.size + 8)
    def rec(self, k): return bytes(self.raw[self.off(k):self.off(k) + self.size])
    def setrec(self, k, data, why):
        assert len(data) == self.size
        o = self.off(k)
        self.raw[o:o + self.size] = data
        self.raw[o + self.size:o + self.size + 8] = mx(data)
        log.append({'lid': self.lid, 'rec': k, 'why': why})

H = lambda b, o: struct.unpack_from('<H', b, o)[0]
out = {}

def edit(rel, fn):
    u, e = LDI(f'{USN}/{rel}'), LDI(f'{EUN}/{rel}')
    assert u.lid == e.lid and u.size == e.size
    fn(u, e)
    out[rel] = u

# band indicator: one record, 25 x u16
def band_ind(u, e):
    r = bytearray(u.rec(0)); er = e.rec(0)
    for k, s in enumerate(NEW):
        assert H(r, 2 * s) == 0 and H(er, 2 * EU_SLOT[k]) == EU_BANDS[k]
        r[2 * s:2 * s + 2] = er[2 * EU_SLOT[k]:2 * EU_SLOT[k] + 2]
    u.setrec(0, bytes(r), 'band indicator slots 7-18')
edit('CALIBRAT/EL03_001', band_ind)

# per-slot calibration records (record index = slot)
def per_slot_records(u, e):
    for k, s in enumerate(NEW):
        assert not any(u.rec(s)), f'{u.lid} rec {s} not empty'
        assert H(e.rec(EU_SLOT[k]), 0) == EU_BANDS[k]
        u.setrec(s, e.rec(EU_SLOT[k]), f'slot {s} <- EU rec {EU_SLOT[k]}')
for f in ('CALIBRAT/EA10_001', 'CALIBRAT/EA40_001', 'CALIBRAT/EA50_001'):
    edit(f, per_slot_records)

# single-record per-slot row tables: MPR (20 B rows), MPR CA and HPUE CA (24 B rows), MIPI bypass (24 B rows)
def rows(stride):
    def fn(u, e):
        r = bytearray(u.rec(0)); er = e.rec(0)
        for k, s in enumerate(NEW):
            es = EU_SLOT[k]
            assert not any(r[s * stride:(s + 1) * stride]), f'{u.lid} row {s} not empty'
            assert H(er, es * stride) == EU_BANDS[k]
            r[s * stride:(s + 1) * stride] = er[es * stride:(es + 1) * stride]
        u.setrec(0, bytes(r), f'rows {stride} B slots 7-18')
    return fn
edit('NVD_DATA/EL01_001', rows(20))
edit('NVD_DATA/EL0K_000', rows(24))
edit('NVD_DATA/EL5C_000', rows(24))
for f in ('CALIBRAT/EL75_000', 'CALIBRAT/EL76_000', 'CALIBRAT/EL77_000', 'CALIBRAT/EL78_000', 'CALIBRAT/EL79_000'):
    edit(f, rows(24))

# A-MPR: compact rows of 52 B, append EU rows 0-3 as rows 4-7
def ampr(u, e):
    r = bytearray(u.rec(0)); er = e.rec(0)
    assert [H(r, i * 52) for i in range(5)] == [2, 4, 13, 50, 0]
    assert [H(er, i * 52) for i in range(5)] == [1, 20, 28, 41, 0]
    for k in range(4):
        assert not any(r[(4 + k) * 52:(5 + k) * 52])
        r[(4 + k) * 52:(5 + k) * 52] = er[k * 52:(k + 1) * 52]
    u.setrec(0, bytes(r), 'A-MPR rows 4-7 <- EU rows 0-3')
edit('NVD_DATA/EL02_001', ampr)

# self-calibration lists, ordered like the filled slots: US 0-6 then EU 7-18 (records past the list keep US's filler)
def compact(first, band_off):
    def fn(u, e):
        for k in range(12):
            assert H(u.rec(first + k), band_off) == 0
            assert H(e.rec(k), band_off) == EU_BANDS[k]
            u.setrec(first + k, e.rec(k), f'compact rec {first+k} <- EU rec {k}')
    return fn
edit('CALIBRAT/EL90_001', compact(7, 980))
edit('CALIBRAT/EL92_001', compact(7, 4))

# IIP2: US recs 0-3 (rec 0 shared), append EU recs 1-3 at 4-6 with the position index = position among filled slots
def iip2(u, e):
    assert u.rec(0) == e.rec(0)
    for k in (1, 2, 3):
        r = bytearray(e.rec(k))
        band, band2, i1, i2 = struct.unpack_from('<HHHH', r, 4)
        pos = EU_BANDS.index(band)
        assert band == band2 and i1 == i2 == pos
        struct.pack_into('<HH', r, 8, 7 + pos, 7 + pos)
        assert not any(u.rec(3 + k))
        u.setrec(3 + k, bytes(r), f'IIP2 rec {3+k} <- EU rec {k} (band {band}, index {7+pos})')
edit('CALIBRAT/EL91_001', iip2)

# 3G B5: EU has it in position LB1 (index 3), which is empty in US. Copy that position, the LB1 front-end records and the B5 calibration.
D = Dict(f'{F21}/us/meta.xml')
def umts_lb1(u, e):
    tn = D.lids[u.lid][1]
    r = bytearray(u.rec(0)); er = e.rec(0)
    for path in ('umtsPdata.rxBpi', 'umtsPdata.txBpi', 'umtsRxLnaPortSel.rxLnaSel', 'umtsTxPathSel.txPathSel'):
        o, s = D.field(tn, path, 3)
        assert r[o] == 0 and er[o] == 5, f'{path}[3]: US band {r[o]}, EU band {er[o]}'
        r[o:o + s] = er[o:o + s]
    o, s = D.field(tn, 'umtsBandIndicator.LB1')
    assert r[o] == 0 and er[o] == 5
    r[o:o + s] = er[o:o + s]
    u.setrec(0, bytes(r), '3G position LB1 <- EU (B5)')
edit('NVD_DATA/UL03_000', umts_lb1)

def copy_all(check):
    def fn(u, e):
        assert u.n == e.n
        for k in range(u.n):
            assert check(u, k), f'{u.lid} rec {k}: US not empty/default'
            u.setrec(k, e.rec(k), f'rec {k} <- EU')
    return fn
empty = lambda u, k: not any(u.rec(k))
for f in ('NVD_DATA/ULM4_000', 'NVD_DATA/ULME_000', 'NVD_DATA/ULMJ_000', 'NVD_DATA/ULMO_000', 'NVD_DATA/ULMT_000', 'NVD_DATA/ULN8_000', 'CALIBRAT/UL15_001', 'CALIBRAT/HL14_001'):
    edit(f, copy_all(empty))
# B5 TXDAC / PA levels / power-on: US holds the uncalibrated default, the same bytes as its B6 file
for f, b6 in (('CALIBRAT/UL1F_000', 'CALIBRAT/UL1G_000'), ('CALIBRAT/UL1Q_000', 'CALIBRAT/UL1R_000'), ('CALIBRAT/ULBU_000', 'CALIBRAT/ULBV_000')):
    dflt = LDI(f'{USN}/{b6}')
    edit(f, copy_all(lambda u, k, dflt=dflt: u.rec(k) == dflt.rec(k)))

# write into a copy of the journal-replayed US nvdata image, block by block
shutil.copy(f'{F21}/us/nvdata.work.img', 'nvdata.duo.img')
for rel, u in out.items():
    write_file('nvdata.duo.img', f'/md/NVRAM/{rel}', bytes(u.raw))

for rel, u in out.items():
    open(f'files_{rel.replace("/", "_")}', 'wb').write(u.raw)
json.dump({'records': log}, open('nvdata_patch_log.json', 'w'), indent=1)
print(f'{len(out)} files edited, {len(log)} records written')
