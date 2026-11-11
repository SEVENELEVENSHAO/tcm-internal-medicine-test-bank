"""Read-only local quiz API; static assets share the GitHub Pages UI."""
from __future__ import annotations
import json
import mimetypes
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Lock
from urllib.parse import parse_qs,urlparse
from quiz_data import build_payload,matches

ROOT=Path(__file__).resolve().parent
DB_PATH=ROOT.parent/'test_bank.sqlite'
ANSWER_FIELDS={'answer_text','answer_key','evidence','evidence_text','confidence','answer_page'}
_cache={}
_lock=Lock()


def payload():
    with _lock:
        version=DB_PATH.stat().st_mtime_ns
        if _cache.get('version')!=version:
            _cache['payload']=build_payload(DB_PATH)
            _cache['version']=version
        return _cache['payload']


class Handler(BaseHTTPRequestHandler):
    def json(self,value,status=200):
        data=json.dumps(value,ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(data)

    def do_GET(self):
        url=urlparse(self.path)
        if url.path=='/api/meta':return self.json(payload()['meta'])
        if url.path=='/api/questions':
            params=parse_qs(url.query)
            try:
                limit=min(500,max(1,int(params.get('limit',['500'])[0])))
                offset=max(0,int(params.get('offset',['0'])[0]))
            except ValueError:return self.json({'error':'Invalid limit or offset'},400)
            rows=[q for q in payload()['questions'] if matches(q,params)]
            return self.json({'total':len(rows),'questions':[{k:v for k,v in q.items() if k not in ANSWER_FIELDS} for q in rows[offset:offset+limit]]})
        if url.path.startswith('/api/questions/') and url.path.endswith('/answer'):
            try:qid=int(url.path.split('/')[3])
            except (ValueError,IndexError):return self.json({'error':'Invalid question ID'},400)
            q=next((q for q in payload()['questions'] if q['id']==qid),None)
            return self.json(q) if q else self.json({'error':'Question not found'},404)
        allowed={'/':'index.html','/index.html':'index.html','/quiz.css':'quiz.css','/quiz.js':'quiz.js','/import-report.md':'import-report.md'}
        if url.path not in allowed:return self.send_error(404)
        path=ROOT/'docs'/allowed[url.path]
        if not path.is_file():return self.send_error(404)
        data=path.read_bytes()
        if path.name=='index.html':data=data.replace(b'<html lang="zh-CN">',b'<html lang="zh-CN" data-api="local">',1)
        self.send_response(200)
        self.send_header('Content-Type',(mimetypes.guess_type(path)[0] or 'application/octet-stream')+'; charset=utf-8')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers();self.wfile.write(data)


def run():
    server=ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('TCM_PORT','8765'))),Handler)
    print('Quiz running at http://%s:%s'%server.server_address,flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':run()
