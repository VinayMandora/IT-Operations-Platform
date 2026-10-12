"""Generate deterministic fictional UK call records; no live PBX data."""
import csv
from datetime import datetime, timedelta
from pathlib import Path


def main():
    target=Path(__file__).resolve().parents[1]/'sample_data'/'task5_call_logs.csv'
    first=datetime(2026,10,1,8,30)
    with target.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.writer(stream)
        writer.writerow(['call_reference','extension','occurred_at','direction','duration_seconds','route','outcome'])
        for i in range(1,61):
            direction='Outbound' if i%5==0 else 'Inbound'
            outcome='Missed' if i%7==0 else ('Voicemail' if i%11==0 else 'Answered')
            writer.writerow([f'NCALL-{i:05d}', str(201+i%7),
                (first+timedelta(minutes=i*26)).strftime('%Y-%m-%dT%H:%M:%SZ'), direction,
                0 if outcome=='Missed' else (i*23)%600,
                'ClaimsQueue' if i%3 else 'Reception', outcome])
    print(f'Generated 60 fictional call records: {target}')


if __name__=='__main__': main()
