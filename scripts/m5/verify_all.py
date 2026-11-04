#!/usr/bin/env python3
# Independent verification of the duo md1img, nvdata and nvram images.
import os, struct, hashlib, subprocess, shutil, json, sys
_R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_R, 'scripts', 'lib'))
from sdec import Dict

F21 = os.path.join(_R, 'tmp', 'm5')
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

# --- md1img
eu_img = open(f'{F21}/eu/md1img_a.bin', 'rb').read()
duo_rom = open('md1rom.duo', 'rb').read()
img = bytearray(eu_img); img[0x200:0x200 + len(duo_rom)] = duo_rom
open('md1img_a.duo.bin', 'wb').write(img)
check(len(img) == len(eu_img) and struct.unpack_from('<I', img, 4)[0] == len(duo_rom), 'md1img same size, md1rom header size matches')
check(img[:0x200] == eu_img[:0x200] and img[0x200 + len(duo_rom):] == eu_img[0x200 + len(duo_rom):], 'md1img: only the md1rom body differs from EU')
shutil.rmtree('split_check', ignore_errors=True)
subprocess.run([sys.executable, os.path.join(_R, 'scripts', 'lib', 'split_md1img.py'), 'md1img_a.duo.bin', 'split_check'], check=True)
check(open('split_check/md1rom', 'rb').read() == duo_rom, 'md1img splits back into the patched md1rom')
for f in os.listdir('split_check'):
    if f != 'md1rom':
        check(open(f'split_check/{f}', 'rb').read() == open(f'{F21}/eu/md1/{f}', 'rb').read(), f'md1img part {f} identical to EU')

# --- nvdata filesystem
r = subprocess.run(['e2fsck', '-fn', 'nvdata.duo.img'], capture_output=True, text=True)
check(r.returncode == 0, f'e2fsck clean on nvdata.duo.img (exit {r.returncode})')
shutil.rmtree('nvdata_check', ignore_errors=True); os.makedirs('nvdata_check')
subprocess.run(['debugfs', '-R', 'rdump / nvdata_check', 'nvdata.duo.img'], capture_output=True)
log = json.load(open('nvdata_patch_log.json'))
edited = {}
for f in os.listdir('.'):
    for d in ('CALIBRAT', 'NVD_DATA'):
        if f.startswith(f'files_{d}_'):
            edited[f'{d}/' + f[len(f'files_{d}_'):]] = open(f, 'rb').read()
base = f'{F21}/eu/nvdata'
same = differ = 0; unexpected = []
for root, _, fs in os.walk(base):
    for f in fs:
        rel = os.path.relpath(os.path.join(root, f), base)
        a = open(os.path.join(root, f), 'rb').read(); b = open(os.path.join('nvdata_check', rel), 'rb').read()
        key = rel.replace('md/NVRAM/', '', 1)
        if key in edited:
            check(b == edited[key], f'{key}: content equals intended patch'); differ += 1
        elif a == b: same += 1
        elif rel in ('AllFile', 'AllMap'): pass
        else: unexpected.append(rel)
check(not unexpected, f'all {same} other nvdata files byte-identical to EU (unexpected: {unexpected})')
for key in edited:
    p = f'/md/NVRAM/{key}'
    s1 = subprocess.run(['debugfs', '-R', f'stat {p}', f'{F21}/eu/nvdata.work.img'], capture_output=True, text=True).stdout
    s2 = subprocess.run(['debugfs', '-R', f'stat {p}', 'nvdata.duo.img'], capture_output=True, text=True).stdout
    strip = lambda s: [l for l in s.splitlines() if not any(w in l for w in ('ctime', 'atime', 'mtime', 'crtime', 'Inode checksum'))]
    check(strip(s1) == strip(s2), f'{key}: inode metadata (owner, mode, size, xattrs, blocks) unchanged')

# --- record checksums and content of edited files
DE = Dict(f'{F21}/eu/meta.xml')
for key, raw in edited.items():
    lid, n, sz, recs, chks = ldi(raw)
    good = all(c == (mx(r) if any(r) else cs16(r)) or c == mx(r) for r, c in zip(recs, chks))
    check(good, f'{key}: every record checksum valid')
    check(raw[:0x40] == open(f'{F21}/eu/nvdata/md/NVRAM/{key}', 'rb').read()[:0x40], f'{key}: LDI header unchanged')

def lidraw(rel): return edited[rel]
lid, n, sz, recs, _ = ldi(lidraw('CALIBRAT/EL03_001'))
bands = struct.unpack('<25H', recs[0])
check(list(bands[:20]) == [1,3,0,5,7,8,20,28,38,39,40,41,2,4,12,13,17,29,50,55], f'band indicator {bands[:20]}')
US_SLOT = [0, 1, 4, 5, 6, 7, 8, 9]
for rel in ('CALIBRAT/EA10_001', 'CALIBRAT/EA40_001', 'CALIBRAT/EA50_001'):
    _, _, _, recs, _ = ldi(lidraw(rel)); _, _, _, urecs, _ = ldi(open(f'{F21}/us/nvdata/md/NVRAM/{rel}', 'rb').read())
    _, _, _, erecs, _ = ldi(open(f'{F21}/eu/nvdata/md/NVRAM/{rel}', 'rb').read())
    check(all(recs[i] == erecs[i] for i in range(12)) and all(recs[12 + k] == urecs[u] for k, u in enumerate(US_SLOT)), f'{rel}: slots 0-11 EU, 12-19 = US calibration (B29 TX empty as in US)')
for rel, off, want in (('CALIBRAT/EL90_001', 980, [1,3,5,7,8,20,28,38,39,40,41,2,4,12,13,17,29,50,55]), ('CALIBRAT/EL92_001', 4, [1,3,5,7,8,20,28,38,39,40,41,2,4,12,13,17,50,55])):
    _, _, _, recs, _ = ldi(lidraw(rel))
    got = [struct.unpack_from('<H', r, off)[0] for r in recs[:len(want)]]
    check(got == want, f'{rel}: band order {got}')
_, _, _, recs, _ = ldi(lidraw('CALIBRAT/EL91_001'))
check([struct.unpack_from('<HHHH', recs[k], 4) for k in range(7)] == [(0,0,260,260),(1,1,0,0),(3,3,1,1),(7,7,3,3),(2,2,11,11),(4,4,12,12),(50,50,17,16)], 'IIP2: EU 0-3, then B2 (11,11), B4 (12,12), B66 (RX 17, TX 16)')

# --- backup (AllFile/AllMap in nvdata, nvram partition)
sys.path.insert(0, os.path.join(_R, 'scripts', 'lib'))
from binregion import allfile_checksum
import re
af = open('nvdata_check/AllFile', 'rb').read(); am = open('nvdata_check/AllMap', 'rb').read()
check(struct.unpack_from('<I', am, 0)[0] == allfile_checksum(af), 'backup checksum in AllMap matches AllFile (MediaTek algorithm)')
eaf = open(f'{F21}/eu/nvdata/AllFile', 'rb').read(); eam = open(f'{F21}/eu/nvdata/AllMap', 'rb').read()
check(am[4:] == eam[4:], 'AllMap: only the 4-byte checksum changed')
ents = {}
for m in re.finditer(rb'/mnt/vendor/nvdata/[\x20-\x7e]+', am):
    t, off, size = struct.unpack_from('<3I', am, m.start() - 12); ents[m.group().decode().replace('/mnt/vendor/nvdata/', '')] = (off, size)
inbk = {k: v for k, v in edited.items() if f'md/NVRAM/{k}' in ents}
check(all(af[ents[f'md/NVRAM/{k}'][0]:ents[f'md/NVRAM/{k}'][0] + len(v)] == v for k, v in inbk.items()), f'AllFile: the {len(inbk)} backed-up edited files equal the live duo files')
ranges = [ents[f'md/NVRAM/{k}'] for k in inbk]
outside = [i for i in range(len(af)) if af[i] != eaf[i] and not any(o <= i < o + s for o, s in ranges)]
check(not outside, f'AllFile: no change outside those files ({len(outside)} stray bytes)')
nv = open('nvram.duo.bin', 'rb').read(); eun = open(f'{F21}/eu/nvram.bin', 'rb').read()
check(struct.unpack_from('<3I', nv, 0) == struct.unpack_from('<3I', eun, 0), 'nvram header unchanged (sizes)')
check(nv[12:12 + len(am)] == am and nv[0x20000:0x20000 + len(af)] == af, 'nvram partition holds exactly the duo AllMap and AllFile')
rest = [i for i in range(len(nv)) if nv[i] != eun[i] and not (12 <= i < 12 + len(am) or 0x20000 <= i < 0x20000 + len(af))]
check(not rest, 'nvram: nothing changed outside the AllMap/AllFile areas')
print('\nALL PASS' if ok else '\nSOME CHECKS FAILED')
