"""Social sentiment and signal models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SentimentSource(str, Enum):
    TWITTER = "twitter"
    DISCORD = "discord"
    GOVERNANCE = "governance"
    BLOG = "blog"
    NEWS = "news"


class SentimentDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class SentimentSignal(BaseModel):
    """A sentiment signal captured from social or news sources."""

    source: SentimentSource
    protocol: str | None = None
    content: str
    author: str | None = None
    author_followers: int | None = None
    url: str | None = None

    direction: SentimentDirection = SentimentDirection.NEUTRAL
    relevance_score: float = Field(0.5, ge=0, le=1)
    engagement_score: float = Field(0.0, ge=0, description="Likes + retweets + replies weighted")

    # Keywords and topics detected
    topics: list[str] = Field(default_factory=list)
    mentioned_protocols: list[str] = Field(default_factory=list)
    mentioned_tokens: list[str] = Field(default_factory=list)

    captured_at: datetime = Field(default_factory=datetime.utcnow)
    published_at: datetime | None = None


class ProtocolMomentum(BaseModel):
    """Aggregated momentum signal for a protocol based on social activity."""

    protocol: str
    period_hours: int = 24

    # Volume metrics
    total_mentions: int = 0
    unique_authors: int = 0
    total_engagement: float = 0.0
    influencer_mentions: int = Field(0, description="Mentions by accounts with >10k followers")

    # Sentiment breakdown
    bullish_pct: float = 0.0
    bearish_pct: float = 0.0
    neutral_pct: float = 0.0

    # Trend
    mention_change_pct: float | None = Field(None, description="% change vs previous period")
    is_trending: bool = False
    momentum_score: float = Field(0.0, ge=-1, le=1, description="-1 to 1: negative=declining, positive=growing")

    top_signals: list[SentimentSignal] = Field(default_factory=list)
    computed_at: datetime = Field(default_factory=datetime.utcnow)
