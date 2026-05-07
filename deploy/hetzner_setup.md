# Hetzner Cloud Setup Runbook

How to provision the production server for the Instagram Audit Skill.

**Recommended Hetzner spec for Phase 1–4:** CX22 or CPX21 (2 vCPU, 4 GB RAM, 40 GB SSD) in Falkenstein or Helsinki. Ubuntu 24.04 LTS. Cost ~€5–7/month.

The audit batch is monthly and runs in minutes — CPU/RAM aren't the bottleneck. Disk for the report archive grows ~50 MB/month.

---

## 1. Create the Hetzner Cloud server

1. Log in to https://console.hetzner.com/projects → Add Server.
2. **Location:** Falkenstein (DE) or Helsinki (FI) — closest to twistnturns.in's DigitalOcean droplet for low cross-traffic latency if you ever want to consolidate.
3. **Image:** Ubuntu 24.04 LTS.
4. **Type:** CX22 (Intel) or CPX21 (AMD). CX22 is cheaper, CPX21 is faster. Either is fine.
5. **SSH key:** add your local public key (`~/.ssh/id_ed25519.pub`). Don't use password auth.
6. **Name:** `ig-audit-prod`.
7. Create. Note the IPv4 address — call it `$IG_HOST`.

```bash
ssh root@$IG_HOST
```

## 2. Initial hardening

```bash
# Update OS
apt update && apt upgrade -y

# Create the deploy user
adduser --disabled-password --gecos "" tapash
usermod -aG sudo tapash
mkdir -p /home/tapash/.ssh
cp ~/.ssh/authorized_keys /home/tapash/.ssh/
chown -R tapash:tapash /home/tapash/.ssh
chmod 700 /home/tapash/.ssh
chmod 600 /home/tapash/.ssh/authorized_keys

# Lock down SSH — disable root login + password auth
sed -i 's/^#*PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#*PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh

# Firewall — allow SSH and the studio admin reverse proxy if needed
ufw allow OpenSSH
ufw --force enable

# Fail2ban (optional but cheap)
apt install -y fail2ban
```

Reconnect as the new user from now on:

```bash
ssh tapash@$IG_HOST
```

## 3. Install dependencies

```bash
sudo apt install -y \
    python3.11 python3.11-venv python3.11-dev \
    mysql-server \
    git build-essential \
    logrotate cron

# Headless matplotlib + python-docx need these
sudo apt install -y \
    libfreetype6-dev libpng-dev pkg-config \
    libxml2-dev libxslt1-dev
```

If `python3.11` is not in the default Ubuntu 24.04 repos, use the deadsnakes PPA:

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
```

## 4. Secure MySQL

```bash
sudo mysql_secure_installation
# Set a strong root password, remove anonymous users, disallow remote root, remove test DB.
```

Apply the schema:

```bash
git clone https://github.com/TapasDas1982/Instagram_Audit_Skill.git ~/projects/instagram-audit-skill
cd ~/projects/instagram-audit-skill
sudo mysql -u root -p < db/schema.sql
```

Create the application user:

```sql
sudo mysql -u root -p
```
```sql
CREATE USER 'ig_audit_user'@'localhost' IDENTIFIED BY 'STRONG_PASSWORD_HERE';
GRANT ALL PRIVILEGES ON ig_audit.* TO 'ig_audit_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

Verify:

```bash
mysql -u ig_audit_user -p ig_audit -e "SHOW TABLES;"
# Expected: accounts, audit_history, audits
```

## 5. Set up the Python venv

```bash
cd ~/projects/instagram-audit-skill
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

python -c "import pandas, docx, matplotlib, requests, mysql.connector; print('ok')"
# Expected: ok
```

## 6. Configure the app

```bash
cp config/config.example.py config/config.py
chmod 600 config/config.py
nano config/config.py
# Fill in MYSQL credentials. Leave META, BREVO as None until Phase 2/4.

# Verify config.py is gitignored — must return the path
git check-ignore config/config.py
```

## 7. Phase 2 — Get the long-lived Meta access token (manual one-time flow)

Run this once Meta App Review approves (or while in Development Mode with Tapash added as Tester):

1. Go to https://developers.facebook.com/tools/explorer/
2. Select your app, request scopes: `pages_show_list`, `instagram_basic`, `instagram_manage_insights`, `pages_read_engagement`
3. Generate a short-lived user token. Copy it.
4. Exchange for a long-lived user token:
   ```
   curl -G "https://graph.facebook.com/v21.0/oauth/access_token" \
     --data-urlencode "grant_type=fb_exchange_token" \
     --data-urlencode "client_id=YOUR_APP_ID" \
     --data-urlencode "client_secret=YOUR_APP_SECRET" \
     --data-urlencode "fb_exchange_token=SHORT_LIVED_TOKEN"
   ```
5. Use the long-lived user token to list Pages (each Page returns its own non-expiring access_token):
   ```
   curl "https://graph.facebook.com/v21.0/me/accounts?access_token=LONG_LIVED_USER_TOKEN"
   ```
6. Find the Page linked to the IG Business account, then get the IG Business account ID:
   ```
   curl "https://graph.facebook.com/v21.0/PAGE_ID?fields=instagram_business_account&access_token=PAGE_TOKEN"
   ```
7. Save `app_id`, `app_secret`, `long_lived_token`, `ig_user_id`, `page_id` into `config/config.py`. Set `token_expires_at` to today + 60 days as ISO string.

## 8. Phase 2 — Schedule the token refresh cron

```bash
crontab -e
```

Add (runs 3 AM on the 1st of every month — well before the 60-day expiry):

```
0 3 1 * * cd /home/tapash/projects/instagram-audit-skill && ./venv/bin/python scripts/refresh_token.py >> /var/log/ig_audit_refresh.log 2>&1
```

## 9. Phase 4 — Schedule the monthly batch

```bash
crontab -e
```

Add (1st of every month, 4 AM — after the token refresh):

```
0 4 1 * * cd /home/tapash/projects/instagram-audit-skill && ./venv/bin/python scripts/batch_run.py >> /var/log/ig_audit_batch.log 2>&1
```

## 10. Log rotation

Create `/etc/logrotate.d/ig_audit`:

```
/var/log/ig_audit_*.log {
    monthly
    rotate 12
    compress
    delaycompress
    missingok
    notifempty
    create 0640 tapash tapash
}
```

Test:

```bash
sudo logrotate -d /etc/logrotate.d/ig_audit
```

## 11. PHP admin panel integration (Phase 4)

The PHP admin panel that already runs on the studio host will grow a new page (`admin/ig-audits.php`) that reads from the `ig_audit` MySQL database on this Hetzner box.

Two options for cross-host access:

1. **MySQL replication or remote read user** — open MySQL on the Hetzner side to the studio host's IP only:
   ```
   CREATE USER 'ig_audit_reader'@'STUDIO_HOST_IP' IDENTIFIED BY 'STRONG_PASSWORD';
   GRANT SELECT ON ig_audit.* TO 'ig_audit_reader'@'STUDIO_HOST_IP';
   FLUSH PRIVILEGES;
   ```
   Plus a UFW rule:
   ```
   sudo ufw allow from STUDIO_HOST_IP to any port 3306
   ```
2. **REST API** — small read-only Python/Flask service on the Hetzner box that exposes audit data over HTTPS. Slightly more work, no MySQL exposure.

Start with option 1 if both hosts are on Hetzner / under one Cloud Network; switch to option 2 if security review pushes back.

## 12. Backups

Hetzner Cloud snapshots are the cheapest backup. Enable automatic snapshots on the server (Hetzner console → Backups → Enable, ~20% server cost).

For finer-grained DB backups, add a daily mysqldump cron:

```bash
crontab -e
```
```
30 2 * * * /usr/bin/mysqldump -u ig_audit_user -pPASSWORD ig_audit | gzip > /home/tapash/backups/ig_audit_$(date +\%Y\%m\%d).sql.gz
```

Rotate daily backups manually or via logrotate-style script (out of scope for Phase 0).

---

## Verification checklist

After completing this runbook:

- [ ] `ssh tapash@$IG_HOST` works; root login disabled
- [ ] `mysql -u ig_audit_user -p ig_audit -e "SHOW TABLES;"` shows three tables
- [ ] `cd ~/projects/instagram-audit-skill && source venv/bin/activate && python -c "import pandas, docx, matplotlib, requests, mysql.connector; print('ok')"` prints `ok`
- [ ] `git check-ignore config/config.py` returns the path
- [ ] `stat -c '%a %n' config/config.py` returns `600 config/config.py`
- [ ] `ufw status` shows OpenSSH allowed, default deny incoming
- [ ] `crontab -l` (Phase 2+) lists the token-refresh and monthly-batch jobs
