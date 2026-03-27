"""Tests for risk scoring engine."""

from sentinel.analyzers.risk_scorer import RiskScorer
from sentinel.models.opportunity import YieldOpportunity, YieldType
from sentinel.models.protocol import Protocol, ProtocolCategory, ProtocolRisk, RiskLevel


class TestRiskScorer:
    """Test risk scoring across different opportunity types."""

    def setup_method(self) -> None:
        self.scorer = RiskScorer()

    def test_low_risk_blue_chip_lending(
        self, sample_lending_opportunity: YieldOpportunity, sample_protocol: Protocol
    ) -> None:
        """Blue-chip lending should score as low risk."""
        score = self.scorer.score_opportunity(sample_lending_opportunity, sample_protocol)
        assert score < 0.4
        assert self.scorer.classify(score) in (RiskLevel.MINIMAL, RiskLevel.LOW)

    def test_high_yield_increases_risk(self) -> None:
        """Very high APY opportunities should be flagged as higher risk."""
        opp = YieldOpportunity(
            id="suspicious",
            protocol="unknown",
            chain="Ethereum",
            pool_name="Amazing Yield",
            underlying_tokens=["USDC"],
            yield_type=YieldType.VAULT,
            base_apy=5.0,
            reward_apy=95.0,
            total_apy=100.0,
            tvl_usd=1_000_000,
            source="defillama",
        )
        score = self.scorer.score_opportunity(opp)
        assert score > 0.4  # Should be elevated

    def test_low_tvl_increases_risk(self) -> None:
        """Low TVL opportunities should have higher liquidity risk."""
        opp = YieldOpportunity(
            id="small-pool",
            protocol="niche",
            chain="Ethereum",
            pool_name="Small Pool",
            underlying_tokens=["USDC"],
            yield_type=YieldType.LENDING,
            base_apy=5.0,
            total_apy=5.0,
            tvl_usd=200_000,
            source="defillama",
        )
        score = self.scorer.score_opportunity(opp)
        # Compare with a larger version
        opp_large = opp.model_copy(update={"tvl_usd": 2_000_000_000})
        score_large = self.scorer.score_opportunity(opp_large)
        assert score > score_large

    def test_classify_risk_levels(self) -> None:
        """Risk classification should map scores to correct levels."""
        assert self.scorer.classify(0.05) == RiskLevel.MINIMAL
        assert self.scorer.classify(0.25) == RiskLevel.LOW
        assert self.scorer.classify(0.45) == RiskLevel.MEDIUM
        assert self.scorer.classify(0.65) == RiskLevel.HIGH
        assert self.scorer.classify(0.85) == RiskLevel.CRITICAL
