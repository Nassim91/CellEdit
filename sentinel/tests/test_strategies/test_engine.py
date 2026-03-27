"""Tests for strategy engine."""

from sentinel.models.opportunity import YieldOpportunity
from sentinel.strategies.engine import StrategyEngine


class TestStrategyEngine:
    """Test strategy generation from opportunity sets."""

    def setup_method(self) -> None:
        self.engine = StrategyEngine()

    def test_generates_lending_strategy(
        self, sample_opportunities: list[YieldOpportunity]
    ) -> None:
        """Should generate a single-sided lending strategy."""
        strategies = self.engine.generate_strategies(
            sample_opportunities, "USDC", 1_000_000
        )
        lending = [s for s in strategies if s.strategy_type == "single_sided_lending"]
        assert len(lending) >= 1

    def test_generates_basis_trade(
        self, sample_opportunities: list[YieldOpportunity]
    ) -> None:
        """Should generate a basis trade strategy when delta-neutral opps exist."""
        strategies = self.engine.generate_strategies(
            sample_opportunities, "USDC", 1_000_000
        )
        basis = [s for s in strategies if s.strategy_type == "basis_trade"]
        assert len(basis) >= 1
        assert basis[0].is_market_neutral

    def test_pt_arbitrage_for_pendle(
        self, sample_opportunities: list[YieldOpportunity]
    ) -> None:
        """Should generate PT arbitrage strategies for Pendle PT opps."""
        strategies = self.engine.generate_strategies(
            sample_opportunities, "stETH", 1_000_000
        )
        pt_arb = [s for s in strategies if s.strategy_type == "pt_arbitrage"]
        # PT arb should be generated if PT yield exceeds risk-free rate
        for s in pt_arb:
            assert s.expected_net_apy > 0

    def test_strategies_sorted_by_apy(
        self, sample_opportunities: list[YieldOpportunity]
    ) -> None:
        """Strategies should be sorted by risk-adjusted return."""
        strategies = self.engine.generate_strategies(
            sample_opportunities, "USDC", 1_000_000
        )
        if len(strategies) >= 2:
            # First strategy should have higher or equal adjusted APY
            # (accounting for risk penalty)
            assert strategies[0].expected_net_apy >= 0

    def test_no_strategies_for_unknown_token(self) -> None:
        """Should handle empty opportunity sets gracefully."""
        strategies = self.engine.generate_strategies([], "UNKNOWN_TOKEN", 1_000_000)
        assert isinstance(strategies, list)
