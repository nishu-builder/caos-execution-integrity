#!/usr/bin/env python3
"""Publish verified captured objects in Git's standard loose-object layout."""
import argparse, hashlib, json, zlib, subprocess, tempfile
from pathlib import Path

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--data',type=Path,default=Path(__file__).resolve().parents[1]/'docs/trajectories/data')
 p.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'docs/trajectories/git')
 a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 refs=[];count=0
 packs=a.output/'packs';packs.mkdir(exist_ok=True)
 for example in json.loads((a.data/'index.json').read_text())['examples']:
  refs.append(example['head']+'\trefs/heads/'+example['id'])
  oids=json.loads((a.data/(example['id']+'.json')).read_text())['evidence']['objects']
  for oid in oids:
   raw=(a.data/'objects'/oid).read_bytes()
   if hashlib.sha1(raw).hexdigest()!=oid:raise ValueError('Hash mismatch: '+oid)
   target=a.output/'objects'/oid[:2]/oid[2:];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(zlib.compress(raw));count+=1
  # Standard Git packs contain the original verified objects, including gitlink
  # targets and child records that an ordinary branch push would not traverse.
  with tempfile.TemporaryDirectory(prefix='caos-pack-') as tmp:
   subprocess.run(['git','init','--quiet',tmp],check=True)
   info=Path(tmp)/'.git/objects/info'
   (info/'alternates').write_text(str((a.output/'objects').resolve())+'\n')
   packed=subprocess.check_output(['git','-C',tmp,'-c','pack.threads=2','pack-objects','--stdout','--delta-base-offset'],input=('\n'.join(sorted(oids))+'\n').encode())
   if hashlib.sha1(packed[:-20]).digest()!=packed[-20:]:raise ValueError('Invalid pack checksum')
   packpath=packs/(example['head']+'.pack')
   packpath.write_bytes(packed)
   subprocess.run(['git','-C',tmp,'index-pack','--index-version=2','-o',str((packs/(example['head']+'.idx')).resolve()),str(packpath.resolve())],check=True,stdout=subprocess.DEVNULL)
   print(example['id'],len(oids),'objects,',len(packed),'packed bytes')
 (a.output/'info').mkdir(exist_ok=True);(a.output/'info/refs').write_text('\n'.join(refs)+'\n')
 (a.output/'HEAD').write_text('ref: '+refs[0].split('\t')[1]+'\n')
 print('Published',count,'verified object references as loose Git objects.')
if __name__=='__main__':main()
