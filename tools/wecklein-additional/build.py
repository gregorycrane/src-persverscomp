"""Build conservative single-witness drafts with evidence-backed reference windows."""
import argparse,collections,json,re,unicodedata,hashlib
from pathlib import Path
from lxml import etree as E
from extract import CONFIG
D=Path(__file__).parent;NS='http://www.tei-c.org/ns/1.0';XML='{http://www.w3.org/XML/1998/namespace}';N={'t':NS}
def node(p,tag,text=None,**attrs):
 x=E.SubElement(p,'{'+NS+'}'+tag,attrs);x.text=text;return x
def norm(s):return ''.join(c for c in unicodedata.normalize('NFD',s.lower().replace('ς','σ')) if '\u03b1'<=c<='\u03c9')
def txt(x):return ''.join(x.itertext())
def addtext(p,s):
 if len(p):p[-1].tail=(p[-1].tail or '')+s
 else:p.text=(p.text or '')+s
GREEK=re.compile(r'[\u0370-\u03ff\u1f00-\u1fff]+(?:[\s᾽’]+[\u0370-\u03ff\u1f00-\u1fff]+)*')
def markup(p,s):
 words=s.split();flags=[]
 for i,w in enumerate(words):
  bad=(GREEK.search(w) and re.search('[A-Za-z]',w)) or any(unicodedata.category(c).startswith('L') and any(a in unicodedata.name(c,'') for a in ['CYRILLIC','THAI','TIBETAN','BENGALI']) for c in w)
  q=node(p,'sic',source='#ocr') if bad else p
  if bad:flags.append(i)
  last=0
  for m in GREEK.finditer(w):addtext(q,w[last:m.start()]);node(q,'mentioned',m[0],**{XML+'lang':'grc'});last=m.end()
  addtext(q,w[last:]);addtext(p,' ')
 return flags

def build(corpus,canonical,out):
 data=json.loads((D/'notes.json').read_text());bounds=json.loads((D/'boundaries.json').read_text())
 for name,cfg in CONFIG.items():
  play=cfg['play'];work='urn:cts:greekLit:tlg0085.'+play;urn=work+'.'+cfg['short'];pages=json.loads((D/(name+'-pages.json')).read_text())
  ref=E.parse(str(canonical/f'data/tlg0085/{play}/tlg0085.{play}.perseus-grc2.xml'))
  refs={x.get('n'):txt(x) for x in ref.xpath('//t:l',namespaces=N)};reforder={n:i for i,n in enumerate(refs)};refkeys=list(refs);refnorm={n:norm(s) for n,s in refs.items()}
  old=E.parse(str(corpus/f'data/tlg0085/{play}/tlg0085.{play}.wecklein1885-grc2.xml'));oldlines={x.get('n'):x for x in old.xpath('//t:l',namespaces=N)}
  pagehits={};pagegreek={}
  for pg,b in bounds[name].items():
   # Require complete normalized reference lines of substantial length in the running text.
   greek=norm(' '.join(pages[str(b['seq'])]['lines'][:b['start']]));pagegreek[pg]=greek
   hits=[k for k,v in refnorm.items() if len(v)>=18 and v in greek]
   pagehits[pg]=hits
  root=E.Element('{'+NS+'}TEI',nsmap={None:NS});hd=node(root,'teiHeader');fd=node(hd,'fileDesc');ts=node(fd,'titleStmt')
  node(ts,'title',f'{cfg["title"]}: {cfg["author"]}'+(f', revised by {cfg["editor"]}' if cfg.get('editor') else '')+f' ({cfg["year"]}), commentary OCR draft');node(ts,'author',cfg['author'])
  if cfg.get('editor'):node(ts,'editor',cfg['editor'],role='reviser')
  rs=node(ts,'respStmt');node(rs,'resp','OCR extraction and provisional reference placement');node(rs,'name','OpenAI Codex, for Gregory Crane')
  pub=node(fd,'publicationStmt');node(pub,'p','Prepared for the Perseus Multitext Viewer; single-witness OCR draft, not proofread.');node(pub,'idno',urn,type='CTS-URN')
  sd=node(fd,'sourceDesc');bibl=node(sd,'bibl');node(bibl,'author',cfg['author']);node(bibl,'title',cfg['title']);node(bibl,'date',cfg['year'],when=cfg['year']);node(bibl,'publisher','B. G. Teubner');node(bibl,'pubPlace','Leipzig')
  if cfg.get('editor'):node(bibl,'editor',cfg['editor'],role='reviser');node(bibl,'edition','Third edition')
  node(bibl,'biblScope',f'{cfg["first"]}–{cfg["last"]}',unit='page');wit=node(node(sd,'listWit'),'witness',**{XML+'id':'ocr'});node(wit,'ref',cfg['scan'],target='https://hdl.handle.net/2027/'+cfg['scan']);node(wit,'p','Single supplied HathiTrust OCR export. SHA-256: '+hashlib.sha256((D/(name+'.txt')).read_bytes()).hexdigest())
  enc=node(hd,'encodingDesc');ed=node(enc,'editorialDecl')
  for s in ['Single-witness OCR is preserved without speculative prose corrections. Every entry is visibly uncollated; sic flags detected mixed-script corruption, not all possible errors. Original OCR and exact extraction coordinates are retained in the audit.', 'Running text, introductions, hypothesis and separate appendices are excluded. Reviewed starts separate running Greek from notes; source note headings determine units. Duplicate labels share one unit, with separate paragraphs and provenance.', 'All reference placements are provisional. An inherited 1885 correspondence is used only when its source Greek is found on the commentary page. Otherwise a local reference window is inferred from complete Greek lines in the running text. A window places the note for review; it does not assert its full scope or verified source lineation. Whole-page content matches can still reflect OCR/layout errors.', 'Physical line endings and printed spelling remain. Greek script uses mentioned; full quotation/citation/gloss semantic tagging remains for scholarly review. No unattested words are supplied. All heading repairs and unresolved layout fragments are recorded in the editorial manifest and extraction audit.']:
   node(ed,'p',s)
  legacy=node(enc,'refsDecl',n='CTS');node(legacy,'cRefPattern',matchPattern='(.+)',replacementPattern="#xpath(/tei:TEI/tei:text/tei:body/tei:div/tei:div[@n='$1'])",n='commline')
  cs=node(node(enc,'refsDecl'), 'citeStructure',match='/TEI/text/body/div',use='@n');node(cs,'citeStructure',match="div[@subtype='commline']",use='@n',unit='commline',delim=':')
  node(node(node(hd,'profileDesc'),'langUsage'),'language','German',ident='ger');node(node(hd,'revisionDesc'),'change','Initial single-witness draft; source/heading/alignment verification remains.',when='2026-09-07')
  edition=node(node(node(root,'text',**{XML+'lang':'ger'}),'body'),'div',type='commentary',n=urn)
  units={};audit=[]
  for note in data[name]:
   pg=note['page'];n=note['n'];start=n.split('-')[0];oldline=oldlines.get(start);target=None;method=None;evidence={}
   if oldline is not None and len(norm(txt(oldline)))>=18 and norm(txt(oldline)) in pagegreek[pg] and oldline.get('corresp'):
    value=oldline.get('corresp').split()[0].rsplit(':',1)[-1]
    if all(k in refs for k in value.split('-')):target=value;method='1885 correspondence corroborated by source Greek on this page';evidence={'source_greek':txt(oldline)}
   if target is None:
    # Include previous-page running text because commentary often trails its text.
    # If this page has no exact matches, widen only to its closest matching neighbours.
    near=[str(i) for i in [int(pg)-1,int(pg)] if pagehits.get(str(i))]
    if not near:
     allpg=sorted(pagehits,key=lambda p:abs(int(p)-int(pg)));near=[p for p in allpg if pagehits[p]][:2]
    hits=sorted({k for p in near for k in pagehits[p]},key=reforder.get)
    if not hits:raise ValueError(('No Greek reference evidence',name,pg))
    target=hits[0] if hits[0]==hits[-1] else hits[0]+'-'+hits[-1];method='provisional local reference window from running Greek';evidence={'pages':near,'matched_reference_lines':{k:refs[k] for k in hits}}
   if n not in units:units[n]=node(edition,'div',type='textpart',subtype='commline',n=n,corresp=work+'.perseus-grc2:'+target,**{XML+'id':'comm-'+n})
   unit=units[n]
   # Same source label can be repeated by OCR or by the editor; retain all source notes.
   if unit.get('corresp')!=work+'.perseus-grc2:'+target:
    nums=unit.get('corresp').rsplit(':',1)[-1].split('-')+target.split('-');nums=sorted(set(nums),key=reforder.get);unit.set('corresp',work+'.perseus-grc2:'+nums[0]+'-'+nums[-1])
   p=node(unit,'p',type='ocr-status');node(p,'note','Single-witness OCR: uncollated. Source layout and readings require scan review; automatic flags are not exhaustive.',type='ocr')
   p=node(unit,'p',type='alignment-status');node(p,'note','Reference placement provisional: '+method+'. Verify the printed source numbering and note scope against the scan.',type='alignment',cert='low')
   b=bounds[name][pg];p=node(unit,'p',type='source');node(p,'ref',f'{cfg["author"]}, {cfg["year"]}, p. {pg}',target=f'https://babel.hathitrust.org/cgi/pt?id={cfg["scan"]}&seq={b["seq"]}')
   if name=='suppliants' and pg=='24' and n=='1-181':
    q=node(unit,'p',type='ocr-status');node(q,'note','Unplaced OCR fragment from the opening page; position unresolved:',type='ocr');node(q,'sic','Die',source='#ocr')
   if name=='suppliants' and any(part['page']=='81' for part in note['parts']):
    node(node(unit,'p',type='ocr-status'),'note','OCR column order unresolved on printed page 81: fragments of notes 631–637 appear interleaved. Original OCR order retained for scan review.',type='ocr')
   p=node(unit,'p');previous=None;flagcount=0
   for part in note['parts']:
    if part['page']!=previous:
     bb=bounds[name][part['page']];node(p,'pb',n=part['page'],facs=f'https://babel.hathitrust.org/cgi/pt?id={cfg["scan"]}&seq={bb["seq"]}');previous=part['page']
    flagcount+=len(markup(p,part['text']))
   audit.append(dict(note,reference=target,alignment_method=method,alignment_evidence=evidence,flagged_tokens=flagcount))
  report={'source':cfg,'status':'single-witness OCR draft; all reference placement provisional','entries':audit,'page_matching':pagehits,'summary':{'source_notes':len(audit),'unique_entries':len(units),'pages':len(bounds[name]),'content_corroborated':sum('1885' in x['alignment_method'] for x in audit),'provisional_windows':sum('window' in x['alignment_method'] for x in audit)}}
  out.mkdir(parents=True,exist_ok=True);E.ElementTree(root).write(str(out/f'tlg0085.{play}.{cfg["short"]}.xml'),encoding='UTF-8',xml_declaration=True,pretty_print=True);(out/(name+'-audit.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(name,report['summary'])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--corpus',type=Path,required=True);p.add_argument('--canonical',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();build(a.corpus,a.canonical,a.out)
