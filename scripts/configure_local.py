"""Create a private local .env with an unpredictable signing key without overwriting secrets."""
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    path = ROOT / '.env'
    if path.exists():
        existing = path.read_text(encoding='utf-8')
    else:
        existing = (ROOT / '.env.example').read_text(encoding='utf-8')
    lines = existing.splitlines()
    found = False
    for idx, line in enumerate(lines):
        if line.startswith('APP_SECRET_KEY='):
            found = True
            if not line.partition('=')[2].strip():
                lines[idx] = 'APP_SECRET_KEY=' + secrets.token_urlsafe(48)
    if not found:
        lines.append('APP_SECRET_KEY=' + secrets.token_urlsafe(48))
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Local .env ready. Existing values and nonempty APP_SECRET_KEY preserved.')


if __name__ == '__main__':
    main()
