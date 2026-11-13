"""Generate private configuration on the authorized host without exporting secrets."""
from pathlib import Path
import secrets

root = Path('private')
root.mkdir(mode=0o700, exist_ok=False)


def write(name, value, mode=0o600):
    path = root / name
    with path.open('x') as stream:
        stream.write(value)
    path.chmod(mode)


pg, runtime, broker, results, auth, health, signing, admin = (
    secrets.token_hex(32) for _ in range(8))
write('pg.env', f'POSTGRES_USER=demo_owner\nPOSTGRES_DB=sgdea_demo\nPOSTGRES_PASSWORD={pg}\n')
write('app.env', f'DATABASE_URL=postgresql+psycopg2://geology_runtime:{runtime}@pg:5432/sgdea_demo\n'
      f'CELERY_BROKER_URL=redis://broker:{broker}@redis:6379/0\n'
      f'CELERY_RESULT_BACKEND=redis://results:{results}@redis:6379/1\n'
      f'AUTH_REDIS_URL=redis://auth:{auth}@redis:6379/2\nGEOLOGY_CLAVE={signing}\n'
      'ORIGENES_PERMITIDOS=http://127.0.0.1:18099\nDB_POOL_SIZE=3\nDB_MAX_OVERFLOW=2\n')
write('redis.env', f'REDISCLI_AUTH={health}\n')
write('redis.conf', Path('redis.conf.example').read_text(), 0o644)
write('users.acl', 'user default off\n'
      f'user health on >{health} +ping\n'
      f'user broker on >{broker} ~tec-sgdea-demo:* &* '
      '+ping +client|setinfo +select|0 +brpop +lpush +rpush +llen +lrange +lrem +sadd +srem +smembers '
      '+del +exists +expire +hset +hget +hdel +zadd +zrem +zrevrangebyscore +set +get +evalsha +script|load '
      '+watch +unwatch +multi +exec +discard +publish +subscribe +psubscribe +unsubscribe +punsubscribe\n'
      f'user results on >{results} ~tec-sgdea-demo:_celery-task-meta-* &tec-sgdea-demo:_celery-task-meta-* '
      '+ping +client|setinfo +select|1 +get +mget +set +setex +del +publish +subscribe +unsubscribe '
      '+psubscribe +punsubscribe +multi +exec +discard +expire +incrby\n'
      f'user auth on >{auth} ~tec-sgdea-demo:auth:v1:* +ping +client|setinfo +eval +get +set +del +waitaof +ttl +select|2\n',
      0o644)
write('owner.env', f'DATABASE_URL=postgresql+psycopg2://demo_owner:{pg}@pg:5432/sgdea_demo\nDEMO_PASSWORD={admin}\n')
write('admin.txt', f'admin.sgdea.demo@example.invalid\n{admin}\n')
write('role.sql', f"CREATE ROLE geology_runtime LOGIN PASSWORD '{runtime}';\n"
      'REVOKE ALL ON DATABASE sgdea_demo FROM PUBLIC;\nGRANT CONNECT ON DATABASE sgdea_demo TO geology_runtime;\n'
      'REVOKE CREATE ON SCHEMA public FROM PUBLIC;\nGRANT USAGE ON SCHEMA public TO geology_runtime;\n'
      'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO geology_runtime;\n'
      'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO geology_runtime;\n')
