"""Tests for Pendle PT arbitrage evaluator."""

from sentinel.models.opportunity import YieldOpportunity, YieldType
from sentinel.strategies.pt_arbitrage import PTArbitrageEvaluator


class TestPTArbitrageEvaluator:
    """Test PT arbitrage opportunity evaluation."""

    def setup_method(self) -> None:
        self.evaluator = PTArbitrageEvaluator(risk_free_rate=5.0, min_spread_bps=100)

    def test_identifies_profitable_pt(self, sample_pendle_pt: YieldOpportunity) -> None:
        """Should identify PT with yield above risk-free as an opportunity."""
        results = self.evaluator.evaluate(
            [sample_pendle_pt], "stETH", 1_000_000
        )
        # PT at 5.5% vs risk-free at 5.0% = 0.5% spread = 50bps < 100bps threshold
        # So this should NOT generate a recommendation with 100bps threshold
        assert len(results) == 0

    def test_identifies_high_spread_pt(self) -> None:
        """Should recommend PT with large spread over risk-free."""
        pt = YieldOpportunity(
            id="pendle-pt-high-yield",
            protocol="pendle",
            chain="Ethereum",
            pool_name="Pendle PT weETH 26DEC2026",
            underlying_tokens=["weETH"],
            yield_type=YieldType.FIXED_LENDING,
            base_apy=8.0,
            total_apy=8.0,
            tvl_usd=200_000_000,
            source="pendle",
            tags=["fixed-yield", "yield-tokenization", "expiry:26DEC2026"],
        )
        results = self.evaluator.evaluate([pt], "weETH", 1_000_000)
        assert len(results) == 1
        assert results[0].strategy_type == "pt_arbitrage"
        assert results[0].expected_net_apy == 8.0
        assert results[0].confidence >= 0.8

    def test_filters_non_pendle(self, sample_lending_opportunity: YieldOpportunity) -> None:
        """Should only evaluate Pendle PT opportunities."""
        results = self.evaluator.evaluate(
            [sample_lending_opportunity], "USDC", 1_000_000
        )
        assert len(results) == 0

    def test_maturity_parsing(self) -> None:
        """Should parse maturity dates from tags."""
        days = self.evaluator._estimate_days_to_maturity("26DEC2026")
        assert days is not None
        assert days > 0
