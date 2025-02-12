import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
import json
from typing import Dict, List, Optional, Set
import os

import tweepy
import praw
import httpx
from bs4 import BeautifulSoup
from pycoingecko import CoinGeckoAPI
from pydantic import BaseModel

from models import NotificationCreate
from twitter_service import TwitterService, Tweet
from vault_service import VaultService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ScrapedNotification(BaseModel):
    source: str
    short_desc: str
    long_desc: str
    notification_date: str

class BaseScraper(ABC):
    def __init__(self):
        self.last_check_time: Optional[datetime] = None
    
    @abstractmethod
    async def scrape(self) -> List[ScrapedNotification]:
        """Scrape data from the source and return a list of scraped items."""
        pass

class TwitterMentionsScraper(BaseScraper):
    def __init__(self, bot_username: str):
        super().__init__()
        self.twitter_service = TwitterService(bot_username=bot_username)
        self.last_mention_id: Optional[str] = None
        
    def _format_tweet_content(self, tweet: Tweet) -> str:
        """Format tweet content with additional context."""
        content_parts = []
        
        # Add main tweet content
        content_parts.append(f"Tweet: {tweet.text}")
        
        # Add trading signals if present
        trading_signals = self.twitter_service.extract_trading_signals(tweet)
        if trading_signals:
            content_parts.append("\nTrading Signals:")
            if 'sentiment' in trading_signals:
                content_parts.append(f"- Sentiment: {trading_signals['sentiment']}")
            for symbol, price in trading_signals.items():
                if symbol != 'sentiment':
                    content_parts.append(f"- {symbol}: ${price:,.2f}")
        
        # Add market events if present
        market_events = self.twitter_service.extract_market_events(tweet)
        if market_events:
            content_parts.append("\nMarket Events:")
            for event_type, details in market_events.items():
                content_parts.append(f"- {event_type.title()}: {', '.join(map(str, details))}")
        
        # Add media information
        if tweet.media_urls:
            content_parts.append("\nMedia:")
            for url in tweet.media_urls:
                content_parts.append(f"- {url}")
        
        # Add quoted tweet if present
        if tweet.quoted_tweet:
            content_parts.append(f"\nQuoted Tweet from @{tweet.quoted_tweet['user_screen_name']}:")
            content_parts.append(tweet.quoted_tweet['text'])
        
        return "\n".join(content_parts)
        
    async def scrape(self) -> List[ScrapedNotification]:
        scraped_data = []
        try:
            mentions = self.twitter_service.get_mentions(since_id=self.last_mention_id)
            
            if mentions:
                self.last_mention_id = mentions[0].id  # Update last seen mention ID
                
            for tweet in mentions:
                scraped_data.append(ScrapedNotification(
                    source="twitter_mentions",
                    short_desc=f"New mention from @{tweet.user_screen_name}",
                    long_desc=self._format_tweet_content(tweet),
                    notification_date=tweet.created_at.isoformat()
                ))
                
        except Exception as e:
            logger.error(f"Error scraping Twitter mentions: {str(e)}")
            
        return scraped_data

class TwitterFeedScraper(BaseScraper):
    def __init__(self, bot_username: str):
        super().__init__()
        self.twitter_service = TwitterService(bot_username=bot_username)
        self.last_tweet_id: Optional[str] = None
        
    def _format_tweet_content(self, tweet: Tweet) -> str:
        """Format tweet content with additional context."""
        content_parts = []
        
        # Add main tweet content
        content_parts.append(f"Tweet: {tweet.text}")
        
        # Add hashtags if present
        if tweet.hashtags:
            content_parts.append(f"\nHashtags: {', '.join(['#' + tag for tag in tweet.hashtags])}")
        
        # Add trading signals if present
        trading_signals = self.twitter_service.extract_trading_signals(tweet)
        if trading_signals:
            content_parts.append("\nTrading Signals:")
            if 'sentiment' in trading_signals:
                content_parts.append(f"- Sentiment: {trading_signals['sentiment']}")
            for symbol, price in trading_signals.items():
                if symbol != 'sentiment':
                    content_parts.append(f"- {symbol}: ${price:,.2f}")
        
        # Add market events if present
        market_events = self.twitter_service.extract_market_events(tweet)
        if market_events:
            content_parts.append("\nMarket Events:")
            for event_type, details in market_events.items():
                content_parts.append(f"- {event_type.title()}: {', '.join(map(str, details))}")
        
        # Add media information
        if tweet.media_urls:
            content_parts.append("\nMedia:")
            for url in tweet.media_urls:
                content_parts.append(f"- {url}")
        
        return "\n".join(content_parts)
        
    async def scrape(self) -> List[ScrapedNotification]:
        scraped_data = []
        try:
            tweets = self.twitter_service.get_own_timeline(count=10, since_id=self.last_tweet_id)
            
            if tweets:
                self.last_tweet_id = tweets[0].id  # Update last seen tweet ID
                
            for tweet in tweets:
                scraped_data.append(ScrapedNotification(
                    source="twitter_feed",
                    short_desc=f"New tweet in feed",
                    long_desc=self._format_tweet_content(tweet),
                    notification_date=tweet.created_at.isoformat()
                ))
                
        except Exception as e:
            logger.error(f"Error scraping Twitter feed: {str(e)}")
            
        return scraped_data

class CoinMarketCapScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.rss_url = "https://blog.coinmarketcap.com/feed/"  # Updated to a working RSS feed
        self.client = httpx.AsyncClient(follow_redirects=True)  # Enable following redirects
        
    async def scrape(self) -> List[ScrapedNotification]:
        scraped_data = []
        try:
            response = await self.client.get(self.rss_url)
            response.raise_for_status()  # Raise exception for bad status codes
            
            # Parse the XML content properly
            soup = BeautifulSoup(response.content, "xml")
            if not soup.find('item'):  # If xml parser didn't work, try lxml
                soup = BeautifulSoup(response.content, "lxml")
            
            items = soup.find_all("item")
            logger.info(f"Found {len(items)} items in the RSS feed")
            
            for item in items[:10]:  # Get the 10 most recent items
                try:
                    title = item.title.text.strip()
                    description = item.description.text.strip()
                    link = item.link.text.strip()
                    pub_date = item.pubDate.text.strip()
                    
                    # Parse the publication date
                    try:
                        pub_date_dt = datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %z")
                    except ValueError:
                        pub_date_dt = datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S +0000")
                    
                    if self.last_check_time and pub_date_dt.replace(tzinfo=None) <= self.last_check_time:
                        continue
                    
                    scraped_data.append(ScrapedNotification(
                        source="coinmarketcap",
                        short_desc=title,
                        long_desc=f"{description}\nLink: {link}",
                        notification_date=pub_date_dt.isoformat()
                    ))
                except Exception as e:
                    logger.error(f"Error processing RSS item: {str(e)}")
                    continue
                
        except Exception as e:
            logger.error(f"Error scraping CoinMarketCap RSS: {str(e)}")
            
        self.last_check_time = datetime.now(datetime)  # Use timezone-aware datetime
        await self.client.aclose()  # Properly close the client
        return scraped_data

class CoinGeckoScraper(BaseScraper):
    def __init__(self, tracked_currencies: List[str], price_change_threshold: float = 5.0):
        super().__init__()
        # Get API key from vault
        vault = VaultService()
        secrets = vault.get_all_secrets()
        self.api_key = secrets.get("COINGECKO_API_KEY", "")
        
        # Initialize HTTP client for direct API calls
        self.client = httpx.AsyncClient(
            base_url="https://pro-api.coingecko.com/api/v3" if self.api_key else "https://api.coingecko.com/api/v3",
            headers={'x-cg-pro-api-key': self.api_key} if self.api_key else {}
        )
        if self.api_key:
            print(self.api_key)
            logger.info("Initialized CoinGecko client with Pro API endpoint")
        else:
            logger.warning("No CoinGecko API key found in vault, using free tier")
            
        self.tracked_currencies = tracked_currencies
        self.price_change_threshold = price_change_threshold
        self.last_prices: Dict[str, float] = {}
        
    async def scrape(self) -> List[ScrapedNotification]:
        scraped_data = []
        try:
            for currency in self.tracked_currencies:
                # Make direct API call with proper parameters
                response = await self.client.get(
                    "/simple/price",
                    params={
                        'ids': currency,
                        'vs_currencies': 'usd',
                        'include_24hr_change': 'true'
                    }
                )
                response.raise_for_status()
                data = response.json()
                
                if not data or currency not in data:
                    continue
                
                current_price = data[currency]['usd']
                price_change = data[currency]['usd_24h_change']
                
                # Check if price change exceeds threshold
                if abs(price_change) >= self.price_change_threshold:
                    change_type = "increase" if price_change > 0 else "decrease"
                    scraped_data.append(ScrapedNotification(
                        source="coingecko",
                        short_desc=f"{currency.upper()} price {change_type} alert",
                        long_desc=f"{currency.upper()} price {change_type}d by {abs(price_change):.2f}% in the last 24h. Current price: ${current_price:,.2f}",
                        notification_date=datetime.utcnow().isoformat()
                    ))
                
                self.last_prices[currency] = current_price
                
        except Exception as e:
            logger.error(f"Error scraping CoinGecko: {str(e)}")
            
        return scraped_data

class RedditScraper(BaseScraper):
    def __init__(self, client_id: str, client_secret: str, user_agent: str, subreddits: List[str]):
        super().__init__()
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )
        self.subreddits = subreddits
        self.seen_posts: Set[str] = set()
        
    async def scrape(self) -> List[ScrapedNotification]:
        scraped_data = []
        try:
            for subreddit_name in self.subreddits:
                subreddit = self.reddit.subreddit(subreddit_name)
                for post in subreddit.hot(limit=10):
                    if post.id in self.seen_posts:
                        continue
                        
                    self.seen_posts.add(post.id)
                    created_time = datetime.fromtimestamp(post.created_utc)
                    
                    if self.last_check_time and created_time <= self.last_check_time:
                        continue
                    
                    scraped_data.append(ScrapedNotification(
                        source=f"reddit_{subreddit_name}",
                        short_desc=post.title,
                        long_desc=f"{post.selftext[:500]}...\nLink: https://reddit.com{post.permalink}",
                        notification_date=created_time.isoformat()
                    ))
                    
        except Exception as e:
            logger.error(f"Error scraping Reddit: {str(e)}")
            
        self.last_check_time = datetime.utcnow()
        return scraped_data

class ScraperManager:
    def __init__(self, notification_client):
        self.notification_client = notification_client
        self.scrapers: List[BaseScraper] = []
        
    def add_scraper(self, scraper: BaseScraper):
        """Add a scraper to the manager."""
        self.scrapers.append(scraper)
        
    async def run_scraping_cycle(self):
        """Run one cycle of scraping from all sources."""
        for scraper in self.scrapers:
            try:
                scraped_items = await scraper.scrape()
                for item in scraped_items:
                    await self.notification_client.create_notification(
                        source=item.source,
                        short_desc=item.short_desc,
                        long_desc=item.long_desc,
                        notification_date=item.notification_date
                    )
            except Exception as e:
                logger.error(f"Error in scraping cycle for {scraper.__class__.__name__}: {str(e)}")
                
    async def start_periodic_scraping(self, interval_seconds: int = 3600):  # Default 1 hour
        """Start periodic scraping with the specified interval."""
        while True:
            await self.run_scraping_cycle()
            await asyncio.sleep(interval_seconds)

# Example usage
if __name__ == "__main__":
    # Test the scrapers with vault credentials
    try:
        # Test CoinMarketCap scraper
        print("\nTesting CoinMarketCap RSS Feed Scraper...")
        
        async def test_cmc():
            cmc_scraper = CoinMarketCapScraper()
            try:
                news = await cmc_scraper.scrape()
                print(f"\nLatest {len(news)} CoinMarketCap news items:")
                for item in news:
                    print(f"- {item.short_desc}")
                    print(f"  {item.long_desc[:200]}...")  # Show first 200 chars of description
            finally:
                await cmc_scraper.client.aclose()
        
        asyncio.run(test_cmc())
        
        # Test Reddit scraper
        print("\nTesting Reddit Scraper...")
        vault = VaultService()
        secrets = vault.get_all_secrets()
        
        reddit_scraper = RedditScraper(
            client_id=secrets.get("REDDIT_CLIENT_ID", ""),
            client_secret=secrets.get("REDDIT_CLIENT_SECRET", ""),
            user_agent="SuperiorAgentsBot/1.0",
            subreddits=[
                "cryptocurrency",
                "bitcoin",
                "ethereum",
                "CryptoMarkets"
            ]
        )
        reddit_posts = asyncio.run(reddit_scraper.scrape())
        print(f"\nLatest {len(reddit_posts)} Reddit posts:")
        for post in reddit_posts:
            print(f"- [{post.source}] {post.short_desc}")
            print(f"  {post.long_desc[:200]}...")  # Show first 200 chars of content
            
    except Exception as e:
        print(f"Error testing scrapers: {str(e)}") 