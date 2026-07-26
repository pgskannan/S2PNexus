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
- **Don't add `--set-env-vars`** unless you mean to replace the entire env var set — it silently wipes `CORS_ORIGINS`/`ALLOWED_HOSTS`/anything not listed. To change one var, use `--update-env-vars KEY=value` instead. To leave env vars untouched (the common case), omit env var flags entirely — Cloud Run carries over the previous revision's config.
- `entrypoint.sh` runs `alembic upgrade head` automatically on container start, so DB migrations ship with the deploy — no separate migration step needed.

## 4. Deploy frontend (Cloud Shell, only when frontend changes)

```
cd ~/S2PNexus/frontend
gcloud builds submit --config=cloudbuild.yaml
```
(Uses `cloudbuild.yaml` rather than a plain `gcloud builds submit --tag=...` because it needs to pass `NEXT_PUBLIC_API_URL` as a build arg at Next.js build time, which the plain command can't do.)

## 5. After deploying

- Check `https://s2pnexus-backend-120737021520.us-central1.run.app/health` — should return `{"status":"healthy", ..., "database":"connected"}`.
- If a code change touched auth/JWT handling, **log out and back in** on the dashboard — old tokens signed under a previous `SECRET_KEY` (or before a fix) won't decode against the new deploy.
- If something still errors, pull backend logs before guessing:
  ```
  gcloud run services logs read s2pnexus-backend --region=us-central1 --project=s2pnexus --limit=100
  ```
  The global exception handler in `app/main.py` prints a full traceback on any unhandled exception, so the real error is almost always in there.

## Service URLs

- Backend: `https://s2pnexus-backend-120737021520.us-central1.run.app`
- Frontend: `https://s2pnexus-frontend-120737021520.us-central1.run.app`
- Region: `us-central1`, Project: `s2pnexus`

## Known incidents (for context, not action items)

- **2026-07-26 — CORS errors on every authenticated endpoint.** Looked like a CORS misconfig; was actually `get_current_user` throwing an unhandled `jwt.InvalidTokenError` on stale/mis-signed tokens. FastAPI/Starlette route handlers registered for the bare `Exception` class through `ServerErrorMiddleware`, which sits *outside* `CORSMiddleware` — so any unhandled exception (not just this one) comes back with no CORS header and browsers report it as "blocked by CORS policy" instead of showing the real error. Fixed at the source in `app/core/dependencies.py` (catch `InvalidTokenError`, raise a proper 401). Worth remembering generally: an unexplained CORS error on a previously-working endpoint is worth checking backend logs for a real exception before assuming it's a CORS config problem.
- **2026-07-25 — Cloud Run deploy lagged commits.** Backend commits sat on `main` for hours before being deployed, including a real CORS fix. If something's broken in prod, check `git log` vs. what's actually deployed before deep-diving — it might just need a redeploy.
