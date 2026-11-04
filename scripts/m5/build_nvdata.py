#!/usr/bin/env python3
# Build duo-band M5 nvdata and nvram images: EU base plus 8 US-only LTE bands in slots 12-19.
import struct, hashlib, shutil, subprocess, re, json

import os
M5 = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'tmp', 'm5')
EUN, USN = f'{M5}/eu/nvdata/md/NVRAM', f'{M5}/us/nvdata/md/NVRAM'
NEW = list(range(12, 20))
US_SLOT = [0, 1, 4, 5, 6, 7, 8, 9]          # B2 B4 B12 B13 B17 B29 B66 B71
US_BANDS = [2, 4, 12, 13, 17, 29, 50, 55]
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

def band_ind(e, u):
    r = bytearray(e.rec(0)); ur = u.rec(0)
    for k, s in enumerate(NEW):
        assert H(r, 2 * s) == 0 and H(ur, 2 * US_SLOT[k]) == US_BANDS[k]
        r[2 * s:2 * s + 2] = ur[2 * US_SLOT[k]:2 * US_SLOT[k] + 2]
    e.setrec(0, bytes(r), 'band indicator slots 12-19')
edit('CALIBRAT/EL03_001', band_ind)

def per_slot_records(e, u):
    for k, s in enumerate(NEW):
        assert not any(e.rec(s)), f'{e.lid} rec {s} not empty'
        ur = u.rec(US_SLOT[k])
        if not any(ur):                       # B29 has no TX calibration: leave the slot empty
            assert US_BANDS[k] == 29; continue
        assert H(ur, 0) == US_BANDS[k]
        e.setrec(s, ur, f'slot {s} <- US slot {US_SLOT[k]}')
for f in ('CALIBRAT/EA10_001', 'CALIBRAT/EA40_001', 'CALIBRAT/EA50_001'):
    edit(f, per_slot_records)

def rows(stride):
    def fn(e, u):
        r = bytearray(e.rec(0)); ur = u.rec(0)
        for k, s in enumerate(NEW):
            us_ = US_SLOT[k]
            assert not any(r[s * stride:(s + 1) * stride]), f'{e.lid} row {s} not empty'
            assert H(ur, us_ * stride) == US_BANDS[k]
            r[s * stride:(s + 1) * stride] = ur[us_ * stride:(us_ + 1) * stride]
        e.setrec(0, bytes(r), f'rows {stride} B slots 12-19')
    return fn
edit('NVD_DATA/EL01_001', rows(20))
edit('NVD_DATA/EL0K_000', rows(24))
edit('NVD_DATA/EL5C_000', rows(24))
for f in ('CALIBRAT/EL75_000', 'CALIBRAT/EL76_000', 'CALIBRAT/EL77_000', 'CALIBRAT/EL78_000', 'CALIBRAT/EL79_000'):
    edit(f, rows(24))

def ampr(e, u):
    r = bytearray(e.rec(0)); ur = u.rec(0)
    assert [H(r, i * 52) for i in range(5)] == [1, 20, 28, 41, 0]
    assert [H(ur, i * 52) for i in range(5)] == [2, 4, 13, 50, 0]
    for k in range(4):
        assert not any(r[(4 + k) * 52:(5 + k) * 52])
        r[(4 + k) * 52:(5 + k) * 52] = ur[k * 52:(k + 1) * 52]
    e.setrec(0, bytes(r), 'A-MPR rows 4-7 <- US rows 0-3')
edit('NVD_DATA/EL02_001', ampr)

# self-cal lists. RX list: EU 11 bands (0-10), then the 8 new bands. TX list: same, without B29.
def compact(src_recs, first, band_off, bands):
    def fn(e, u):
        for j, (ui, b) in enumerate(zip(src_recs, bands)):
            assert H(u.rec(ui), band_off) == b, (e.lid, ui, H(u.rec(ui), band_off))
            e.setrec(first + j, u.rec(ui), f'compact rec {first+j} <- US rec {ui} (band {b})')
    return fn
edit('CALIBRAT/EL90_001', compact([0, 1, 4, 5, 6, 7, 8, 9], 11, 980, [2, 4, 12, 13, 17, 29, 50, 55]))
edit('CALIBRAT/EL92_001', compact([0, 1, 4, 5, 6, 7, 8], 11, 4, [2, 4, 12, 13, 17, 50, 55]))

# IIP2: append B2, B4, B66 with (RX position, TX position) in the duo lists
def iip2(e, u):
    assert e.rec(0) == u.rec(0)
    want = {2: (11, 11), 4: (12, 12), 50: (17, 16)}
    dst = 4
    for k in range(1, u.n):
        r = bytearray(u.rec(k))
        if not any(r): continue
        band = H(r, 4)
        if band not in want: continue          # B7 is already in the EU list
        struct.pack_into('<HH', r, 8, *want[band])
        assert not any(e.rec(dst))
        e.setrec(dst, bytes(r), f'IIP2 rec {dst} <- US rec {k} (band {band}, index {want[band]})')
        dst += 1
    assert dst == 7
edit('CALIBRAT/EL91_001', iip2)

shutil.copy(f'{M5}/eu/nvdata.work.img', 'nvdata.duo.img')
img = open('nvdata.duo.img', 'r+b')
m = re.search(r'Block size:\s+(\d+)', subprocess.run(['debugfs', '-R', 'stats', 'nvdata.duo.img'], capture_output=True, text=True).stdout)
assert m, 'could not read block size'
bs = int(m.group(1))
for rel, e in out.items():
    blocks = [int(x) for x in subprocess.run(['debugfs', '-R', f'blocks /md/NVRAM/{rel}', 'nvdata.duo.img'], capture_output=True, text=True).stdout.split()]
    data = bytes(e.raw)
    assert len(blocks) == (len(data) + bs - 1) // bs, rel
    for i, b in enumerate(blocks):
        img.seek(b * bs); img.write(data[i * bs:(i + 1) * bs])
img.close()

shutil.copy(f'{M5}/eu/nvram.bin', 'nvram.duo.bin')
nv = bytearray(open('nvram.duo.bin', 'rb').read())
patched_nvram = []
for rel, e in out.items():
    orig = open(f'{EUN}/{rel}', 'rb').read()
    hits = [mm.start() for mm in re.finditer(re.escape(orig[:64]), nv)]
    if not hits: continue
    assert len(hits) == 1 and nv[hits[0]:hits[0] + len(orig)] == orig, rel
    nv[hits[0]:hits[0] + len(orig)] = e.raw
    patched_nvram.append(rel)
open('nvram.duo.bin', 'wb').write(nv)
for rel, e in out.items():
    open(f'files_{rel.replace("/", "_")}', 'wb').write(e.raw)
json.dump({'records': log, 'nvram_patched': patched_nvram}, open('nvdata_patch_log.json', 'w'), indent=1)
print(f'{len(out)} files edited, {len(log)} records written; nvram copies patched: {len(patched_nvram)}')
