#!/bin/bash

# Get the absolute path of the notification directory
NOTIFICATION_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$NOTIFICATION_DIR/notification-venv/bin/python"

# Check if virtual environment exists
if [ ! -f "$VENV_PYTHON" ]; then
    echo "Error: Virtual environment not found at $VENV_PYTHON"
    echo "Please create and activate the virtual environment first:"
    echo "python3 -m venv venv"
    echo "source venv/bin/activate"
    exit 1
fi

# Load environment variables from .env
if [ -f "$NOTIFICATION_DIR/.env" ]; then
    source "$NOTIFICATION_DIR/.env"
else
    echo "Error: .env file not found inside the notification directory"
    exit 1
fi

# Set default intervals if not defined in .env
TWITTER_INTERVAL=${TWITTER_SCRAPING_INTERVAL:-60}
COINGECKO_INTERVAL=${COINGECKO_SCRAPING_INTERVAL:-60}
CMC_INTERVAL=${CMC_SCRAPING_INTERVAL:-60}
REDDIT_INTERVAL=${REDDIT_SCRAPING_INTERVAL:-60}

# Create logs directory if it doesn't exist
mkdir -p "$NOTIFICATION_DIR/logs"

# Create a temporary crontab file
TEMP_CRONTAB="/tmp/notification_crontab.txt"

# Start with a clean file
cat > "$TEMP_CRONTAB" << EOL
# Notification Service Cron Jobs
# m h dom mon dow command

# Run Twitter scraper every hour
0 * * * * cd ${NOTIFICATION_DIR} && SCRAPER=twitter ${VENV_PYTHON} ./cron_worker.py

# Run CoinGecko price checks every hour
0 * * * * cd ${NOTIFICATION_DIR} && SCRAPER=coingecko ${VENV_PYTHON} ./cron_worker.py

# Run CoinMarketCap news scraper every hour
0 * * * * cd ${NOTIFICATION_DIR} && SCRAPER=coinmarketcap ${VENV_PYTHON} ./cron_worker.py

# Run Reddit scraper every hour
0 * * * * cd ${NOTIFICATION_DIR} && SCRAPER=reddit ${VENV_PYTHON} ./cron_worker.py

# Log rotation: Delete logs older than 7 days at midnight
0 0 * * * find ${NOTIFICATION_DIR}/logs -name "*.log" -mtime +7 -delete
EOL

# Create a temporary file with the current crontab
crontab -l > /tmp/current_crontab 2>/dev/null || true

# Remove any existing notification service entries
sed -i.bak '/superior-agents\/notification/d' /tmp/current_crontab

# Add new cron jobs
cat "$TEMP_CRONTAB" >> /tmp/current_crontab

# Install the new crontab
crontab /tmp/current_crontab

# Clean up
rm /tmp/current_crontab /tmp/current_crontab.bak "$TEMP_CRONTAB"

echo "Cron jobs installed successfully with intervals:"
echo "- Twitter: every hour"
echo "- CoinGecko: every hour"
echo "- CoinMarketCap: every hour"
echo "- Reddit: every hour"
echo ""
echo "Using Python interpreter: ${VENV_PYTHON}"
echo "You can verify the installation with: crontab -l" 