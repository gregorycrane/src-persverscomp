"""Experimental source-region adapter; no corpus or existing shard mutations."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

NS = {'t': 'http://www.tei-c.org/ns/1.0'}
XID = '{http://www.w3.org/XML/1998/namespace}id'
TEXTGROUP = 'tlg0085'
VERSION = 'nauck1889grc1'
VERSION_LABEL = 'Greek (Nauck, 1889; transcription preview)'
SOURCE_EDITION_URN = f'urn:cts:greekLit:{TEXTGROUP}.fragmenta.{VERSION}'
CITE_NAMESPACE = 'perseus'
PLAY_COLLECTION = 'fragmentaryplays.v1'
ATTRIBUTION_COLLECTION = 'fragmentattributions.v1'

def content(element):
    return ' '.join(''.join(element.itertext()).split())

def parse_fragment(frag, play_urn=None):
    lines = [dict(ref=str(i), source_id=l.get(XID), text=content(l))
             for i, l in enumerate(frag.findall('t:lg/t:l', NS), 1)]
    number = frag.get('n')
    record = dict(number=number, source_id=frag.get(XID), lines=lines,
                  context='\n\n'.join(content(c) for c in frag
                      if c.tag not in ('{'+NS['t']+'}lg', '{'+NS['t']+'}head')))
    if play_urn:
        raw_corresp = (frag.get('corresp') or '').split()
        corresp = []
        for target in raw_corresp:
            if target.startswith('#'):
                corresp.append(work_identity(target[1:])[1])
            elif target.startswith('urn:'):
                corresp.append(target)
            else:
                corresp.append(f'urn:cts:greekLit:{target}')
        # `corresp` is deliberately a list: TEI @corresp is a whitespace-
        # separated list of pointers, and an editor may offer more than one
        # attribution.  `same_as` is reserved for links to the equivalent
        # fragment in another edition; it is not the play attribution.
        record.update(
            edition=VERSION,
            source_fragment_urn=f'{SOURCE_EDITION_URN}:{number}',
            corresp=corresp or [play_urn],
            same_as=[],
        )
    return record


def work_identity(record_id):
    """Return the route slug and CITE2 object URN for a fragmentary play."""
    slug = record_id[len('aeschylus-'):] if record_id.startswith('aeschylus-') else record_id
    work = slug.replace('-', '_')
    return work, f'urn:cite2:{CITE_NAMESPACE}:{PLAY_COLLECTION}:{work}'


def source_version_record(source):
    return dict(short_id=VERSION, edition_urn=SOURCE_EDITION_URN,
                label=VERSION_LABEL, source=Path(source).name)


def route_fragments_by_corresp(works):
    """Build each play view from the edition's explicit attribution claims.

    A fragment keeps its source-edition URN while copies may appear under more
    than one play when @corresp has multiple targets.  This is intentional:
    the play membership is an editorial assertion, not fragment identity.
    """
    by_urn = {work['object_urn']: work for work in works.values()}
    routed = {urn: [] for urn in by_urn}
    for source_work in works.values():
        for fragment in source_work['fragments']:
            for target in dict.fromkeys(fragment.get('corresp') or []):
                if target not in by_urn:
                    raise ValueError(f"Unknown fragment @corresp target: {target}")
                routed[target].append(copy.deepcopy(fragment))
    for urn, work in by_urn.items():
        work['fragments'] = routed[urn]
        work['line_count'] = sum(len(f['lines']) for f in work['fragments'])
        work['status'] = 'Fragmentary text' if work['line_count'] else (
            'Testimonia only' if work['fragments'] else 'Evidence only')


def materialize_work_views(data):
    """Derive play groupings from stand-off attribution records.

    The returned object is suitable for PMV's existing collection browser.
    The source object remains normalized: fragments live once at top level and
    do not depend on any proposed play title.
    """
    result = copy.deepcopy(data)
    fragments = {f['source_fragment_urn']: f for f in result.get('fragments', [])}
    versions = {v['short_id']: v for v in result.get('versions', [])}
    works_by_urn = {w['object_urn']: w for w in result['works'].values()}
    for work in works_by_urn.values():
        work['fragments'] = []
        work['versions'] = []
    for assertion in result.get('attributions', []):
        work = works_by_urn.get(assertion['play_urn'])
        if work is None:
            raise ValueError(f"Unknown attribution play: {assertion['play_urn']}")
        version = versions[assertion['edition']]
        if not any(v['short_id'] == version['short_id'] for v in work['versions']):
            work['versions'].append(copy.deepcopy(version))
        for target in assertion.get('corresp', []):
            if target not in fragments:
                raise ValueError(f"Unknown attribution fragment: {target}")
            fragment = copy.deepcopy(fragments[target])
            fragment['attribution_id'] = assertion['id']
            fragment['attributed_by'] = assertion.get('resp')
            work['fragments'].append(fragment)
    for work in works_by_urn.values():
        work['line_count'] = sum(len(f['lines']) for f in work['fragments'])
        work['status'] = 'Fragmentary text' if work['line_count'] else (
            'Testimonia only' if work['fragments'] else 'Evidence only')
    return result

def grouped_record(record_id, title, source_title, fragments, selector, source):
    work, wid = work_identity(record_id)
    parsed = [parse_fragment(frag, wid) for frag in fragments]
    lines = sum(len(f['lines']) for f in parsed)
    return dict(id=record_id, work=work, object_urn=wid,
        title=title, source_title=source_title, source='nauck-aeschylus.xml', selector=selector,
        status='Fragmentary text' if lines else 'Evidence only', line_count=lines,
        fragments=parsed, introduction='')

def build(source):
    source = Path(source)
    tree = ET.parse(source)
    works = {}
    covered = 0
    assigned_fragments = set()
    for play in tree.findall('.//t:div[@subtype="play"]', NS):
        root_id = play.get(XID)
        if not root_id or root_id in works:
            raise ValueError('Missing or duplicate play identity: ' + str(root_id))
        source_fragments = play.findall('t:div[@type="fragment"]', NS)
        assigned_fragments.update(source_fragments)
        work, wid = work_identity(root_id)
        fragments = [parse_fragment(frag, wid) for frag in source_fragments]
        refs = [f['number'] for f in fragments]
        if len(refs) != len(set(refs)):
            raise ValueError('Duplicate fragment numbers: ' + root_id)
        covered += len(fragments)
        lines = sum(len(f['lines']) for f in fragments)
        works[root_id] = dict(id=root_id, work=work, object_urn=wid,
            title=work.replace('_',' ').title(),
            source_title=play.get('n'), source='nauck-aeschylus.xml', selector='#'+root_id,
            status='Fragmentary text' if lines else 'Evidence only', line_count=lines,
            fragments=fragments,
            introduction='\n\n'.join(content(c) for c in play if c.get('type')!='fragment'
                                       and c.tag!='{'+NS['t']+'}head'))
    play_headings = len(works)
    all_fragments = tree.findall('.//t:div[@type="fragment"]', NS)
    dubia_section = next((div for div in tree.findall('.//t:div[@subtype="section"]', NS)
                          if div.get(XID) == 'aeschylus-dubia-spuria'), None)
    dubia = dubia_section.findall('t:div[@type="fragment"]', NS) if dubia_section is not None else []
    dubia_fragments = set(dubia)
    uncertain = [frag for frag in all_fragments
                 if frag not in assigned_fragments and frag not in dubia_fragments]
    if uncertain:
        works['aeschylus-incertae'] = grouped_record(
            'aeschylus-incertae', 'Uncertain-play fragments',
            'FRAGMENTA INCERTARVM FABVLARVM', uncertain,
            '#aesch-fr%s–#aesch-fr%s' % (uncertain[0].get('n'), uncertain[-1].get('n')), source)
    if dubia:
        works['aeschylus-dubia-spuria'] = grouped_record(
            'aeschylus-dubia-spuria', 'Dubious and spurious fragments',
            'FRAGMENTA DVBIA ET SPVRIA', dubia, '#aeschylus-dubia-spuria', source)
    # Capture the edition's fragments once, before deriving any play views.
    source_fragments = []
    seen_source_urns = set()
    for work in works.values():
        for fragment in work['fragments']:
            urn = fragment['source_fragment_urn']
            if urn not in seen_source_urns:
                seen_source_urns.add(urn)
                source_fragment = copy.deepcopy(fragment)
                source_fragment.pop('corresp', None)
                source_fragments.append(source_fragment)
    route_fragments_by_corresp(works)
    attributions = []
    for work in works.values():
        if work['fragments']:
            attribution_id = f"{VERSION}-{work['work']}"
            attributions.append(dict(
                id=attribution_id,
                urn=f'urn:cite2:{CITE_NAMESPACE}:{ATTRIBUTION_COLLECTION}:{attribution_id}',
                resp='Perseus', edition=VERSION, play_urn=work['object_urn'],
                corresp=[f['source_fragment_urn'] for f in work['fragments']],
            ))
        for key in ('fragments', 'versions', 'line_count', 'status'):
            work.pop(key, None)
    total = len(all_fragments)
    return dict(schema_version=4, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                versions=[source_version_record(source)], fragments=source_fragments,
                works=works, attributions=attributions,
                collections=[dict(id='aeschylus-fragments', title='Fragments',
                author='Aeschylus', textgroup='tlg0085', members=list(works)),
                dict(id='nauck1889', title='Nauck 1889 — fragmentary plays',
                author='Aeschylus', textgroup='tlg0085', members=list(works),
                editions=[SOURCE_EDITION_URN])],
                scope=dict(play_headings=play_headings, included_fragments=total,
                           assigned_to_plays=covered, uncertain_fragments=len(uncertain),
                           dubious_spurious_fragments=len(dubia),
                           outside_play_containers=total-covered),
                editorial_note='Experimental reading of the supplied Nauck transcription. Named-play headings and attribution require review. Uncertain-play and dubious or spurious fragments are grouped as collection-level works rather than assigned to invented plays. Verse line numbers are derived within each fragment; they are not new canonical references.')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('source',type=Path)
    p.add_argument('output',type=Path)
    a=p.parse_args()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(build(a.source),ensure_ascii=False),encoding='utf8')

if __name__=='__main__': main()
