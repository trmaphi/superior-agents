import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
import re

import tweepy
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Tweet(BaseModel):
    id: str
    text: str
    created_at: datetime
    user_screen_name: str
    user_id: str
    is_retweet: bool
    is_quote: bool
    mentioned_users: List[str]
    hashtags: List[str]
    urls: List[str]
    media_urls: List[str]
    quoted_tweet: Optional[Dict] = None
    retweeted_tweet: Optional[Dict] = None
    reply_to_tweet_id: Optional[str] = None
    reply_to_user_id: Optional[str] = None
    
class TwitterService:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        access_token: str,
        access_token_secret: str,
        bot_username: str
    ):
        """Initialize Twitter service with credentials and bot configuration."""
        auth = tweepy.OAuthHandler(api_key, api_secret)
        auth.set_access_token(access_token, access_token_secret)
        self.api = tweepy.API(auth, wait_on_rate_limit=True)
        self.bot_username = bot_username
        self.seen_tweets: Set[str] = set()
        
    def _process_tweet(self, tweet) -> Tweet:
        """Process a tweet object and extract relevant information."""
        # Extract mentioned users
        mentioned_users = [user['screen_name'] for user in tweet.entities.get('user_mentions', [])]
        
        # Extract hashtags
        hashtags = [tag['text'] for tag in tweet.entities.get('hashtags', [])]
        
        # Extract URLs
        urls = [url['expanded_url'] for url in tweet.entities.get('urls', [])]
        
        # Extract media URLs
        media_urls = []
        if hasattr(tweet, 'extended_entities') and 'media' in tweet.extended_entities:
            for media in tweet.extended_entities['media']:
                if media['type'] == 'photo':
                    media_urls.append(media['media_url_https'])
                elif media['type'] == 'video':
                    # Get highest quality video URL
                    variants = media['video_info']['variants']
                    video_variants = [v for v in variants if v['content_type'] == 'video/mp4']
                    if video_variants:
                        highest_bitrate = max(video_variants, key=lambda x: x.get('bitrate', 0))
                        media_urls.append(highest_bitrate['url'])
        
        # Handle quoted tweets
        quoted_tweet = None
        if hasattr(tweet, 'quoted_status'):
            quoted_tweet = {
                'id': tweet.quoted_status.id_str,
                'text': tweet.quoted_status.full_text if hasattr(tweet.quoted_status, 'full_text') else tweet.quoted_status.text,
                'user_screen_name': tweet.quoted_status.user.screen_name
            }
        
        # Handle retweets
        retweeted_tweet = None
        if hasattr(tweet, 'retweeted_status'):
            retweeted_tweet = {
                'id': tweet.retweeted_status.id_str,
                'text': tweet.retweeted_status.full_text if hasattr(tweet.retweeted_status, 'full_text') else tweet.retweeted_status.text,
                'user_screen_name': tweet.retweeted_status.user.screen_name
            }
        
        return Tweet(
            id=tweet.id_str,
            text=tweet.full_text if hasattr(tweet, 'full_text') else tweet.text,
            created_at=tweet.created_at.replace(tzinfo=timezone.utc),
            user_screen_name=tweet.user.screen_name,
            user_id=tweet.user.id_str,
            is_retweet=hasattr(tweet, 'retweeted_status'),
            is_quote=hasattr(tweet, 'quoted_status'),
            mentioned_users=mentioned_users,
            hashtags=hashtags,
            urls=urls,
            media_urls=media_urls,
            quoted_tweet=quoted_tweet,
            retweeted_tweet=retweeted_tweet,
            reply_to_tweet_id=tweet.in_reply_to_status_id_str,
            reply_to_user_id=tweet.in_reply_to_user_id_str
        )
    
    def get_mentions(self, count: int = 50, since_id: Optional[str] = None) -> List[Tweet]:
        """Get recent mentions of the bot account."""
        try:
            mentions = self.api.mentions_timeline(
                count=count,
                since_id=since_id,
                tweet_mode='extended'
            )
            return [self._process_tweet(tweet) for tweet in mentions]
        except Exception as e:
            logger.error(f"Error getting mentions: {str(e)}")
            return []
    
    def get_own_timeline(self, count: int = 10, since_id: Optional[str] = None) -> List[Tweet]:
        """Get recent tweets from bot's own timeline."""
        try:
            tweets = self.api.user_timeline(
                screen_name=self.bot_username,
                count=count,
                since_id=since_id,
                tweet_mode='extended'
            )
            return [self._process_tweet(tweet) for tweet in tweets]
        except Exception as e:
            logger.error(f"Error getting own timeline: {str(e)}")
            return []
    
    def extract_trading_signals(self, tweet: Tweet) -> Optional[Dict]:
        """Extract trading-related signals from tweet content."""
        text = tweet.text.lower()
        signals = {}
        
        # Price patterns (e.g., "$BTC 50000" or "BTC/USD 50000")
        price_pattern = r'\$?([a-z]{2,5})[/-]?(?:usd)?\s*[\$]?\s*([\d,.]+)k?'
        matches = re.finditer(price_pattern, text)
        for match in matches:
            symbol, price = match.groups()
            # Convert price to float, handling "k" notation
            price = price.replace(',', '')
            if 'k' in price.lower():
                price = float(price.lower().replace('k', '')) * 1000
            else:
                price = float(price)
            signals[symbol.upper()] = price
        
        # Trading keywords
        bullish_keywords = ['buy', 'long', 'bullish', 'support', 'breakout', 'accumulate']
        bearish_keywords = ['sell', 'short', 'bearish', 'resistance', 'breakdown', 'dump']
        
        if any(keyword in text for keyword in bullish_keywords):
            signals['sentiment'] = 'bullish'
        elif any(keyword in text for keyword in bearish_keywords):
            signals['sentiment'] = 'bearish'
        
        return signals if signals else None
    
    def extract_market_events(self, tweet: Tweet) -> Optional[Dict]:
        """Extract market-related events from tweet content."""
        text = tweet.text.lower()
        events = {}
        
        # Event keywords
        event_keywords = {
            'listing': r'(?:listed|listing|lists) on (\w+)',
            'partnership': r'partners? with (\w+)',
            'launch': r'(?:launch|releases?|announces?) (\w+)',
            'hack': r'(?:hack|exploit|breach|attack)',
            'regulation': r'(?:sec|regulation|regulatory|law|compliance)',
        }
        
        for event_type, pattern in event_keywords.items():
            matches = re.finditer(pattern, text)
            for match in matches:
                if event_type not in events:
                    events[event_type] = []
                if len(match.groups()) > 0:
                    events[event_type].append(match.group(1))
                else:
                    events[event_type].append(True)
        
        return events if events else None 