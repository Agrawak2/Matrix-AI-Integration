# Matrix AI Integration Deployment

This project is currently deployed on the RHEL 9 server `RNOAPPHEN01D`.

## Server Layout

- Application root: `/opt/matrix-ai-integration`
- Active release: `/opt/matrix-ai-integration/current`
- Release history: `/opt/matrix-ai-integration/releases/<timestamp>`
- Shared virtual environment: `/opt/matrix-ai-integration/shared/venv`
- Django environment file: `/opt/matrix-ai-integration/shared/env`
- SQLite data directory: `/var/lib/matrix-ai-integration`
- Application logs: `/var/log/matrix-ai-integration`
- Gunicorn socket: `/run/matrix-ai-integration/gunicorn.sock`
- systemd service: `matrix-ai-integration`
- nginx config: `/etc/nginx/conf.d/matrix-ai-integration.conf`

The public portal is served through nginx:

```text
http://RNOAPPHEN01D/
```

## Runtime

RHEL 9 ships with Python 3.9 by default, but this project uses Django 6, so the server deploy uses Python 3.12 from the RHEL repositories.

Installed server packages include:

```bash
python3.12 python3.12-pip python3.12-devel gcc gcc-c++ make sqlite nginx
```

Python dependencies are installed into the shared virtual environment, not system Python:

```bash
/opt/matrix-ai-integration/shared/venv/bin/python -m pip install -r /opt/matrix-ai-integration/current/requirements.txt gunicorn
```

## Environment

Deployment settings are read from:

```text
/opt/matrix-ai-integration/shared/env
```

Required/expected values:

```bash
DJANGO_SECRET_KEY=...
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=RNOAPPHEN01D,rnoapphen01d,localhost,127.0.0.1
PYTHONUNBUFFERED=1
```

Do not commit secrets or server-local `.local.json` files.

## Service Commands

Check status:

```bash
systemctl status matrix-ai-integration
systemctl status nginx
```

Restart after a deploy or configuration change:

```bash
sudo systemctl restart matrix-ai-integration
sudo systemctl reload nginx
```

View logs:

```bash
sudo journalctl -u matrix-ai-integration -n 100 --no-pager
tail -n 100 /var/log/matrix-ai-integration/error.log
tail -n 100 /var/log/matrix-ai-integration/nginx-error.log
```

## Smoke Tests

From Windows:

```powershell
curl.exe http://RNOAPPHEN01D/
.\scripts\test-django-part-search.ps1 -Url http://RNOAPPHEN01D/api/ PCB
```

The smoke test logs in as the mock `engineer` user and performs a mock part search through the deployed nginx/gunicorn/Django path.

## Release Process

The preferred deploy shape is a timestamped release plus a `current` symlink:

1. Build a clean source bundle from the workspace, excluding `.git`, `.venv`, `.idea`, `tmp`, `data`, `__pycache__`, `.pytest_cache`, and `config/*.local.json`.
2. Upload it to `/home/codex/uploads/`.
3. Extract it into `/opt/matrix-ai-integration/releases/<timestamp>`.
4. Link the shared data directory into the release:

   ```bash
   ln -sfn /var/lib/matrix-ai-integration /opt/matrix-ai-integration/releases/<timestamp>/data
   ```

5. Install/update dependencies in `/opt/matrix-ai-integration/shared/venv`.
6. Run:

   ```bash
   cd /opt/matrix-ai-integration/releases/<timestamp>
   set -a
   . /opt/matrix-ai-integration/shared/env
   set +a
   /opt/matrix-ai-integration/shared/venv/bin/python manage.py check
   /opt/matrix-ai-integration/shared/venv/bin/python manage.py migrate --noinput
   /opt/matrix-ai-integration/shared/venv/bin/python manage.py collectstatic --noinput
   ```

7. Point `current` at the new release and restart the app:

   ```bash
   ln -sfn /opt/matrix-ai-integration/releases/<timestamp> /opt/matrix-ai-integration/current
   sudo systemctl restart matrix-ai-integration
   ```

When creating bundles from Windows/OneDrive, prefer a zip bundle over tar. The first tar attempt preserved Windows/OneDrive permission metadata that caused `Permission denied` errors during Linux extraction.
