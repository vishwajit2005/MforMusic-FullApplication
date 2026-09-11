"""Refresh private Docker URLs from the existing host database settings."""
from pathlib import Path
import os
from dotenv import dotenv_values
from sqlalchemy.engine import URL, make_url

root = Path(__file__).resolve().parents[1]
backend = dotenv_values(root / 'backend/.env')
mlops = dotenv_values(root / 'mlops/.env')
postgres_url = make_url(mlops['DATABASE_URL'])
if postgres_url.host in ('localhost', '127.0.0.1', '::1'):
    postgres_url = postgres_url.set(host='host.docker.internal')
# Use the host configuration's TLS policy. The project has no Aiven private CA
# configured, so this enables encryption without adding a new CA requirement.
mysql_url = URL.create(
    'mysql+pymysql', username=backend['DB_USER'], password=backend['DB_PASSWORD'],
    host=backend['DB_HOST'], port=int(backend['DB_PORT']), database=backend['DB_NAME'],
    query={'ssl_verify_identity': 'true'},
)
path = root / '.docker-host.env'
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as handle:
    handle.write('DATABASE_URL=' + postgres_url.render_as_string(hide_password=False) + '\n')
    handle.write('MYSQL_URL=' + mysql_url.render_as_string(hide_password=False) + '\n')
os.chmod(path, 0o600)
print('Updated private Docker database settings. No credentials displayed.')
