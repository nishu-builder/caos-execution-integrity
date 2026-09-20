#!/usr/bin/env python3
"""Test-only CORS-enabled object and smart Git server. No viewer API or exporter."""
import argparse,json,os,subprocess,tempfile,urllib.parse,urllib.request,zlib
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=18191);p.add_argument('--live-caos');args=p.parse_args()
with tempfile.TemporaryDirectory(prefix='browser-remote-test-') as tmp:
 root=Path(tmp);repo=root/'fresh.git'
 def git(*a):return subprocess.check_output(['git','-C',str(repo),*a],text=True,stderr=subprocess.DEVNULL).strip()
 repo.mkdir();git('init','--quiet');git('config','user.name','Browser test');git('config','user.email','test@example.invalid')
 (repo/'.caos').mkdir();(repo/'.caos/identity.json').write_text('{"id":"fresh-browser-run"}')
 (repo/'.caos/title').write_text('A conversation fetched entirely in the browser');(repo/'hello.txt').write_text('First snapshot.\n')
 (repo/'.caos/transcript').mkdir()
 (repo/'.caos/transcript/0001.json').write_text(json.dumps({'message_id':'test-message','role':'assistant','blocks':[{'type':'text','text':'<img src=x onerror="window.injected=1">'}]}))
 git('add','.');git('commit','--quiet','-m','conversation.root');first=git('rev-parse','HEAD')
 (repo/'hello.txt').write_text('Second snapshot, from a new Git commit.\n');git('add','.');git('commit','--quiet','-m','tool.complete');second=git('rev-parse','HEAD')
 repo.rename(root/'work')
 subprocess.run(['git','clone','--bare','--quiet',str(root/'work'),str(repo)],check=True)
 git('config','uploadpack.allowAnySHA1InWant','true')
 # CAOS stores may have no default branch; fetching an explicit hash must work.
 git('symbolic-ref','HEAD','refs/heads/no-default-branch')
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*a):pass
  def answer(self,status,body,typ='application/octet-stream',cors=True):
   self.send_response(status);self.send_header('Content-Type',typ);self.send_header('Content-Length',str(len(body)))
   if cors:self.send_header('Access-Control-Allow-Origin','*');self.send_header('Access-Control-Allow-Headers','Content-Type, Git-Protocol, Authorization');self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS');self.send_header('Access-Control-Expose-Headers','Content-Type')
   self.end_headers();self.wfile.write(body)
  def do_OPTIONS(self):self.answer(204,b'')
  def do_POST(self):self.do_GET()
  def do_GET(self):
   u=urllib.parse.urlsplit(self.path);path=u.path
   if path=='/fixture.json':return self.answer(200,json.dumps({'first':first,'second':second}).encode(),'application/json')
   if path.startswith('/smart/'):
    if self.command=='POST' and not path.endswith('/git-upload-pack'):return self.answer(405,b'')
    body=self.rfile.read(int(self.headers.get('Content-Length',0)))
    env=dict(os.environ,GIT_PROJECT_ROOT=str(root),GIT_HTTP_EXPORT_ALL='1',PATH_INFO=path[len('/smart'):],REQUEST_METHOD=self.command,QUERY_STRING=u.query,CONTENT_TYPE=self.headers.get('Content-Type',''),CONTENT_LENGTH=str(len(body)))
    result=subprocess.run(['git','http-backend'],input=body,capture_output=True,env=env,timeout=60)
    if result.returncode:return self.answer(500,result.stderr)
    headers,sep,data=result.stdout.partition(b'\r\n\r\n');status=200;typ='application/octet-stream'
    for line in headers.decode().splitlines():
     if line.lower().startswith('status:'):status=int(line.split()[1])
     if line.lower().startswith('content-type:'):typ=line.split(':',1)[1].strip()
    return self.answer(status,data,typ)
   if path.startswith('/live/') and args.live_caos:
    body=self.rfile.read(int(self.headers.get('Content-Length',0))) if self.command=='POST' else None
    req=urllib.request.Request(args.live_caos.rstrip('/')+path[len('/live'):]+('?' +u.query if u.query else ''),data=body,headers={'Content-Type':self.headers.get('Content-Type','application/octet-stream')},method=self.command)
    try:
     with urllib.request.urlopen(req,timeout=60) as r:return self.answer(r.status,r.read(),r.headers.get('Content-Type','application/octet-stream'))
    except urllib.error.HTTPError as e:return self.answer(e.code,e.read())
   if any(path.startswith(prefix+'/packs/') for prefix in ['/bad-pack','/bad-index','/pack-no-index']):
    name=path.rsplit('/',1)[1]
    oid,_,ext=name.partition('.')
    if len(oid)!=40 or any(c not in '0123456789abcdef' for c in oid) or ext not in ['pack','idx']:return self.answer(404,b'')
    target=ROOT/'docs/trajectories/git/packs'/name
    if path.startswith('/pack-no-index/') and ext=='idx':return self.answer(404,b'')
    if not target.is_file():return self.answer(404,b'')
    raw=bytearray(target.read_bytes())
    if (path.startswith('/bad-pack/') and ext=='pack') or (path.startswith('/bad-index/') and ext=='idx'):raw[-1]^=1
    return self.answer(200,raw)
   if any(path.startswith(prefix+'/object/') for prefix in ['/caos','/blocked','/corrupt']):
    oid=path.rsplit('/',1)[1];target=ROOT/'docs/trajectories/data/objects'/oid
    if len(oid)!=40 or any(c not in '0123456789abcdef' for c in oid) or not target.is_file():return self.answer(404,b'Not found')
    raw=target.read_bytes()
    if path.startswith('/corrupt/'):raw=raw+b'altered'
    return self.answer(200,raw,cors=not path.startswith('/blocked/'))
   if path.startswith('/loose.git/'):path=path.replace('/loose.git/','/loose/',1)
   if path.startswith('/loose/objects/'):
    oid=path[len('/loose/objects/'):].replace('/','')
    if len(oid)!=40 or any(c not in '0123456789abcdef' for c in oid):return self.answer(404,b'')
    target=ROOT/'docs/trajectories/data/objects'/oid
    if target.is_file():return self.answer(200,zlib.compress(target.read_bytes()))
   self.answer(404,b'Not found')
 server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
 print('Test remote on',args.port,flush=True)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
