import os
import sys
import hashlib
from pathlib import Path

# Load DATABASE_URL from the .env file located in the project root (apps/api/.env)
env_path = Path(__file__).resolve().parents[1] / ".env"
if env_path.is_file():
    for line in env_path.read_text().splitlines():
        if line.startswith('DATABASE_URL='):
            _, val = line.split('=', 1)
            # Convert legacy scheme to SQLAlchemy-supported scheme
            if val.startswith('postgres://'):
                val = 'postgresql://' + val[len('postgres://'):]
            os.environ['DATABASE_URL'] = val.strip()
            break

# Ensure the project root (apps/api) is on PYTHONPATH for app imports
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import Link, ClickEvent

def main() -> None:
    db = SessionLocal()
    try:
        # Ensure the sample link exists (idempotent)
        link = db.query(Link).filter_by(code='abc123').first()
        if not link:
            link = Link(
                code='abc123',
                long_url='https://example.com',
                created_by='org_1',
                tags='demo,seed',
            )
            db.add(link)
            db.commit()
            db.refresh(link)
            print(f'Inserted link id={link.id} code={link.code}')
        else:
            print(f'Link already exists id={link.id} code={link.code}')

        # Insert a click event (always add a new click)
        ip = '1.2.3.4'
        ip_hash = hashlib.sha256(ip.encode()).hexdigest()
        click = ClickEvent(
            link_id=link.id,
            user_agent='seed_verify/1.0',
            referrer='https://referrer.test',
            ip_hash=ip_hash,
        )
        db.add(click)
        db.commit()
        db.refresh(click)
        print(f'Inserted click id={click.id} for link_id={click.link_id}')

        # Retrieve the link by short code and show its URL
        fetched = db.query(Link).filter_by(code='abc123').first()
        print(f'Lookup URL: {fetched.long_url}')

        # Count clicks for that link
        click_count = db.query(ClickEvent).filter_by(link_id=link.id).count()
        print(f'Click count for {link.code}: {click_count}')
    finally:
        db.close()

if __name__ == '__main__':
    main()
