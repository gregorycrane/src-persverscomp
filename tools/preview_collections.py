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

def build_preview(source, output, db):
    from pipeline import index_builder
    from pipeline.fragment_collections import build
    output.mkdir(parents=True,exist_ok=True)
    (output/'site').mkdir(exist_ok=True)
    (output/'site/fragment-collections.json').write_text(json.dumps(build(source),ensure_ascii=False))
    index_builder.SRC_DIR=SRC
    index_builder.WORKSPACE_DIR=output
    index_builder.DB_PATH=db
    with sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True) as conn:
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
    p.add_argument('--port',type=int,default=8001)
    p.add_argument('--build-only',action='store_true')
    a=p.parse_args()
    build_preview(a.source.resolve(),a.output.resolve(),a.db)
    if a.build_only: return
    PreviewHandler.preview=a.output.resolve()
    PreviewHandler.existing=a.existing.resolve()
    server=ThreadingHTTPServer(('127.0.0.1',a.port),PreviewHandler)
    print(f'Preview: http://localhost:{a.port}/?collections=1',flush=True)
    server.serve_forever()

if __name__=='__main__': main()
