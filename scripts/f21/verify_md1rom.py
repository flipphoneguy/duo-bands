#!/usr/bin/env python3
# Independent checks on md1rom.duo against the EU and US originals.
import struct, json, sys, os
_R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_R, 'scripts', 'lib'))
from sdec import Dict

F21 = os.path.join(_R, 'tmp', 'f21')
B = 0x90000000
eu = open(f'{F21}/eu/md1/md1rom', 'rb').read()
us = open(f'{F21}/us/md1/md1rom', 'rb').read()
dd = open('md1rom.duo', 'rb').read()
log = json.load(open('md1rom_patch_log.json'))
I = lambda d, o: struct.unpack_from('<I', d, o)[0]
ok = True
def check(cond, msg):
    global ok
    print(('PASS ' if cond else 'FAIL ') + msg)
    ok &= bool(cond)

check(len(dd) == len(eu), 'same size as EU md1rom')
# every changed byte lies inside a logged write
ranges = [(int(x['off'], 16), int(x['off'], 16) + x['len']) for x in log]
diff = [i for i in range(len(eu)) if eu[i] != dd[i]]
check(all(any(a <= i < b for a, b in ranges) for i in diff), f'all {len(diff)} changed bytes are inside logged writes')
check(not any(a < 0xf80000 or b > 0x1008000 for a, b in ranges), 'all writes inside RF data area or free gap')
check(dd[0x100e9a4:] == eu[0x100e9a4:], 'CHECK_HEADER untouched')

# band lists
for o in (0xf906c8, 0xfe7228):
    bands = struct.unpack_from('<25H', dd, o)
    check(list(bands[:21]) == [1,0,3,5,7,8,0,20,28,34,38,39,40,41,2,4,12,13,17,50,55] and not any(bands[21:]), f'band list {o:#x} = EU 0-13 + US 14-20')

# route tables decode with the EU dictionary
D = Dict(f'{F21}/eu/meta.xml')
for name, o, st, tn, mk in (('TX', 0xffb0a0, 48, 'LTE_FE_TX_ROUTE_TABLE_T', 'cfg.TxMipiTblIdx'), ('RX', 0xffb7c0, 68, 'LTE_FE_RX_ROUTE_TABLE_T', 'cfg.RxMipiTblIdx')):
    rows = [dict(D.flat(tn, dd[o + i * st:o + (i + 1) * st])) for i in range(25)]
    check(all(rows[i][mk] == f'LTE_Route{i}' for i in range(25)), f'{name} route table: MIPI index = slot for all 25 entries')
    usrows = [dict(D.flat(tn, us[(0xf9ada0 if name == 'TX' else 0xf9b4c0) + k * st:][:st])) for k in range(7)]
    same = all({a: b for a, b in rows[14 + k].items() if a != mk} == {a: b for a, b in usrows[k].items() if a != mk} for k in range(7))
    check(same, f'{name} route entries 14-20 equal US 0-6 apart from MIPI index')
    euorig = [eu[o + i * st:o + (i + 1) * st] for i in range(14)]
    check(all(dd[o + i * st:o + (i + 1) * st] == euorig[i] for i in range(14)), f'{name} route entries 0-13 unchanged')

# pointer tables: every new route resolves to bytes identical to the US array
PT = [(0xff858c, None, 0xf9828c, None, 0x50), (0xff8624, 0xff86bc, 0xf98324, 0xf983bc, None), (0xff8754, 0xff87ec, 0xf98454, 0xf984ec, None),
      (0xff8884, 0xff891c, 0xf98584, 0xf9861c, None), (0xff89b4, 0xff8a38, 0xf986b4, 0xf98738, None), (0xff8abc, 0xff8b40, 0xf987bc, 0xf98840, None),
      (0xff8c50, 0xff8ce8, 0xf98950, 0xf989e8, None), (0xff8d80, 0xff8e18, 0xf98a80, 0xf98b18, None), (0xff8eb0, 0xff8f34, 0xf98bb0, 0xf98c34, None),
      (0xff8fb8, 0xff903c, 0xf98cb8, 0xf98d3c, None)]
for ept, esz, upt, usz, fixed in PT:
    good = True
    for k in range(7):
        p, up = I(dd, ept + 4 * (14 + k)) - B, I(us, upt + 4 * k) - B
        ln = I(dd, esz + 4 * (14 + k)) if esz else fixed
        uln = I(us, usz + 4 * k) if usz else fixed
        good &= ln == uln and 0 <= p < len(dd) and dd[p:p + ln] == us[up:up + uln]
    good &= all(I(dd, ept + 4 * i) == I(eu, ept + 4 * i) for i in range(14))
    check(good, f'pointer table {ept:#x}: routes 14-20 resolve to the US arrays, routes 0-13 unchanged')

# RX-gain and TX calibration defaults: new routes keep EU's empty entry
check(all(I(dd, 0xff9388 + 4 * s) == I(eu, 0xff9388 + 4 * 1) for s in range(14, 21)), 'RX-gain defaults: routes 14-20 point at EU empty entry (not added)')
check(all(dd[t + 12 * s:t + 12 * s + 12] == eu[t + 12:t + 24] for t in (0xff9488, 0xff965c) for s in range(14, 21)), 'TX calibration defaults: routes 14-20 EU empty entry (not added)')
# PA TPC section data: both halves equal the US data
good = True
for k in range(7):
    for h in (0, 1):
        p = I(dd, 0xff832c + 12 * (14 + k) + 4 * h) - B; up = I(us, 0xf9802c + 12 * k + 4 * h) - B
        good &= dd[p:p + 920] == us[up:up + 920]
good &= all(I(dd, 0xff832c + 12 * i + 4 * h) == I(eu, 0xff832c + 12 * i + 4 * h) for i in range(14) for h in (0, 1, 2))
check(good, 'PA TPC section data: routes 14-20 both halves = US data, routes 0-13 unchanged')
# A-MPR default rows
rows = [struct.unpack_from('<H', dd, 0xfe7570 + r * 52)[0] for r in range(9)]
check(rows == [1, 20, 28, 41, 2, 4, 13, 50, 0], f'A-MPR default bands {rows}')
print('\nALL PASS' if ok else '\nSOME CHECKS FAILED')
