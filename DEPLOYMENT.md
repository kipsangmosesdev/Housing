# Deploying KaoProX to Vercel

Vercel detects this Django project from `manage.py` and `myProject.settings`; no hand-written catch-all route or `api/` wrapper is needed. It runs `collectstatic` from the configured `STATIC_ROOT` and serves the collected files through its CDN.

## Before deploying

1. Push the project to a Git provider connected to Vercel.
2. Connect your Neon project to Vercel and set `DATABASE_URL` to Neon's pooled connection string (the hostname contains `-pooler`). The Django settings enforce SSL, disable persistent Django connections and server-side cursors; Neon pooling manages serverless connection reuse. Vercel function storage is temporary, so the checked-in SQLite database is for local development only.
3. Configure persistent object storage for property uploads. Set `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME`, `AWS_ACCESS_KEY_ID`, and `AWS_SECRET_ACCESS_KEY` for an S3-compatible bucket. If using a custom asset domain, set `AWS_S3_CUSTOM_DOMAIN`. The bucket must permit the access pattern selected by `AWS_QUERYSTRING_AUTH`.
4. Add the following Vercel environment variables for Production and Preview as appropriate:
   - `SECRET_KEY`: a newly generated, private Django key.
   - `DEBUG=False`.
   - `DATABASE_URL`: Neon's pooled connection URL for that environment. Use Neon branches or the Vercel Neon Preview integration to keep Preview deployments isolated from production data.
   - `ALLOWED_HOSTS`: `.vercel.app` plus any custom host names, comma separated.
   - `CSRF_TRUSTED_ORIGINS`: `https://*.vercel.app` plus each custom origin including `https://`.
   - Storage credentials above.
   - SMTP settings if account emails should be sent, and integration credentials for Google Maps, OpenAI, and M-Pesa features you intend to enable.
5. Set the Vercel project Root Directory to the repository root. Leave the framework preset/build command at its detected/default value; the project uses Vercel's native Django build and static collection.

## First deploy and migrations

Deploy once with the production environment variables set. Apply database migrations against Neon from a trusted local environment using Neon's direct (non-pooled) connection URL as `DATABASE_URL`:

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
```

Use the direct connection for migrations because Django migrations may require session-level PostgreSQL behavior that transaction poolers do not provide. Keep the pooled URL configured as `DATABASE_URL` in the Vercel runtime.

Create an admin account as needed with `python manage.py createsuperuser`. Do not run migrations during the Vercel build: build jobs should not mutate the live database, and preview builds may use different databases.

## Local setup

Copy `.env.example` to `.env`, set `DEBUG=True`, and install requirements. Leaving `DATABASE_URL` blank uses local SQLite; leaving SMTP unset uses Django's console email backend. Keep `.env` out of Git.

## Operational notes

- Static files are collected into `staticfiles/`; Vercel collects these during its Django build.
- Uploaded property images require persistent object storage. Without S3-compatible storage configured, Django uses local disk, which is suitable only for development and is not durable on Vercel.
- `DEBUG=False` requires `SECRET_KEY`. Production HTTPS redirects and secure session/CSRF cookies default on; the forwarded HTTPS header is configured for Vercel.
- SQLite and local media are not copied from your development machine into production. Migrate/import data separately and configure the production bucket before enabling property uploads.
- `.env` is ignored by Git; add secrets in Vercel Project Settings instead of committing them.
