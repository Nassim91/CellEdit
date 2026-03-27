"""Tests for the sentiment analyzer."""

from sentinel.models.sentiment import SentimentDirection, SentimentSignal, SentimentSource
from sentinel.scrapers.sentiment_analyzer import SentimentAnalyzer, SignalType


class TestSentimentAnalyzer:
    """Test DeFi-specific sentiment analysis."""

    def setup_method(self) -> None:
        self.analyzer = SentimentAnalyzer()

    def test_bullish_signal(self) -> None:
        """Should classify bullish DeFi content correctly."""
        signal = SentimentSignal(
            source=SentimentSource.TWITTER,
            content="Morpho vaults are printing amazing yield. This is the alpha. Bullish on DeFi lending.",
            engagement_score=100,
        )
        result = self.analyzer.analyze(signal)
        assert result.polarity > 0
        assert result.signal.direction == SentimentDirection.BULLISH

    def test_bearish_signal(self) -> None:
        """Should classify bearish/exploit content correctly."""
        signal = SentimentSignal(
            source=SentimentSource.TWITTER,
            content="WARNING: Protocol X has been exploited. $50M drained. Avoid depositing. Hack confirmed.",
            engagement_score=500,
        )
        result = self.analyzer.analyze(signal)
        assert result.polarity < 0
        assert result.signal.direction == SentimentDirection.BEARISH

    def test_exploit_alert_detection(self) -> None:
        """Should detect exploit alerts as actionable."""
        signal = SentimentSignal(
            source=SentimentSource.TWITTER,
            content="Flash loan attack on DeFi protocol. Funds drained via reentrancy exploit.",
            engagement_score=1000,
        )
        result = self.analyzer.analyze(signal)
        assert result.signal_type == SignalType.EXPLOIT_ALERT
        assert result.actionable is True

    def test_yield_alpha_detection(self) -> None:
        """Should detect yield alpha signals."""
        signal = SentimentSignal(
            source=SentimentSource.TWITTER,
            content="Hidden gem yield alpha: new vault offering 12% APY on USDC with no lock-up.",
            engagement_score=80,
        )
        result = self.analyzer.analyze(signal)
        assert result.signal_type == SignalType.YIELD_ALPHA

    def test_neutral_signal(self) -> None:
        """Should classify neutral content correctly."""
        signal = SentimentSignal(
            source=SentimentSource.TWITTER,
            content="The weather is nice today. Going for a walk in the park.",
            engagement_score=5,
        )
        result = self.analyzer.analyze(signal)
        assert result.signal.direction == SentimentDirection.NEUTRAL
        assert result.signal_type == SignalType.GENERAL

    def test_batch_analysis(self) -> None:
        """Should handle batch analysis."""
        signals = [
            SentimentSignal(source=SentimentSource.TWITTER, content="Bullish on DeFi yield alpha opportunity"),
            SentimentSignal(source=SentimentSource.TWITTER, content="Warning: avoid this scam protocol"),
            SentimentSignal(source=SentimentSource.TWITTER, content="Just had lunch"),
        ]
        results = self.analyzer.analyze_batch(signals)
        assert len(results) == 3

    def test_topic_extraction(self) -> None:
        """Should extract DeFi topics from text."""
        topics = self.analyzer._extract_topics("pendle pt yield token aave lending restaking eigenlayer")
        assert "yield_tokenization" in topics
        assert "lending" in topics
        assert "restaking" in topics

    def test_influencer_signal_actionable(self) -> None:
        """Influencer signals with strong sentiment should be actionable."""
        signal = SentimentSignal(
            source=SentimentSource.TWITTER,
            content="This new yield opportunity is incredible alpha. Bullish.",
            author="BigInfluencer",
            author_followers=100_000,
            engagement_score=300,
        )
        result = self.analyzer.analyze(signal)
        assert result.actionable is True
