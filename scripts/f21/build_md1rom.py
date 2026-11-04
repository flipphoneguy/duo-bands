#!/usr/bin/env python3
# Build a duo-band F21 md1rom: EU md1rom with the 7 US LTE bands added in slots 14-20.
import struct, json

import os
F21 = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'tmp', 'f21')
B = 0x90000000
de = bytearray(open(f'{F21}/eu/md1/md1rom', 'rb').read())
du = open(f'{F21}/us/md1/md1rom', 'rb').read()
orig = bytes(de)
NEW = list(range(14, 21))          # duo slots
US_BANDS = [2, 4, 12, 13, 17, 50, 55]
log = []

H = lambda d, o: struct.unpack_from('<H', d, o)[0]
I = lambda d, o: struct.unpack_from('<I', d, o)[0]

def put(o, data, why):
    assert len(data) > 0
    de[o:o + len(data)] = data
    log.append({'off': hex(o), 'len': len(data), 'why': why})

# 1. per-slot tables, paired EU/US (same order, same stride)
EU_T = [(0xf8d64c,42),(0xf8dabc,42),(0xf8ded8,80),(0xf8e7a8,52),(0xf8ecbc,52),(0xf8f1d0,52),(0xf8f6e4,50),(0xf8fbc8,38),(0xf8ffe4,24),(0xf9023c,24),(0xf90494,20),(0xf906c8,2),
        (0xfe46e0,42),(0xfe4b50,42),(0xfe4f6c,52),(0xfe5480,52),(0xfe5994,52),(0xfe5ea8,50),(0xfe638c,38),(0xfe6760,80),(0xfe7228,2),(0xfe7bbc,24),(0xfe7e14,24),(0xfe806c,20),(0xff98f8,112)]
US_T = [(0xf3a024,42),(0xf3a494,42),(0xf3a8b0,80),(0xf3b180,52),(0xf3b694,52),(0xf3bba8,52),(0xf3c0bc,50),(0xf3c5a0,38),(0xf3c9bc,24),(0xf3cc14,24),(0xf3ce6c,20),(0xf3d0a0,2),
        (0xf846e0,42),(0xf84b50,42),(0xf84f6c,52),(0xf85480,52),(0xf85994,52),(0xf85ea8,50),(0xf8638c,38),(0xf86760,80),(0xf87228,2),(0xf87bbc,24),(0xf87e14,24),(0xf8806c,20),(0xf995f8,112)]
for (ep, s), (up, us) in zip(EU_T, US_T):
    assert s == us
    for k, slot in enumerate(NEW):
        eo, uo = ep + slot * s, up + k * s
        assert H(de, eo) == 0, f'EU table {ep:#x} slot {slot} not empty'
        assert H(du, uo) == US_BANDS[k], f'US table {up:#x} entry {k} band {H(du,uo)}'
        entry = bytearray(du[uo:uo + s])
        if s == 112:                      # last two u16 are the slot number: keep EU's
            assert struct.unpack_from('<HH', entry, 108) == (k, k)
            entry[108:112] = de[eo + 108:eo + 112]
            assert struct.unpack_from('<HH', entry, 108) == (slot, slot)
        put(eo, bytes(entry), f'per-slot table {ep:#x} (stride {s}) slot {slot} <- US {up:#x}[{k}]')

# 2. one-byte per-slot flags (CA support flags, and the 2/1 flags)
for ef, uf in ((0xf906ac,0xf3d084),(0xfe720c,0xf8720c),(0xf8ff80,0xf3c958),(0xfe7170,0xf87170)):
    for k, slot in enumerate(NEW):
        assert de[ef + slot] == 0 and du[uf + k] != 0
        put(ef + slot, du[uf + k:uf + k + 1], f'flag table {ef:#x} slot {slot} <- US {uf:#x}[{k}]')

# 3. route tables: copy US entry, then point it at its own MIPI table (= slot)
for ep, up, s, mi in ((0xffb0a0, 0xf9ada0, 48, 44), (0xffb7c0, 0xf9b4c0, 68, 60)):
    for k, slot in enumerate(NEW):
        eo, uo = ep + slot * s, up + k * s
        assert H(de, eo + 4) == 0 and H(de, eo + mi) == slot, f'route {ep:#x} slot {slot} not empty'
        assert H(du, uo + 4) == US_BANDS[k] and H(du, uo + mi) == k
        entry = bytearray(du[uo:uo + s])
        struct.pack_into('<H', entry, mi, slot)
        put(eo, bytes(entry), f'route table {ep:#x} slot {slot} <- US {up:#x}[{k}], MIPI idx {slot}')

# 4. A-MPR default: compact rows, append US rows 0-3 as rows 4-7
EA, UA, RS = 0xfe7570, 0xf87570, 52
eu_rows = [H(de, EA + r * RS) for r in range(25)]
us_rows = [H(du, UA + r * RS) for r in range(25)]
assert eu_rows[:5] == [1, 20, 28, 41, 0] and us_rows[:5] == [2, 4, 13, 50, 0], (eu_rows[:6], us_rows[:6])
for k in range(4):
    assert not any(de[EA + (4 + k) * RS:EA + (5 + k) * RS])
    put(EA + (4 + k) * RS, du[UA + k * RS:UA + (k + 1) * RS], f'A-MPR default row {4+k} <- US row {k}')

# 5. per-route pointer tables
FREE_LO, FREE_HI = 0x1003200, 0x1007f00
assert not any(de[0x1003100:0x1008000]), 'free gap not zero'
cursor = FREE_LO
def alloc(data):
    global cursor
    o = (cursor + 15) & ~15
    assert o + len(data) <= FREE_HI
    put(o, data, f'new array ({len(data)} B)')
    cursor = o + len(data)
    return o

PT = [  # (EU ptr table, EU sizes, US ptr table, US sizes, fixed length if unsized)
    (0xff858c, None, 0xf9828c, None, 0x50),
    (0xff8624, 0xff86bc, 0xf98324, 0xf983bc, None),
    (0xff8754, 0xff87ec, 0xf98454, 0xf984ec, None),
    (0xff8884, 0xff891c, 0xf98584, 0xf9861c, None),
    (0xff89b4, 0xff8a38, 0xf986b4, 0xf98738, None),
    (0xff8abc, 0xff8b40, 0xf987bc, 0xf98840, None),
    (0xff8c50, 0xff8ce8, 0xf98950, 0xf989e8, None),
    (0xff8d80, 0xff8e18, 0xf98a80, 0xf98b18, None),
    (0xff8eb0, 0xff8f34, 0xf98bb0, 0xf98c34, None),
    (0xff8fb8, 0xff903c, 0xf98cb8, 0xf98d3c, None),
]
summary = []
for ept, esz, upt, usz, fixed in PT:
    eptr = [I(de, ept + 4 * i) for i in range(25)]
    uptr = [I(du, upt + 4 * i) for i in range(25)]
    esizes = [I(de, esz + 4 * i) for i in range(25)] if esz else [fixed] * 25
    usizes = [I(du, usz + 4 * i) for i in range(25)] if usz else [fixed] * 25
    empty = eptr[14]
    assert all(eptr[i] == empty for i in [1, 6] + list(range(14, 25))), f'{ept:#x} empty slots differ'
    for k, slot in enumerate(NEW):
        arr = du[uptr[k] - B:uptr[k] - B + usizes[k]]
        # reuse an existing EU array with identical bytes and size if there is one
        cand = [i for i in range(25) if esizes[i] == usizes[k] and bytes(de[eptr[i] - B:eptr[i] - B + esizes[i]]) == arr]
        if cand:
            p = eptr[cand[0]]; how = f'reuse EU route {cand[0]}'
        else:
            p = B + alloc(arr); how = 'new'
        put(ept + 4 * slot, struct.pack('<I', p), f'ptr table {ept:#x} route {slot} -> {p:#x} ({how})')
        if esz:
            put(esz + 4 * slot, struct.pack('<I', usizes[k]), f'size table {esz:#x} route {slot} = {usizes[k]:#x}')
        summary.append((hex(ept), slot, how))

# 6. PA TPC section data (12-byte entries: ptr normal half, ptr CCA half, 0), 920 B per half
TPC_E, TPC_U, HALF = 0xff832c, 0xf9802c, 920
for k, slot in enumerate(NEW):
    eo, uo = TPC_E + 12 * slot, TPC_U + 12 * k
    assert de[eo:eo + 12] == de[TPC_E + 12 * 1:TPC_E + 12 * 2], f'TPC slot {slot} not the empty entry'
    assert de[uo:uo + 12] != du[TPC_U + 12 * 7:TPC_U + 12 * 8] and I(du, uo + 8) == 0
    ptrs = []
    for h in (0, 1):
        up = I(du, uo + 4 * h) - B
        ptrs.append(B + alloc(du[up:up + HALF]))
    put(eo, struct.pack('<III', ptrs[0], ptrs[1], 0), f'PA TPC route {slot} <- US route {k} (both halves)')
# 7. TX calibration default tables stay EU-empty for the new routes (checked, not changed)
for t in (0xff9488, 0xff965c):
    assert all(de[t + 12 * s:t + 12 * s + 12] == de[t + 12:t + 24] for s in NEW)
open('md1rom.duo', 'wb').write(de)
json.dump(log, open('md1rom_patch_log.json', 'w'), indent=1)
changed = sum(1 for a, b in zip(orig, de) if a != b)
print(f'writes: {len(log)}, bytes changed: {changed}, new-array space used: {cursor - FREE_LO} B')
for s in summary: print('  ', s)
