# Leitor de .lxo (Modo): itens, canais, camadas (PNTS/POLS/PTAG/VMAP) — use com exec() nos scripts do Blender.
# Uso: LXO=arquivo.lxo; exec(open('lxo_parse.py').read())
import struct
d=open(__import__('os').environ.get('LXO','model.lxo'),'rb').read()
def cstr(b,o):
    e=b.index(b'\0',o); s=b[o:e]; e+=1
    if (e-o)%2: e+=1
    return s.decode('utf8','replace'),e
chnm=[];items=[];layers=[];cur=None;tags=[]
i=12
while i<len(d)-8:
    tag=d[i:i+4]; n=struct.unpack('>I',d[i+4:i+8])[0]; b=d[i+8:i+8+n]
    if tag==b'CHNM':
        o=4
        while o<n:
            s,o=cstr(b,o); chnm.append(s)
    elif tag==b'TAGS':
        o=0
        while o<n: s,o=cstr(b,o); tags.append(s)
    elif tag==b'LAYR':
        cur={'idx':struct.unpack('>H',b[0:2])[0],'name':cstr(b,16)[0],'chunks':[]}; layers.append(cur)
    elif tag in (b'PNTS',b'POLS',b'VMAP',b'VMAD',b'PTAG',b'BBOX') and cur is not None:
        cur['chunks'].append((tag.decode(),b))
    elif tag==b'ITEM':
        typ,o=cstr(b,0); name,o=cstr(b,o); ref=struct.unpack('>I',b[o:o+4])[0]; o+=4
        it={'id':ref,'type':typ,'name':name,'links':[],'ch':{},'raw':[]}
        while o+6<=n:
            st=b[o:o+4].decode('latin1'); sn=struct.unpack('>H',b[o+4:o+6])[0]; sb=b[o+6:o+6+sn]
            try:
                if st=='CHAN':
                    ci,ct=struct.unpack('>HH',sb[:4]); v=sb[4:]; t=ct&0xff
                    if t in(1,0x21): val=struct.unpack('>i',v[:4])[0]
                    elif t in(2,0x22): val=struct.unpack('>f',v[:4])[0]
                    elif t in(3,0x23): val=v.split(b'\0')[0].decode('utf8','replace')
                    else: val=('?',hex(ct),v)
                    it['ch'][chnm[ci] if ci<len(chnm) else ci]=val
                elif st=='CHNV':
                    nm,o2=cstr(sb,0); dt,dims=struct.unpack('>HH',sb[o2:o2+4]); o2+=4; vals=[]
                    while o2+6<=len(sb):
                        sub,o3=cstr(sb,o2); vals.append((sub,struct.unpack('>f',sb[o3:o3+4])[0])); o2=o3+4
                    it['ch'][nm]=vals
                elif st=='LINK':
                    ln,o2=cstr(sb,0); it['links'].append((ln,)+struct.unpack('>II',sb[o2:o2+8]))
                else: it['raw'].append((st,sb))
            except Exception as e:
                it['raw'].append((st+'!',sb))
            o+=6+sn+(sn&1)
        items.append(it)
    i+=8+n+(n&1)
byid={it['id']:it for it in items}
