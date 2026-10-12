"""Offline application export recovery check. Prints table counts only, writes NO database data."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description='Read-only inspect a Northstar application recovery export')
    parser.add_argument('archive', type=Path)
    args=parser.parse_args()
    if args.archive.suffix.lower()!='.zip':
        parser.error('Expected a .zip application export')
    with zipfile.ZipFile(args.archive) as bundle:
        if bundle.testzip() is not None: raise ValueError('ZIP CRC verification failed')
        manifest=json.loads(bundle.read('manifest.json'))
        if manifest.get('format')!='NorthstarRecoverySnapshotV1': raise ValueError('Incorrect snapshot version')
        print('READ ONLY: no database connections or restore operations')
        for table,info in manifest['tables'].items():
            if table not in {'claims','tickets','assets','call_logs'}: raise ValueError('Unknown snapshot table')
            data=bundle.read(table+'.json')
            if hashlib.sha256(data).hexdigest()!=info['sha256']: raise ValueError('Hash mismatch')
            count=len(json.loads(data))
            if count!=info['rows']: raise ValueError('Row count mismatch')
            print(f'{table}: {count} recoverable rows (hash verified)')
    print('Recovery export integrity verified. Restore only into an isolated lab database.')


if __name__=='__main__': main()
