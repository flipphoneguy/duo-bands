#!/usr/bin/env python3
# Pack the F21 duo images for the app: app/assets/f21duo.tar.xz plus layout.json (sizes, hashes, and where the identity files sit in nvdata and the backup).
import os, sys, json, struct, re, tarfile, lzma, hashlib, shutil
_R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_R, 'scripts', 'lib'))
from ext4blocks import data_blocks, block_size

DUO = os.path.join(_R, 'tmp', 'f21_duo')
OUT = os.path.join(_R, 'app', 'assets')
PARTS = [('md1img_a.bin', 'md1img_a.duo.signed.bin'), ('nvdata.bin', 'nvdata.duo.img'), ('nvram.bin', 'nvram.duo.bin')]
IDENTITY = ['md/NVRAM/NVD_IMEI/LD0B_001', 'APCFG/APRDEB/BT_Addr', 'APCFG/APRDEB/WIFI']
os.makedirs(OUT, exist_ok=True)

img = f'{DUO}/nvdata.duo.img'
am = open(f'{DUO}/AllMap.duo', 'rb').read(); af = open(f'{DUO}/AllFile.duo', 'rb').read()
nv = open(f'{DUO}/nvram.duo.bin', 'rb').read()
assert nv[12:12 + len(am)] == am and nv[0x20000:0x20000 + len(af)] == af, 'nvram.duo.bin does not hold the duo AllMap/AllFile'

ents = {}
for m in re.finditer(rb'/mnt/vendor/nvdata/[\x20-\x7e]+', am):
    t, off, size = struct.unpack_from('<3I', am, m.start() - 12)
    ents[m.group().decode().replace('/mnt/vendor/nvdata/', '')] = (off, size)

layout = {'block_size': block_size(img), 'partitions': [], 'files': {}, 'nvram_allmap_off': 12, 'nvram_allfile_off': 0x20000}
for name, src in PARTS:
    h = hashlib.sha256()
    with open(f'{DUO}/{src}', 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''): h.update(chunk)
    layout['partitions'].append({'name': name, 'size': os.path.getsize(f'{DUO}/{src}'), 'sha256': h.hexdigest()})
for rel in IDENTITY + ['AllFile', 'AllMap']:
    blocks = data_blocks(img, '/' + rel)
    size = {'AllFile': len(af), 'AllMap': len(am)}.get(rel) or ents[rel][1]
    entry = {'size': size, 'blocks': blocks}
    if rel in ents: entry['allfile_off'] = ents[rel][0]
    layout['files'][rel] = entry
json.dump(layout, open(f'{OUT}/layout.json', 'w'), indent=1)
shutil.copy(f'{DUO}/AllFile.duo', f'{OUT}/AllFile.bin')
shutil.copy(f'{DUO}/AllMap.duo', f'{OUT}/AllMap.bin')

# preset 6 keeps the xz dictionary at 8 MiB, small enough for the pure-Java decoder on the phone
with lzma.open(f'{OUT}/f21duo.tar.xz', 'wb', preset=6) as xz, tarfile.open(fileobj=xz, mode='w|', format=tarfile.USTAR_FORMAT) as tar:
    for name, src in PARTS:
        tar.add(f'{DUO}/{src}', arcname=name)
print(json.dumps({k: v for k, v in layout.items() if k != 'files'}, indent=1))
print('identity files:', {k: (v['size'], len(v['blocks'])) for k, v in layout['files'].items()})
print('f21duo.tar.xz', os.path.getsize(f'{OUT}/f21duo.tar.xz'), 'bytes')
