#!/bin/bash
# Run this on your EC2 (Ubuntu) as root or with sudo
# Usage: ssh into EC2, then: sudo bash setup-ec2.sh

set -e

echo "=== 1. System updates ==="
apt update && apt upgrade -y

echo "=== 2. Install Nginx, Python, Certbot ==="
apt install -y nginx python3 python3-pip python3-venv certbot python3-certbot-nginx git

echo "=== 3. Clone/setup project ==="
mkdir -p /opt/news-agg
cd /opt/news-agg

# If not already cloned, you'll scp the project here (see instructions below)
# For now, create the output directory
mkdir -p output

echo "=== 4. Python virtual environment ==="
python3 -m venv /opt/news-agg/venv
/opt/news-agg/venv/bin/pip install --upgrade pip
/opt/news-agg/venv/bin/pip install anthropic python-dotenv pymongo dnspython requests feedparser jinja2 beautifulsoup4

echo "=== 5. Nginx config for news.rishotics.com ==="
cat > /etc/nginx/sites-available/news.rishotics.com <<'NGINX'
server {
    listen 80;
    server_name news.rishotics.com;

    root /opt/news-agg/output;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
    }

    # Serve archived editions too
    location ~* \.html$ {
        add_header Cache-Control "public, max-age=86400";
    }
}
NGINX

ln -sf /etc/nginx/sites-available/news.rishotics.com /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo "=== 6. SSL with Let's Encrypt ==="
echo ">> Make sure DNS is pointing to this server first!"
echo ">> Run this AFTER the A record is live:"
echo ">>   sudo certbot --nginx -d news.rishotics.com --non-interactive --agree-tos -m your@email.com"
echo ""

echo "=== 7. Cron job (6 AM IST = 00:30 UTC) ==="
CRON_CMD="30 0 * * * cd /opt/news-agg && /opt/news-agg/venv/bin/python main.py >> /opt/news-agg/cron.log 2>&1"
(crontab -l 2>/dev/null | grep -v "news-agg"; echo "$CRON_CMD") | crontab -
echo "Cron installed: $CRON_CMD"

echo ""
echo "========================================="
echo "  SETUP COMPLETE"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. Add DNS A record in GoDaddy: news -> 54.196.205.112"
echo "  2. SCP your project files to this server:"
echo "     scp -r ./* ec2-user@54.196.205.112:/opt/news-agg/"
echo "     scp .env ec2-user@54.196.205.112:/opt/news-agg/.env"
echo "  3. Once DNS propagates, run:"
echo "     sudo certbot --nginx -d news.rishotics.com --non-interactive --agree-tos -m YOUR_EMAIL"
echo "  4. Test: /opt/news-agg/venv/bin/python /opt/news-agg/main.py"
echo "  5. Visit https://news.rishotics.com"
echo ""
