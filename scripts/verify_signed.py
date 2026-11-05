#!/usr/bin/env python3
# Independent check of md1img_a.duo.signed.bin: re-parse from scratch, walk the chain against the
# kaios root, confirm only the two cert regions changed, and that md1dsp's untouched chain still validates.
import sys, hashlib, struct, re
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import os
dev = sys.argv[1]
_R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(_R, 'tmp')
duo = os.path.join(BASE, f'{dev}_duo')
SET = {'f21': 'us', 'm5': 'eu'}[dev]
C1 = 'cert1md' if os.path.exists(f'{BASE}/{dev}/{SET}/md1/cert1md') else 'cert1'
kaios_pub = serialization.load_pem_private_key(open(os.path.join(_R, 'keystore', 'kaios_da_privkey.pem'), 'rb').read(), None).public_key()
MODPAT = b'\x02\x82\x01\x01\x00'; OIDH = bytes.fromhex('060760867693160201')
ok = True
def ck(c, m):
    global ok; print(('PASS ' if c else 'FAIL ') + m); ok &= bool(c)
def lv(d, i):
    b = d[i]; i += 1
    if b < 0x80: return b, i
    n = b & 0x7f; return int.from_bytes(d[i:i + n], 'big'), i + n
def split(d):
    _, i = lv(d, 1); tl, j = lv(d, i + 1); t0, t1 = i, j + tl
    k = t1; al, m = lv(d, k + 1); k = m + al; sl, n = lv(d, k + 1)
    return d[t0:t1], d[n + 1:n + sl]
def pss_ok(mod, sig, tbs):
    try: rsa.RSAPublicNumbers(65537, mod).public_key().verify(sig, tbs, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256()); return True
    except Exception: return False
def parts(d):
    off = 0; out = []
    while off < len(d):
        mg, sz = struct.unpack_from('<II', d, off)
        if mg != 0x58881688: break
        nm = d[off + 8:off + 40].split(b'\0')[0].decode(); hd = struct.unpack_from('<I', d, off + 0x34)[0]
        out.append((nm, off + hd, sz)); off = (off + hd + sz + 15) & ~15
    return out

sgn = open(f'{duo}/md1img_a.duo.signed.bin', 'rb').read()
duoimg = open(f'{duo}/md1img_a.duo.bin', 'rb').read()
ck(len(sgn) == len(duoimg), 'signed md1img same size as unsigned duo')

allp = parts(sgn)
c1o, c1s = next((o, s) for n, o, s in allp if n == C1)
# md1rom's cert2 = the first cert2 in the file (adjacent to cert1md)
c2o, c2s = next((o, s) for n, o, s in allp if n == 'cert2')
diff = [i for i in range(len(sgn)) if sgn[i] != duoimg[i]]
inside = lambda i: (c1o <= i < c1o + c1s) or (c2o <= i < c2o + c2s)
ck(all(inside(i) for i in diff), f'all {len(diff)} changed bytes are within {C1} or the first cert2')

# md1rom in the signed image is exactly the duo md1rom
romo, roms = next((o, s) for n, o, s in allp if n == 'md1rom')
rom = sgn[romo:romo + roms]
ck(rom == open(f'{duo}/md1rom.duo', 'rb').read(), 'md1rom in signed image == md1rom.duo')

# walk the chain purely from the image bytes
c1 = sgn[c1o:c1o + c1s]; c2 = sgn[c2o:c2o + c2s]
tbs1, sig1 = split(c1); tbs2, sig2 = split(c2)
k0 = int.from_bytes(c1[re.search(re.escape(MODPAT), c1).end():][:256], 'big')
mpos = [m.end() for m in re.finditer(re.escape(MODPAT), c1)]
inter_mod = int.from_bytes(c1[mpos[1]:mpos[1] + 256], 'big')
ck(k0 == kaios_pub.public_numbers().n, f'{C1} key0 == kaios root')
ck(pss_ok(kaios_pub.public_numbers().n, sig1, tbs1), f'kaios root signature over {C1} is valid')
ck(pss_ok(inter_mod, sig2, tbs2), f'intermediate (from {C1}) signature over cert2 is valid')
hi = c2.find(OIDH) + len(OIDH) + 3
ck(c2[hi:hi + 32] == hashlib.sha256(rom + b'\0' * ((-len(rom)) % 16)).digest(), 'cert2 img-hash == sha256(md1rom in image, padded)')

# the untouched md1dsp chain (its own cert1 + cert2 copies) is unchanged and self-consistent
# cert copies after md1dsp: find the 'cert1'/'cert2' that follow the md1dsp part
names = [n for n, o, s in allp]
di = names.index('md1dsp')
dsp_c1 = next((o, s) for n, o, s in allp[di:] if n == 'cert1')
dsp_c2 = next((o, s) for n, o, s in allp[di:] if n == 'cert2')
eu = open(f'{BASE}/{dev}/{SET}/md1img_a.bin', 'rb').read()
ck(sgn[dsp_c1[0]:dsp_c1[0] + dsp_c1[1]] == eu[dsp_c1[0]:dsp_c1[0] + dsp_c1[1]], f"md1dsp's cert1 untouched (== {SET.upper()})")
dc1 = sgn[dsp_c1[0]:dsp_c1[0] + dsp_c1[1]]; dc2 = sgn[dsp_c2[0]:dsp_c2[0] + dsp_c2[1]]
dt1, ds1 = split(dc1); dt2, ds2 = split(dc2)
dk0 = int.from_bytes(dc1[re.search(re.escape(MODPAT), dc1).end():][:256], 'big')
dmp = [m.end() for m in re.finditer(re.escape(MODPAT), dc1)]
dkey1 = int.from_bytes(dc1[dmp[1]:dmp[1] + 256], 'big')
ck(pss_ok(dk0, ds1, dt1) and pss_ok(dkey1, ds2, dt2), "md1dsp chain still validates (original key1, unchanged)")
dsp_o, dsp_s = next((o, s) for n, o, s in allp if n == 'md1dsp'); dsp = sgn[dsp_o:dsp_o + dsp_s]
hj = dc2.find(OIDH) + len(OIDH) + 3
ck(dc2[hj:hj + 32] == hashlib.sha256(dsp + b'\0' * ((-len(dsp)) % 16)).digest(), "md1dsp's cert2 hash matches md1dsp (unchanged)")

print('\nALL PASS' if ok else '\nSOME CHECKS FAILED')
