import struct,sys,os
src,out=sys.argv[1],sys.argv[2]; os.makedirs(out,exist_ok=True)
d=open(src,'rb').read(); off=0
while off<len(d):
    magic,size=struct.unpack_from('<II',d,off)
    if magic!=0x58881688: break
    name=d[off+8:off+40].split(b'\0')[0].decode(); hdr=struct.unpack_from('<I',d,off+0x34)[0]
    fn=name if not os.path.exists(f'{out}/{name}') else name+'_'+hex(off)
    open(f'{out}/{fn}','wb').write(d[off+hdr:off+hdr+size]); off=(off+hdr+size+15)&~15
