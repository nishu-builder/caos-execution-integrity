#!/usr/bin/env python3
"""Publish verified captured objects in Git's standard loose-object layout."""
import argparse, hashlib, json, zlib
from pathlib import Path

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--data',type=Path,default=Path(__file__).resolve().parents[1]/'docs/trajectories/data')
 p.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'docs/trajectories/git')
 a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 refs=[];count=0
 for example in json.loads((a.data/'index.json').read_text())['examples']:
  refs.append(example['head']+'\trefs/heads/'+example['id'])
  for oid in json.loads((a.data/(example['id']+'.json')).read_text())['evidence']['objects']:
   raw=(a.data/'objects'/oid).read_bytes()
   if hashlib.sha1(raw).hexdigest()!=oid:raise ValueError('Hash mismatch: '+oid)
   target=a.output/'objects'/oid[:2]/oid[2:];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(zlib.compress(raw));count+=1
 (a.output/'info').mkdir(exist_ok=True);(a.output/'info/refs').write_text('\n'.join(refs)+'\n')
 (a.output/'HEAD').write_text('ref: refs/heads/repair\n')
 print('Published',count,'verified object references as loose Git objects.')
if __name__=='__main__':main()
