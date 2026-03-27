"""NLP-based sentiment analyzer for DeFi social content.

Uses TextBlob for quick polarity scoring and custom DeFi-specific
keyword matching for domain-aware sentiment classification.

This module processes raw social signals (tweets, forum posts, etc.)
and enriches them with:
1. Polarity score (-1 bearish to +1 bullish)
2. Subjectivity score (0 objective to 1 subjective)
3. DeFi-specific sentiment classification
4. Key topic extraction
5. Risk/opportunity signal detection
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sentinel.models.sentiment import SentimentDirection, SentimentSignal
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)


class SignalType(str, Enum):
    """Type of actionable signal detected in social content."""

    YIELD_ALPHA = "yield_alpha"         # New yield opportunity discovered
    PROTOCOL_LAUNCH = "protocol_launch" # New protocol/product launch
    EXPLOIT_ALERT = "exploit_alert"     # Potential exploit or vulnerability
    DEPEG_WARNING = "depeg_warning"     # Stablecoin or LST depeg risk
    WHALE_MOVEMENT = "whale_movement"   # Large wallet activity
    GOVERNANCE = "governance"           # Important governance proposal
    STRATEGY_IDEA = "strategy_idea"     # Novel yield strategy
    GENERAL = "general"                 # Non-specific DeFi discussion


@dataclass
class AnalyzedSignal:
    """Enriched sentiment signal with NLP analysis."""

    signal: SentimentSignal
    polarity: float          # -1 (bearish) to +1 (bullish)
    subjectivity: float      # 0 (objective) to 1 (subjective)
    signal_type: SignalType
    confidence: float        # 0 to 1
    key_topics: list[str]
    actionable: bool         # Whether this signal warrants attention


# DeFi-specific sentiment lexicon (supplements TextBlob's general lexicon)
DEFI_BULLISH = {
    # Yield-specific
    "alpha": 0.7, "yield": 0.3, "apy": 0.3, "apr": 0.3, "earn": 0.4,
    "profit": 0.5, "gains": 0.5, "farming": 0.3, "harvest": 0.3,
    "compound": 0.2, "accumulate": 0.5, "stack": 0.3,
    # Protocol health
    "audit": 0.3, "secure": 0.4, "battle-tested": 0.6, "immutable": 0.3,
    "decentralized": 0.3, "transparent": 0.3, "open-source": 0.3,
    # Market sentiment
    "bullish": 0.8, "moon": 0.6, "undervalued": 0.7, "gem": 0.6,
    "opportunity": 0.5, "launch": 0.4, "innovative": 0.5,
    "revolutionary": 0.6, "game changer": 0.7, "breakout": 0.6,
    "tvl growth": 0.5, "adoption": 0.4, "partnership": 0.4,
}

DEFI_BEARISH = {
    # Exploit/risk
    "exploit": -0.9, "hack": -0.9, "vulnerability": -0.8, "rug": -0.9,
    "scam": -0.9, "ponzi": -0.8, "drain": -0.7, "stolen": -0.8,
    "compromised": -0.8, "backdoor": -0.9,
    # Market risk
    "depeg": -0.7, "insolvent": -0.8, "liquidation": -0.5,
    "cascade": -0.6, "contagion": -0.7, "collapse": -0.8,
    # Warnings
    "warning": -0.5, "caution": -0.4, "avoid": -0.6, "risky": -0.5,
    "overvalued": -0.6, "dump": -0.7, "bearish": -0.8,
    "declining": -0.4, "tvl drop": -0.5, "outflow": -0.4,
    "unsustainable": -0.6, "dilution": -0.4,
}

# Signal type detection patterns
SIGNAL_PATTERNS: dict[SignalType, list[str]] = {
    SignalType.YIELD_ALPHA: [
        "yield alpha", "new yield", "high apy", "best yield",
        "yield opportunity", "earn %", "apy of", "farming strategy",
    ],
    SignalType.PROTOCOL_LAUNCH: [
        "just launched", "new protocol", "mainnet launch", "going live",
        "beta launch", "testnet to mainnet", "product launch", "v2 launch", "v3 launch",
    ],
    SignalType.EXPLOIT_ALERT: [
        "exploit", "hack", "drained", "vulnerability", "reentrancy",
        "flash loan attack", "oracle manipulation", "rugpull", "compromised",
    ],
    SignalType.DEPEG_WARNING: [
        "depeg", "below peg", "lost peg", "depegging", "peg risk",
        "redemption queue", "liquidity crisis",
    ],
    SignalType.WHALE_MOVEMENT: [
        "whale", "large transfer", "million moved", "billion moved",
        "smart money", "institutional", "whale alert",
    ],
    SignalType.GOVERNANCE: [
        "governance proposal", "vote", "snapshot", "temperature check",
        "forum discussion", "dao vote", "governance update",
    ],
    SignalType.STRATEGY_IDEA: [
        "strategy thread", "delta neutral", "basis trade", "yield thread",
        "farming guide", "defi strategy", "how to earn", "loop strategy",
    ],
}


class SentimentAnalyzer:
    """Analyzes DeFi social content for sentiment and actionable signals.

    Combines TextBlob NLP with a domain-specific DeFi lexicon for
    accurate sentiment classification in the crypto/DeFi context.
    """

    def __init__(self) -> None:
        self._textblob_available = False
        try:
            from textblob import TextBlob
            self._textblob_available = True
        except ImportError:
            logger.warning("sentiment.textblob_not_available", note="Falling back to keyword-only analysis")

    def analyze(self, signal: SentimentSignal) -> AnalyzedSignal:
        """Analyze a single sentiment signal."""
        text = signal.content.lower()

        # 1. NLP polarity and subjectivity
        polarity, subjectivity = self._compute_polarity(text)

        # 2. DeFi-specific keyword scoring
        defi_score = self._defi_keyword_score(text)

        # 3. Blend NLP and keyword scores
        blended_polarity = 0.4 * polarity + 0.6 * defi_score

        # 4. Determine sentiment direction
        if blended_polarity > 0.15:
            signal.direction = SentimentDirection.BULLISH
        elif blended_polarity < -0.15:
            signal.direction = SentimentDirection.BEARISH
        else:
            signal.direction = SentimentDirection.NEUTRAL

        # 5. Detect signal type
        signal_type = self._detect_signal_type(text)

        # 6. Extract key topics
        key_topics = self._extract_topics(text)

        # 7. Determine if actionable
        actionable = self._is_actionable(signal, signal_type, blended_polarity)

        # 8. Confidence based on engagement and textual clarity
        confidence = self._compute_confidence(signal, abs(blended_polarity), subjectivity)

        return AnalyzedSignal(
            signal=signal,
            polarity=blended_polarity,
            subjectivity=subjectivity,
            signal_type=signal_type,
            confidence=confidence,
            key_topics=key_topics,
            actionable=actionable,
        )

    def analyze_batch(self, signals: list[SentimentSignal]) -> list[AnalyzedSignal]:
        """Analyze a batch of signals."""
        return [self.analyze(s) for s in signals]

    def _compute_polarity(self, text: str) -> tuple[float, float]:
        """Compute NLP polarity and subjectivity."""
        if self._textblob_available:
            from textblob import TextBlob
            blob = TextBlob(text)
            return blob.sentiment.polarity, blob.sentiment.subjectivity
        # Fallback: use keyword-only
        return self._defi_keyword_score(text), 0.5

    def _defi_keyword_score(self, text: str) -> float:
        """Score text using DeFi-specific keyword lexicon."""
        score = 0.0
        matches = 0

        for keyword, weight in DEFI_BULLISH.items():
            if keyword in text:
                score += weight
                matches += 1

        for keyword, weight in DEFI_BEARISH.items():
            if keyword in text:
                score += weight  # Already negative
                matches += 1

        if matches == 0:
            return 0.0

        # Normalize to -1 to 1 range
        return max(-1.0, min(1.0, score / max(matches, 1)))

    def _detect_signal_type(self, text: str) -> SignalType:
        """Detect the type of actionable signal."""
        best_type = SignalType.GENERAL
        best_matches = 0

        for sig_type, patterns in SIGNAL_PATTERNS.items():
            matches = sum(1 for p in patterns if p in text)
            if matches > best_matches:
                best_matches = matches
                best_type = sig_type

        return best_type

    def _extract_topics(self, text: str) -> list[str]:
        """Extract key DeFi topics from text."""
        topics = []

        topic_keywords = {
            "lending": ["lending", "borrow", "supply", "aave", "compound", "morpho"],
            "staking": ["staking", "validator", "steth", "lido", "rocket pool"],
            "restaking": ["restaking", "eigenlayer", "avs", "lrt", "ether.fi", "renzo"],
            "yield_tokenization": ["pendle", "pt ", "yt ", "yield token", "principal token"],
            "basis_trade": ["basis trade", "funding rate", "delta neutral", "perp short"],
            "stablecoin": ["stablecoin", "usdc", "usdt", "dai", "usde", "depeg"],
            "governance": ["governance", "proposal", "vote", "dao"],
            "airdrop": ["airdrop", "points", "season", "drop"],
            "nft": ["nft", "pfp", "mint"],
            "l2": ["l2", "layer 2", "rollup", "arbitrum", "optimism", "base", "zksync"],
        }

        for topic, keywords in topic_keywords.items():
            if any(kw in text for kw in keywords):
                topics.append(topic)

        return topics

    def _is_actionable(
        self, signal: SentimentSignal, signal_type: SignalType, polarity: float
    ) -> bool:
        """Determine if a signal warrants immediate attention."""
        # Exploit alerts are always actionable
        if signal_type in (SignalType.EXPLOIT_ALERT, SignalType.DEPEG_WARNING):
            return True

        # High-engagement signals about yield alpha
        if signal_type == SignalType.YIELD_ALPHA and signal.engagement_score > 50:
            return True

        # Influencer signals with strong sentiment
        if signal.author_followers and signal.author_followers > 10_000 and abs(polarity) > 0.5:
            return True

        # Protocol launches
        if signal_type == SignalType.PROTOCOL_LAUNCH and signal.engagement_score > 20:
            return True

        return False

    def _compute_confidence(
        self, signal: SentimentSignal, polarity_strength: float, subjectivity: float
    ) -> float:
        """Compute confidence in the sentiment classification."""
        # Higher polarity = more confident
        polarity_conf = min(1.0, polarity_strength * 2)

        # Lower subjectivity = more confident (facts > opinions)
        subjectivity_conf = 1.0 - subjectivity * 0.5

        # Higher engagement = more confident
        engagement_conf = min(1.0, signal.engagement_score / 200)

        # Influencer boost
        influencer_conf = 0.2 if signal.author_followers and signal.author_followers > 10_000 else 0.0

        return min(1.0, 0.3 * polarity_conf + 0.2 * subjectivity_conf + 0.3 * engagement_conf + 0.2 + influencer_conf)
