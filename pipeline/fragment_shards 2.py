"""Materialize shared-source fragment editions for the normal PMV reader."""
import html
import json
from pathlib import Path
from pipeline.core.storage import init_storage_engine

VERSION='nauck1889grc1'

def build_shards(data, output, existing):
    output=Path(output)
    catalog=json.loads((Path(existing)/'site/catalog.json').read_text())
    aggregate=init_storage_engine(output/'fragment-editions.db')
    for record in data['works'].values():
        if not record['fragments']:
            continue  # Metadata-only works never acquire an invented passage.
        work='frag_'+record['id'].replace('aeschylus-','',1).replace('-','_')
        key='tlg0085.'+work
        urn='urn:cts:perseusDemo:'+key
        record['work_urn']=urn
        record['edition_urn']=urn+'.'+VERSION
        record['pmv_work_key']=key
        record['pmv_focus']=key.replace('.','_')+'_nauck1889'
        folder=output/'site/data/tlg0085'/work
        folder.mkdir(parents=True,exist_ok=True)
        shard=folder/(key+'.part1.db')
        conn=init_storage_engine(shard)
        unit=(record['pmv_focus'],urn+'.'+VERSION,'Greek (Nauck, 1889; transcription preview)',
              'greek-text','tlg0085',work,VERSION,'edition')
        fragments=record['fragments']
        refs=[urn+':'+f['number']+'.1' for f in fragments]
        for db in (conn,aggregate):
            db.execute('INSERT INTO text_units VALUES (?,?,?,?,?,?,?,?)',unit)
        for i,f in enumerate(fragments):
            verse=''.join('<div class="fc-line"><span>'+html.escape(l['ref'])+'</span><div lang="grc">'+html.escape(l['text'])+'</div></div>' for l in f['lines'])
            if not verse: verse='<p>No quoted verse is encoded in this testimonium.</p>'
            intro='<details><summary>Editorial evidence for this play</summary><p>'+html.escape(record['introduction'])+'</p></details>' if i==0 and record['introduction'] else ''
            body='<div class="pmv-fragment"><h3>'+html.escape(record['title'])+' · Fragment '+html.escape(f['number'])+'</h3>'+intro+'<div class="fc-verse">'+verse+'</div><details class="fc-context" open><summary>Transmitting source and Nauck’s notes</summary><p>'+html.escape(f['context']).replace('\n\n','</p><p>')+'</p></details></div>'
            grid=(refs[i],'tlg0085',work,None,f['number'],'1',refs[i-1] if i else None,refs[i+1] if i+1<len(refs) else None,i+1)
            for db in (conn,aggregate):
                db.execute('INSERT INTO alignment_grid VALUES (?,?,?,?,?,?,?,?,?)',grid)
                db.execute('INSERT INTO text_segments VALUES (?,?,?)',(refs[i],VERSION,body))
                db.execute('INSERT INTO edition_chapter_order VALUES (?,?,?,?,?,?)',('tlg0085',work,VERSION,None,f['number'],i+1))
        conn.commit();conn.close()
        catalog['works'][key]=dict(textgroup='tlg0085',work=work,title=record['title'],
            experimental_fragment=True,default_columns=1,unit_labels={'chapter':'Fragment','section':'Section'},
            parts=[dict(part=1,file=shard.name,books=[],chapters=[f['number'] for f in fragments],bytes=shard.stat().st_size)],
            versions=[dict(short_id=VERSION,urn=urn+'.'+VERSION,label=unit[2],doc_type='edition',text_class='greek-text')],annotations={})
    aggregate.commit();aggregate.close()
    (output/'site/catalog.json').write_text(json.dumps(catalog,ensure_ascii=False))
    return output/'fragment-editions.db'
