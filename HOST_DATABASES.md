# Docker services using the host databases

`docker-compose.override.yml` is loaded automatically by ordinary `docker compose` commands. Backend, MLOps and Streamlit use Aiven MySQL and the Mac's PostgreSQL; the database credentials are not embedded in Compose.

* Backend loads its DB_* and JWT_SECRET values from `backend/.env`.
* MLOps and Streamlit use `.docker-host.env`, generated from `backend/.env` and `mlops/.env`. PostgreSQL's loopback hostname is translated to `host.docker.internal` for Docker Desktop. MySQL uses the same Aiven database as the backend.
* `.docker-host.env` is mode 0600 and ignored by Git. Its Compose env-file format is raw, so password characters are not interpreted as variable references.
* Aiven connections use TLS. The existing host configuration does not provide the private Aiven CA; this change preserves that connection policy rather than claiming CA-verified authentication.
* Kafka remains enabled with its existing consumer group and offsets. All three partitions had zero backlog before the switch. No historical data was copied or merged.
* The old MySQL/PostgreSQL services belong to the `isolated-db` profile. Their existing named volumes are preserved. Do not use `down -v` if you want to retain those databases.

## Normal startup

Start the Mac PostgreSQL service and Docker Desktop, then run from this project:

```sh
docker compose up -d
```

The app continues to use `http://10.0.2.2:8080/` in the emulator. Sign out and sign in with an account from Aiven after switching datasets. Old Docker account IDs and cached account details do not establish account identity in Aiven.

## After host database credentials change

```sh
mlops/venv/bin/python scripts/sync-host-database-env.py
docker compose up -d --force-recreate backend mlops streamlit
```

## Return to the original isolated Docker dataset

Explicitly selecting the base Compose file excludes the host override:

```sh
docker compose -f docker-compose.yml up -d mysql postgres kafka zookeeper
docker compose -f docker-compose.yml up -d --force-recreate backend mlops streamlit
```

Use accounts from that dataset after switching back. This is a connection switch, not a migration or merge.
