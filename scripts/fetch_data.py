"""Download the official archive, verify its checksum, and extract only event logs.

No downloaded Python is executed. Raw data stays local and is git-ignored.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
import urllib.request

URL = 'https://zenodo.org/records/10439422/files/KuaiRand-1K.tar.gz'
MD5 = '6b0b9c8222d67fcd4c676218edca3f1f'
SIZE = 1135436720
FILES = ['log_random_4_22_to_5_08_1k.csv',
         'log_standard_4_08_to_4_21_1k.csv',
         'log_standard_4_22_to_5_08_1k.csv']
ROOT = Path(__file__).resolve().parents[1]

def digest(path, algorithm='sha256'):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, algorithm).hexdigest()

def fetch(raw, workers=4):
    raw.mkdir(parents=True, exist_ok=True)
    archive = raw / 'KuaiRand-1K.tar.gz'
    if not archive.exists():
        # Bounded range requests permit resuming individual completed chunks.
        def chunk(i):
            start, end = SIZE*i//workers, SIZE*(i+1)//workers-1
            dest = raw / f'archive-{workers}-{i}.part'
            if not dest.exists() or dest.stat().st_size != end-start+1:
                subprocess.run(['curl.exe' if shutil.which('curl.exe') else 'curl',
                    '-sS', '-L', '--fail', '--retry', '3', '--range', f'{start}-{end}',
                    '--output', str(dest), URL], check=True)
            if dest.stat().st_size != end-start+1:
                raise ValueError('Server did not return the requested byte range')
            print(f'Chunk {i+1}/{workers} complete', flush=True)
            return dest
        with ThreadPoolExecutor(max_workers=workers) as pool:
            chunks = list(pool.map(chunk, range(workers)))
        staging = raw / 'assembled.tar.gz.part'
        with staging.open('wb') as out:
            for part in chunks:
                with part.open('rb') as f:
                    shutil.copyfileobj(f, out)
        if digest(staging, 'md5') != MD5:
            raise ValueError('Archive checksum mismatch; refusing extraction')
        staging.replace(archive)
        for part in chunks:
            part.unlink()  # Only our now-redundant download chunks.
    if digest(archive, 'md5') != MD5:
        raise ValueError('Archive checksum mismatch')
    print('Official MD5 verified; extracting event logs only', flush=True)
    extracted = {}
    with tarfile.open(archive, 'r|gz') as tar:
        for member in tar:
            name = Path(member.name).name
            if name not in FILES:
                continue
            if not member.isfile() or name in extracted:
                raise ValueError('Unexpected archive member')
            target = raw / name
            if not target.exists() or target.stat().st_size != member.size:
                with tar.extractfile(member) as src, target.open('wb') as out:
                    shutil.copyfileobj(src, out)
            extracted[name] = {'bytes': target.stat().st_size, 'sha256': digest(target)}
            print(f'Extracted {name}', flush=True)
    if set(extracted) != set(FILES):
        raise ValueError('Missing required logs')
    provenance = {'url': URL, 'archive_md5': MD5, 'archive_sha256': digest(archive),
                  'archive_bytes': SIZE, 'files': extracted}
    (raw/'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--raw-dir', type=Path, default=ROOT/'data/raw')
    p.add_argument('--workers', type=int, choices=range(1,5), default=4)
    a = p.parse_args(); fetch(a.raw_dir, a.workers)
