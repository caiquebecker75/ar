exec(open('lxo_parse.py').read().split("import collections")[0])
import re
def txt(sb): return ' '.join(m.decode() for m in re.findall(rb'[ -~]{2,}', sb))
for it in items:
    if it['type']=='mask' and it['id']>=229:
        print('MASK', it['id'], [ (st, txt(sb)[:80]) for st,sb in it['raw'] ][:12], {k:v for k,v in it['ch'].items() if isinstance(v,(str,int)) and k not in ('blend',)})
    if it['type']=='txtrLocator' and 14<=it['id']<=31:
        ch=it['ch']
        m=[round(ch.get(k,0),4) if isinstance(ch.get(k,0),float) else ch.get(k) for k in ('m00','m01','m02','m10','m11','m12','m20','m21','m22')]
        xf=[(x['type'], {k:v for k,v in x['ch'].items() if isinstance(v,list)}) for x in items if x['type'] in('translation','scale','rotation') and any(l[1]==it['id'] for l in x['links'])]
        print('LOC', it['id'], ch.get('projType'), 'axis', ch.get('projAxis'), 'size', ch.get('size'), 'm', m, 'xf', xf, 'links', it['links'])
