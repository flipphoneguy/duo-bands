#!/usr/bin/env python3
# Unpack tmp/tars/{dev}-{set}.tar.xz into the exact tree the build/verify scripts expect:
#   tmp/{dev}/{set}/md1img_a.bin  nvcfg.bin  nvdata.bin  nvram.bin   (tar members)
#   tmp/{dev}/{set}/md1/          split md1img parts (md1rom, cert1md, cert2, md1dsp, ...)
#   tmp/{dev}/{set}/meta.xml      decompressed NVRAM dictionary (md1_mddbmetaodb)
#   tmp/{dev}/{set}/nvdata.work.img   journal-replayed copy of nvdata.bin
#   tmp/{dev}/{set}/nvdata/       debugfs rdump of that image (md/NVRAM/..., AllFile, AllMap)
import os, sys, gzip, shutil, subprocess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(REPO, 'tmp')
SPLIT = os.path.join(REPO, 'scripts', 'lib', 'split_md1img.py')
SETS = [('f21', 'eu'), ('f21', 'us'), ('m5', 'eu'), ('m5', 'us')]

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)

for dev, st in SETS:
    tar = os.path.join(TMP, 'tars', f'{dev}-{st}.tar.xz')
    dst = os.path.join(TMP, dev, st)
    if not os.path.exists(tar):
        print(f'SKIP {dev}/{st}: missing {tar}'); continue
    print(f'=== {dev}/{st} ===')
    shutil.rmtree(dst, ignore_errors=True); os.makedirs(dst)

    run(['tar', '-xJf', tar, '-C', dst])
    run([sys.executable, SPLIT, os.path.join(dst, 'md1img_a.bin'), os.path.join(dst, 'md1')])

    with gzip.open(os.path.join(dst, 'md1', 'md1_mddbmetaodb'), 'rb') as g:
        open(os.path.join(dst, 'meta.xml'), 'wb').write(g.read())

    work = os.path.join(dst, 'nvdata.work.img')
    shutil.copy(os.path.join(dst, 'nvdata.bin'), work)
    run(['e2fsck', '-fy', work])                     # replays the journal (EU sets need it)
    nv = os.path.join(dst, 'nvdata'); os.makedirs(nv)
    run(['debugfs', '-R', f'rdump / {nv}', work])

    need = ('md1/md1rom', 'md1/cert2', 'meta.xml', 'nvdata.work.img',
            'nvdata/md/NVRAM/CALIBRAT/EL03_001', 'nvdata/AllFile', 'nvram.bin')
    ok = all(os.path.exists(os.path.join(dst, p)) for p in need) and \
        any(os.path.exists(os.path.join(dst, 'md1', c)) for c in ('cert1md', 'cert1'))
    print('  ', 'OK' if ok else 'INCOMPLETE')

print('done')
