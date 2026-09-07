"""Conservative TEI commentary generation, with inspectable OCR/alignment audit."""
import argparse,collections,difflib,hashlib,itertools,json,re,unicodedata
from pathlib import Path
from lxml import etree as E
from extract import CONFIG
D=Path(__file__).parent
NS='http://www.tei-c.org/ns/1.0';XML='http://www.w3.org/XML/1998/namespace';N={'t':NS}
SCAN={'hw42j8':'hvd.hw42j8','hxjha8':'hvd.hxjha8'}

def child(p,tag,text=None,**attrs):
 x=E.SubElement(p,'{'+NS+'}'+tag,attrs);x.text=text;return x

def norm(s):return ''.join(c for c in unicodedata.normalize('NFD',s.lower().replace('ς','σ')) if '\u03b1'<=c<='\u03c9')
def content(x):return ''.join(x.itertext())
def append(p,s):
 if len(p):p[-1].tail=(p[-1].tail or '')+s
 else:p.text=(p.text or '')+s

def plain(parts):
 return re.sub(r'(?<=[^\W\d_])[-¬]\n(?=[^\W\d_])','', '\n'.join(x['text'] for x in parts)).replace('\n',' ').strip()
def groups(parts):return [(pg,list(xs)) for pg,xs in itertools.groupby(parts,key=lambda x:x['page'])]
def note_text(note):return ' '.join(plain(xs) for pg,xs in groups(note['parts']))

GREEK=r'[\u0370-\u03ff\u1f00-\u1fff]+(?:[\s᾽’]+[\u0370-\u03ff\u1f00-\u1fff]+)*'
CITE=r'(?:(?:Soph\.\s+)?(?:Oed\.\s*[TK]\.|Ai\.|Ant\.|El\.|Phil\.|Trach\.)|Eum\.|Cho\.|Prom\.|Suppl\.|Sept\.|Pers\.|Ag\.)\s*\d+(?:\s*[-–—]\s*\d+)?(?:\s+ff?\.)?'
MARK=re.compile('('+CITE+')|('+GREEK+')')
def markup(p,text):
 last=0
 for m in MARK.finditer(text):
  between=text[last:m.start()];append(p,between)
  if m[1]:child(p,'bibl',m[0],n=m[0])
  else:
   # A Greek passage immediately after a recognized citation is quoted text.
   # Keep the printed citation-before-quotation order rather than rewriting it.
   if len(p) and E.QName(p[-1]).localname=='bibl' and not between.strip():
    bib=p[-1];p.remove(bib);cit=child(p,'cit');cit.append(bib);child(cit,'quote',m[0],**{'{'+XML+'}lang':'grc'})
   else:child(p,'mentioned',m[0],**{'{'+XML+'}lang':'grc'})
  last=m.end()
 append(p,text[last:])

def map_lines(edition,reference):
 weck=E.parse(str(edition),E.XMLParser(recover=False));ref=E.parse(str(reference),E.XMLParser(recover=False))
 src={x.get('n'):x for x in weck.xpath('//t:l',namespaces=N) if x.get('n','').isdigit()}
 refs={x.get('n'):x for x in ref.xpath('//t:l',namespaces=N)};mapped={};supp=[]
 for n,x in src.items():
  if x.get('corresp'):
   v=x.get('corresp').split()[0].rsplit(':',1)[-1]
   if all(k in refs for k in v.split('-')):mapped[n]=v
 for n in range(1,max(map(int,src))+1):
  if str(n) in mapped:continue
  before=max((int(k) for k in mapped if int(k)<n),default=None);after=min((int(k) for k in mapped if int(k)>n),default=None)
  if before is None or after is None:raise ValueError(('No bounded correspondence',n))
  limits=[int(v) for k in [before,after] for v in mapped[str(k)].split('-') if v.isdigit()]
  low,high=min(limits),max(limits);x=src.get(str(n));g=norm(content(x)) if x is not None else ''
  matches=[k for k,r in refs.items() if k.isdigit() and low-5<=int(k)<=high+5 and len(g)>7 and g in norm(content(r))]
  if len(matches)==1:v=matches[0];method='unique Greek-content match near existing neighbours'
  else:v=str(low) if low==high else f'{low}-{high}';method='provisional bounding range from mapped neighbouring lines'
  assert all(k in refs for k in v.split('-'))
  mapped[str(n)]=v;supp.append({'source':str(n),'reference':v,'method':method,'source_greek':content(x) if x is not None else None,'reference_greek':{k:content(refs[k]) for k in v.split('-')}})
 return src,refs,mapped,supp

def build(play,corpus,canonical,out):
 cfg=CONFIG[play];work='urn:cts:greekLit:tlg0085.'+play;version=work+'.wecklein1888-com-ger1'
 data=json.loads((D/'notes.json').read_text())[play];pages=json.loads((D/'pages.json').read_text());bounds=json.loads((D/'boundaries.json').read_text())
 src,refs,mapping,supp=map_lines(corpus/'data/tlg0085'/play/f'tlg0085.{play}.wecklein1885-grc2.xml',canonical/'data/tlg0085'/play/f'tlg0085.{play}.perseus-grc2.xml')
 root=E.Element('{'+NS+'}TEI',nsmap={None:NS});hd=child(root,'teiHeader');fd=child(hd,'fileDesc');ts=child(fd,'titleStmt')
 child(ts,'title',f'Wecklein’s explanatory commentary on Aeschylus, {cfg["title"]} (1888): OCR draft');child(ts,'author','N. Wecklein')
 rs=child(ts,'respStmt',**{'{'+XML+'}id':'conversion'});child(rs,'resp','Conservative OCR extraction, collation where available, and TEI conversion with explicit uncertainty');child(rs,'name','OpenAI Codex, for Gregory Crane')
 pub=child(fd,'publicationStmt');child(pub,'publisher','Perseus Multitext project');child(pub,'date','2026-09-07',when='2026-09-07');child(pub,'idno',version,type='CTS-URN');child(child(pub,'availability'),'p','Public-domain print source, as stated in the preserved HathiTrust OCR exports.')
 sd=child(fd,'sourceDesc');bib=child(sd,'bibl');child(bib,'title','Äschylos Orestie mit erklärenden Anmerkungen von N. Wecklein');child(bib,'editor','N. Wecklein');child(bib,'pubPlace','Leipzig');child(bib,'publisher','B. G. Teubner');child(bib,'date','1888',when='1888');child(bib,'biblScope',f'{cfg["first"]}–{cfg["last"]}',unit='page')
 lw=child(sd,'listWit')
 for w in cfg['witnesses']:
  wit=child(lw,'witness',**{'{'+XML+'}id':w});child(wit,'ref',SCAN[w],target='https://hdl.handle.net/2027/'+SCAN[w]);child(wit,'p','Google-digitized Harvard copy; original HathiTrust OCR and rights statement preserved. SHA-256: '+hashlib.sha256((D/(w+'.txt')).read_bytes()).hexdigest())
 enc=child(hd,'encodingDesc');ed=child(enc,'editorialDecl')
 for s in [
 'Only explanatory notes are included. Running Greek, title/cast lists and the separate textual appendix are excluded. Page milestones stay inside passage-addressable notes.',
 'HW42J8 is the base. Choephoroi uses that single witness as requested. Eumenides is collated against HXJHA8, whose export lacks printed pages 294–295. Those pages use the base alone; the comparison-witness absence is explicitly marked as an OCR-source gap.',
 'Unresolved OCR is retained in sic. A single witness is not treated as a confirmed reading. Note headings are repaired only from clear local sequence/Greek context or an alternate witness; original headings and every intervention remain in the audit. Physical line-end hyphenation is joined mechanically; historical spelling is preserved.',
 'Reference alignment reuses the existing Wecklein 1885-to-Smyth mapping, with documented supplements. Matching Greek in the 1888 running-text page corroborates content but does not fully verify 1888 line numbers. Other mappings and bounding ranges are visibly provisional.',
 'An explicit f. covers two lines; ff. anchors only its starting line. Ranges preserve the printed note scope. Greek discussion uses mentioned; recognized citation-following Greek quotations use cit/quote/bibl. Cross-work passage correspondences are not invented. Further proofreading and semantic tagging remain necessary.'
 ]:child(ed,'p',s)
 old=child(enc,'refsDecl',n='CTS');pattern=child(old,'cRefPattern',n='commline',matchPattern='(.+)',replacementPattern="#xpath(/tei:TEI/tei:text/tei:body/tei:div/tei:div[@n='$1'])");child(pattern,'p','Select the source commentary line or range.')
 modern=child(enc,'refsDecl',**{'{'+XML+'}id':'CTS-modern'});cs=child(modern,'citeStructure',match='/TEI/text/body/div',use='@n');child(cs,'citeStructure',match="div[@subtype='commline']",use='@n',unit='commline',delim=':')
 lu=child(child(hd,'profileDesc'),'langUsage')
 for ident,name in [('ger','German'),('grc','Ancient Greek'),('lat','Latin')]:child(lu,'language',name,ident=ident)
 child(child(hd,'revisionDesc'),'change','Initial conservative commentary integration with original OCR and alignment audit.',when='2026-09-07')
 text=child(root,'text',**{'{'+XML+'}lang':'ger'});body=child(text,'body');edition=child(body,'div',type='commentary',n=version)
 report={'version':version,'status':'OCR draft','witnesses':cfg['witnesses'],'second_witness_missing_pages':[294,295] if play=='tlg007' else [],'alignment_supplements':supp,'entries':[]}
 hi=collections.defaultdict(list)
 for h in data.get('hxjha8',[]):hi[(h['page'],h['n'].split('-')[0])].append(h)
 used=collections.Counter();entries={};missing_notes=0
 for a in data['hw42j8']:
  key=(a['page'],a['n'].split('-')[0]);hs=hi.get(key,[]);h=hs[min(used[key],len(hs)-1)] if hs else None;used[key]+=1
  label=a['n'];numbers=[int(k) for k in label.split('-')];n=numbers[0]
  target=mapping[str(n)]
  if len(numbers)>1:
   covered=[int(k) for i in range(n,numbers[-1]+1) for k in mapping[str(i)].split('-') if k.isdigit()];lo,high=min(covered),max(covered);target=str(lo) if lo==high else f'{lo}-{high}'
  x=entries.get(label)
  if x is None:x=child(edition,'div',type='textpart',subtype='commline',n=label,corresp=work+'.perseus-grc2:'+target,**{'{'+XML+'}id':'comm-'+label});entries[label]=x
  greek=norm(content(src[str(n)])) if str(n) in src else '';pagegreek=norm(' '.join(pages['hw42j8'][a['page']]['lines'][:bounds[a['page']]['start']]))
  supplemented=any(s['source']==str(n) for s in supp);checked=len(greek)>11 and greek in pagegreek and not supplemented
  if not checked:child(child(x,'p',type='alignment-status'),'note','Reference alignment provisional: inherited from the 1885 edition or a documented bounding range; verify against the 1888 scan.',type='alignment',cert='low')
  pgset={z['page'] for z in a['parts']};missing=[pg for pg in pgset if play=='tlg007' and pg not in pages['hxjha8']]
  if play=='tlg006':child(child(x,'p',type='ocr-status'),'note','Single-witness OCR: uncollated; flagged readings require scan review.',type='ocr')
  if missing:
   missing_notes+=1;p=child(x,'p',type='ocr-status');child(p,'note','Second-witness OCR is unavailable for printed page(s) '+', '.join(sorted(missing))+'. HW42J8 text is retained; this is not a lacuna in the ancient text.',type='ocr');child(p,'gap',reason='ocr-source-unavailable',source='#hxjha8',unit='page',quantity=str(len(missing)))
  source=child(x,'p',type='source');child(source,'ref',f'Wecklein 1888, p. {a["page"]}',target=f'https://babel.hathitrust.org/cgi/pt?id={SCAN["hw42j8"]}&seq={pages["hw42j8"][a["page"]]["seq"]}')
  raw=note_text(a);alt=note_text(h) if h else None;words=raw.split();flags=set();diffs=[]
  if alt is not None:
   hw=alt.split()
   for op,i,j,k,l in difflib.SequenceMatcher(None,words,hw,autojunk=False).get_opcodes():
    if op!='equal':flags.update(range(i,j));diffs.append({'base_words':[i,j],'hw42j8':' '.join(words[i:j]),'hxjha8':' '.join(hw[k:l])})
  for i,w in enumerate(words):
   if (re.search(GREEK,w) and re.search('[A-Za-z]',w)) or any(unicodedata.category(c).startswith('L') and any(z in unicodedata.name(c,'') for z in ['CYRILLIC','TIBETAN','THAI','ARABIC','BENGALI']) for c in w):flags.add(i)
  p=child(x,'p');offset=0
  for pg,parts in groups(a['parts']):
   child(p,'pb',n=pg,facs=f'https://babel.hathitrust.org/cgi/pt?id={SCAN["hw42j8"]}&seq={pages["hw42j8"][pg]["seq"]}')
   ws=plain(parts).split();i=0
   while i<len(ws):
    flagged=offset+i in flags;j=i+1
    while j<len(ws) and (offset+j in flags)==flagged:j+=1
    node=child(p,'sic',source='#hw42j8',resp='#conversion') if flagged else p;markup(node,' '.join(ws[i:j]));append(p,' ');i=j
   offset+=len(ws)
  assert offset==len(words)
  if any(not d['hw42j8'] and d['hxjha8'] for d in diffs):child(child(x,'p',type='ocr-status'),'note','The comparison OCR has additional text: possible base omission or layout disagreement. See the collation audit.',type='ocr')
  if play=='tlg007' and not h and not missing:raise ValueError(('Unmatched second-witness note',key))
  report['entries'].append({'n':label,'page':a['page'],'reference':target,'alignment':'page-content-corroborated' if checked else 'provisional','source_heading':a['heading'],'original_heading_line':a['original_heading_line'],'second_heading':h['heading'] if h else None,'hw42j8':raw,'hxjha8':alt,'differences':diffs,'flagged_word_indices':sorted(flags),'missing_comparison_pages':sorted(missing)})
 summary={'entries':len(entries),'source_notes':len(data['hw42j8']),'pages':cfg['last']-cfg['first']+1,'content_corroborated':sum(a['alignment']=='page-content-corroborated' for a in report['entries']),'provisional':sum(a['alignment']=='provisional' for a in report['entries']),'disagreement_spans':sum(len(a['differences']) for a in report['entries']),'notes_affected_by_missing_comparison':missing_notes}
 report['unanchored_comparison']=json.loads((D/'unanchored-comparison.json').read_text()) if play=='tlg007' else []
 report['summary']=summary;out.mkdir(parents=True,exist_ok=True);path=out/(version.split(':')[-1]+'.xml');E.ElementTree(root).write(str(path),encoding='UTF-8',xml_declaration=True,pretty_print=True);(out/(play+'-audit.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(play,json.dumps(summary));return path

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--corpus',type=Path,required=True);p.add_argument('--canonical',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 for play in CONFIG:build(play,a.corpus,a.canonical,a.out)
