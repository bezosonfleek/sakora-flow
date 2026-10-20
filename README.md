# SakoraFlow

Point-of-sale for supermarkets and shops. Django + Postgres, behind Caddy (automatic HTTPS), with Databasus backups, all in Docker Compose.

Status: **Phase 0** (hosting) done. **Phase 1** (core selling) written, awaiting its first run: see "First run of Phase 1".

| Container | Job |
|---|---|
| `caddy` | HTTPS certificates and routing |
| `web` | Django + gunicorn (runs migrations on start) |
| `db` | PostgreSQL 16 on a persistent volume |
| `databasus` | Scheduled backups of `db` (UI on localhost:4005 only) |

## First run of Phase 1 (migrations must be generated once)

Phase 1 adds database models, so their migration files must be generated and committed. The web container refuses to start until they exist (this is deliberate: it stops a model change from reaching a server without its migration).

```bash
git switch -c phase-1
cp .env.example .env            # skip if .env exists; set HTTP_PORT=8080 locally if port 80 is taken
docker compose build web
./deploy/makemigrations.sh      # writes accounts/, catalog/, sales/ migrations/ folders
git add -A && git status        # check .env is NOT listed
docker compose up -d --build
docker compose exec web python manage.py test     # run the test suite
docker compose exec web python manage.py createsuperuser   # you, the SUPERADMIN
docker compose exec web python manage.py seed_demo         # demo client "Kijani Mini Mart"
```

`seed_demo` prints one-time sign-in details for the demo owner, admin and cashier. Use it on development machines only.

## Using it

- **SUPERADMIN** (`/admin/`): create clients (businesses) and their first owner, suspend a client, fix records.
- **Owner / Admin**: dashboard, products, stock actions, CSV import, staff, sales, voids, daily report, shifts. Only the owner edits business settings (VAT rate, receipt width and text).
- **Cashier**: password at `/login/` or username + PIN at `/pin-login/`. Opens a shift (counted float), sells at `/till/`, closes the shift by counting the drawer.
- **Till keys**: scan or type then Enter; `3*<barcode>` adds three; Enter on an empty box or F2 opens payment; Esc goes back.
- **Payments**: cash, M-Pesa (typed code, used once only, shown as "unverified" until you reconcile with the M-Pesa statement), card and bank (recorded only). Split payments allowed; cash covers the remainder and change is worked out.
- **Receipts** print through the browser at the width set in settings (58 or 80 mm). For no print dialog, start Chrome with `--kiosk-printing`.
- **Selling past zero stock** is allowed (the item is already at the till). Stock goes negative and shows on the dashboard.

## Deploying

1. Server with Docker and the Compose plugin; DNS A record for your hostname; firewall open on 22, 80, 443 only.
2. `git clone`, `cp .env.example .env`, fill in `DOMAIN`, hostnames and secrets:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(60))"   # DJANGO_SECRET_KEY
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # POSTGRES_PASSWORD
   ```
3. `docker compose up -d --build`, then `docker compose exec web python manage.py createsuperuser`.
4. Check `https://<host>/healthz`, then set `DJANGO_HSTS_SECONDS=31536000` once HTTPS works.
5. Do **not** run `seed_demo` on a production server.

Updates: `git pull && docker compose up -d --build` (migrations run on start). Take a Databasus backup before releases that change the database.

## Backups with Databasus

The UI listens on the server's localhost only: `ssh -L 4005:localhost:4005 user@server`, then open http://localhost:4005.
Add the database (host `db`, port `5432`, values from `.env`), choose storage **off the server**, schedule every 1-6 hours, turn on failure alerts. Test a restore into a scratch Postgres now and monthly.

## Working with git

- One branch per phase or feature (`phase-1`, `phase-2-offline`), merged to `main` by pull request after the tests pass.
- Always commit migration files together with the model change that needs them.
- Never commit `.env`. Tag what goes live (`git tag v0.1.0`) so you can roll back.

## Commands

```bash
docker compose ps                         # status and health
docker compose logs -f web                # app logs
docker compose exec web python manage.py test
docker compose exec web python manage.py shell
docker compose exec db psql -U sakoratill sakoratill
./deploy/makemigrations.sh                # after changing any models
```
