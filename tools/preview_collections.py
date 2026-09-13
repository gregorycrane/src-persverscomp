"""Build and serve an isolated collections trial with read-only existing assets."""
import argparse
import functools
import json
import sqlite3
import sys
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SRC))

def build_preview(source, output, db, existing, claudel=None, claudel_score=None):
    from pipeline import index_builder
    from pipeline.fragment_collections import build
    from pipeline.fragment_shards import build_shards
    output.mkdir(parents=True,exist_ok=True)
    (output/'site').mkdir(exist_ok=True)
    data=build(source)
    additions=build_shards(data,output,existing)
    from pipeline.tragedy_statistics import build as build_statistics
    existing_catalog=existing/'site/catalog.json'
    data['tragedy_statistics']=build_statistics(Path('/Users/gcrane/github/canonical-greekLit/data'), json.loads(existing_catalog.read_text()))
    (output/'site/fragment-collections.json').write_text(json.dumps(data,ensure_ascii=False))
    index_builder.SRC_DIR=SRC
    index_builder.WORKSPACE_DIR=output
    index_builder.DB_PATH=db
    claudel_db=None
    if claudel and claudel.exists():
        from pipeline.claudel_translation import build_translation
        score=claudel_score if claudel_score and claudel_score.exists() else None
        claudel_db=build_translation(claudel,output,existing,score)
    with sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True) as conn:
        conn.execute('ATTACH DATABASE ? AS fragments',(str(additions),))
        schemas=['main','fragments']
        if claudel_db:
            conn.execute('ATTACH DATABASE ? AS claudel',(str(claudel_db),))
            schemas.append('claudel')
        for table in ('text_units','alignment_grid','text_segments','edition_chapter_order'):
            conn.execute('CREATE TEMP VIEW '+table+' AS '+' UNION ALL '.join('SELECT * FROM '+schema+'.'+table for schema in schemas))
        index_builder.rebuild(conn=conn)

class PreviewHandler(SimpleHTTPRequestHandler):
    def translate_path(self,path):
        relative=Path(unquote(urlsplit(path).path).lstrip('/') or 'index.html')
        if '..' in relative.parts: return str(self.preview/'__blocked__')
        candidate=self.preview/relative
        if candidate.is_file(): return str(candidate)
        return str(self.existing/relative)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--db',type=Path,default=Path('/tmp/persvers_build/corpus_alignment_grid.db'))
    p.add_argument('--existing',type=Path,default=Path('/Users/gcrane/github/persverscomp'))
    p.add_argument('--claudel',type=Path,default=Path('/Users/gcrane/Downloads/aeschylus-eumenides-claudel-wu-89013526876-1789301260.txt'))
    p.add_argument('--claudel-score',type=Path,default=Path('/Users/gcrane/Downloads/aeschylus-eumenides-claudel-uc1-31822002779502-1789305538.txt'))
    p.add_argument('--port',type=int,default=8001)
    p.add_argument('--build-only',action='store_true')
    a=p.parse_args()
    build_preview(a.source.resolve(),a.output.resolve(),a.db,a.existing.resolve(),a.claudel.resolve(),a.claudel_score.resolve())
    if a.build_only: return
    PreviewHandler.preview=a.output.resolve()
    PreviewHandler.existing=a.existing.resolve()
    server=ThreadingHTTPServer(('127.0.0.1',a.port),PreviewHandler)
    print(f'Preview: http://localhost:{a.port}/?collections=1',flush=True)
    server.serve_forever()

if __name__=='__main__': main()
