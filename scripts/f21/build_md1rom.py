#!/usr/bin/env python3
# Build a duo-band F21 md1rom: US md1rom with the 12 EU LTE bands added in slots 7-18, plus the Israeli operators in the modem's operator table.
import struct, json

import os
F21 = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'tmp', 'f21')
B = 0x90000000
du = bytearray(open(f'{F21}/us/md1/md1rom', 'rb').read())
de = open(f'{F21}/eu/md1/md1rom', 'rb').read()
orig = bytes(du)
NEW = list(range(7, 19))                       # duo slots
EU_SLOT = [0, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13]   # EU slots of B1 B3 B5 B7 B8 B20 B28 B34 B38 B39 B40 B41
EU_BANDS = [1, 3, 5, 7, 8, 20, 28, 34, 38, 39, 40, 41]
log = []

H = lambda d, o: struct.unpack_from('<H', d, o)[0]
I = lambda d, o: struct.unpack_from('<I', d, o)[0]

def put(o, data, why):
    assert len(data) > 0
    du[o:o + len(data)] = data
    log.append({'off': hex(o), 'len': len(data), 'why': why})

# 1. per-slot tables, paired US/EU (same order, same stride)
US_T = [(0xf3a024,42),(0xf3a494,42),(0xf3a8b0,80),(0xf3b180,52),(0xf3b694,52),(0xf3bba8,52),(0xf3c0bc,50),(0xf3c5a0,38),(0xf3c9bc,24),(0xf3cc14,24),(0xf3ce6c,20),(0xf3d0a0,2),
        (0xf846e0,42),(0xf84b50,42),(0xf84f6c,52),(0xf85480,52),(0xf85994,52),(0xf85ea8,50),(0xf8638c,38),(0xf86760,80),(0xf87228,2),(0xf87bbc,24),(0xf87e14,24),(0xf8806c,20),(0xf995f8,112)]
EU_T = [(0xf8d64c,42),(0xf8dabc,42),(0xf8ded8,80),(0xf8e7a8,52),(0xf8ecbc,52),(0xf8f1d0,52),(0xf8f6e4,50),(0xf8fbc8,38),(0xf8ffe4,24),(0xf9023c,24),(0xf90494,20),(0xf906c8,2),
        (0xfe46e0,42),(0xfe4b50,42),(0xfe4f6c,52),(0xfe5480,52),(0xfe5994,52),(0xfe5ea8,50),(0xfe638c,38),(0xfe6760,80),(0xfe7228,2),(0xfe7bbc,24),(0xfe7e14,24),(0xfe806c,20),(0xff98f8,112)]
for (up, s), (ep, es) in zip(US_T, EU_T):
    assert s == es
    for k, slot in enumerate(NEW):
        uo, eo = up + slot * s, ep + EU_SLOT[k] * s
        assert H(du, uo) == 0, f'US table {up:#x} slot {slot} not empty'
        assert H(de, eo) == EU_BANDS[k], f'EU table {ep:#x} slot {EU_SLOT[k]} band {H(de,eo)}'
        entry = bytearray(de[eo:eo + s])
        if s == 112:                      # last two u16 are the slot number: keep US's
            assert struct.unpack_from('<HH', entry, 108) == (EU_SLOT[k],) * 2
            entry[108:112] = du[uo + 108:uo + 112]
            assert struct.unpack_from('<HH', entry, 108) == (slot, slot)
        put(uo, bytes(entry), f'per-slot table {up:#x} (stride {s}) slot {slot} <- EU {ep:#x}[{EU_SLOT[k]}]')

# 2. one-byte per-slot flags (CA support flags, and the 2/1 flags), EU value per band
for uf, ef in ((0xf3d084,0xf906ac),(0xf8720c,0xfe720c),(0xf3c958,0xf8ff80),(0xf87170,0xfe7170)):
    for k, slot in enumerate(NEW):
        assert du[uf + slot] == 0 and de[ef + EU_SLOT[k]] != 0
        put(uf + slot, de[ef + EU_SLOT[k]:ef + EU_SLOT[k] + 1], f'flag table {uf:#x} slot {slot} <- EU {ef:#x}[{EU_SLOT[k]}]')

# 3. route tables: copy EU entry, then point it at its own MIPI table (= slot)
for up, ep, s, mi in ((0xf9ada0, 0xffb0a0, 48, 44), (0xf9b4c0, 0xffb7c0, 68, 60)):
    for k, slot in enumerate(NEW):
        uo, eo = up + slot * s, ep + EU_SLOT[k] * s
        assert H(du, uo + 4) == 0 and H(du, uo + mi) == slot, f'route {up:#x} slot {slot} not empty'
        assert H(de, eo + 4) == EU_BANDS[k] and H(de, eo + mi) == EU_SLOT[k]
        entry = bytearray(de[eo:eo + s])
        struct.pack_into('<H', entry, mi, slot)
        put(uo, bytes(entry), f'route table {up:#x} slot {slot} <- EU {ep:#x}[{EU_SLOT[k]}], MIPI idx {slot}')

# 4. A-MPR default: compact rows, append EU rows 0-3 as rows 4-7
UA, EA, RS = 0xf87570, 0xfe7570, 52
us_rows = [H(du, UA + r * RS) for r in range(25)]
eu_rows = [H(de, EA + r * RS) for r in range(25)]
assert us_rows[:5] == [2, 4, 13, 50, 0] and eu_rows[:5] == [1, 20, 28, 41, 0], (us_rows[:6], eu_rows[:6])
for k in range(4):
    assert not any(du[UA + (4 + k) * RS:UA + (5 + k) * RS])
    put(UA + (4 + k) * RS, de[EA + k * RS:EA + (k + 1) * RS], f'A-MPR default row {4+k} <- EU row {k}')

# 5. per-route pointer tables
FREE_LO, FREE_HI = 0xfa2e80, 0xfa7f00
assert not any(du[0xfa2d80:0xfa8000]), 'free gap not zero'
cursor = FREE_LO
placed = {}
def alloc(data):
    global cursor
    if data in placed: return placed[data]
    o = (cursor + 15) & ~15
    assert o + len(data) <= FREE_HI, f'free gap full at {o:#x} (+{len(data)})'
    put(o, data, f'new array ({len(data)} B)')
    cursor = o + len(data)
    placed[data] = o
    return o

PT = [  # (US ptr table, US sizes, EU ptr table, EU sizes, fixed length if unsized)
    (0xf9828c, None, 0xff858c, None, 0x50),
    (0xf98324, 0xf983bc, 0xff8624, 0xff86bc, None),
    (0xf98454, 0xf984ec, 0xff8754, 0xff87ec, None),
    (0xf98584, 0xf9861c, 0xff8884, 0xff891c, None),
    (0xf986b4, 0xf98738, 0xff89b4, 0xff8a38, None),
    (0xf987bc, 0xf98840, 0xff8abc, 0xff8b40, None),
    (0xf98950, 0xf989e8, 0xff8c50, 0xff8ce8, None),
    (0xf98a80, 0xf98b18, 0xff8d80, 0xff8e18, None),
    (0xf98bb0, 0xf98c34, 0xff8eb0, 0xff8f34, None),
    (0xf98cb8, 0xf98d3c, 0xff8fb8, 0xff903c, None),
]
summary = []
for upt, usz, ept, esz, fixed in PT:
    uptr = [I(du, upt + 4 * i) for i in range(25)]
    eptr = [I(de, ept + 4 * i) for i in range(25)]
    usizes = [I(du, usz + 4 * i) for i in range(25)] if usz else [fixed] * 25
    esizes = [I(de, esz + 4 * i) for i in range(25)] if esz else [fixed] * 25
    empty = uptr[7]
    assert all(uptr[i] == empty for i in range(7, 25)), f'{upt:#x} empty slots differ'
    for k, slot in enumerate(NEW):
        e = EU_SLOT[k]
        arr = de[eptr[e] - B:eptr[e] - B + esizes[e]]
        # reuse an existing US array with identical bytes and size if there is one
        cand = [i for i in range(25) if usizes[i] == esizes[e] and bytes(du[uptr[i] - B:uptr[i] - B + usizes[i]]) == arr]
        if cand:
            p = uptr[cand[0]]; how = f'reuse US route {cand[0]}'
        else:
            p = B + alloc(arr); how = 'new'
        put(upt + 4 * slot, struct.pack('<I', p), f'ptr table {upt:#x} route {slot} -> {p:#x} ({how})')
        if usz:
            put(usz + 4 * slot, struct.pack('<I', esizes[e]), f'size table {usz:#x} route {slot} = {esizes[e]:#x}')
        summary.append((hex(upt), slot, how))

# 6. PA TPC section data (12-byte entries: ptr normal half, ptr CCA half, 0), 920 B per half. Normal half = EU data, CCA half stays the US empty entry (the US CA routes never cover the EU bands).
TPC_U, TPC_E, HALF = 0xf9802c, 0xff832c, 920
empty_tpc = du[TPC_U + 12 * 7:TPC_U + 12 * 8]
for k, slot in enumerate(NEW):
    uo, eo = TPC_U + 12 * slot, TPC_E + 12 * EU_SLOT[k]
    assert du[uo:uo + 12] == empty_tpc, f'TPC slot {slot} not the empty entry'
    assert de[eo:eo + 12] != de[TPC_E + 12:TPC_E + 24] and I(de, eo + 8) == 0
    p = B + alloc(de[I(de, eo) - B:I(de, eo) - B + HALF])
    put(uo, struct.pack('<I', p) + empty_tpc[4:12], f'PA TPC route {slot} <- EU route {EU_SLOT[k]} (normal half, CCA half US empty)')

# 7. calibration default tables stay US-empty for the new routes (checked, not changed)
assert all(I(du, 0xf99088 + 4 * s) == I(du, 0xf99088 + 4 * 7) for s in NEW)
for t in (0xf99188, 0xf9935c):
    assert all(du[t + 12 * s:t + 12 * s + 12] == du[t + 12 * 7:t + 12 * 8] for s in NEW)

# 8. operator table (mccmnc, mccmnc, operator id): five Malaysian entries become the Israeli operators, so the modem picks an IMS profile for them itself (same mapping as The-curious's md1img patch)
OPS = {50213: (42501, 232), 50219: (42502, 232), 50212: (42507, 172), 50217: (42509, 232), 50218: (42519, 232)}
for old, (new, op) in OPS.items():
    pat = struct.pack('<II', old, old)
    o = du.find(pat)
    assert o != -1 and du.find(pat, o + 1) == -1, f'operator entry {old} not unique'
    assert du.find(struct.pack('<II', new, new)) == -1, f'{new} already listed'
    put(o, struct.pack('<III', new, new, op), f'operator table {old} -> {new} (op {op})')

open('md1rom.duo', 'wb').write(du)
json.dump(log, open('md1rom_patch_log.json', 'w'), indent=1)
changed = sum(1 for a, b in zip(orig, du) if a != b)
print(f'writes: {len(log)}, bytes changed: {changed}, new-array space used: {cursor - FREE_LO} B of {FREE_HI - FREE_LO}')
for s in summary: print('  ', s)
