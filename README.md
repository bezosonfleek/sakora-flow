# Sakora Till - Phase 0

A Django app behind Caddy (automatic HTTPS) with Postgres and Databasus backups, all in Docker Compose.

| Container | Job |
|---|---|
| `caddy` | HTTPS certificates and routing (ports 80/443) |
| `web` | Django + gunicorn (runs migrations on start) |
| `db` | PostgreSQL 16 on a persistent volume |
| `databasus` | Scheduled backups of `db` (UI on localhost:4005 only) |

## 1. Prepare the server

- Linux server with Docker and the Compose plugin installed.
- A DNS **A record** for your hostname (e.g. `app.yourdomain.com`) pointing at the server's public IP.
- Firewall: allow 22, 80 and 443 only. Do **not** open 5432 or 4005.

## 2. Deploy

```bash
git clone <your-repo-url> sakoratill && cd sakoratill
cp .env.example .env
```

Edit `.env`: set `DOMAIN`, the two hostnames, and generate the secrets:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(60))"   # DJANGO_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # POSTGRES_PASSWORD
```

Start everything and create your SUPERADMIN login:

```bash
docker compose up -d --build
docker compose exec web python manage.py createsuperuser
```

Check it: open `https://<your hostname>/healthz` (should show `{"status": "ok", "db": "up"}`), then `/login/` and `/admin/`.

Once HTTPS works, set `DJANGO_HSTS_SECONDS=31536000` in `.env` and run `docker compose up -d`.

## 3. Backups with Databasus

The UI listens on the server's localhost only. From your laptop:

```bash
ssh -L 4005:localhost:4005 user@your-server
```

Then open http://localhost:4005 and:

1. Create the admin account.
2. Add a database: host `db`, port `5432`, and the `POSTGRES_*` values from `.env`.
3. Set **storage off the server** (S3-compatible bucket or Google Drive).
4. Set the schedule to **every 1-6 hours**, with sensible retention.
5. Turn on failure notifications (email, Slack or Telegram).

Check the image name and options in the Databasus docs before first use, since they change.

**Restore test (do it now, then monthly):** download a backup, restore it into a scratch Postgres container, and confirm the tables and rows are there. Until you've done this, you don't have backups.

## 4. Updating

```bash
git pull
docker compose up -d --build
```

Migrations run automatically when `web` starts. Take a backup in Databasus before releases that change the database.

## 5. Staging

Use a second server (or the same one with a different folder, hostname and `.env`) so you never test on a client's live system. Give it its own database and its own Databasus.

## Useful commands

```bash
docker compose ps                  # status and health
docker compose logs -f web         # app logs
docker compose exec web python manage.py shell
docker compose exec db psql -U sakoratill sakoratill
```

## Local development without Docker for the app

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export DJANGO_DEBUG=1 POSTGRES_HOST=localhost POSTGRES_PASSWORD=dev
python manage.py migrate && python manage.py runserver
```

(Run a local Postgres first, e.g. `docker run -d -p 5432:5432 -e POSTGRES_USER=sakoratill -e POSTGRES_PASSWORD=dev -e POSTGRES_DB=sakoratill postgres:16-alpine`.)
