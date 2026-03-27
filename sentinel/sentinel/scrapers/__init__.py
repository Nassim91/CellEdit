"""Social and web scrapers for DeFi sentiment analysis."""

from sentinel.scrapers.twitter_scraper import TwitterScraper
from sentinel.scrapers.sentiment_analyzer import SentimentAnalyzer

__all__ = ["SentimentAnalyzer", "TwitterScraper"]
