#!/bin/sh
set -eu
# Railway mounts empty volumes as root. Only this bounded initialization runs
# as root; the API process and created project files run as uid 10001.
mkdir -p /data
chown 10001:10001 /data
chmod 0700 /data
exec gosu 10001:10001 uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
