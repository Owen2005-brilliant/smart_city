from pathlib import Path
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from datetime import date,timedelta
import hashlib,json,subprocess,zipfile
tree=json.loads(Path('taiwan_tree.json').read_text());months=('202308', '202309')
items=[i for i in tree['tree'] if i['path'].endswith('.zip') and i['path'][-12:-6] in months and '淹水感測器' in i['path']]
def get(i):
 path=i['path'];name=Path('tw')/Path(path).name
 url='https://raw.githubusercontent.com/cjw612/Flood_Analysis/'+tree['sha']+'/'+quote(path)
 if not name.exists() or name.stat().st_size!=i['size']:
  urls=[url,'https://cdn.jsdelivr.net/gh/cjw612/Flood_Analysis@'+tree['sha']+'/'+quote(path),'https://api.github.com/repos/cjw612/Flood_Analysis/git/blobs/'+i['sha']]
  for candidate in urls:
   res=subprocess.run(['curl','-fLsS','--max-time','40','--connect-timeout','6','--retry','1','--retry-all-errors','-H','Accept: application/vnd.github.raw+json',candidate,'-o',str(name)])
   if res.returncode==0 and name.stat().st_size==i['size']:break
  else:raise RuntimeError(path)
 data=name.read_bytes();assert hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()==i['sha']
 with zipfile.ZipFile(name) as z:assert z.testzip() is None
 return {'file':name.name,'url':url,'sha256':hashlib.sha256(data).hexdigest()}
Path('tw').mkdir(exist_ok=True)
with ThreadPoolExecutor(max_workers=6) as pool:result=list(pool.map(get,items))
Path('manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(len(result), sum(f.stat().st_size for f in Path('tw').glob('*.zip')))
