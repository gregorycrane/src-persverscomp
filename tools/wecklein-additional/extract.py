"""Extract OCR notes using reviewed page starts; retain original coordinates."""
import json,re
from pathlib import Path
D=Path(__file__).parent
CONFIG={'persians':{'play':'tlg002','year':'1886','short':'teuffel-wecklein1886-com-ger1','title':'Persians','author':'W. S. Teuffel','editor':'N. Wecklein','scan':'hvd.hw2bkq','first':43,'last':97,'sigil':'Teuff.–Weck.'},'seven':{'play':'tlg004','year':'1902','short':'wecklein1902-com-ger1','title':'Seven Against Thebes','author':'N. Wecklein','scan':'mdp.39015058551444','first':15,'last':100,'sigil':'Weck.'},'suppliants':{'play':'tlg001','year':'1902','short':'wecklein1902-com-ger1','title':'Suppliants','author':'N. Wecklein','scan':'mdp.39015058551436','first':24,'last':120,'sigil':'Weck.'}}
PAT=re.compile(r'^(\d{1,4})(?:\s*[-–—]+\s*(\d{1,4}))?\s*(?:(ff?\.)|[.,:]|(?<=\d)(?=\s+[A-ZÄÖÜ]))\s*')
def extract():
 for name in CONFIG:
  chunks=re.split(r'## p\.\s*(.*?)\s*\(#(\d+)\) #+\n',(D/(name+'.txt')).read_text())
  pages={chunks[i+1]:{'page':chunks[i],'lines':[x.strip() for x in chunks[i+2].splitlines() if x.strip()]} for i in range(1,len(chunks),3)}
  (D/(name+'-pages.json')).write_text(json.dumps(pages,ensure_ascii=False,indent=2))
 bounds=json.loads((D/'boundaries.json').read_text());ed=json.loads((D/'editorial.json').read_text());out={};excluded=[]
 for name,cfg in CONFIG.items():
  pages=json.loads((D/(name+'-pages.json')).read_text());notes=[];prev=1
  for pg,b in bounds[name].items():
   ls=pages[str(b['seq'])]['lines']
   if name=='persians' and int(pg)==cfg['first']:
    notes.append({'n':'1-64','page':pg,'heading':'Parodos (1–64 stated in paragraph)','parts':[],'heading_index':20,'editorial_anchor':True})
   for i in range(b['start'],b.get('end',len(ls))):
    raw=ls[i];s=raw;key=f'{name}:{pg}:{i}';rule=ed.get(key,{})
    if rule.get('skip') or re.fullmatch(r'[\d\W_]+',s) or re.match(r'^(stroph\.|antistr\.|epod\.|Äschylos,|Druck von)',s):
     excluded.append({'source':name,'page':pg,'index':i,'text':raw});continue
    if rule.get('replace') is not None:s=rule['replace']
    matchtext=re.sub(r'^V\.\s*','',s) if name=='persians' else s
    m=PAT.match(matchtext) if name!='persians' or s.startswith('V.') else None
    if not m and (name!='persians' or s.startswith('V.')):
     m=re.match(r'^(\d+)\s*[-–—]+\s*(\d+)()\s+',matchtext)
    if rule.get('not_heading'):m=None
    if m and (name=='persians' or not notes or abs(int(m[1])-prev)<90 or rule.get('heading')):
     n=int(m[1]);end=int(m[2]) if m[2] else n+(1 if m[3]=='f.' else 0)
     if end<n:end=int(str(n)[:-len(m[2])]+m[2])
     label=str(n) if end==n else f'{n}-{end}';prev=n
     notes.append({'n':label,'page':pg,'heading':raw,'heading_index':i,'parts':[]});s=matchtext[m.end():]
    if not notes:
     # Preserve a dislocated opening word in the first note, with explicit audit.
     if name=='suppliants' and s=='Die':excluded.append({'source':name,'page':pg,'index':i,'text':raw,'reason':'dislocated opening word; retained in raw source, placement unresolved'});continue
     raise ValueError((name,pg,i,s))
    notes[-1]['parts'].append({'page':pg,'index':i,'text':s,'raw':raw})
  out[name]=notes;print(name,len(notes),'notes;',notes[-1]['n'])
 (D/'notes.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');(D/'excluded-layout.json').write_text(json.dumps(excluded,ensure_ascii=False,indent=2)+'\n')
 return out
if __name__=='__main__':extract()
