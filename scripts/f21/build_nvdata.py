#!/usr/bin/env python3
# Build duo-band F21 nvdata and nvram images: EU base plus US LTE records in slots 14-20.
import struct, hashlib, shutil, subprocess, re, json

import os
F21 = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'tmp', 'f21')
EUN, USN = f'{F21}/eu/nvdata/md/NVRAM', f'{F21}/us/nvdata/md/NVRAM'
NEW = list(range(14, 21))
US_BANDS = [2, 4, 12, 13, 17, 50, 55]
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
    e, u = LDI(f'{EUN}/{rel}'), LDI(f'{USN}/{rel}')
    assert e.lid == u.lid and e.size == u.size
    fn(e, u)
    out[rel] = e

# band indicator: one record, 25 x u16
def band_ind(e, u):
    r = bytearray(e.rec(0)); ur = u.rec(0)
    for k, s in enumerate(NEW):
        assert H(r, 2 * s) == 0 and H(ur, 2 * k) == US_BANDS[k]
        r[2 * s:2 * s + 2] = ur[2 * k:2 * k + 2]
    e.setrec(0, bytes(r), 'band indicator slots 14-20')
edit('CALIBRAT/EL03_001', band_ind)

# per-slot calibration records (record index = slot)
def per_slot_records(e, u):
    for k, s in enumerate(NEW):
        assert not any(e.rec(s)), f'{e.lid} rec {s} not empty'
        assert H(u.rec(k), 0) == US_BANDS[k]
        e.setrec(s, u.rec(k), f'slot {s} <- US rec {k}')
for f in ('CALIBRAT/EA10_001', 'CALIBRAT/EA40_001', 'CALIBRAT/EA50_001'):
    edit(f, per_slot_records)

# single-record per-slot row tables: MPR (20 B rows), MPR CA and HPUE CA (24 B rows), MIPI bypass (24 B rows)
def rows(stride):
    def fn(e, u):
        r = bytearray(e.rec(0)); ur = u.rec(0)
        for k, s in enumerate(NEW):
            assert H(r, s * stride) == 0 and not any(r[s * stride:(s + 1) * stride]), f'{e.lid} row {s} not empty'
            assert H(ur, k * stride) == US_BANDS[k]
            r[s * stride:(s + 1) * stride] = ur[k * stride:(k + 1) * stride]
        e.setrec(0, bytes(r), f'rows {stride} B slots 14-20')
    return fn
edit('NVD_DATA/EL01_001', rows(20))
edit('NVD_DATA/EL0K_000', rows(24))
edit('NVD_DATA/EL5C_000', rows(24))
for f in ('CALIBRAT/EL75_000', 'CALIBRAT/EL76_000', 'CALIBRAT/EL77_000', 'CALIBRAT/EL78_000', 'CALIBRAT/EL79_000'):
    edit(f, rows(24))

# A-MPR: compact rows of 52 B, append US rows 0-3 as rows 4-7
def ampr(e, u):
    r = bytearray(e.rec(0)); ur = u.rec(0)
    assert [H(r, i * 52) for i in range(5)] == [1, 20, 28, 41, 0]
    assert [H(ur, i * 52) for i in range(5)] == [2, 4, 13, 50, 0]
    for k in range(4):
        assert not any(r[(4 + k) * 52:(5 + k) * 52])
        r[(4 + k) * 52:(5 + k) * 52] = ur[k * 52:(k + 1) * 52]
    e.setrec(0, bytes(r), 'A-MPR rows 4-7 <- US rows 0-3')
edit('NVD_DATA/EL02_001', ampr)

# self-calibration lists, ordered like the filled slots: EU 0-11 then US 12-18
def compact(first, n_us, band_off):
    def fn(e, u):
        for k in range(n_us):
            assert H(u.rec(k), band_off) == US_BANDS[k]
            e.setrec(first + k, u.rec(k), f'compact rec {first+k} <- US rec {k}')
    return fn
edit('CALIBRAT/EL90_001', compact(12, 7, 980))
edit('CALIBRAT/EL92_001', compact(12, 7, 4))

# IIP2: EU recs 0-3 (rec 0 shared), append US recs 1-3 at 4-6 with the position index moved by 12
def iip2(e, u):
    assert e.rec(0) == u.rec(0)
    for k in (1, 2, 3):
        r = bytearray(u.rec(k))
        band, band2, i1, i2 = struct.unpack_from('<HHHH', r, 4)
        pos = US_BANDS.index(band)
        assert band == band2 and i1 == i2 == pos
        struct.pack_into('<HH', r, 8, 12 + pos, 12 + pos)
        assert not any(e.rec(3 + k))
        e.setrec(3 + k, bytes(r), f'IIP2 rec {3+k} <- US rec {k} (band {band}, index {12+pos})')
edit('CALIBRAT/EL91_001', iip2)

# write into a copy of the journal-replayed EU nvdata image, block by block
shutil.copy(f'{F21}/eu/nvdata.work.img', 'nvdata.duo.img')
img = open('nvdata.duo.img', 'r+b')
m = re.search(r'Block size:\s+(\d+)', subprocess.run(['debugfs', '-R', 'stats', 'nvdata.duo.img'], capture_output=True, text=True).stdout)
assert m, 'could not read block size'
bs = int(m.group(1))
for rel, e in out.items():
    path = f'/md/NVRAM/{rel}'
    blocks = [int(x) for x in subprocess.run(['debugfs', '-R', f'blocks {path}', 'nvdata.duo.img'], capture_output=True, text=True).stdout.split()]
    data = bytes(e.raw)
    assert len(blocks) == (len(data) + bs - 1) // bs, rel
    for i, b in enumerate(blocks):
        img.seek(b * bs); img.write(data[i * bs:(i + 1) * bs])
img.close()

# same records in the nvram backup partition
shutil.copy(f'{F21}/eu/nvram.bin', 'nvram.duo.bin')
nv = bytearray(open('nvram.duo.bin', 'rb').read())
patched_nvram = []
for rel, e in out.items():
    orig = open(f'{EUN}/{rel}', 'rb').read()
    hits = [m.start() for m in re.finditer(re.escape(orig[:64]), nv)]
    if not hits: continue
    assert len(hits) == 1 and nv[hits[0]:hits[0] + len(orig)] == orig, rel
    nv[hits[0]:hits[0] + len(orig)] = e.raw
    patched_nvram.append(rel)
open('nvram.duo.bin', 'wb').write(nv)

for rel, e in out.items():
    open(f'files_{rel.replace("/", "_")}', 'wb').write(e.raw)
json.dump({'records': log, 'nvram_patched': patched_nvram}, open('nvdata_patch_log.json', 'w'), indent=1)
print(f'{len(out)} files edited, {len(log)} records written; nvram copies patched: {len(patched_nvram)} {patched_nvram}')
