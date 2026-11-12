"""Restore the 124 audited WRA archives by pinned source URL and SHA-256."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
import hashlib,json,subprocess,zipfile
def fetch(entry):
 path=Path('tw')/entry['file']
 def verified():
  return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
 if not verified():
  url=entry['url']
  alt=url.replace('https://raw.githubusercontent.com/cjw612/Flood_Analysis/','https://cdn.jsdelivr.net/gh/cjw612/Flood_Analysis@')
  for target in (url,alt):
   proc=subprocess.run(['curl','-fsSL','--retry','2','--retry-all-errors','--max-time','60',target,'-o',str(path)])
   if proc.returncode==0 and verified():break
  else:raise RuntimeError('Could not restore exact snapshot '+str(path))
 with zipfile.ZipFile(path) as z: assert z.testzip() is None
Path('tw').mkdir(exist_ok=True)
with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(fetch,json.loads(Path('manifest.json').read_text())))
print('Verified all source archives.')
