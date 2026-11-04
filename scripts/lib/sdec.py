import re,struct
class Dict:
    def __init__(s,xml):
        t=open(xml).read(); s.structs={}; s.enums={}; s.lids={}
        for m in re.finditer(r'<Struct name="([^"]+)" size="(\d+)">(.*?)</Struct>',t,re.S):
            fl=[dict(re.findall(r'(\w+)="([^"]*)"',f)) for f in re.findall(r'<Field ([^>]*)/>',m[3])]
            s.structs[m[1]]=(int(m[2]),fl)
        for m in re.finditer(r'<Enum name="([^"]+)" size="\d+">(.*?)</Enum>',t,re.S):
            s.enums[m[1]]={int(v):k for k,v in re.findall(r'key="([^"]+)" value="(-?\d+)"',m[2])}
        for m in re.finditer(r'<NVRAM_LID name="([^"]+)" id="(\d+)" record_count="\d+" version="\d+" type_name="([^"]*)"',t):
            s.lids[int(m[2])]=(m[1],m[3])
        s.td={m[1]:m[2] for m in re.finditer(r'<Typedef name="([^"]+)" defined_type_name="([^"]+)"',t)}
    def flat(s,tname,b,pre=''):
        out=[]
        while tname not in s.structs and tname in getattr(s,'td',{}): tname=s.td[tname]
        if tname not in s.structs: return [(pre or tname,b.hex())]
        _,fl=s.structs[tname]
        for f in fl:
            off,size=int(f['offset']),int(f['size']); dims=[int(x) for x in f.get('array_sizes','').split(',') if x] if f.get('array_sizes') else []
            n=1
            for x in dims: n*=x
            es=size//n if n else size
            for i in range(n):
                nm=f"{pre}{f['name']}"+(f"[{i}]" if n>1 else '')
                chunk=b[off+i*es:off+(i+1)*es]
                ty=f.get('type','')
                if ty=='struct' or (f.get('type_name') in s.structs or f.get('type_name') in s.td and f.get('type')!='enum' and int(f['size'])>4): out+=s.flat(f.get('type_name',''),chunk,nm+'.')
                elif es in (1,2,4) and len(chunk)==es:
                    v=int.from_bytes(chunk,'little')
                    if ty=='enum' and f.get('type_name') in s.enums: v=s.enums[f['type_name']].get(v,v)
                    out.append((nm,v))
                else: out.append((nm,chunk.hex()))
        return out
