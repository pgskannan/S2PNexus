# S2PNexus Deploy Cheat Sheet

The working push → pull → deploy flow for the backend, plus the gotchas that have actually bitten us. Keep this updated whenever the flow changes.

## 1. Push (on your local machine, in `C:\S2PNexus`)

```
git add -A
git commit -m "<message>"
git push origin main
```

- If `git add`/`git commit` fails with `Unable to create '.git/index.lock': File exists`: no git process is actually stuck most of the time — just delete it and retry. If it keeps coming back, check for a hung `git.exe` (`tasklist | findstr git`, then `taskkill /F /IM git.exe`) or close any IDE/Git GUI (VS Code, GitHub Desktop, etc.) with the repo open — those poll `git status` in the background and can hold the lock.
  ```
  del C:\S2PNexus\.git\index.lock
  ```
- `warning: LF will be replaced by CRLF` on `git add` is harmless (Windows line-ending normalization) — ignore it.

## 2. Pull (Cloud Shell)

First time only:
```
git clone https://github.com/pgskannan/S2PNexus.git
```

Every time after:
```
cd ~/S2PNexus
git pull origin main
```

## 3. Deploy backend (Cloud Shell)

```
cd ~/S2PNexus/backend
gcloud run deploy s2pnexus-backend --source . --region=us-central1 --project=s2pnexus
```

- First-ever source deploy asks to create an Artifact Registry repo (`cloud-run-source-deploy`) — say `y`, it's a one-time setup.
- **Don't add `--set-env-vars`** unless you mean to replace the entire env var set — it silently wipes *any* var not listed, not just `CORS_ORIGINS`/`ALLOWED_HOSTS` (it hit `SECRET_KEY` and `DATABASE_URL` too on 2026-07-26, see incident below). To change one var, use `--update-env-vars KEY=value` instead. To leave env vars untouched (the common case), omit env var flags entirely — Cloud Run carries over the previous revision's config.
- `entrypoint.sh` runs `alembic upgrade head` automatically on container start, so DB migrations ship with the deploy — no separate migration step needed. This also means a bad env var (missing `SECRET_KEY`, wrong `DATABASE_URL` password, etc.) crashes the container *before* `uvicorn` ever starts, which Cloud Run reports as a generic "container failed to start and listen on port 8080" — don't take that message literally as a port/config problem, it almost always means the process crashed on startup for an unrelated reason.

### If a deploy fails with "container failed to start and listen on port 8080"

Don't guess — pull the actual startup traceback for that specific revision (the generic health-check message hides it):
```
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.revision_name=<REVISION_NAME>" --project=s2pnexus --limit=50 --format="value(textPayload)"
```
(Get `<REVISION_NAME>` from the failed deploy's own output, or `gcloud run revisions list --service=s2pnexus-backend --region=us-central1 --project=s2pnexus --sort-by=~metadata.creationTimestamp --limit=5` — the ✔/✘ column shows which ones actually went healthy.)

If it turns out to be a corrupted/missing env var, compare variable *names* (not values — don't paste secret values into a chat/AI session) between the current service and the last known-good revision:
```
gcloud run revisions describe <LAST_GOOD_REVISION> --region=us-central1 --project=s2pnexus --format="value(spec.containers[0].env[].name)" | tr ';' '\n' | sort > /tmp/good_vars.txt
gcloud run services describe s2pnexus-backend --region=us-central1 --project=s2pnexus --format="value(spec.template.spec.containers[0].env[].name)" | tr ';' '\n' | sort > /tmp/current_vars.txt
diff /tmp/good_vars.txt /tmp/current_vars.txt
```
If names match but a value is still wrong (like the DB password incident), pull the correct value from the known-good revision directly in your terminal and reapply with `--update-env-vars` — don't relay full secret values through chat/AI tooling. If you do end up pasting a secret somewhere it shouldn't be, rotate it afterward (new `SECRET_KEY`, `ALTER USER ... WITH PASSWORD ...` on Postgres + update `DATABASE_URL`, etc.).

## 4. Deploy frontend (Cloud Shell, only when frontend changes)

```
cd ~/S2PNexus/frontend
gcloud builds submit --config=cloudbuild.yaml
gcloud run deploy s2pnexus-frontend --image=us-central1-docker.pkg.dev/s2pnexus/s2pnexus-repo/frontend:latest --region=us-central1 --project=s2pnexus
```
(Uses `cloudbuild.yaml` rather than a plain `gcloud builds submit --tag=...` because it needs to pass `NEXT_PUBLIC_API_URL` as a build arg at Next.js build time, which the plain command can't do.)

**Both commands are required** — `cloudbuild.yaml` only builds the image and pushes it to Artifact Registry (`:latest` tag), it has no deploy step. Without the second command the Cloud Run service keeps serving the old revision even though the build says `STATUS: SUCCESS` (confirmed 2026-07-27: a Documents page build succeeded and pushed but never went live until this was run explicitly). Ignore `⨯ Failed to patch lockfile` / `TypeError: Cannot read properties of undefined (reading 'os')` during the build — it's a harmless Next.js SWC-lockfile-patching quirk that doesn't stop the build (look for `✓ Compiled successfully` right after it).

## 5. After deploying

- Check `https://s2pnexus-backend-120737021520.us-central1.run.app/health` — should return `{"status":"healthy", ..., "database":"connected"}`.
- If a code change touched auth/JWT handling, **log out and back in** on the dashboard — old tokens signed under a previous `SECRET_KEY` (or before a fix) won't decode against the new deploy.
- If something still errors, pull backend logs before guessing:
  ```
  gcloud run services logs read s2pnexus-backend --region=us-central1 --project=s2pnexus --limit=100
  ```
  The global exception handler in `app/main.py` prints a full traceback on any unhandled exception, so the real error is almost always in there.

## 6. Running one-off scripts against the DB from Cloud Shell (seed scripts, manual queries, etc.)

The database is **not** Cloud SQL — it's a self-hosted Postgres instance on Compute Engine VM `s2pnexus-db-vm` (zone `us-central1-a`, internal IP `10.128.0.2`, port 5432). Cloud Run reaches it over the VPC connector; Cloud Shell is not on that network, so a direct connection times out. As of 2026-08-02, an IAP tunnel path is set up and working:

**One-time setup already done** (don't repeat unless it breaks):
- Firewall rule `allow-iap-postgres` allows `35.235.240.0/20` (IAP's range) to reach port 5432 on tag `postgres-db`.
- `/etc/postgresql/15/main/pg_hba.conf` on the VM has `host s2pnexus s2pnexus_app 35.235.240.0/20 md5` appended (reloaded via `sudo systemctl reload postgresql`).

**Every time you need to run a script:**

Tab 1 — start the tunnel and leave it running:
```
gcloud compute start-iap-tunnel s2pnexus-db-vm 5432 \
  --local-host-port=localhost:5433 \
  --zone=us-central1-a --project=s2pnexus
```

Tab 2 — pull `SECRET_KEY`/`DATABASE_URL` fresh from the live Cloud Run service (don't rely on a local `.env` — there isn't one in `backend/`) and swap the DB host to the tunnel:
```
cd ~/S2PNexus/backend
source .venv/bin/activate

export SECRET_KEY="$(gcloud run services describe s2pnexus-backend \
  --region=us-central1 --project=s2pnexus \
  --format=json | python3 -c "import sys,json; envs=json.load(sys.stdin)['spec']['template']['spec']['containers'][0].get('env',[]); print(next(e['value'] for e in envs if e['name']=='SECRET_KEY'))")"

export DATABASE_URL="$(gcloud run services describe s2pnexus-backend \
  --region=us-central1 --project=s2pnexus \
  --format=json | python3 -c "import sys,json; envs=json.load(sys.stdin)['spec']['template']['spec']['containers'][0].get('env',[]); print(next(e['value'] for e in envs if e['name']=='DATABASE_URL'))" | sed -E 's#@10\.128\.0\.2:5432/#@localhost:5433/#')"

python -m scripts.<whatever_script>
```

Env vars don't carry across Cloud Shell tabs — re-export in whichever tab you're actually running the script from. If the tunnel test fails with `[4003: 'failed to connect to backend']`, that's the firewall rule missing/reverted; if `asyncpg.exceptions.InvalidAuthorizationSpecificationError: no pg_hba.conf entry...`, that's the `pg_hba.conf` line missing/reverted — both should already be in place per above.

## Service URLs

- Backend: `https://s2pnexus-backend-120737021520.us-central1.run.app`
- Frontend: `https://s2pnexus-frontend-120737021520.us-central1.run.app`
- Region: `us-central1`, Project: `s2pnexus`

## Known incidents (for context, not action items)

- **2026-07-26 — CORS errors on every authenticated endpoint.** Looked like a CORS misconfig; was actually `get_current_user` throwing an unhandled `jwt.InvalidTokenError` on stale/mis-signed tokens. FastAPI/Starlette route handlers registered for the bare `Exception` class through `ServerErrorMiddleware`, which sits *outside* `CORSMiddleware` — so any unhandled exception (not just this one) comes back with no CORS header and browsers report it as "blocked by CORS policy" instead of showing the real error. Fixed at the source in `app/core/dependencies.py` (catch `InvalidTokenError`, raise a proper 401). Worth remembering generally: an unexplained CORS error on a previously-working endpoint is worth checking backend logs for a real exception before assuming it's a CORS config problem.
- **2026-07-25 — Cloud Run deploy lagged commits.** Backend commits sat on `main` for hours before being deployed, including a real CORS fix. If something's broken in prod, check `git log` vs. what's actually deployed before deep-diving — it might just need a redeploy.
- **2026-07-26 — Three deploys in a row failed silently after an env var wipe.** Traffic stayed pinned on revision `00017` (04:39 UTC) while `00019`–`00022` all failed their health check and were auto-discarded — from the browser this looked identical to earlier CORS incidents (every authenticated call failing), which cost time before checking `gcloud run revisions list` and noticing the ✘ column. Root cause: `SECRET_KEY` had been wiped to an empty string at the service level (Pydantic rejected it, container exited before `uvicorn` bound to the port) and `DATABASE_URL`'s password no longer matched the DB (`asyncpg.exceptions.InvalidPasswordError`). Both fixed with `--update-env-vars` (new random `SECRET_KEY` via `openssl rand -hex 32`; `DATABASE_URL` restored from the last known-good revision, `00017`). **Lesson:** after any deploy attempt, check `gcloud run revisions list` for the ✔/✘ column and confirm traffic actually moved — "the push/pull/deploy commands all succeeded" doesn't mean the new revision is serving.
