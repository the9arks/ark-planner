# VPS deploy runbook (Timeweb Cloud, Ubuntu 22.04)

One domain serves everything: `/` is the Mini App static build, and
`/webhook`, `/api`, `/shortcut`, `/payments`, `/cron` proxy to the Python
backend on `127.0.0.1:8080`. Same origin for the Mini App and its API, so
no CORS juggling.

## 0. Prerequisites
- A fresh Ubuntu 22.04 VPS, IP address known.
- A domain pointed at that IP (A record), already propagated.
- SSH access (key-based preferred).

## 1. System packages
```bash
apt update && apt upgrade -y
apt install -y python3 python3-venv python3-pip nginx certbot rsync
```

## 2. App user + directory
```bash
useradd -r -s /bin/false -d /opt/ark-planner arkplanner || true
mkdir -p /opt/ark-planner
```

## 3. Ship the code
Run from the local machine (not the server) — rsyncs everything except
venv/node_modules/.git, including the already-built `miniapp/dist`:
```bash
rsync -avz --exclude venv --exclude node_modules --exclude .git --exclude .env.local \
  /Users/germangrisin/life-tracker-bot/ root@<VPS_IP>:/opt/ark-planner/
```

## 4. Python env (on the server)
```bash
cd /opt/ark-planner
python3 -m venv venv
venv/bin/pip install -r requirements.txt
chown -R arkplanner:arkplanner /opt/ark-planner
```

## 5. `.env` (on the server, /opt/ark-planner/.env)
Same secrets as Render, plus:
```
EXTERNAL_URL=https://<DOMAIN>
PORT=8080
```
(Drop `ALLOW_DEV_AUTH` or keep it `false`.)

## 6. systemd service
```bash
cp deploy/ark-planner.service /etc/systemd/system/ark-planner.service
systemctl daemon-reload
systemctl enable --now ark-planner
systemctl status ark-planner   # should be "active (running)"
```

## 7. nginx + TLS — two-phase bring-up (cert doesn't exist yet on first boot)

**Phase A — HTTP only, to pass the ACME challenge:**
```bash
mkdir -p /var/www/certbot
cat > /etc/nginx/sites-available/ark-planner <<'EOF'
server {
    listen 80;
    server_name <DOMAIN>;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 200 'ok'; }
}
EOF
ln -sf /etc/nginx/sites-available/ark-planner /etc/nginx/sites-enabled/ark-planner
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

certbot certonly --webroot -w /var/www/certbot -d <DOMAIN>
```

**Phase B — full config with TLS:**
```bash
sed 's/__DOMAIN__/<DOMAIN>/g' deploy/nginx.conf > /etc/nginx/sites-available/ark-planner
nginx -t && systemctl reload nginx
```

Certbot installs its own renewal timer (`systemctl list-timers | grep certbot`) —
no cron needed for renewal.

## 8. Point Telegram + the free-tier keep-alive pinger at the new domain
- The bot sets its own webhook to `EXTERNAL_URL` on startup — nothing manual
  needed there, just confirm via `getWebhookInfo`.
- Update the cron-job.org ping target from
  `https://ark-planner-backend.onrender.com/cron/<secret>` to
  `https://<DOMAIN>/cron/<secret>` (still doubles as the reminder scheduler;
  a VPS doesn't spin down, but the reminder tick still needs a periodic hit).
- Update `miniapp/.env`'s `VITE_API_URL` to `https://<DOMAIN>` and rebuild
  before the next `rsync` if the domain ever changes.

## 9. Verify, then retire Render
Test `/api/digest` (401 expected unauthenticated), the bot's `/start`, a
real message, and the Mini App loading at the domain — all before pausing
or deleting the Render services.
