#!/usr/bin/env python3
import asyncio
import logging
import sys
from datetime import datetime

from dotenv import load_dotenv
from scrapers import RSSFeedScraper, CoinMarketCapScraper, NotificationDatabaseManager

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
        # Test RSS Feed Scraper
        logger.info("Testing RSS Feed Scraper...")
        rss_feeds = {
            "bitcoin_magazine": "https://bitcoinmagazine.com/feed",
            "cointelegraph": "https://cointelegraph.com/rss"
        }
        
        # Create RSS scraper
        rss_scraper = RSSFeedScraper(feed_urls=rss_feeds, bot_username="test_bot")
        rss_scraper.notification_manager = notification_manager
        
        # Scrape RSS feeds
        start_time = datetime.now()
        items = await rss_scraper.scrape()
        logger.info(f"RSS scrape found {len(items)} items in {(datetime.now() - start_time).total_seconds():.2f} seconds")
        
        # Print the first few items
        for i, item in enumerate(items[:3]):
            logger.info(f"Item {i+1}: {item.short_desc}")
        
        # Test CoinMarketCap Scraper
        logger.info("\nTesting CoinMarketCap Scraper...")
        cmc_scraper = CoinMarketCapScraper(bot_username="test_bot")
        cmc_scraper.notification_manager = notification_manager
        
        # Scrape CoinMarketCap
        start_time = datetime.now()
        cmc_items = await cmc_scraper.scrape()
        logger.info(f"CoinMarketCap scrape found {len(cmc_items)} items in {(datetime.now() - start_time).total_seconds():.2f} seconds")
        
    except Exception as e:
        logger.error(f"Error in test: {str(e)}")
    finally:
        # Close the notification manager
        await notification_manager.close()

if __name__ == "__main__":
    asyncio.run(test_scrapers()) 