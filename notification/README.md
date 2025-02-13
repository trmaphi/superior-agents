# Notification Service

A comprehensive notification service that aggregates data from multiple sources including Twitter, Reddit, CoinGecko, and CoinMarketCap. The service runs as scheduled cron jobs to collect and process information at configurable intervals.

## Requirements

- Python 3.12 or higher
- pip (Python package installer)
- cron (for scheduling)
- virtualenv or venv (for virtual environment)

## Features

- **Multi-source Data Collection**:
  - Twitter mentions and timeline monitoring
  - Reddit cryptocurrency subreddit monitoring
  - CoinGecko price alerts
  - CoinMarketCap news updates

- **Configurable Intervals**: Each data source can be configured with its own scraping interval
- **Robust Error Handling**: Comprehensive error handling and logging
- **Resource Cleanup**: Proper cleanup of connections and resources
- **Modular Design**: Easy to add new data sources

## Installation

1. Ensure you have Python >= 3.10  installed:
```bash
python3 --version  # Should show 3.10.x or higher
```

2. Create and activate a virtual environment:
```bash
# Create virtual environment
python3.12 -m venv venv

# Activate virtual environment
# On Unix or MacOS:
source venv/bin/activate
# On Windows:
.\venv\Scripts\activate
```

3. Navigate to the notification directory:
```bash
cd notification
```

4. Install required dependencies:
```bash
pip install -r requirements.txt
```

5. Copy the example environment file and configure your settings:
```bash
cp .env.example .env
```

6. Edit `.env` with your credentials and settings:
   - API keys for Twitter, Reddit, CoinGecko
   - Scraping intervals for each service
   - Logging configuration
   - Other service-specific settings

7. Install the cron jobs:
```bash
./install_cron.sh
```

8. Verify the installation:
```bash
# Check if dependencies are installed correctly
pip list

# Check if cron jobs are installed
crontab -l
```

### Important Notes

- Always use the virtual environment when running the scrapers manually
- Make sure the cron jobs are configured to use the correct Python interpreter from the virtual environment
- The virtual environment must be recreated if you move the project to a different location

## Configuration

### Environment Variables

Key environment variables in `.env`:

```ini
# API Authentication
API_KEY=your_api_key

# Scraping Intervals (in minutes)
TWITTER_SCRAPING_INTERVAL=15
COINGECKO_SCRAPING_INTERVAL=5
CMC_SCRAPING_INTERVAL=60
REDDIT_SCRAPING_INTERVAL=30

# Price change threshold for crypto alerts
PRICE_CHANGE_THRESHOLD=5.0

# Logging
LOG_LEVEL=INFO
```

## File Structure

- `cron_worker.py`: Main worker script that runs the scraping jobs
- `client.py`: HTTP client for sending notifications to the API
- `models.py`: Data models for notifications and responses
- `scrapers.py`: Implementation of different scrapers
- `twitter_service.py`: Twitter API integration
- `vault_service.py`: Secure credential management
- `install_cron.sh`: Script to install cron jobs
- `requirements.txt`: Python package dependencies

## Usage

### Running Individual Scrapers

You can run specific scrapers manually:

```bash
# Run all scrapers
./cron_worker.py

# Run specific scrapers
SCRAPER=twitter ./cron_worker.py
SCRAPER=coingecko ./cron_worker.py
SCRAPER=reddit ./cron_worker.py
SCRAPER=coinmarketcap ./cron_worker.py
```

### Monitoring Logs

Logs are stored in the `logs` directory with daily rotation:

```bash
# View today's logs
tail -f logs/cron_worker_YYYYMMDD.log
```

### Managing Cron Jobs

```bash
# View current cron jobs
crontab -l

# Reinstall cron jobs (e.g., after changing intervals)
./install_cron.sh
```

## Components

### Scrapers

- **TwitterScraper**: Monitors mentions and timeline of a specified bot account
  - Rate limits: 180 requests/15min for mentions, 5 requests/15min for timeline
  - Configurable via `TWITTER_SCRAPING_INTERVAL`

- **CoinGeckoScraper**: Monitors cryptocurrency price changes
  - Supports multiple currencies
  - Configurable price change threshold
  - Configurable via `COINGECKO_SCRAPING_INTERVAL`

- **CoinMarketCapScraper**: Fetches latest crypto news
  - RSS feed monitoring
  - Configurable via `CMC_SCRAPING_INTERVAL`

- **RedditScraper**: Monitors cryptocurrency subreddits
  - Configurable subreddit list
  - Configurable via `REDDIT_SCRAPING_INTERVAL`

### Services

- **NotificationClient**: Handles sending notifications to the API
  - Async HTTP client
  - Automatic retries
  - Error handling

- **VaultService**: Manages secure access to credentials
  - Environment variable management
  - Secure secret storage

## Maintenance

### Log Rotation

Logs are automatically rotated and cleaned up:
- Daily log files: `logs/cron_worker_YYYYMMDD.log`
- Auto-deletion after 7 days

### Updating

1. Pull latest changes
2. Update dependencies: `pip install -r requirements.txt`
3. Update environment variables if needed
4. Reinstall cron jobs: `./install_cron.sh`

## Troubleshooting

Common issues and solutions:

1. **Cron jobs not running**:
   - Check crontab: `crontab -l`
   - Check logs for errors
   - Verify file permissions

2. **API Authentication Errors**:
   - Verify API keys in `.env`
   - Check vault service configuration

3. **Rate Limiting**:
   - Adjust scraping intervals in `.env`
   - Check service-specific rate limits

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

[Your License Here] 