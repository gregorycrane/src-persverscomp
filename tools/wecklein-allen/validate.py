"""Validate content preservation, provenance, reference targets and parser output."""
import argparse,json,re
from pathlib import Path
from lxml import etree as E,html
N={'t':'http://www.tei-c.org/ns/1.0'}
def validate(path,audit,canonical):
 t=E.parse(str(path));a=json.loads(audit.read_text());ref=E.parse(str(canonical));refs=set(ref.xpath('//t:l/@n',namespaces=N));units=t.xpath('//t:div[@subtype="commline"]',namespaces=N)
 assert len(units)==a['summary']['entries']
 assert {p['page'] for e in a['entries'] for p in e['parts']}==set(map(str,range(31,145)))
 assert len(set(t.xpath('//@xml:id',namespaces={'xml':'http://www.w3.org/XML/1998/namespace'})))==len(t.xpath('//@xml:id',namespaces={'xml':'http://www.w3.org/XML/1998/namespace'}))
 assert t.xpath('//t:text/@xml:lang',namespaces=N)==['eng']
 assert t.xpath('//t:titleStmt/t:editor[@role="translator"]/text()',namespaces=N)==['F. D. Allen']
 assert set(t.xpath('//t:bibl/t:date/text()',namespaces=N))=={'1891','1893'}
 assert units[0].get('n')=='1-127' and units[-1].get('n')=='1093'
 for u,e in zip(units,a['entries']):
  assert u.get('n')==e['n']
  assert all(n in refs for n in u.get('corresp').rsplit(':',1)[-1].split('-'))
  content=' '.join(''.join(p.itertext()).split() and ' '.join(''.join(p.itertext()).split()) or '' for p in u.findall('t:p',N) if p.get('type') is None)
  expected=' '.join(' '.join(p['text'].split()) for p in e['parts'])
  assert content==expected,(e['n'],content[:80],expected[:80])
  assert u.find('t:p[@type="ocr-status"]/t:note',N) is not None
  assert u.find('t:p[@type="alignment-status"]/t:note',N) is not None
 assert len(t.xpath('//t:sic',namespaces=N))==a['summary']['flagged_tokens']
 assert 'with the rock on which he hangs' in ''.join(units[-1].itertext())
 print('Validated',len(units),'entries; all 114 pages; exact extracted content, flags and reference targets.')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('xml',type=Path);p.add_argument('audit',type=Path);p.add_argument('canonical',type=Path);a=p.parse_args();validate(a.xml,a.audit,a.canonical)
