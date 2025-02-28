#!/usr/bin/env python3
import asyncio
import logging
import sys
from datetime import datetime

from dotenv import load_dotenv
from scrapers import RSSFeedScraper, CoinMarketCapScraper, ScraperManager
from notification_database_manager import NotificationDatabaseManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

async def test_scrapers():
    """Test the scrapers functionality."""
    # Load environment variables
    load_dotenv()
    
    # Initialize notification manager
    notification_manager = NotificationDatabaseManager()
    
    try:
        # Initialize scraper manager
        scraper_manager = ScraperManager(notification_manager)
        
        # Test RSS Feed Scraper
        logger.info("Testing RSS Feed Scraper...")
        rss_feeds = {
            "bitcoin_magazine": "https://bitcoinmagazine.com/feed",
            "cointelegraph": "https://cointelegraph.com/rss"
        }
        
        # Create RSS scraper
        rss_scraper = RSSFeedScraper(feed_urls=rss_feeds, bot_username="test_bot")
        scraper_manager.add_scraper(rss_scraper)
        
        # Test CoinMarketCap Scraper
        logger.info("\nTesting CoinMarketCap Scraper...")
        cmc_scraper = CoinMarketCapScraper(bot_username="test_bot")
        scraper_manager.add_scraper(cmc_scraper)
        
        # Run scraping cycle
        logger.info("\nRunning scraping cycle...")
        await scraper_manager.run_scraping_cycle()
        
    except Exception as e:
        logger.error(f"Error in test: {str(e)}")
    finally:
        # Close the notification manager
        await notification_manager.close()

if __name__ == "__main__":
    asyncio.run(test_scrapers()) 