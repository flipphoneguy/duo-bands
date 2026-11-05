#!/usr/bin/env python3
# Path B re-sign: rebuild the md1rom cert chain of a duo md1img so it validates to the
# kaios test root we hold. Generates a fresh intermediate key, keeps every field the same size.
#
#   kaios(root, we have priv) --signs--> cert1md(embeds intermediate pub) --> intermediate --signs--> cert2(md1rom hash)
#
# Only cert1md and the first cert2 (md1rom's pair) are touched. md1dsp/md1drdi certs stay original & valid.
import sys, hashlib, struct, re
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import os
dev = sys.argv[1]                       # f21 | m5
_R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(_R, 'tmp')
duo = os.path.join(BASE, f'{dev}_duo')
SET = {'f21': 'us', 'm5': 'eu'}[dev]    # the set each duo is built on
MD1 = f'{BASE}/{dev}/{SET}/md1'
C1 = 'cert1md' if os.path.exists(f'{MD1}/cert1md') else 'cert1'   # md1rom's first cert (US F21 names it cert1)
kaios = serialization.load_pem_private_key(open(os.path.join(_R, 'keystore', 'kaios_da_privkey.pem'), 'rb').read(), None)

# OID 2.16.886.2454.2.1 (the md1rom-hash field inside cert2)
OID_IMGHASH = bytes.fromhex('060760867693160201')
MODPAT = b'\x02\x82\x01\x01\x00'         # INTEGER len 257, leading 0x00, then 256-byte modulus

def der_lv(d, i):                       # return (length, index-after-length-bytes)
    b = d[i]; i += 1
    if b < 0x80: return b, i
    n = b & 0x7f; return int.from_bytes(d[i:i + n], 'big'), i + n

def split_cert(d):                      # -> (tbs_bytes, tbs_start, tbs_end, sig_start, sig_len)
    assert d[0] == 0x30; _, i = der_lv(d, 1)
    assert d[i] == 0x30; tl, j = der_lv(d, i + 1); tbs0, tbs1 = i, j + tl   # tbs = SEQUENCE incl header
    k = tbs1
    assert d[k] == 0x30; al, m = der_lv(d, k + 1); k = m + al                # sigAlg
    assert d[k] == 0x03; sl, n = der_lv(d, k + 1)                            # signature BIT STRING
    return d[tbs0:tbs1], tbs0, tbs1, n + 1, sl - 1                           # +1 skips unused-bits byte

def pss_sign(priv, tbs):
    return priv.sign(tbs, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())

def pss_ok(pub, sig, tbs):
    try: pub.verify(sig, tbs, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256()); return True
    except Exception: return False

# --- new intermediate key, 2048-bit so its modulus is exactly 256 bytes (same slot size)
while True:
    inter = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    imod = inter.public_key().public_numbers().n.to_bytes(256, 'big')
    if imod[0] & 0x80: break            # top bit set -> encodes without an extra leading byte

# ---------- cert1md: swap key1's modulus for the intermediate's, re-sign with kaios ----------
c1 = bytearray(open(f'{MD1}/{C1}', 'rb').read())
mpos = [m.end() for m in re.finditer(re.escape(MODPAT), c1)]
assert len(mpos) == 2, f'expected 2 keys in {C1}, found {len(mpos)}'
c1[mpos[0]:mpos[0] + 256] = kaios.public_key().public_numbers().n.to_bytes(256, 'big')   # root slot = kaios (already so on EU, a key we don't hold on US)
key1_off = mpos[1]                       # second embedded key = intermediate slot
c1[key1_off:key1_off + 256] = imod
tbs, t0, t1, so, sl = split_cert(bytes(c1))
assert sl == 256
c1[so:so + 256] = pss_sign(kaios, tbs)
cert1md_new = bytes(c1)
assert pss_ok(kaios.public_key(), cert1md_new[so:so + 256], cert1md_new[t0:t1]), 'cert1md re-sign failed'

# ---------- cert2 (first copy = md1rom's): set duo md1rom hash, re-sign with intermediate ----------
c2 = bytearray(open(f'{MD1}/cert2', 'rb').read())
rom = open(f'{duo}/md1rom.duo', 'rb').read()
rom_pad = rom + b'\0' * ((-len(rom)) % 16)
newhash = hashlib.sha256(rom_pad).digest()
oi = c2.find(OID_IMGHASH); assert oi != -1, 'img-hash OID not found'
bi = oi + len(OID_IMGHASH)
assert c2[bi] == 0x03 and c2[bi + 1] == 0x21 and c2[bi + 2] == 0x00  # BIT STRING, 33, unused=0
c2[bi + 3:bi + 3 + 32] = newhash
tbs2, t20, t21, so2, sl2 = split_cert(bytes(c2))
assert sl2 == 256
c2[so2:so2 + 256] = pss_sign(inter, tbs2)
cert2_new = bytes(c2)

# ---------- verify the full chain ----------
kpub = kaios.public_key(); ipub = inter.public_key()
ok_root = pss_ok(kpub, cert1md_new[so:so + 256], cert1md_new[t0:t1])
inter_mod = int.from_bytes(imod, 'big')
mpos2 = [m.end() for m in re.finditer(re.escape(MODPAT), cert1md_new)]
embedded_inter = int.from_bytes(cert1md_new[mpos2[1]:mpos2[1] + 256], 'big')
ok_embed = embedded_inter == inter_mod
ok_leaf = pss_ok(ipub, cert2_new[so2:so2 + 256], cert2_new[t20:t21])
hi = cert2_new.find(OID_IMGHASH) + len(OID_IMGHASH) + 3
ok_hash = cert2_new[hi:hi + 32] == newhash
print(f'[{dev}] root(kaios)->cert1md sig: {ok_root}')
print(f'[{dev}] cert1md embeds our intermediate pub: {ok_embed}')
print(f'[{dev}] intermediate->cert2 sig: {ok_leaf}')
print(f'[{dev}] cert2 holds sha256(duo md1rom padded): {ok_hash}')
assert all((ok_root, ok_embed, ok_leaf, ok_hash))

# sizes must be identical so md1img layout is untouched
assert len(cert1md_new) == len(open(f'{MD1}/{C1}', 'rb').read())
assert len(cert2_new) == len(open(f'{MD1}/cert2', 'rb').read())

# ---------- splice into the duo md1img at the original offsets ----------
img = bytearray(open(f'{duo}/md1img_a.duo.bin', 'rb').read())
def part_offsets(d):
    off = 0; parts = []
    while off < len(d):
        magic, size = struct.unpack_from('<II', d, off)
        if magic != 0x58881688: break
        name = d[off + 8:off + 40].split(b'\0')[0].decode(); hdr = struct.unpack_from('<I', d, off + 0x34)[0]
        parts.append((name, off + hdr, size)); off = (off + hdr + size + 15) & ~15
    return parts
parts = part_offsets(img)
c1_off = next(o for n, o, s in parts if n == C1)          # first one = md1rom's
c2_off = next(o for n, o, s in parts if n == 'cert2')      # first cert2 = md1rom's
assert img[c1_off:c1_off + len(cert1md_new)] == open(f'{MD1}/{C1}', 'rb').read()
img[c1_off:c1_off + len(cert1md_new)] = cert1md_new
img[c2_off:c2_off + len(cert2_new)] = cert2_new
open(f'{duo}/md1img_a.duo.signed.bin', 'wb').write(img)
serialization_pem = inter.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption())
open(f'{duo}/intermediate_privkey.pem', 'wb').write(serialization_pem)
open(f'{duo}/cert1md.signed', 'wb').write(cert1md_new); open(f'{duo}/cert2.signed', 'wb').write(cert2_new)
print(f'[{dev}] md1img size unchanged: {len(img) == len(open(f"{duo}/md1img_a.duo.bin","rb").read())}; wrote md1img_a.duo.signed.bin')
