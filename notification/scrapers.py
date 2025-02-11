import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional

import tweepy
from bs4 import BeautifulSoup
import httpx
from pydantic import BaseModel

from notification_manager import AgentType, NotificationPriority

logger = logging.getLogger(__name__)

class ScrapedData(BaseModel):
    source: str
    content: str
    priority: NotificationPriority
    target_agents: List[AgentType]
    metadata: Dict = {}

class BaseScraper(ABC):
    def __init__(self):
        self.last_check_time: Optional[datetime] = None
    
    @abstractmethod
    async def scrape(self) -> List[ScrapedData]:
        """Scrape data from the source and return a list of scraped items."""
        pass

class TwitterScraper(BaseScraper):
    def __init__(self, api_key: str, api_secret: str, access_token: str, access_token_secret: str):
        super().__init__()
        auth = tweepy.OAuthHandler(api_key, api_secret)
        auth.set_access_token(access_token, access_token_secret)
        self.api = tweepy.API(auth)
        self.tracked_accounts = [
            "whale_alert",  # Crypto whale transactions
            "DocumentingBTC",  # Bitcoin news
            "DefiLlama",  # DeFi updates
            # Add more relevant accounts
        ]
        
    async def scrape(self) -> List[ScrapedData]:
        scraped_data = []
        
        for account in self.tracked_accounts:
            try:
                tweets = self.api.user_timeline(screen_name=account, count=10)
                for tweet in tweets:
                    # Skip if we've already seen this tweet
                    if self.last_check_time and tweet.created_at <= self.last_check_time:
                        continue
                        
                    priority = self._determine_priority(tweet.text)
                    target_agents = self._determine_target_agents(tweet.text)
                    
                    scraped_data.append(ScrapedData(
                        source=f"twitter_{account}",
                        content=tweet.text,
                        priority=priority,
                        target_agents=target_agents,
                        metadata={
                            "tweet_id": tweet.id,
                            "created_at": tweet.created_at.isoformat(),
                            "user": account
                        }
                    ))
                
            except Exception as e:
                logger.error(f"Error scraping Twitter for {account}: {str(e)}")
        
        self.last_check_time = datetime.utcnow()
        return scraped_data
    
    def _determine_priority(self, text: str) -> NotificationPriority:
        """Determine notification priority based on tweet content."""
        text_lower = text.lower()
        
        # High priority keywords
        if any(kw in text_lower for kw in ["urgent", "breaking", "alert", "$1000000"]):
            return NotificationPriority.HIGH
            
        # Medium priority keywords
        if any(kw in text_lower for kw in ["update", "announcement", "news"]):
            return NotificationPriority.MEDIUM
            
        return NotificationPriority.LOW
    
    def _determine_target_agents(self, text: str) -> List[AgentType]:
        """Determine which agents should receive this notification."""
        text_lower = text.lower()
        agents = set()
        
        # Trading-related content
        if any(kw in text_lower for kw in ["price", "trade", "market", "buy", "sell"]):
            agents.add(AgentType.TRADING)
            agents.add(AgentType.TRADING_ASSISTED)
            
        # Marketing-related content
        if any(kw in text_lower for kw in ["announcement", "partnership", "community"]):
            agents.add(AgentType.MARKETING)
            
        # If no specific category, send to all
        if not agents:
            return list(AgentType)
            
        return list(agents)

class CryptoNewsScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.sources = [
            "https://cointelegraph.com/rss",
            "https://cryptonews.com/news/feed",
            # Add more news sources
        ]
        self.client = httpx.AsyncClient()
        
    async def scrape(self) -> List[ScrapedData]:
        scraped_data = []
        
        for source in self.sources:
            try:
                response = await self.client.get(source)
                soup = BeautifulSoup(response.text, "xml")
                
                for item in soup.find_all("item")[:10]:  # Get latest 10 items
                    pub_date = datetime.strptime(item.pubDate.text, "%a, %d %b %Y %H:%M:%S %z")
                    
                    if self.last_check_time and pub_date <= self.last_check_time:
                        continue
                    
                    priority = self._determine_priority(item.title.text)
                    target_agents = self._determine_target_agents(item.title.text)
                    
                    scraped_data.append(ScrapedData(
                        source=f"crypto_news_{source}",
                        content=f"{item.title.text}: {item.description.text}",
                        priority=priority,
                        target_agents=target_agents,
                        metadata={
                            "link": item.link.text,
                            "published_at": pub_date.isoformat(),
                            "source_url": source
                        }
                    ))
                    
            except Exception as e:
                logger.error(f"Error scraping news from {source}: {str(e)}")
        
        self.last_check_time = datetime.utcnow()
        return scraped_data
    
    def _determine_priority(self, text: str) -> NotificationPriority:
        """Determine notification priority based on news content."""
        text_lower = text.lower()
        
        if any(kw in text_lower for kw in ["breaking", "urgent", "major", "critical"]):
            return NotificationPriority.HIGH
            
        if any(kw in text_lower for kw in ["announces", "launches", "partners"]):
            return NotificationPriority.MEDIUM
            
        return NotificationPriority.LOW
    
    def _determine_target_agents(self, text: str) -> List[AgentType]:
        """Determine which agents should receive this notification."""
        text_lower = text.lower()
        agents = set()
        
        if any(kw in text_lower for kw in ["price", "market", "trading", "analysis"]):
            agents.add(AgentType.TRADING)
            agents.add(AgentType.TRADING_ASSISTED)
            
        if any(kw in text_lower for kw in ["partnership", "adoption", "community"]):
            agents.add(AgentType.MARKETING)
            
        if not agents:
            return list(AgentType)
            
        return list(agents)

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
                        content=item.content,
                        priority=item.priority,
                        target_agents=item.target_agents,
                        metadata=item.metadata
                    )
            except Exception as e:
                logger.error(f"Error in scraping cycle for {scraper.__class__.__name__}: {str(e)}")
                
    async def start_periodic_scraping(self, interval_seconds: int = 300):  # Default 5 minutes
        """Start periodic scraping with the specified interval."""
        while True:
            await self.run_scraping_cycle()
            await asyncio.sleep(interval_seconds) 