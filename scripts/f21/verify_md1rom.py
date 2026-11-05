#!/usr/bin/env python3
# Independent checks on md1rom.duo against the US and EU originals.
import struct, json, sys, os
_R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_R, 'scripts', 'lib'))
from sdec import Dict

F21 = os.path.join(_R, 'tmp', 'f21')
B = 0x90000000
us = open(f'{F21}/us/md1/md1rom', 'rb').read()
eu = open(f'{F21}/eu/md1/md1rom', 'rb').read()
dd = open('md1rom.duo', 'rb').read()
log = json.load(open('md1rom_patch_log.json'))
I = lambda d, o: struct.unpack_from('<I', d, o)[0]
EU_SLOT = [0, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13]
NEW = range(7, 19)
GAP = (0xfa2e80, 0xfa7f00)
ok = True
def check(cond, msg):
    global ok
    print(('PASS ' if cond else 'FAIL ') + msg)
    ok &= bool(cond)

check(len(dd) == len(us), 'same size as US md1rom')
ranges = [(int(x['off'], 16), int(x['off'], 16) + x['len']) for x in log]
diff = [i for i in range(len(us)) if us[i] != dd[i]]
check(all(any(a <= i < b for a, b in ranges) for i in diff), f'all {len(diff)} changed bytes are inside logged writes')
check(all(0xf3a000 <= a and b <= 0xfa8000 or 0xea2000 <= a and b <= 0xea5000 for a, b in ranges), 'all writes inside the RF data area, the free gap or the operator table')
check(dd[0xfa8000:] == us[0xfa8000:], 'everything from the end of the free gap on (code, CHECK_HEADER) untouched')

# band lists
for o in (0xf3d0a0, 0xf87228):
    bands = struct.unpack_from('<25H', dd, o)
    check(list(bands) == [2, 4, 12, 13, 17, 50, 55, 1, 3, 5, 7, 8, 20, 28, 34, 38, 39, 40, 41] + [0] * 6, f'band list {o:#x} = US 0-6 + EU 7-18')

# route tables decode with the US dictionary
D = Dict(f'{F21}/us/meta.xml')
for name, o, eo, st, tn, mk, mi in (('TX', 0xf9ada0, 0xffb0a0, 48, 'LTE_FE_TX_ROUTE_TABLE_T', 'cfg.TxMipiTblIdx', 44), ('RX', 0xf9b4c0, 0xffb7c0, 68, 'LTE_FE_RX_ROUTE_TABLE_T', 'cfg.RxMipiTblIdx', 60)):
    rows = [dict(D.flat(tn, dd[o + i * st:o + (i + 1) * st])) for i in range(25)]
    check(all(rows[i][mk] == f'LTE_Route{i}' for i in range(25)), f'{name} route table: MIPI index = slot for all 25 entries')
    strip = lambda b: b[:mi] + b[mi + 2:]
    check(all(strip(dd[o + s * st:o + (s + 1) * st]) == strip(eu[eo + e * st:eo + (e + 1) * st]) for s, e in zip(NEW, EU_SLOT)), f'{name} route entries 7-18 equal the EU entries apart from MIPI index')
    check(dd[o:o + 7 * st] == us[o:o + 7 * st] and dd[o + 19 * st:o + 25 * st] == us[o + 19 * st:o + 25 * st], f'{name} route entries 0-6 and 19-24 unchanged')

# pointer tables: every new route resolves to bytes identical to the EU array, and new arrays sit in the free gap
PT = [(0xf9828c, None, 0xff858c, None, 0x50), (0xf98324, 0xf983bc, 0xff8624, 0xff86bc, None), (0xf98454, 0xf984ec, 0xff8754, 0xff87ec, None),
      (0xf98584, 0xf9861c, 0xff8884, 0xff891c, None), (0xf986b4, 0xf98738, 0xff89b4, 0xff8a38, None), (0xf987bc, 0xf98840, 0xff8abc, 0xff8b40, None),
      (0xf98950, 0xf989e8, 0xff8c50, 0xff8ce8, None), (0xf98a80, 0xf98b18, 0xff8d80, 0xff8e18, None), (0xf98bb0, 0xf98c34, 0xff8eb0, 0xff8f34, None),
      (0xf98cb8, 0xf98d3c, 0xff8fb8, 0xff903c, None)]
uptrs = {I(us, t + 4 * i) for t, *_ in PT for i in range(25)}
for upt, usz, ept, esz, fixed in PT:
    good = True
    for s, e in zip(NEW, EU_SLOT):
        p, ep = I(dd, upt + 4 * s) - B, I(eu, ept + 4 * e) - B
        ln = I(dd, usz + 4 * s) if usz else fixed
        eln = I(eu, esz + 4 * e) if esz else fixed
        good &= ln == eln and dd[p:p + ln] == eu[ep:ep + eln]
        good &= (p + B) in uptrs or GAP[0] <= p and p + ln <= GAP[1]
    good &= all(I(dd, upt + 4 * i) == I(us, upt + 4 * i) for i in list(range(7)) + list(range(19, 25)))
    check(good, f'pointer table {upt:#x}: routes 7-18 resolve to the EU arrays (US reuse or free gap), other routes unchanged')

# calibration default tables: new routes keep US's empty entry
check(all(I(dd, 0xf99088 + 4 * s) == I(us, 0xf99088 + 4 * 7) for s in NEW), 'RX-gain defaults: routes 7-18 point at US empty entry (not added)')
check(all(dd[t + 12 * s:t + 12 * s + 12] == us[t + 84:t + 96] for t in (0xf99188, 0xf9935c) for s in NEW), 'TX calibration defaults: routes 7-18 US empty entry (not added)')

# PA TPC section data: normal half = EU data inside the free gap, CCA half = US empty entry
good = True
for s, e in zip(NEW, EU_SLOT):
    p = I(dd, 0xf9802c + 12 * s) - B; ep = I(eu, 0xff832c + 12 * e) - B
    good &= dd[p:p + 920] == eu[ep:ep + 920] and GAP[0] <= p and p + 920 <= GAP[1]
    good &= dd[0xf9802c + 12 * s + 4:0xf9802c + 12 * s + 12] == us[0xf9802c + 12 * 7 + 4:0xf9802c + 12 * 8]
good &= dd[0xf9802c:0xf9802c + 84] == us[0xf9802c:0xf9802c + 84]
check(good, 'PA TPC: routes 7-18 normal half = EU data, CCA half = US empty entry, routes 0-6 unchanged')

# A-MPR default rows
rows = [struct.unpack_from('<H', dd, 0xf87570 + r * 52)[0] for r in range(9)]
check(rows == [2, 4, 13, 50, 1, 20, 28, 41, 0], f'A-MPR default bands {rows}')

# operator table
found = {}
for mm in (42501, 42502, 42507, 42509, 42519, 50212, 50213, 50217, 50218, 50219):
    o = dd.find(struct.pack('<II', mm, mm))
    found[mm] = I(dd, o + 8) if o != -1 else None
check(found == {42501: 232, 42502: 232, 42507: 172, 42509: 232, 42519: 232, 50212: None, 50213: None, 50217: None, 50218: None, 50219: None}, f'operator table: Israeli operators listed {found}')
print('\nALL PASS' if ok else '\nSOME CHECKS FAILED')
