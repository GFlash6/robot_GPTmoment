"""Independent loopback HTTP service: GET only, no runtime imports."""
import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from .ledger import Ledger, ObserverError


def make_server(root,host='127.0.0.1',port=8765,static=None,origins=()):
    if host not in {'127.0.0.1','localhost'}: raise ValueError('观察服务仅绑定 loopback；远程部署需要独立认证代理')
    ledger=Ledger(root);assets=Path(static).resolve() if static else None
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): return

        def json(self,status,body):
            data=json.dumps(body,ensure_ascii=False,allow_nan=False).encode()
            try:
                self.send_response(status);self.headers_common('application/json; charset=utf-8',len(data));self.end_headers();self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):
                return

        def headers_common(self,kind,length):
            self.send_header('Content-Type',kind);self.send_header('Content-Length',str(length));self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
            origin=self.headers.get('Origin')
            if origin in origins: self.send_header('Access-Control-Allow-Origin',origin);self.send_header('Vary','Origin')

        def do_GET(self):
            try:
                parsed=urlsplit(self.path);path=unquote(parsed.path);params={k:v[-1] for k,v in parse_qs(parsed.query).items()}
                if path.startswith('/api/'):
                    parts=path.strip('/').split('/')
                    if parts[:2]!=['api','v1']: raise ObserverError('NOT_FOUND','API 不存在',404)
                    if len(parts)==3:
                        name=parts[2]
                        if name=='overview': result=ledger.overview()
                        elif name=='resources': result=ledger.resources()
                        elif name in {'tasks','assets','memories','models'}: result=ledger.listing('model_responses' if name=='models' else name,params)
                        else: raise ObserverError('NOT_FOUND','接口不存在',404)
                    elif len(parts)==4 and parts[2]=='tasks': result=ledger.task(parts[3])
                    elif len(parts)==5 and parts[2]=='tasks' and parts[4]=='events': result=ledger.events(parts[3],params)
                    elif len(parts)==4 and parts[2]=='models': result=ledger.model(parts[3])
                    elif len(parts)==5 and parts[2]=='models' and parts[4]=='context-diff': result=ledger.model_context_diff(parts[3],params)
                    elif len(parts)==5 and parts[2]=='models' and parts[4]=='context': result=ledger.model_context(parts[3])
                    else: raise ObserverError('NOT_FOUND','接口不存在',404)
                    self.json(200,result);return
                if assets is None: raise ObserverError('UI_NOT_BUILT','API 已启动；前端需单独启动或传入 --static 构建目录',404)
                target=(assets/path.lstrip('/')).resolve()
                if assets not in target.parents and target!=assets: raise ObserverError('NOT_FOUND','资源不存在',404)
                if path=='/' or (not target.suffix and not target.is_file()): target=assets/'index.html'
                if not target.is_file(): raise ObserverError('NOT_FOUND','静态资源不存在；请先构建 UI',404)
                data=target.read_bytes();self.send_response(200);self.headers_common(mimetypes.guess_type(target)[0] or 'application/octet-stream',len(data));self.end_headers();self.wfile.write(data)
            except ObserverError as exc: self.json(exc.status,{'api_version':'1','error':{'code':exc.code,'message':str(exc)}})
            except (BrokenPipeError,ConnectionResetError): return
            except Exception: self.json(500,{'api_version':'1','error':{'code':'INTERNAL_ERROR','message':'观察服务无法解析该请求'}})

        def reject(self): self.json(405,{'error':{'code':'READ_ONLY','message':'观察服务只接受读取请求'}})
        do_POST=do_PUT=do_PATCH=do_DELETE=reject

    return ThreadingHTTPServer((host,port),Handler)


def main(argv=None):
    p=argparse.ArgumentParser(description='机器人流程只读观察 API / 静态 UI')
    p.add_argument('--root',required=True,help='实际运行账本目录')
    p.add_argument('--port',type=int,default=8765);p.add_argument('--static',help='独立前端 dist 目录');p.add_argument('--origin',action='append',default=[])
    a=p.parse_args(argv);server=make_server(a.root,port=a.port,static=a.static,origins=a.origin)
    print(f'Observer: http://127.0.0.1:{server.server_port} (read only)',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: return 0
    finally: server.server_close()


if __name__=='__main__': main()
