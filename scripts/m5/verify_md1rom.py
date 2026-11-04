#!/usr/bin/env python3
# Independent checks on the M5 md1rom.duo against the EU and US originals.
import struct, json, sys, os
_R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_R, 'scripts', 'lib'))
from sdec import Dict

M5 = os.path.join(_R, 'tmp', 'm5')
B = 0x90000000; D = 0x2a9b70
eu = open(f'{M5}/eu/md1/md1rom', 'rb').read(); us = open(f'{M5}/us/md1/md1rom', 'rb').read(); dd = open('md1rom.duo', 'rb').read()
log = json.load(open('md1rom_patch_log.json'))
I = lambda d, o: struct.unpack_from('<I', d, o)[0]
US_SLOT = [0, 1, 4, 5, 6, 7, 8, 9]
ok = True
def check(c, m):
    global ok
    print(('PASS ' if c else 'FAIL ') + m); ok &= bool(c)

check(len(dd) == len(eu), 'same size as EU md1rom')
ranges = [(int(x['off'], 16), int(x['off'], 16) + x['len']) for x in log]
diff = [i for i in range(len(eu)) if eu[i] != dd[i]]
check(all(any(a <= i < b for a, b in ranges) for i in diff), f'all {len(diff)} changed bytes are inside logged writes')
check(not any(a < 0x1200000 or b > 0x1288000 for a, b in ranges), 'all writes inside RF data area or free gap')
check(dd[0x128e9e4:] == eu[0x128e9e4:], 'CHECK_HEADER untouched')
for o in (0x1213cc4, 0x1265624):
    bands = struct.unpack_from('<25H', dd, o)
    check(list(bands[:20]) == [1,3,0,5,7,8,20,28,38,39,40,41,2,4,12,13,17,29,50,55] and not any(bands[20:]), f'band list {o:#x} = EU 0-11 + US 12-19')

Dct = Dict(f'{M5}/eu/meta.xml')
for name, o, uo, st, tn, mk in (('TX', 0x127c734, 0xfd2bc4, 48, 'LTE_FE_TX_ROUTE_TABLE_T', 'cfg.TxMipiTblIdx'), ('RX', 0x127ce54, 0xfd32e4, 68, 'LTE_FE_RX_ROUTE_TABLE_T', 'cfg.RxMipiTblIdx')):
    rows = [dict(Dct.flat(tn, dd[o + i * st:o + (i + 1) * st])) for i in range(25)]
    check(all(rows[i][mk] == f'LTE_Route{i}' for i in range(25)), f'{name} route table: MIPI index = slot for all 25 entries')
    usrows = [dict(Dct.flat(tn, us[uo + u * st:uo + (u + 1) * st])) for u in US_SLOT]
    check(all({a: b for a, b in rows[12 + k].items() if a != mk} == {a: b for a, b in usrows[k].items() if a != mk} for k in range(8)), f'{name} route entries 12-19 equal US entries apart from MIPI index')
    check(all(dd[o + i * st:o + (i + 1) * st] == eu[o + i * st:o + (i + 1) * st] for i in range(12)), f'{name} route entries 0-11 unchanged')
check(dict(Dct.flat('LTE_FE_TX_ROUTE_TABLE_T', dd[0x127c734 + 17 * 48:0x127c734 + 18 * 48]))['cfg.TxIodata.txio'] == 'TX_IO_NON_USED', 'B29 (slot 17) has no TX output')

PT = [(0x127a3f0, None, 0x64), (0x127a488, 0x127a520, None), (0x127a5b8, 0x127a650, None), (0x127a6e8, 0x127a780, None),
      (0x127a818, 0x127a89c, None), (0x127a920, 0x127a9a4, None), (0x127aab4, 0x127ab4c, None), (0x127abe4, 0x127ac7c, None),
      (0x127ad14, 0x127ad98, None), (0x127ae1c, 0x127aea0, None)]
for ept, esz, fixed in PT:
    good = True
    for k, u in enumerate(US_SLOT):
        p, up = I(dd, ept + 4 * (12 + k)) - B, I(us, ept - D + 4 * u) - B
        uempty = I(us, ept - D + 4 * 12) - B
        ln = I(dd, esz + 4 * (12 + k)) if esz else fixed
        uln = I(us, esz - D + 4 * u) if esz else fixed
        if up == uempty:
            good &= p == I(eu, ept + 4 * 12) - B            # US empty -> EU empty
        else:
            good &= ln == uln and dd[p:p + ln] == us[up:up + uln]
    good &= all(I(dd, ept + 4 * i) == I(eu, ept + 4 * i) for i in range(12))
    check(good, f'pointer table {ept:#x}: routes 12-19 resolve to the US data (empty stays empty), routes 0-11 unchanged')
check(all(I(dd, 0x127b1ec + 4 * s) == I(eu, 0x127b1ec + 4 * 2) for s in range(12, 20)), 'RX-gain defaults: routes 12-19 EU empty entry (not added)')
check(all(dd[t + 12 * s:t + 12 * s + 12] == eu[t + 24:t + 36] for t in (0x127b2ec, 0x127b4c0) for s in range(12, 20)), 'TX calibration defaults: routes 12-19 EU empty entry (not added)')
good = True
for k, u in enumerate(US_SLOT):
    eo = 0x127a190 + 12 * (12 + k); uo = 0x127a190 - D + 12 * u
    if u == 7:
        good &= dd[eo:eo + 12] == eu[0x127a190 + 24:0x127a190 + 36]; continue
    p = I(dd, eo) - B; up = I(us, uo) - B
    good &= dd[p:p + 920] == us[up:up + 920] and dd[eo + 4:eo + 12] == eu[0x127a190 + 28:0x127a190 + 36]
good &= all(dd[0x127a190 + 12 * i:0x127a190 + 12 * i + 12] == eu[0x127a190 + 12 * i:0x127a190 + 12 * i + 12] for i in range(12))
check(good, 'PA TPC: routes 12-19 normal half = US data, CCA half EU empty, B29 fully EU empty, routes 0-11 unchanged')
rows = [struct.unpack_from('<H', dd, 0x126596c + r * 52)[0] for r in range(9)]
check(rows == [1, 20, 28, 41, 2, 4, 13, 50, 0], f'A-MPR default bands {rows}')
print('\nALL PASS' if ok else '\nSOME CHECKS FAILED')
