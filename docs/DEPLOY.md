# Deploying Rivon (EU)

Three pieces, all in the EU:

| Piece | Where | Who sets it up |
|---|---|---|
| Database | Neon project `rivon-eu`, Frankfurt | Done |
| API, worker, relay, Redis | One EC2 server, `eu-central-1` (Frankfurt) | You, in the AWS console |
| Dashboard | Vercel, `fra1` (Frankfurt) | CLI, after the API is up |

Everything below assumes the domain you own. Replace `example.com` with it.
`api.example.com` is the backend; `app.example.com` is the dashboard.

---

## 1. Launch the server (AWS console)

**Region: Europe (Frankfurt) `eu-central-1`.** Check the region menu, top right.

### 1.1 Key pair
EC2 → Network & Security → **Key Pairs** → *Create key pair*
- Name `rivon-eu`, type **RSA**, format **.pem**
- It downloads once. Keep it safe; it's the only way to log in.

### 1.2 Security group
EC2 → Network & Security → **Security Groups** → *Create security group*
- Name `rivon-eu`, description "Rivon API server", default VPC
- **Inbound rules:**

| Type | Port | Source | Why |
|---|---|---|---|
| HTTP | 80 | Anywhere `0.0.0.0/0` | Certificate checks, redirect to HTTPS |
| HTTPS | 443 | Anywhere `0.0.0.0/0` | The API itself |
| SSH | 22 | **My IP** | Administration. Not open to the world. |

- Outbound: leave the default (all traffic).

### 1.3 Instance
EC2 → Instances → **Launch instances**
- Name: `rivon-eu`
- AMI: **Amazon Linux 2023**, 64-bit (x86)
- Instance type: **t3.small** (2 GB RAM; t3.micro is too small to build images)
- Key pair: `rivon-eu`
- Network: default VPC, **existing security group** `rivon-eu`
- Storage: **20 GiB gp3**, and tick **Encrypted**
- Advanced details → **User data**: paste this, which installs Docker and fetches the code:

```bash
#!/bin/bash
set -eux
dnf update -y
dnf install -y docker git
systemctl enable --now docker
usermod -aG docker ec2-user
mkdir -p /usr/local/lib/docker/cli-plugins
curl -sSL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
# 2 GB swap so image builds don't run out of memory
if [ ! -f /swapfile ]; then
  dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
install -d -o ec2-user -g ec2-user /opt/rivon
sudo -u ec2-user git clone --depth 20 https://github.com/Tehman700/rivon.git /opt/rivon
touch /opt/rivon/.bootstrap-complete
```

- Launch. Cost is roughly **$18/month** (instance ≈ $16, 20 GB disk ≈ $2).

### 1.4 Fixed IP
EC2 → Network & Security → **Elastic IPs** → *Allocate* → then *Actions → Associate*
with the `rivon-eu` instance. Without this the address changes on every stop/start.

**Send me the Elastic IP.**

---

## 2. DNS (at your domain registrar)

| Record | Type | Value |
|---|---|---|
| `api` | A | the Elastic IP |
| `app` | CNAME | `cname.vercel-dns.com` (added in step 4) |

Certificates are issued automatically once `api.example.com` resolves to the server.

---

## 3. Start the stack (over SSH)

```sh
ssh -i rivon-eu.pem ec2-user@<ELASTIC-IP>
cloud-init status --wait          # setup finished when this says "done"
cd /opt/rivon
```

Create `/opt/rivon/.env.production` from `.env.production.example`. I'll give you
the exact contents: the three Neon URLs, the JWT secret, your domain. It is never
committed, and only this server has it.

```sh
chmod 600 .env.production
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml ps        # all services up, migrate exited 0
curl -s https://api.example.com/health               # {"status":"ok",...}
```

Migrations run automatically on every start, before the API accepts traffic.

### Create the first business

```sh
docker compose -f docker-compose.prod.yml --env-file .env.production \
  exec api python -m rivon.platform.cli provision-tenant \
  --name "Their Business" --slug their-business --owner-email owner@example.com
```

Until an email provider is chosen, the "set your password" link is printed in the
logs: `docker compose -f docker-compose.prod.yml logs api | tail -20`.

### Updating later

```sh
cd /opt/rivon && git pull
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

---

## 4. Dashboard on Vercel

From `web/` on a machine with the Vercel CLI signed in to the Rivon account:

```sh
vercel link            # project: rivon
vercel env add RIVON_API_URL production     # https://api.example.com
vercel --prod
vercel domains add app.example.com          # then add the CNAME above
```

`vercel.json` already pins functions to Frankfurt. After the domain is live, set
`RIVON_PUBLIC_APP_URL=https://app.example.com` in `.env.production` on the server
and restart, so password-reset emails link to the right place.

---

## Notes

- **Where data sits:** Neon (Frankfurt), EC2 (Frankfurt), Vercel functions
  (Frankfurt). Nothing is processed outside the EU.
- **Database roles:** `rivon_app` and `rivon_relay` cannot bypass row-level
  security. On Neon the migration role does have that power, which is why it is
  used only by Alembic, never by the app.
- **Backups:** Neon keeps point-in-time history (6 hours on the free plan).
  Before real customer data, raise that and test a restore (OPS-07).
- **Redis** runs on the server with persistence off: it is a queue and cache
  only. If it restarts, pending work is re-dispatched from the database outbox.
- **Not yet done:** rate limiting on login (OPS-06), an email provider, and
  Sentry (OPS-05).
