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
        self.rss_url = "https://coinmarketcap.com/headlines/news/rss"
        self.client = httpx.AsyncClient()
        
    async def scrape(self) -> List[ScrapedNotification]:
        scraped_data = []
        try:
            response = await self.client.get(self.rss_url)
            soup = BeautifulSoup(response.text, "xml")
            
            for item in soup.find_all("item")[:10]:
                pub_date = datetime.strptime(item.pubDate.text, "%a, %d %b %Y %H:%M:%S %z")
                
                if self.last_check_time and pub_date <= self.last_check_time:
                    continue
                
                scraped_data.append(ScrapedNotification(
                    source="coinmarketcap",
                    short_desc=item.title.text,
                    long_desc=f"{item.description.text}\nLink: {item.link.text}",
                    notification_date=pub_date.isoformat()
                ))
                
        except Exception as e:
            logger.error(f"Error scraping CoinMarketCap RSS: {str(e)}")
            
        self.last_check_time = datetime.utcnow()
        return scraped_data

class CoinGeckoScraper(BaseScraper):
    def __init__(self, tracked_currencies: List[str], price_change_threshold: float = 5.0):
        super().__init__()
        self.cg = CoinGeckoAPI()
        self.tracked_currencies = tracked_currencies
        self.price_change_threshold = price_change_threshold
        self.last_prices: Dict[str, float] = {}
        
    async def scrape(self) -> List[ScrapedNotification]:
        scraped_data = []
        try:
            for currency in self.tracked_currencies:
                data = self.cg.get_price(
                    ids=currency,
                    vs_currencies='usd',
                    include_24hr_change=True
                )
                
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
        bot_username = "hyperstitiabot"
        
        # Test Twitter mentions scraper
        mentions_scraper = TwitterMentionsScraper(bot_username=bot_username)
        mentions = asyncio.run(mentions_scraper.scrape())
        print(f"\nScraped {len(mentions)} mentions:")
        for item in mentions:
            print(f"- {item.short_desc}")
            print(f"  {item.long_desc[:100]}...")
        
        # Test Twitter feed scraper
        feed_scraper = TwitterFeedScraper(bot_username=bot_username)
        feed_items = asyncio.run(feed_scraper.scrape())
        print(f"\nScraped {len(feed_items)} feed items:")
        for item in feed_items:
            print(f"- {item.short_desc}")
            print(f"  {item.long_desc[:100]}...")
            
    except Exception as e:
        print(f"Error testing scrapers: {str(e)}") 