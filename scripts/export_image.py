"""Download official sub2api into an OCI archive for slow server networks.

Usage: python scripts/export_image.py /path/to/sub2api.tar
Verify every blob against the registry digest. No credentials are needed.
"""
import concurrent.futures
import hashlib
import json
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

base='https://ghcr.io/v2/wei-shaw/sub2api/'
token=json.load(urllib.request.urlopen('https://ghcr.io/token?scope=repository:wei-shaw/sub2api:pull',timeout=30))['token']
headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json'}
def get(url):
    return urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=120)
with get(base+'manifests/latest') as r: index=json.load(r)
descriptor=next(x for x in index['manifests'] if x.get('platform',{}).get('architecture')=='amd64' and x.get('platform',{}).get('os')=='linux')
with get(base+'manifests/'+descriptor['digest']) as r: manifest_bytes=r.read()
assert hashlib.sha256(manifest_bytes).hexdigest()==descriptor['digest'].split(':')[1]
manifest=json.loads(manifest_bytes)
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp); blobs=root/'blobs'/'sha256';blobs.mkdir(parents=True)
    (blobs/descriptor['digest'].split(':')[1]).write_bytes(manifest_bytes)
    def download(item):
        name=item['digest'].split(':')[1]
        digest=hashlib.sha256()
        with get(base+'blobs/'+item['digest']) as r, (blobs/name).open('wb') as f:
            while chunk:=r.read(1024*1024):
                f.write(chunk);digest.update(chunk)
        if digest.hexdigest()!=name:raise RuntimeError('Image digest mismatch')
        print('Verified blob',name[:12],flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(download,[manifest['config']]+manifest['layers']))
    descriptor['annotations']={'org.opencontainers.image.ref.name':'ghcr.io/wei-shaw/sub2api:latest','io.containerd.image.name':'ghcr.io/wei-shaw/sub2api:latest'}
    (root/'index.json').write_text(json.dumps({'schemaVersion':2,'manifests':[descriptor]}))
    (root/'oci-layout').write_text('{"imageLayoutVersion":"1.0.0"}')
    with tarfile.open(sys.argv[1],'w') as archive:
        for path in root.rglob('*'):
            if path.is_file():archive.add(path,arcname=path.relative_to(root))
    print('Archive ready. Manifest:',descriptor['digest'])
