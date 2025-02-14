#!/usr/bin/env python3
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
import os
from typing import Optional

from dotenv import load_dotenv
from crontab import CronTab

from scrapers import (
    ScraperManager,
    TwitterMentionsScraper,
    TwitterFeedScraper,
    CoinMarketCapScraper,
    CoinGeckoScraper,
    RedditScraper
)
from notification_database_manager import NotificationDatabaseManager

# Configure logging
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / f"cron_worker_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class CronManager:
    def __init__(self, notification_dir: str):
        self.notification_dir = notification_dir
        self.cron = CronTab(user=True)
        self.venv_python = str(Path(notification_dir) / "venv" / "bin" / "python")
        
    def _create_job(self, name: str, interval: int, scraper: str) -> None:
        """Create a cron job for a specific scraper."""
        # Remove existing job if it exists
        self.cron.remove_all(comment=f"notification_{name}")
        
        # Create new job
        job = self.cron.new(
            command=f"cd {self.notification_dir} && SCRAPER={scraper} {self.venv_python} ./cron_worker.py",
            comment=f"notification_{name}"
        )
        
        # Handle hourly intervals
        if interval >= 60:
            hours = interval // 60
            job.hour.every(hours)
            job.minute.on(0)  # Run at minute 0 of the hour
        else:
            job.minute.every(interval)
        
    def setup_jobs(self, intervals: dict) -> None:
        """Setup all cron jobs with specified intervals."""
        # Verify virtual environment exists
        if not os.path.isfile(self.venv_python):
            raise FileNotFoundError(
                f"Virtual environment Python not found at {self.venv_python}. "
                "Please create and activate the virtual environment first."
            )
        
        # Setup scraper jobs
        self._create_job("twitter", intervals["twitter"], "twitter")
        self._create_job("coingecko", intervals["coingecko"], "coingecko")
        self._create_job("coinmarketcap", intervals["cmc"], "coinmarketcap")
        self._create_job("reddit", intervals["reddit"], "reddit")
        
        # Setup log rotation job
        self.cron.remove_all(comment="notification_log_rotation")
        log_job = self.cron.new(
            command=f'find {self.notification_dir}/logs -name "cron_worker_*.log" -mtime +7 -delete',
            comment="notification_log_rotation"
        )
        log_job.every().day()
        
        # Write to crontab
        self.cron.write()
        
    def remove_all_jobs(self) -> None:
        """Remove all notification-related cron jobs."""
        self.cron.remove_all(comment=lambda c: c and c.startswith("notification_"))
        self.cron.write()
        
    def list_jobs(self) -> None:
        """List all notification-related cron jobs."""
        for job in self.cron:
            if job.comment and job.comment.startswith("notification_"):
                print(f"{job.comment}:")
                print(f"  Schedule: {job.slices}")
                print(f"  Command: {job.command}")
                print()

class CronNotificationWorker:
    def __init__(self, env_path: str = ".env"):
        # Initialize components
        load_dotenv(dotenv_path=env_path)
        self.notification_manager = NotificationDatabaseManager()
        self.scraper_manager = ScraperManager(self.notification_manager)
        
    @staticmethod
    def setup_cron_jobs(notification_dir: str) -> None:
        """Setup cron jobs for all scrapers."""
        try:
            # Load environment variables
            env_path = os.path.join(notification_dir, ".env")
            load_dotenv(env_path)
            
            # Get intervals from environment
            intervals = {
                "twitter": int(os.getenv("TWITTER_SCRAPING_INTERVAL", "60")),
                "coingecko": int(os.getenv("COINGECKO_SCRAPING_INTERVAL", "60")),
                "cmc": int(os.getenv("CMC_SCRAPING_INTERVAL", "60")),
                "reddit": int(os.getenv("REDDIT_SCRAPING_INTERVAL", "60"))
            }
            
            # Setup cron jobs
            cron_manager = CronManager(notification_dir)
            cron_manager.setup_jobs(intervals)
            
            logger.info("Cron jobs setup successfully")
            logger.info("Current cron jobs:")
            cron_manager.list_jobs()
            
        except Exception as e:
            logger.error(f"Error setting up cron jobs: {str(e)}")
            raise
            
    async def initialize_scrapers(self):
        """Initialize all scrapers with appropriate credentials."""
        try:
            # Get the specific scraper to run from environment variable
            target_scraper = os.getenv("SCRAPER", "all").lower()
            logger.info(f"Initializing scraper(s): {target_scraper}")
            
            # Initialize Twitter scrapers if requested
            if target_scraper in ["all", "twitter"]:
                twitter_creds = {
                    "api_key": os.getenv("TWITTER_API_KEY"),
                    "api_secret": os.getenv("TWITTER_API_SECRET"),
                    "access_token": os.getenv("TWITTER_ACCESS_TOKEN"),
                    "access_token_secret": os.getenv("TWITTER_ACCESS_TOKEN_SECRET"),
                    "bot_username": "Superior_Agents" # os.getenv("TWITTER_BOT_USERNAME", "hyperstitia")
                }

                if all(twitter_creds.values()):
                    mentions_scraper = TwitterMentionsScraper(bot_username=twitter_creds["bot_username"])
                    feed_scraper = TwitterFeedScraper(bot_username=twitter_creds["bot_username"])
                    self.scraper_manager.add_scraper(mentions_scraper)
                    self.scraper_manager.add_scraper(feed_scraper)
                    logger.info("Twitter scrapers initialized")
                else:
                    logger.warning("Twitter credentials not complete, skipping Twitter scrapers")
            
            # Initialize CoinGecko scraper if requested
            if target_scraper in ["all", "coingecko"]:
                tracked_currencies = [
                    "bitcoin",
                    "ethereum",
                    "binancecoin",
                    "ripple",
                    "cardano",
                    "solana",
                    "polkadot",
                    "dogecoin"
                ]
                coingecko_scraper = CoinGeckoScraper(
                    tracked_currencies=tracked_currencies,
                    price_change_threshold=float(os.getenv("PRICE_CHANGE_THRESHOLD", "5.0"))
                )
                self.scraper_manager.add_scraper(coingecko_scraper)
                logger.info("CoinGecko scraper initialized")
            
            # Initialize CoinMarketCap scraper if requested
            if target_scraper in ["all", "coinmarketcap"]:
                cmc_scraper = CoinMarketCapScraper()
                self.scraper_manager.add_scraper(cmc_scraper)
                logger.info("CoinMarketCap scraper initialized")
            
            # Initialize Reddit scraper if requested
            if target_scraper in ["all", "reddit"]:
                reddit_creds = {
                    "client_id": os.getenv("REDDIT_CLIENT_ID"),
                    "client_secret": os.getenv("REDDIT_CLIENT_SECRET")
                }
                
                if all(reddit_creds.values()):
                    reddit_scraper = RedditScraper(
                        client_id=reddit_creds["client_id"],
                        client_secret=reddit_creds["client_secret"],
                        user_agent="SuperiorAgentsBot/1.0",
                        subreddits=[
                            "cryptocurrency",
                            "bitcoin",
                            "ethereum",
                            "CryptoMarkets"
                        ]
                    )
                    self.scraper_manager.add_scraper(reddit_scraper)
                    logger.info("Reddit scraper initialized")
                else:
                    logger.warning("Reddit credentials not complete, skipping Reddit scraper")
                    
        except Exception as e:
            logger.error(f"Error initializing scrapers: {str(e)}")
            raise
            
    async def run_single_cycle(self):
        """Run a single scraping cycle."""
        try:
            logger.info("Initializing scrapers...")
            await self.initialize_scrapers()
            
            logger.info("Starting scraping cycle...")
            await self.scraper_manager.run_scraping_cycle()
            logger.info("Scraping cycle completed successfully")
            
        except Exception as e:
            logger.error(f"Error in scraping cycle: {str(e)}")
            raise
        finally:
            # Cleanup any remaining tasks
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            
            # Close notification manager
            try:
                await self.notification_manager.close()
            except Exception as e:
                logger.error(f"Error closing notification manager: {str(e)}")
            
            # Close scraper clients
            for scraper in self.scraper_manager.scrapers:
                if hasattr(scraper, 'client') and hasattr(scraper.client, 'aclose'):
                    try:
                        await scraper.client.aclose()
                    except Exception as e:
                        logger.error(f"Error closing client for {scraper.__class__.__name__}: {str(e)}")
                        
                if hasattr(scraper, 'close'):
                    try:
                        await scraper.close()
                    except Exception as e:
                        logger.error(f"Error closing {scraper.__class__.__name__}: {str(e)}")

async def run_forever():
    """Run the scraping cycle continuously."""
    while True:
        start_time = datetime.now()
        logger.info(f"Starting scraping cycle at {start_time}")
        
        worker = CronNotificationWorker()
        try:
            await worker.run_single_cycle()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
            break
        except Exception as e:
            logger.error(f"Error in scraping cycle: {str(e)}")
            # Don't break on non-fatal errors, continue to next cycle
        finally:
            end_time = datetime.now()
            duration = end_time - start_time
            logger.info(f"Scraping cycle completed at {end_time} (Duration: {duration})")
            
            # Get the scraper type and its interval
            scraper_type = os.getenv("SCRAPER", "all").lower()
            interval = {
                "twitter": int(os.getenv("TWITTER_SCRAPING_INTERVAL", "60")),
                "coingecko": int(os.getenv("COINGECKO_SCRAPING_INTERVAL", "60")),
                "coinmarketcap": int(os.getenv("CMC_SCRAPING_INTERVAL", "60")),
                "reddit": int(os.getenv("REDDIT_SCRAPING_INTERVAL", "60")),
                "all": 60  # Default interval if not specified
            }.get(scraper_type, 60)
            
            # Sleep until next cycle
            logger.info(f"Waiting {interval} minutes until next cycle...")
            await asyncio.sleep(interval * 60)  # Convert minutes to seconds

def main():
    """Main entry point for the cron worker."""
    try:
        asyncio.run(run_forever())
    except KeyboardInterrupt:
        logger.info("Shutting down notification worker...")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    # If INSTALL_CRON environment variable is set, setup cron jobs
    if os.getenv("INSTALL_CRON"):
        notification_dir = str(Path(__file__).parent)
        CronNotificationWorker.setup_cron_jobs(notification_dir)
    else:
        main()  # Run the continuous scraping process
