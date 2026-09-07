"""Conservative Wecklein–Allen OCR draft. No automatic word substitutions.
Inputs: archived 1893 text, reviewed boundaries, 1891 PDF bbox extraction.
Word occurrence comparison is page-local; it is not a critical collation.
"""
import json,re,unicodedata,hashlib,collections,argparse
from pathlib import Path
from lxml import etree as E
D=Path(__file__).parent;NS='http://www.tei-c.org/ns/1.0';N={'t':NS};XML='{http://www.w3.org/XML/1998/namespace}'
SHORT='wecklein-allen1893-com-eng1';WORK='urn:cts:greekLit:tlg0085.tlg003';URN=WORK+'.'+SHORT

def norm(s):return ''.join(c for c in unicodedata.normalize('NFD',s.lower().replace('ς','σ')) if c.isalnum())
def greek(s):return ''.join(c for c in norm(s) if '\u03b1'<=c<='\u03c9')
def node(p,t,s=None,**a):
 x=E.SubElement(p,'{'+NS+'}'+t,a);x.text=s;return x
def append(p,s):
 if len(p):p[-1].tail=(p[-1].tail or '')+s
 else:p.text=(p.text or '')+s

def build(canonical,out):
 pages={int(x['seq']):x for x in json.loads((D/'pages1893.json').read_text())};bounds=json.loads((D/'boundaries.json').read_text());sec=json.loads((D/'secondary-columns.json').read_text())
 ref=E.parse(str(canonical));refs={x.get('n'):''.join(x.itertext()) for x in ref.xpath('//t:l',namespaces=N)};order={n:i for i,n in enumerate(refs)}
 refnorm={n:greek(t) for n,t in refs.items()}; pagegreek={pg:greek(' '.join(pages[b['seq']]['lines'][:b['start']])) for pg,b in bounds.items()}; hits={pg:[n for n,t in refnorm.items() if len(t)>=18 and t in pagegreek[pg]] for pg in bounds}
 root=E.Element('{'+NS+'}TEI',nsmap={None:NS});hd=node(root,'teiHeader');fd=node(hd,'fileDesc');ts=node(fd,'titleStmt')
 node(ts,'title','Prometheus Bound: N. Wecklein, translated by F. D. Allen (1893; compared with 1891), English commentary OCR draft');node(ts,'author','N. Wecklein');node(ts,'editor','F. D. Allen',role='translator')
 rs=node(ts,'respStmt');node(rs,'resp','Conservative OCR extraction, page comparison and provisional alignment');node(rs,'name','OpenAI Codex, for Gregory Crane')
 pub=node(fd,'publicationStmt');node(pub,'p','Local Perseus Multitext Viewer OCR draft; not a proofread edition.');node(pub,'idno',URN,type='CTS-URN')
 sd=node(fd,'sourceDesc');lw=node(sd,'listWit')
 for year,scan in [('1893','oxu1.601566764'),('1891','oxu1.601623131')]:
  w=node(lw,'witness',**{XML+'id':'w'+year});b=node(w,'bibl');node(b,'author','N. Wecklein');node(b,'editor','F. D. Allen',role='translator');node(b,'title','The Prometheus Bound of Aeschylus and the fragments of the Prometheus Unbound');node(b,'publisher','Ginn & Company');node(b,'pubPlace','Boston and London');node(b,'date',year,when=year);node(b,'biblScope','31–144',unit='page');node(b,'ref',scan,target='https://hdl.handle.net/2027/'+scan)
 enc=node(hd,'encodingDesc');ed=node(enc,'editorialDecl')
 for s in ['1893 is the base OCR. Printed pages 31–144 only: introduction, hypothesis, Prometheus Unbound fragments, metre section, appendix and separate handwritten interleaves are excluded. The translator states that this English adaptation derives from Wecklein’s second edition (1878), with alterations; it is not the 1888 German Oresteia commentary.', 'The 1891 PDF text layer is extracted in two columns. Page-local normalized word occurrence counts identify unmatched base words. These are flagged with sic; agreement is not proof of correctness. Punctuation, accents, word order, missing text and true printing differences remain unresolved. No automatic lexical corrections or silent conflation are made.', 'On page 120 the 1893 OCR interleaves columns; the reconstructed 1891 text is displayed instead, explicitly labeled. Both page texts remain in the audit. Selected handwritten intrusions are excluded in the editorial manifest; uncertain residue remains flagged for review.', 'Source heading segmentation and all reference placements remain provisional. Complete Greek lines in nearby running text supply a local reference window. Such windows are placement aids, not claims about the complete scope of a note. Physical hyphenation is retained.']:
  node(ed,'p',s)
 rd=node(enc,'refsDecl',n='CTS');node(rd,'cRefPattern',matchPattern='(.+)',replacementPattern="#xpath(/tei:TEI/tei:text/tei:body/tei:div/tei:div[@n='$1'])",n='commline')
 cs=node(node(enc,'refsDecl'),'citeStructure',match='/TEI/text/body/div',use='@n');node(cs,'citeStructure',match="div[@subtype='commline']",use='@n',unit='commline',delim=':')
 lu=node(node(hd,'profileDesc'),'langUsage');node(lu,'language','English',ident='eng');node(lu,'language','Greek',ident='grc');node(node(hd,'revisionDesc'),'change','Initial two-source comparison draft.',when='2026-09-07')
 body=node(node(node(root,'text',**{XML+'lang':'eng'}),'body'),'div',type='commentary',n=URN)
 audit=[];notes=[];current=None;last=0;pageaudit={};headings=[]
 edits=json.loads((D/'editorial.json').read_text())
 for pg,b in bounds.items():
  ls=pages[b['seq']]['lines'][b['start']:b['end']];text='\n'.join(ls)
  for edit in edits.get(pg,[]):
   assert edit['old'] in text,(pg,edit);text=text.replace(edit['old'],edit['new'],1)
  secondary='\n'.join(sec[pg]['lines']);base=text
  if pg=='120':text=secondary
  other=base if pg=='120' else secondary
  counts=collections.Counter(norm(t) for t in re.findall(r'\S+',other));flags=[]
  near=[q for q in [str(int(pg)-1),pg] if hits.get(q)]
  if not near:near=sorted([q for q in hits if hits[q]],key=lambda q:abs(int(q)-int(pg)))[:2]
  rh=sorted(set(n for q in near for n in hits[q]),key=order.get);assert rh
  window=rh[0] if len(rh)==1 else rh[0]+'-'+rh[-1]
  # Headings start a line, increase within the local passage, and are near running-text evidence.
  for idx,line in enumerate(text.splitlines()):
   m=re.match(r'^(\d{1,4})(?:\s*[-–]\s*(\d{1,4}))?\s*(?:f{1,2}\s*)?[.:]\s*(.*)',line)
   candidate=int(m[1]) if m else -1
   if m and (m[3].strip() or line.startswith('915 f.')) and (last<=candidate<=int(re.match(r'\d+',rh[-1])[0])+12) and candidate>=max(1,int(re.match(r'\d+',rh[0])[0])-20):
    label=m[1]+('-'+m[2] if m[2] else '')
    if current is None or current['n']!=label:
     current={'n':label,'parts':[],'page':pg,'reference':window,'evidence':{q:hits[q] for q in near}};notes.append(current);headings.append([pg,idx,line]);last=candidate
   assert current is not None,(pg,line)
   tokens=[]
   for t in re.findall(r'\S+',line):
    key=norm(t);unmatched=bool(key) and counts[key]<=0
    if counts[key]>0:counts[key]-=1
    tokens.append({'text':t,'unmatched':unmatched})
    if unmatched:flags.append(t)
   current['parts'].append({'page':pg,'line':idx,'text':line,'tokens':tokens,'witness':'1891' if pg=='120' else '1893'})
  pageaudit[pg]={'base1893':base,'secondary1891':secondary,'unmatched_tokens':flags,'reference_matches':hits[pg],'pdf_page':int(pg)+13,'seq1893':b['seq']}
 seen=collections.Counter()
 for note in notes:
  seen[note['n']]+=1;ident='comm-'+note['n']+('-'+str(seen[note['n']]) if seen[note['n']]>1 else '')
  div=node(body,'div',type='textpart',subtype='commline',n=note['n'],corresp=WORK+'.perseus-grc2:'+note['reference'],**{XML+'id':ident})
  node(node(div,'p',type='ocr-status'),'note','Two-source OCR draft: unmatched words are bracketed; readings, punctuation, possible marginalia and note boundaries remain unverified. Agreement between OCR sources is not proof of correctness.',type='ocr')
  node(node(div,'p',type='alignment-status'),'note','Reference placement provisional: local window supported by running Greek. Source note '+note['n']+'; verify numbering and scope.',type='alignment',cert='low')
  previous=None
  for part in note['parts']:
   pg=part['page']
   if pg!=previous:
    p=node(div,'p',type='source');node(p,'ref','1893, p. '+pg,target='https://babel.hathitrust.org/cgi/pt?id=oxu1.601566764&seq='+str(bounds[pg]['seq']));append(p,'; ');node(p,'ref','1891, p. '+pg,target='https://babel.hathitrust.org/cgi/pt?id=oxu1.601623131&seq='+str(int(pg)+13))
    if pg=='120':node(node(div,'p',type='ocr-status'),'note','This page uses the reconstructed 1891 OCR because the 1893 OCR interleaves columns. Word order and readings require scan review.',type='ocr')
    p=node(div,'p');node(p,'pb',n=pg);previous=pg
   for token in part['tokens']:
    t=token['text'];tag='sic' if token['unmatched'] else 'seg'
    if token['unmatched']:node(p,tag,t,source='#w'+part['witness'])
    elif greek(t):node(p,'mentioned',t,**{XML+'lang':'grc'})
    else:append(p,t)
    append(p,' ')
  audit.append(note)
 out.mkdir(parents=True,exist_ok=True);E.ElementTree(root).write(str(out/('tlg0085.tlg003.'+SHORT+'.xml')),encoding='UTF-8',xml_declaration=True,pretty_print=True)
 summary={'entries':len(notes),'pages':len(pageaudit),'flagged_tokens':sum(len(v['unmatched_tokens']) for v in pageaudit.values()),'status':'two-source page-word comparison; all alignment provisional; not proofread'}
 (out/'audit.json').write_text(json.dumps({'summary':summary,'boundaries':bounds,'pages':pageaudit,'entries':audit},ensure_ascii=False,indent=2)+'\n');(out/'headings.json').write_text(json.dumps(headings,ensure_ascii=False,indent=2));print(summary)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--canonical',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();build(a.canonical,a.out)
