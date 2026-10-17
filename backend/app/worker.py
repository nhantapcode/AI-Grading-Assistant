"""Run separately: python -m app.worker [--once] [--cleanup-orphans]."""
import argparse
import json
import mimetypes
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from app.core.config import settings
from app.repositories.jobs import JobRepository
from app.storage.local import LocalStorage


def connection() -> psycopg.Connection:
    return psycopg.connect(settings.database_url,row_factory=dict_row)


def run_once(file_id: UUID | None = None) -> bool:
    storage = LocalStorage()
    with connection() as db:
        repo = JobRepository(db)
        job = repo.claim(file_id)
        if not job:
            return False
        asset = repo.asset(job)
    objects = []
    try:
        with connection() as db:
            JobRepository(db).stage(job)
        with tempfile.TemporaryDirectory(prefix='grading-extract-') as directory:
            destination = Path(directory)
            process = subprocess.run([sys.executable,'-m','app.extract_file','--',str(storage.path(asset['object_key'])),asset['original_filename'],directory],
                                     capture_output=True,timeout=120)
            if process.returncode:
                error = (destination/'error.txt').read_text() if (destination/'error.txt').exists() else 'File processing failed'
                with connection() as db:
                    JobRepository(db).fail(job,error,True)
                return True
            data = json.loads((destination/'manifest.json').read_text())
            if data['sha256'] != asset['sha256']:
                raise ValueError('File checksum mismatch')
            children = []
            if asset['original_filename'].lower().endswith('.zip'):
                for entry in data['files']:
                    key = uuid4()
                    with Path(entry['path']).open('rb') as stream:
                        size,digest = storage.write(str(key),stream,settings.max_file_bytes)
                    objects.append(str(key))
                    children.append({'id':key,'name':entry['name'],'text':entry['text'],'size':size,'digest':digest,
                                     'content_type':mimetypes.guess_type(entry['name'])[0] or 'text/plain'})
            text = '\n\n'.join(f"{entry['name']}\n{entry['text']}" for entry in data['files'])
            with connection() as db:
                completed = JobRepository(db).complete(job,asset,text,children)
            if not completed:
                for key in objects:
                    storage.delete(key)
    except Exception as error:
        for key in objects:
            storage.delete(key)
        with connection() as db:
            JobRepository(db).fail(job,'Processing timed out' if isinstance(error,subprocess.TimeoutExpired) else 'Processing failed. Retry or upload a replacement',False)
    return True


def cleanup_orphans() -> int:
    storage = LocalStorage()
    with connection() as db:
        tracked = JobRepository(db).object_keys()
    count = 0
    for path in storage.root.glob('*'):
        if path.is_file() and path.name not in tracked and path.stat().st_mtime<time.time()-86400:
            # Only this storage namespace is touched, and keys must be UUIDs.
            storage.delete(path.name)
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--cleanup-orphans',action='store_true')
    args = parser.parse_args()
    if args.cleanup_orphans:
        print(f'Removed {cleanup_orphans()} orphan objects older than 24 hours')
        return
    while True:
        worked = run_once()
        if args.once:
            break
        if not worked:
            time.sleep(1)


if __name__=='__main__':
    main()
