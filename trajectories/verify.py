#!/usr/bin/env python3
"""Verify the exported evidence and the outcomes of the generated examples."""
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'docs/trajectories/data'

def raw(oid):
    value=(DATA/'objects'/oid).read_bytes()
    assert hashlib.sha1(value).hexdigest()==oid, ('hash mismatch',oid)
    header, body=value.split(b'\0',1)
    kind,size=header.decode().split(' ')
    assert len(body)==int(size)
    return kind,body

def tree(oid):
    kind,body=raw(oid); assert kind=='tree'
    rows=[]
    while body:
        header,body=body.split(b'\0',1); mode,name=header.split(b' ',1)
        rows.append((mode.decode(),name.decode(),body[:20].hex()));body=body[20:]
    return rows

def commit(oid):
    kind,body=raw(oid);assert kind=='commit'
    headers,message=body.split(b'\n\n',1)
    fields={}
    for line in headers.decode().splitlines():
        k,_,v=line.partition(' ');fields.setdefault(k,[]).append(v)
    return fields,message.decode()

def verify_export(d):
    for oid in d['evidence']['objects']: raw(oid)
    for oid,b in d['blobs'].items():
        kind,value=raw(oid);assert kind=='blob' and len(value)==b['size']
        if b['text'] is not None: assert value.decode()==b['text']
    def files(oid,prefix=''):
        result={}
        for mode,name,child in tree(oid):
            if not prefix and name=='.caos': continue
            path=prefix+name
            if mode=='40000': result.update(files(child,path+'/'))
            elif mode=='160000': result.update(files(commit(child)[0]['tree'][0],path+'/'))
            else: result[path]={'mode':mode,'oid':child}
        return result
    for oid,snapshot in d['snapshots'].items():
        assert files(oid)==snapshot['files'],('snapshot mismatch',oid)
    ids={c['id']:c for c in d['conversations']}
    for c in ids.values():
        assert c['events'][-1]['oid']==c['head']
        previous=None
        for e in c['events']:
            fields,message=commit(e['oid'])
            assert fields['tree'][0]==e['tree'] and len(fields['parent'])==1
            assert fields['parent'][0]==e['parent']
            assert message.partition('\n\n')[0]==e['kind']
            if previous: assert e['parent']==previous['oid']
            before=d['snapshots'][e['before_tree']]['files'] if e['before_tree'] else {}
            after=d['snapshots'][e['tree']]['files']
            expected={p for p in before.keys()|after.keys() if before.get(p)!=after.get(p)}
            assert expected=={x['path'] for x in e['changes']}
            previous=e
        for child in c['children']:
            assert child['id'] in ids
            assert ids[child['id']]['identity']['owner']['parent']==c['id']
            assert ids[child['id']]['head']==child['terminal_head']
    for oid,request in d['requests'].items():
        assert [(e['mode'],e['name'],e['oid']) for e in request['entries']]==tree(oid)
    return ids

def content(d,event,path):
    item=d['snapshots'][event['tree']]['files'].get(path)
    return d['blobs'][item['oid']]['text'] if item else None

def main():
    index=json.loads((DATA/'index.json').read_text())
    summary=[]
    for row in index['examples']:
        d=json.loads((DATA/(row['id']+'.json')).read_text())
        ids=verify_export(d)
        root=ids[d['root']]
        assert root['events'][-1]['kind']=='request.terminal'
        assert root['events'][-1]['records'][0]['status']=='idle'
        if row['id'] in ('repair', 'cleanup'):
            assert len(root['children'])>=2
        if row['id']=='repair':
            test='code/dirty/test-discount.sh'; program='code/dirty/discount.sh'
            assert '100 150' in content(d,root['events'][0],test)
            assert any('100 150' not in (content(d,e,test) or '') for e in root['events'][1:])
            assert '100 150' in content(d,root['events'][-1],test)
            assert content(d,root['events'][-1],program)!=content(d,root['events'][0],program)
            with tempfile.TemporaryDirectory(prefix='trajectory-verify-') as directory:
                for name in ('discount.sh','test-discount.sh'):
                    Path(directory,name).write_text(content(d,root['events'][-1],'code/dirty/'+name))
                completed=subprocess.run(['bash','test-discount.sh'],cwd=directory,capture_output=True,text=True,timeout=5)
                assert completed.returncode==0,completed.stderr+completed.stdout
                for percent,expected in [('150','0'),('-50','100'),('20','80')]:
                    actual=subprocess.check_output(['bash','discount.sh','100',percent],cwd=directory,text=True,timeout=5).strip()
                    assert actual==expected,(percent,actual)
        if row['id']=='cleanup':
            final=root['events'][-1]
            assert content(d,final,'code/dirty/public/diagnostics.txt')==content(d,final,'code/dirty/private/example-secret.txt')
            assert content(d,final,'code/dirty/REVIEW.md')
            assert len(root['children'])==3
            assert len([e for e in root['events'] if any(m['role']=='user' for m in e['messages'])])==2
        summary.append({'example':row['id'],'conversations':len(ids),'commits':sum(len(c['events']) for c in ids.values()),'verified_objects':len(d['evidence']['objects'])})
    print(json.dumps({'verified':summary},indent=2))

if __name__=='__main__': main()
