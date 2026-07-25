# secrets/

Put the downloaded GCP service account JSON key here as:

    gcp-service-account.json

docker-compose mounts this whole folder read-only into the backend container at
`/app/secrets`, and `GOOGLE_APPLICATION_CREDENTIALS` is already set to
`/app/secrets/gcp-service-account.json` in docker-compose.yml.

This folder is gitignored — never commit key files.
