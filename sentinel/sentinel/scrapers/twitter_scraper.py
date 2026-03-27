"""X/Twitter scraper for DeFi sentiment and momentum analysis.

Tracks:
- New DeFi protocol launches and alpha leaks
- Yield farming opportunities trending on CT (Crypto Twitter)
- Influencer sentiment on protocols
- Protocol momentum (mention velocity, engagement)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from sentinel.config.settings import TwitterConfig
from sentinel.models.sentiment import (
    ProtocolMomentum,
    SentimentDirection,
    SentimentSignal,
    SentimentSource,
)
from sentinel.utils.http import HttpClient
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)

# DeFi-focused search queries for yield alpha
DEFI_YIELD_QUERIES = [
    "DeFi yield alpha -is:retweet lang:en",
    "yield farming opportunity -is:retweet lang:en",
    "new DeFi protocol launch -is:retweet lang:en",
    "delta neutral strategy DeFi -is:retweet lang:en",
    "basis trade crypto yield -is:retweet lang:en",
    "restaking yield EigenLayer -is:retweet lang:en",
    "Pendle PT YT yield -is:retweet lang:en",
    "Morpho vault yield -is:retweet lang:en",
    "liquid restaking LRT -is:retweet lang:en",
    "DeFi farming airdrop points -is:retweet lang:en",
    "stablecoin yield safe -is:retweet lang:en",
    "cross chain yield DeFi -is:retweet lang:en",
]

# Key DeFi influencers to track (CT thought leaders)
DEFI_INFLUENCERS = [
    "DefiIgnas",
    "DeFi_Made_Here",
    "Dynamo_Patrick",
    "CryptoHayes",
    "0xHamz",
    "pentaborian",
    "route2fi",
    "0xngmi",
    "staborian",
    "ZoomerOracle",
]

# Protocol-specific accounts
PROTOCOL_ACCOUNTS: dict[str, str] = {
    "aave": "AaveAave",
    "compound": "compoundfinance",
    "morpho": "MorphoLabs",
    "pendle": "penaborle_fi",
    "eigenlayer": "eigenlayer",
    "ethena": "ethaborena_labs",
    "lido": "LidoFinance",
    "maker": "MakerDAO",
    "yearn": "yeaborarnfi",
    "uniswap": "Uniswap",
    "curve": "CurveFinance",
    "convex": "ConvexFinance",
}

# Bullish/bearish keyword patterns
BULLISH_KEYWORDS = {
    "bullish", "moon", "undervalued", "gem", "alpha", "opportunity",
    "accumulate", "long", "buy", "apy", "yield", "earn", "profit",
    "launch", "innovative", "revolutionary", "game changer",
}
BEARISH_KEYWORDS = {
    "bearish", "dump", "scam", "rug", "exploit", "hack", "vulnerability",
    "overvalued", "short", "sell", "depeg", "insolvent", "ponzi", "risk",
    "warning", "caution", "avoid",
}


class TwitterScraper:
    """Scrapes X/Twitter for DeFi yield sentiment and momentum signals.

    Supports two modes:
    1. API mode (with bearer token) — uses Twitter API v2
    2. Scraping mode (no API key) — uses web scraping as fallback

    Features:
    - Protocol-specific sentiment tracking
    - Influencer signal detection
    - New protocol discovery via CT buzz
    - Yield opportunity momentum scoring
    """

    def __init__(
        self,
        config: TwitterConfig | None = None,
        http: HttpClient | None = None,
    ) -> None:
        self.config = config or TwitterConfig()
        self.http = http or HttpClient()
        self._api_base = "https://api.twitter.com/2"

    @property
    def _has_api_access(self) -> bool:
        return bool(self.config.bearer_token)

    async def scrape_defi_sentiment(
        self,
        protocols: list[str] | None = None,
        hours: int = 24,
    ) -> list[SentimentSignal]:
        """Scrape DeFi-related tweets and extract sentiment signals.

        Args:
            protocols: Specific protocols to track. None = general DeFi sentiment.
            hours: How far back to look.

        Returns:
            List of sentiment signals, sorted by relevance.
        """
        logger.info("twitter.scrape_start", protocols=protocols, hours=hours)

        signals: list[SentimentSignal] = []

        if self._has_api_access:
            signals = await self._scrape_via_api(protocols, hours)
        else:
            signals = await self._scrape_via_web(protocols, hours)

        # Sort by engagement score
        signals.sort(key=lambda s: s.engagement_score, reverse=True)

        logger.info("twitter.scrape_complete", signals=len(signals))
        return signals

    async def compute_protocol_momentum(
        self,
        protocol: str,
        hours: int = 24,
    ) -> ProtocolMomentum:
        """Compute momentum score for a specific protocol.

        Analyzes mention velocity, engagement, influencer attention,
        and sentiment direction to produce a -1 to 1 momentum score.
        """
        signals = await self.scrape_defi_sentiment(
            protocols=[protocol],
            hours=hours,
        )

        if not signals:
            return ProtocolMomentum(protocol=protocol, period_hours=hours)

        # Compute metrics
        total_mentions = len(signals)
        unique_authors = len({s.author for s in signals if s.author})
        total_engagement = sum(s.engagement_score for s in signals)
        influencer_mentions = sum(
            1 for s in signals
            if s.author_followers and s.author_followers >= self.config.influencer_min_followers
        )

        # Sentiment breakdown
        bullish = sum(1 for s in signals if s.direction == SentimentDirection.BULLISH)
        bearish = sum(1 for s in signals if s.direction == SentimentDirection.BEARISH)
        neutral = total_mentions - bullish - bearish

        bullish_pct = bullish / total_mentions if total_mentions > 0 else 0
        bearish_pct = bearish / total_mentions if total_mentions > 0 else 0
        neutral_pct = neutral / total_mentions if total_mentions > 0 else 1

        # Momentum score: -1 (declining) to +1 (growing)
        # Based on: sentiment direction + engagement + influencer attention
        sentiment_factor = (bullish_pct - bearish_pct)  # -1 to 1
        volume_factor = min(1.0, total_mentions / 50)  # Normalize to 50 mentions
        influencer_factor = min(1.0, influencer_mentions / 5)  # Normalize to 5 influencers

        momentum = (
            0.4 * sentiment_factor +
            0.3 * volume_factor +
            0.3 * influencer_factor
        )

        is_trending = total_mentions > 20 and momentum > 0.3

        return ProtocolMomentum(
            protocol=protocol,
            period_hours=hours,
            total_mentions=total_mentions,
            unique_authors=unique_authors,
            total_engagement=total_engagement,
            influencer_mentions=influencer_mentions,
            bullish_pct=bullish_pct,
            bearish_pct=bearish_pct,
            neutral_pct=neutral_pct,
            is_trending=is_trending,
            momentum_score=max(-1.0, min(1.0, momentum)),
            top_signals=signals[:10],
            computed_at=datetime.utcnow(),
        )

    async def discover_new_protocols(self, hours: int = 72) -> list[dict[str, Any]]:
        """Discover new/emerging DeFi protocols via Twitter buzz.

        Looks for patterns like:
        - "new DeFi protocol" mentions
        - First-time protocol name trending
        - Influencer shilling of unknown projects
        """
        logger.info("twitter.discover_protocols", hours=hours)

        queries = [
            "new DeFi protocol just launched -is:retweet lang:en",
            "DeFi alpha thread -is:retweet lang:en",
            "underrated DeFi protocol -is:retweet lang:en",
            "hidden gem DeFi yield -is:retweet lang:en",
        ]

        signals = await self._search_tweets(queries, hours)

        # Extract mentioned protocols from signals
        protocol_mentions: dict[str, dict[str, Any]] = {}
        for signal in signals:
            for protocol in signal.mentioned_protocols:
                if protocol not in protocol_mentions:
                    protocol_mentions[protocol] = {
                        "name": protocol,
                        "mentions": 0,
                        "total_engagement": 0,
                        "first_seen": signal.published_at or signal.captured_at,
                        "signals": [],
                    }
                protocol_mentions[protocol]["mentions"] += 1
                protocol_mentions[protocol]["total_engagement"] += signal.engagement_score
                protocol_mentions[protocol]["signals"].append(signal)

        # Sort by engagement
        discoveries = sorted(
            protocol_mentions.values(),
            key=lambda x: x["total_engagement"],
            reverse=True,
        )

        logger.info("twitter.discovered_protocols", count=len(discoveries))
        return discoveries[:20]

    async def _scrape_via_api(
        self, protocols: list[str] | None, hours: int
    ) -> list[SentimentSignal]:
        """Scrape using Twitter API v2."""
        queries = self._build_queries(protocols)
        return await self._search_tweets(queries, hours)

    async def _scrape_via_web(
        self, protocols: list[str] | None, hours: int
    ) -> list[SentimentSignal]:
        """Fallback web scraping when no API key is available.

        Uses public Twitter search and parsing.
        """
        logger.info("twitter.web_scrape_mode", note="No API key — using web scraping fallback")

        # Use Nitter or similar public frontends as fallback
        nitter_instances = [
            "https://nitter.net",
            "https://nitter.privacydev.net",
        ]

        signals: list[SentimentSignal] = []
        queries = self._build_queries(protocols)

        for query in queries[:5]:  # Limit to avoid rate limits
            for instance in nitter_instances:
                try:
                    html = await self.http.get_text(
                        f"{instance}/search",
                        params={"f": "tweets", "q": query},
                    )
                    parsed = self._parse_nitter_html(html, query)
                    signals.extend(parsed)
                    break  # Success, move to next query
                except Exception:
                    continue  # Try next instance

        return signals

    async def _search_tweets(
        self, queries: list[str], hours: int
    ) -> list[SentimentSignal]:
        """Search tweets via Twitter API v2."""
        signals: list[SentimentSignal] = []
        since = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

        for query in queries:
            try:
                data = await self.http.get_json(
                    f"{self._api_base}/tweets/search/recent",
                    params={
                        "query": query,
                        "max_results": min(self.config.max_tweets_per_query, 100),
                        "start_time": since,
                        "tweet.fields": "created_at,public_metrics,author_id",
                        "expansions": "author_id",
                        "user.fields": "username,public_metrics",
                    },
                )

                tweets = data.get("data", [])
                users = {
                    u["id"]: u
                    for u in data.get("includes", {}).get("users", [])
                }

                for tweet in tweets:
                    signal = self._tweet_to_signal(tweet, users)
                    if signal:
                        signals.append(signal)

            except Exception as e:
                logger.debug("twitter.search_error", query=query, error=str(e))

        return signals

    def _tweet_to_signal(
        self, tweet: dict[str, Any], users: dict[str, dict[str, Any]]
    ) -> SentimentSignal | None:
        """Convert a raw tweet to a SentimentSignal."""
        text = tweet.get("text", "")
        if not text:
            return None

        metrics = tweet.get("public_metrics", {})
        author_id = tweet.get("author_id", "")
        user = users.get(author_id, {})
        username = user.get("username", "")
        followers = user.get("public_metrics", {}).get("followers_count", 0)

        # Compute engagement score
        likes = metrics.get("like_count", 0)
        retweets = metrics.get("retweet_count", 0)
        replies = metrics.get("reply_count", 0)
        engagement = likes + retweets * 2 + replies * 1.5

        # Determine sentiment direction
        direction = self._classify_sentiment(text)

        # Extract mentioned protocols
        mentioned = self._extract_protocols(text)
        tokens = self._extract_tokens(text)

        return SentimentSignal(
            source=SentimentSource.TWITTER,
            content=text[:500],
            author=username,
            author_followers=followers,
            url=f"https://x.com/{username}/status/{tweet.get('id', '')}",
            direction=direction,
            relevance_score=min(1.0, engagement / 100),
            engagement_score=engagement,
            mentioned_protocols=mentioned,
            mentioned_tokens=tokens,
            captured_at=datetime.utcnow(),
            published_at=datetime.fromisoformat(tweet["created_at"].replace("Z", "+00:00"))
            if tweet.get("created_at")
            else None,
        )

    def _classify_sentiment(self, text: str) -> SentimentDirection:
        """Simple keyword-based sentiment classification."""
        lower = text.lower()
        bullish_count = sum(1 for kw in BULLISH_KEYWORDS if kw in lower)
        bearish_count = sum(1 for kw in BEARISH_KEYWORDS if kw in lower)

        if bullish_count > bearish_count + 1:
            return SentimentDirection.BULLISH
        if bearish_count > bullish_count + 1:
            return SentimentDirection.BEARISH
        return SentimentDirection.NEUTRAL

    def _extract_protocols(self, text: str) -> list[str]:
        """Extract mentioned DeFi protocol names from tweet text."""
        lower = text.lower()
        found = []
        for protocol in PROTOCOL_ACCOUNTS:
            if protocol in lower:
                found.append(protocol)

        # Also check for common DeFi protocol mentions
        extra_protocols = [
            "euler", "balancer", "velodrome", "aerodrome", "camelot",
            "gmx", "hyperliquid", "drift", "jupiter", "raydium",
            "marinade", "jito", "ondo", "centrifuge", "maple",
            "goldfinch", "clearpool", "gearbox", "instadapp",
            "sommelier", "beefy", "harvest", "concentrator",
            "symbiotic", "karak", "kelp", "puffer", "renzo",
            "ether.fi", "swell", "mantle", "blast",
        ]
        for p in extra_protocols:
            if p in lower:
                found.append(p)

        return list(set(found))

    def _extract_tokens(self, text: str) -> list[str]:
        """Extract token symbols from text (basic $SYMBOL detection)."""
        import re
        return list(set(re.findall(r'\$([A-Z]{2,10})', text)))

    def _build_queries(self, protocols: list[str] | None) -> list[str]:
        """Build Twitter search queries."""
        if protocols:
            queries = []
            for p in protocols:
                handle = PROTOCOL_ACCOUNTS.get(p.lower(), "")
                if handle:
                    queries.append(f"@{handle} OR {p} DeFi yield -is:retweet lang:en")
                else:
                    queries.append(f"{p} DeFi yield -is:retweet lang:en")
            return queries
        return DEFI_YIELD_QUERIES

    def _parse_nitter_html(self, html: str, query: str) -> list[SentimentSignal]:
        """Parse Nitter HTML response into signals (basic fallback parser)."""
        # Basic HTML parsing — extract tweet text from timeline items
        signals: list[SentimentSignal] = []

        # Simple regex-based extraction (production would use BeautifulSoup)
        import re
        tweet_pattern = re.compile(r'class="tweet-content[^"]*"[^>]*>(.*?)</div>', re.DOTALL)
        matches = tweet_pattern.findall(html)

        for match in matches[:20]:
            # Strip HTML tags
            text = re.sub(r'<[^>]+>', ' ', match).strip()
            if len(text) < 20:
                continue

            direction = self._classify_sentiment(text)
            mentioned = self._extract_protocols(text)

            signals.append(SentimentSignal(
                source=SentimentSource.TWITTER,
                content=text[:500],
                direction=direction,
                mentioned_protocols=mentioned,
                mentioned_tokens=self._extract_tokens(text),
                captured_at=datetime.utcnow(),
            ))

        return signals

    async def close(self) -> None:
        await self.http.close()
