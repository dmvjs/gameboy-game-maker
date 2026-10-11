import zlib, struct
def read(path):
    d=open(path,'rb').read(); assert d[:8]==b'\x89PNG\r\n\x1a\n'
    i=8; idat=b''; plte=None; trns=None
    while i<len(d):
        n,t=struct.unpack('>I4s',d[i:i+8]); c=d[i+8:i+8+n]; i+=12+n
        if t==b'IHDR': w,h,bd,ct,_,_,il=struct.unpack('>IIBBBBB',c)
        elif t==b'IDAT': idat+=c
        elif t==b'PLTE': plte=c
        elif t==b'tRNS': trns=c
    assert bd==8 and il==0, (bd,il)
    ch={2:3,6:4,0:1,4:2,3:1}[ct]; raw=zlib.decompress(idat); st=w*ch
    out=[]; prev=bytearray(st); p=0
    for y in range(h):
        f=raw[p]; line=bytearray(raw[p+1:p+1+st]); p+=1+st
        for x in range(st):
            a=line[x-ch] if x>=ch else 0; b=prev[x]; c=prev[x-ch] if x>=ch else 0
            if f==1: line[x]=(line[x]+a)&255
            elif f==2: line[x]=(line[x]+b)&255
            elif f==3: line[x]=(line[x]+((a+b)>>1))&255
            elif f==4:
                pp=a+b-c; pa,pb,pc=abs(pp-a),abs(pp-b),abs(pp-c)
                line[x]=(line[x]+(a if pa<=pb and pa<=pc else b if pb<=pc else c))&255
        prev=line
        row=[]
        for x in range(w):
            px=line[x*ch:x*ch+ch]
            if ct==2: row.append((px[0],px[1],px[2],255))
            elif ct==6: row.append(tuple(px))
            elif ct==3: k=px[0]; row.append((plte[3*k],plte[3*k+1],plte[3*k+2],trns[k] if trns and k<len(trns) else 255))
            else: row.append((px[0],)*3+(255 if ct==0 else px[1],))
        out.append(row)
    return w,h,out
def write(path,w,h,rows):
    raw=b''.join(b'\0'+bytes(v for p in r for v in p) for r in rows)
    ck=lambda t,c: struct.pack('>I',len(c))+t+c+struct.pack('>I',zlib.crc32(t+c)&0xffffffff)
    open(path,'wb').write(b'\x89PNG\r\n\x1a\n'+ck(b'IHDR',struct.pack('>IIBBBBB',w,h,8,6,0,0,0))+ck(b'IDAT',zlib.compress(raw,9))+ck(b'IEND',b''))
