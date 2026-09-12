"""Experimental source-region adapter; no corpus or existing shard mutations."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

NS = {'t': 'http://www.tei-c.org/ns/1.0'}
XID = '{http://www.w3.org/XML/1998/namespace}id'

def content(element):
    return ' '.join(''.join(element.itertext()).split())

def build(source):
    source = Path(source)
    tree = ET.parse(source)
    works = {}
    covered = 0
    for play in tree.findall('.//t:div[@subtype="play"]', NS):
        root_id = play.get(XID)
        if not root_id or root_id in works:
            raise ValueError('Missing or duplicate play identity: ' + str(root_id))
        fragments = []
        for frag in play.findall('t:div[@type="fragment"]', NS):
            lines = [dict(ref=str(i), source_id=l.get(XID), text=content(l))
                     for i, l in enumerate(frag.findall('t:lg/t:l', NS), 1)]
            fragments.append(dict(number=frag.get('n'), source_id=frag.get(XID), lines=lines,
                                  context='\n\n'.join(content(c) for c in frag
                                      if c.tag not in ('{'+NS['t']+'}lg', '{'+NS['t']+'}head'))))
        refs = [f['number'] for f in fragments]
        if len(refs) != len(set(refs)):
            raise ValueError('Duplicate fragment numbers: ' + root_id)
        covered += len(fragments)
        lines = sum(len(f['lines']) for f in fragments)
        slug = root_id[len('aeschylus-'):] if root_id.startswith('aeschylus-') else root_id
        wid = 'urn:cts:perseusDemo:aeschylus.' + slug.replace('-','_')
        works[root_id] = dict(id=root_id, work_urn=wid,
            edition_urn=wid+'.nauck1889grc1' if lines else None,
            title=slug.replace('-',' ').title(),
            source_title=play.get('n'), source='nauck-aeschylus.xml', selector='#'+root_id,
            status='Fragmentary text' if lines else 'Evidence only', line_count=lines,
            fragments=fragments,
            introduction='\n\n'.join(content(c) for c in play if c.get('type')!='fragment'
                                       and c.tag!='{'+NS['t']+'}head'))
    total = len(tree.findall('.//t:div[@type="fragment"]', NS))
    return dict(schema_version=1, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                works=works, collections=[dict(id='aeschylus-fragments', title='Fragments',
                author='Aeschylus', textgroup='tlg0085', members=list(works)),
                dict(id='nauck1889', title='Nauck 1889 — fragmentary plays',
                author='Aeschylus', textgroup='tlg0085', members=list(works),
                editions=[w['edition_urn'] for w in works.values() if w['edition_urn']])],
                scope=dict(play_headings=len(works), included_fragments=covered,
                           outside_play_containers=total-covered),
                editorial_note='Experimental reading of the supplied Nauck transcription. Headings and attribution require review. Verse line numbers are derived within each fragment; they are not new canonical references.')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('source',type=Path)
    p.add_argument('output',type=Path)
    a=p.parse_args()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(build(a.source),ensure_ascii=False),encoding='utf8')

if __name__=='__main__': main()
