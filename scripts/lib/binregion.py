# MediaTek NVRAM backup checksum (the 4-byte word at the start of AllMap),
# recovered from NVM_CheckData_OneFile in libnvram.so.
import struct

def allfile_checksum(af):
    s = 0; n = len(af) // 4
    for i, w in enumerate(struct.unpack(f'<{n}I', af[:n * 4])):
        s = (s ^ w) if i % 2 == 0 else (s + w) & 0xffffffff
    tail = af[n * 4:]
    if tail:
        s = (s + struct.unpack('<I', tail + b'\0' * (4 - len(tail)))[0]) & 0xffffffff
    return s ^ (len(af) & 0xffffffff)
