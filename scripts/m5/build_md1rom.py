#!/usr/bin/env python3
# Build a duo-band M5 md1rom: EU md1rom with 8 US-only LTE bands added in slots 12-19.
import struct, json

import os
M5 = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'tmp', 'm5')
B = 0x90000000
de = bytearray(open(f'{M5}/eu/md1/md1rom', 'rb').read())
du = open(f'{M5}/us/md1/md1rom', 'rb').read()
orig = bytes(de)
NEW = list(range(12, 20))                  # duo slots
US_SLOT = [0, 1, 4, 5, 6, 7, 8, 9]         # US slots of B2 B4 B12 B13 B17 B29 B66 B71
US_BANDS = [2, 4, 12, 13, 17, 29, 50, 55]
log = []
H = lambda d, o: struct.unpack_from('<H', d, o)[0]
I = lambda d, o: struct.unpack_from('<I', d, o)[0]

def put(o, data, why):
    de[o:o + len(data)] = data
    log.append({'off': hex(o), 'len': len(data), 'why': why})

# 1. per-slot tables (block 1, block 2, antenna 112 B table)
EU_T = [(0x1212954,42),(0x1212d70,34),(0x12131c4,38),(0x12135e0,24),(0x1213838,24),(0x1213a90,20),(0x1213cc4,2),
        (0x12647e8,42),(0x1264c04,38),(0x1264fd8,34),(0x1265624,2),(0x1265fb8,24),(0x1266210,24),(0x1266468,20),(0x127b694,112)]
US_T = [(0xf75014,42),(0xf75430,34),(0xf75884,38),(0xf75ca0,24),(0xf75ef8,24),(0xf76150,20),(0xf76384,2),
        (0xfbe6e8,42),(0xfbeb04,38),(0xfbeed8,34),(0xfbf524,2),(0xfbfeb8,24),(0xfc0110,24),(0xfc0368,20),(0xfd1b24,112)]
for (ep, s), (up, us) in zip(EU_T, US_T):
    assert s == us
    for k, slot in enumerate(NEW):
        eo, uo = ep + slot * s, up + US_SLOT[k] * s
        assert H(de, eo) == 0, f'EU table {ep:#x} slot {slot} not empty'
        assert H(du, uo) == US_BANDS[k], f'US table {up:#x} slot {US_SLOT[k]} band {H(du,uo)}'
        entry = bytearray(du[uo:uo + s])
        if s == 112:                          # last two u16 are the slot number: keep EU's
            assert struct.unpack_from('<HH', entry, 108) == (US_SLOT[k],) * 2
            entry[108:112] = de[eo + 108:eo + 112]
            assert struct.unpack_from('<HH', entry, 108) == (slot, slot)
        put(eo, bytes(entry), f'per-slot table {ep:#x} (stride {s}) slot {slot} <- US slot {US_SLOT[k]}')

# 2. one-byte per-slot flags (CA support, 2/1 flags), two copies each
for ef, uf in ((0x1213ca8, 0xf76368), (0x1265608, 0xfbf508), (0x121357c, 0xf75c3c), (0x126556c, 0xfbf46c)):
    for k, slot in enumerate(NEW):
        assert de[ef + slot] == 0 and du[uf + US_SLOT[k]] != 0
        put(ef + slot, du[uf + US_SLOT[k]:uf + US_SLOT[k] + 1], f'flag table {ef:#x} slot {slot}')

# 3. route tables: copy US entry, point it at its own MIPI table (= slot)
for ep, up, s, mi in ((0x127c734, 0xfd2bc4, 48, 44), (0x127ce54, 0xfd32e4, 68, 60)):
    for k, slot in enumerate(NEW):
        eo, uo = ep + slot * s, up + US_SLOT[k] * s
        assert H(de, eo + 4) == 0 and H(de, eo + mi) == slot, f'route {ep:#x} slot {slot} not empty'
        assert H(du, uo + 4) == US_BANDS[k] and H(du, uo + mi) == US_SLOT[k]
        entry = bytearray(du[uo:uo + s])
        struct.pack_into('<H', entry, mi, slot)
        put(eo, bytes(entry), f'route table {ep:#x} slot {slot} <- US slot {US_SLOT[k]}, MIPI idx {slot}')

# 4. A-MPR default: compact rows, append US rows 0-3 as rows 4-7
EA, UA, RS = 0x126596c, 0xfbf86c, 52
assert [H(de, EA + r * RS) for r in range(5)] == [1, 20, 28, 41, 0]
assert [H(du, UA + r * RS) for r in range(5)] == [2, 4, 13, 50, 0]
for k in range(4):
    assert not any(de[EA + (4 + k) * RS:EA + (5 + k) * RS])
    put(EA + (4 + k) * RS, du[UA + k * RS:UA + (k + 1) * RS], f'A-MPR default row {4+k} <- US row {k}')

# 5. per-route pointer tables
FREE_LO, FREE_HI = 0x1284e60, 0x1287f80
assert not any(de[0x1284d58:0x1288000]), 'free gap not zero'
cursor = FREE_LO
placed = {}
def alloc(data):
    global cursor
    if data in placed: return placed[data]
    o = (cursor + 3) & ~3
    assert o + len(data) <= FREE_HI, 'free gap too small'
    put(o, data, f'new array ({len(data)} B)')
    cursor = o + len(data)
    placed[data] = o
    return o

D = 0x2a9b70
PT = [(0x127a3f0, None, 0x64), (0x127a488, 0x127a520, None), (0x127a5b8, 0x127a650, None), (0x127a6e8, 0x127a780, None),
      (0x127a818, 0x127a89c, None), (0x127a920, 0x127a9a4, None), (0x127aab4, 0x127ab4c, None), (0x127abe4, 0x127ac7c, None),
      (0x127ad14, 0x127ad98, None), (0x127ae1c, 0x127aea0, None)]
summary = []
for ept, esz, fixed in PT:
    upt, usz = ept - D, (esz - D if esz else None)
    eptr = [I(de, ept + 4 * i) for i in range(25)]
    uptr = [I(du, upt + 4 * i) for i in range(25)]
    esizes = [I(de, esz + 4 * i) for i in range(25)] if esz else [fixed] * 25
    usizes = [I(du, usz + 4 * i) for i in range(25)] if usz else [fixed] * 25
    empty = eptr[12]
    assert all(eptr[i] == empty for i in [2] + list(range(12, 25))), f'{ept:#x} empty slots differ'
    for k, slot in enumerate(NEW):
        u = US_SLOT[k]
        arr = du[uptr[u] - B:uptr[u] - B + usizes[u]]
        cand = [i for i in range(25) if esizes[i] == usizes[u] and bytes(de[eptr[i] - B:eptr[i] - B + esizes[i]]) == arr]
        if uptr[u] == uptr[12] and (not esz or usizes[u] == esizes[12]):
            p = empty; how = 'US empty entry -> EU empty entry'
        elif cand:
            p = eptr[cand[0]]; how = f'reuse EU route {cand[0]}'
        else:
            p = B + alloc(arr); how = 'new'
        put(ept + 4 * slot, struct.pack('<I', p), f'ptr table {ept:#x} route {slot} -> {p:#x} ({how})')
        if esz:
            put(esz + 4 * slot, struct.pack('<I', usizes[u]), f'size table {esz:#x} route {slot} = {usizes[u]:#x}')
        summary.append((hex(ept), slot, how))

# 6. PA TPC section data (12-byte entries: normal half, CCA half, 0). Space allows the normal half only;
#    the CCA half (contiguous uplink CA) keeps EU's empty entry. B29 has no TX: whole entry stays empty.
TPC_E, TPC_U, HALF = 0x127a190, 0x127a190 - D, 920
empty_e = de[TPC_E + 12 * 2:TPC_E + 12 * 3]
empty_u = du[TPC_U + 12 * 10:TPC_U + 12 * 11]
for k, slot in enumerate(NEW):
    eo, uo = TPC_E + 12 * slot, TPC_U + 12 * US_SLOT[k]
    assert de[eo:eo + 12] == empty_e, f'TPC slot {slot} not empty'
    if du[uo:uo + 12] == empty_u:
        assert US_BANDS[k] == 29; continue
    up = I(du, uo) - B
    pa = B + alloc(du[up:up + HALF])
    put(eo, struct.pack('<I', pa), f'PA TPC route {slot} normal half <- US slot {US_SLOT[k]} (CCA half stays EU empty)')
for t in (0x127b2ec, 0x127b4c0):
    assert all(de[t + 12 * s:t + 12 * s + 12] == de[t + 24:t + 36] for s in NEW)
open('md1rom.duo', 'wb').write(de)
json.dump(log, open('md1rom_patch_log.json', 'w'), indent=1)
changed = sum(1 for a, b in zip(orig, de) if a != b)
print(f'writes: {len(log)}, bytes changed: {changed}, new-array space used: {cursor - FREE_LO} of {FREE_HI - FREE_LO} B')
from collections import Counter
print(Counter((t, h.split(" route")[0]) for t, _, h in summary))
