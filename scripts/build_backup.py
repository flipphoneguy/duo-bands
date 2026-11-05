#!/usr/bin/env python3
# Rebuild the NVRAM backup (AllFile/AllMap in nvdata, and the nvram partition) for a duo build:
# copy the patched live files into AllFile, recompute the AllMap checksum, mirror both into nvram.
import struct, re, sys, json, os
_R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_R, 'scripts', 'lib'))
from binregion import allfile_checksum
from ext4blocks import write_file

dev = sys.argv[1]                            # f21 | m5
base = os.path.join(_R, 'tmp', dev, {'f21': 'us', 'm5': 'eu'}[dev])   # the set each duo is built on
duo = os.path.join(_R, 'tmp', f'{dev}_duo')
am = bytearray(open(f'{base}/nvdata/AllMap', 'rb').read())
af = bytearray(open(f'{base}/nvdata/AllFile', 'rb').read())
log = []

# the patched files of this duo build
edited = {}
for d in ('CALIBRAT', 'NVD_DATA'):
    import os
    for f in os.listdir(duo):
        if f.startswith(f'files_{d}_'):
            edited[f'md/NVRAM/{d}/' + f[len(f'files_{d}_'):]] = open(f'{duo}/{f}', 'rb').read()

entries = {}
for m in re.finditer(rb'/mnt/vendor/nvdata/[\x20-\x7e]+', am):
    typ, off, size = struct.unpack_from('<3I', am, m.start() - 12)
    entries[m.group().decode().replace('/mnt/vendor/nvdata/', '')] = (off, size)

for rel, data in edited.items():
    if rel not in entries:
        log.append(f'{rel}: not part of the backup'); continue
    off, size = entries[rel]
    assert size == len(data), rel
    assert af[off:off + size] == open(f'{base}/nvdata/{rel}', 'rb').read(), f'{rel}: backup copy differs from live original'
    af[off:off + size] = data
    log.append(f'{rel}: backup copy replaced at AllFile offset {off:#x}')

old = struct.unpack_from('<I', am, 0)[0]
new = allfile_checksum(bytes(af))
struct.pack_into('<I', am, 0, new)
log.append(f'AllMap checksum {old:#010x} -> {new:#010x}')

# nvdata image: overwrite AllFile and AllMap data blocks in place (sizes unchanged)
for name, data in (('AllFile', af), ('AllMap', am)):
    write_file(f'{duo}/nvdata.duo.img', f'/{name}', bytes(data))

# nvram partition: header (sizes) + AllMap at 12 + AllFile at 0x20000
nv = bytearray(open(f'{base}/nvram.bin', 'rb').read())
assert struct.unpack_from('<2I', nv, 0) == (len(am), len(af))
nv[12:12 + len(am)] = am
nv[0x20000:0x20000 + len(af)] = af
open(f'{duo}/nvram.duo.bin', 'wb').write(nv)
open(f'{duo}/AllFile.duo', 'wb').write(af); open(f'{duo}/AllMap.duo', 'wb').write(am)
json.dump(log, open(f'{duo}/backup_log.json', 'w'), indent=1)
print('\n'.join(log))
