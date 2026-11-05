#!/usr/bin/env python3
# Independent verification of the duo md1img, nvdata and nvram images.
import os, struct, hashlib, subprocess, shutil, sys, re
_R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_R, 'scripts', 'lib'))
from binregion import allfile_checksum
from sdec import Dict

F21 = os.path.join(_R, 'tmp', 'f21')
EU_SLOT = [0, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13]
ok = True
def check(c, m):
    global ok
    print(('PASS ' if c else 'FAIL ') + m); ok &= bool(c)
def mx(b):
    h = hashlib.md5(b).digest(); return bytes(h[i] ^ h[i + 8] for i in range(8))
def cs16(b):
    lo, hi = 0xEF, 0xCD
    for i, x in enumerate(b):
        if i & 1: hi = (hi + x) & 0xff
        else: lo = (lo + x) & 0xff
    return bytes([lo, hi]) + b'\0' * 6
def ldi(raw):
    lid, n = struct.unpack_from('<HH', raw, 4); sz = struct.unpack_from('<I', raw, 8)[0]
    return lid, n, sz, [raw[0x40 + k * (sz + 8):0x40 + k * (sz + 8) + sz] for k in range(n)], [raw[0x40 + k * (sz + 8) + sz:0x40 + k * (sz + 8) + sz + 8] for k in range(n)]
def recs(path): return ldi(open(path, 'rb').read())[3]

# --- md1img
us_img = open(f'{F21}/us/md1img_a.bin', 'rb').read()
duo_rom = open('md1rom.duo', 'rb').read()
img = bytearray(us_img); img[0x200:0x200 + len(duo_rom)] = duo_rom
open('md1img_a.duo.bin', 'wb').write(img)
check(len(img) == len(us_img) and struct.unpack_from('<I', img, 4)[0] == len(duo_rom), 'md1img same size, md1rom header size matches')
check(img[:0x200] == us_img[:0x200] and img[0x200 + len(duo_rom):] == us_img[0x200 + len(duo_rom):], 'md1img: only the md1rom body differs from US')
shutil.rmtree('split_check', ignore_errors=True)
subprocess.run([sys.executable, os.path.join(_R, 'scripts', 'lib', 'split_md1img.py'), 'md1img_a.duo.bin', 'split_check'], check=True)
check(open('split_check/md1rom', 'rb').read() == duo_rom, 'md1img splits back into the patched md1rom')
for f in os.listdir('split_check'):
    if f != 'md1rom':
        check(open(f'split_check/{f}', 'rb').read() == open(f'{F21}/us/md1/{f}', 'rb').read(), f'md1img part {f} identical to US')

# --- nvdata filesystem
r = subprocess.run(['e2fsck', '-fn', 'nvdata.duo.img'], capture_output=True, text=True)
check(r.returncode == 0, f'e2fsck clean on nvdata.duo.img (exit {r.returncode})')
shutil.rmtree('nvdata_check', ignore_errors=True); os.makedirs('nvdata_check')
subprocess.run(['debugfs', '-R', 'rdump / nvdata_check', 'nvdata.duo.img'], capture_output=True)
edited = {}
for f in os.listdir('.'):
    for d in ('CALIBRAT', 'NVD_DATA'):
        if f.startswith(f'files_{d}_'):
            edited[f'{d}/' + f[len(f'files_{d}_'):]] = open(f, 'rb').read()
base = f'{F21}/us/nvdata'
same = 0; unexpected = []
for root, _, fs in os.walk(base):
    for f in fs:
        rel = os.path.relpath(os.path.join(root, f), base)
        a = open(os.path.join(root, f), 'rb').read(); b = open(os.path.join('nvdata_check', rel), 'rb').read()
        key = rel.replace('md/NVRAM/', '', 1)
        if key in edited: check(b == edited[key], f'{key}: content equals intended patch')
        elif a == b: same += 1
        elif rel in ('AllFile', 'AllMap'): pass
        else: unexpected.append(rel)
check(not unexpected, f'all {same} other nvdata files byte-identical to US, including IMEI, barcode and IMS profile (unexpected: {unexpected})')
for key in edited:
    p = f'/md/NVRAM/{key}'
    s1 = subprocess.run(['debugfs', '-R', f'stat {p}', f'{F21}/us/nvdata.work.img'], capture_output=True, text=True).stdout
    s2 = subprocess.run(['debugfs', '-R', f'stat {p}', 'nvdata.duo.img'], capture_output=True, text=True).stdout
    strip = lambda s: [l for l in s.splitlines() if not any(w in l for w in ('ctime', 'atime', 'mtime', 'crtime', 'Inode checksum'))]
    check(strip(s1) == strip(s2), f'{key}: inode metadata (owner, mode, size, xattrs, blocks) unchanged')

# --- record checksums and content of edited files
for key, raw in edited.items():
    lid, n, sz, rs, chks = ldi(raw)
    check(all(c == mx(r) or c == cs16(r) for r, c in zip(rs, chks)), f'{key}: every record checksum valid')
    check(raw[:0x40] == open(f'{base}/md/NVRAM/{key}', 'rb').read()[:0x40], f'{key}: LDI header unchanged')

bands = struct.unpack('<25H', ldi(edited['CALIBRAT/EL03_001'])[3][0])
check(list(bands) == [2, 4, 12, 13, 17, 50, 55, 1, 3, 5, 7, 8, 20, 28, 34, 38, 39, 40, 41] + [0] * 6, f'band indicator {bands[:19]}')
for rel in ('CALIBRAT/EA10_001', 'CALIBRAT/EA40_001', 'CALIBRAT/EA50_001'):
    d, u, e = ldi(edited[rel])[3], recs(f'{base}/md/NVRAM/{rel}'), recs(f'{F21}/eu/nvdata/md/NVRAM/{rel}')
    check(d[:7] == u[:7] and all(d[7 + k] == e[s] for k, s in enumerate(EU_SLOT)) and d[19:] == u[19:], f'{rel}: slots 0-6 US, 7-18 = EU calibration per band')
for rel in ('CALIBRAT/EL90_001', 'CALIBRAT/EL92_001'):
    d, u, e = ldi(edited[rel])[3], recs(f'{base}/md/NVRAM/{rel}'), recs(f'{F21}/eu/nvdata/md/NVRAM/{rel}')
    check(d[:7] == u[:7] and d[7:19] == e[:12] and d[19:] == u[19:], f'{rel}: self-cal list US 0-6, EU 7-18, rest US')
rs = ldi(edited['CALIBRAT/EL91_001'])[3]
check([struct.unpack_from('<HHHH', rs[k], 4) for k in range(7)] == [(0, 0, 260, 260), (2, 2, 0, 0), (4, 4, 1, 1), (50, 50, 5, 5), (1, 1, 7, 7), (3, 3, 8, 8), (7, 7, 10, 10)], 'IIP2 records: US 0-3, EU B1/B3/B7 at index 7/8/10')

# --- 3G: B5 added in position LB1, B1 (HB1) and B8 (HB2) untouched
D = Dict(f'{F21}/us/meta.xml')
lid = ldi(edited['NVD_DATA/UL03_000'])[0]; tn = D.lids[lid][1]
d3 = dict(D.flat(tn, ldi(edited['NVD_DATA/UL03_000'])[3][0])); u3 = dict(D.flat(tn, recs(f'{base}/md/NVRAM/NVD_DATA/UL03_000')[0]))
e3 = dict(D.flat(tn, recs(f'{F21}/eu/nvdata/md/NVRAM/NVD_DATA/UL03_000')[0]))
ind = {p: d3[f'umtsBandIndicator.{p}'] for p in ('HB1', 'HB2', 'HB3', 'LB1', 'LB2')}
check(ind == {'HB1': 'UMTSBand1', 'HB2': 'UMTSBand8', 'HB3': 'UMTSBandNone', 'LB1': 'UMTSBand5', 'LB2': 'UMTSBandNone'}, f'3G band positions {ind}')
lb1 = lambda k: any(f'[3].' in k and k.startswith(p) for p in ('umtsPdata.rxBpi', 'umtsPdata.txBpi', 'umtsRxLnaPortSel', 'umtsTxPathSel')) or k == 'umtsBandIndicator.LB1'
check(all(d3[k] == (e3[k] if lb1(k) else u3[k]) for k in d3), '3G RF parameters: LB1 entries = EU (B5 PRX5/DRX4, TX LB2), everything else = US')
for rel in ('NVD_DATA/ULM4_000', 'NVD_DATA/ULME_000', 'NVD_DATA/ULMJ_000', 'NVD_DATA/ULMO_000', 'NVD_DATA/ULMT_000', 'NVD_DATA/ULN8_000', 'CALIBRAT/UL15_001', 'CALIBRAT/HL14_001', 'CALIBRAT/UL1F_000', 'CALIBRAT/UL1Q_000', 'CALIBRAT/ULBU_000'):
    check(ldi(edited[rel])[3] == recs(f'{F21}/eu/nvdata/md/NVRAM/{rel}'), f'{rel}: records = EU (3G LB1 front end / B5 calibration)')

# --- backup (AllFile/AllMap in nvdata, nvram partition)
af = open('nvdata_check/AllFile', 'rb').read(); am = open('nvdata_check/AllMap', 'rb').read()
check(struct.unpack_from('<I', am, 0)[0] == allfile_checksum(af), 'backup checksum in AllMap matches AllFile (MediaTek algorithm)')
uaf = open(f'{base}/AllFile', 'rb').read(); uam = open(f'{base}/AllMap', 'rb').read()
check(am[4:] == uam[4:], 'AllMap: only the 4-byte checksum changed')
ents = {}
for m in re.finditer(rb'/mnt/vendor/nvdata/[\x20-\x7e]+', am):
    t, off, size = struct.unpack_from('<3I', am, m.start() - 12); ents[m.group().decode().replace('/mnt/vendor/nvdata/', '')] = (off, size)
inbk = {k: v for k, v in edited.items() if f'md/NVRAM/{k}' in ents}
check(all(af[ents[f'md/NVRAM/{k}'][0]:ents[f'md/NVRAM/{k}'][0] + len(v)] == v for k, v in inbk.items()), f'AllFile: the {len(inbk)} backed-up edited files equal the live duo files')
rngs = [ents[f'md/NVRAM/{k}'] for k in inbk]
outside = [i for i in range(len(af)) if af[i] != uaf[i] and not any(o <= i < o + s for o, s in rngs)]
check(not outside, f'AllFile: no change outside those files ({len(outside)} stray bytes)')
nv = open('nvram.duo.bin', 'rb').read(); usn = open(f'{F21}/us/nvram.bin', 'rb').read()
check(struct.unpack_from('<3I', nv, 0) == struct.unpack_from('<3I', usn, 0), 'nvram header unchanged (sizes)')
check(nv[12:12 + len(am)] == am and nv[0x20000:0x20000 + len(af)] == af, 'nvram partition holds exactly the duo AllMap and AllFile')
rest = [i for i in range(len(nv)) if nv[i] != usn[i] and not (12 <= i < 12 + len(am) or 0x20000 <= i < 0x20000 + len(af))]
check(not rest, 'nvram: nothing changed outside the AllMap/AllFile areas')
print('\nALL PASS' if ok else '\nSOME CHECKS FAILED')
