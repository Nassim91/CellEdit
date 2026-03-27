"""Tests for funding rates source."""

from sentinel.sources.funding_rates import FundingRateEntry, FundingRatesSource


class TestFundingRatesSource:
    """Test funding rate parsing and arbitrage detection."""

    def setup_method(self) -> None:
        self.source = FundingRatesSource(min_annualized_rate=2.0)

    def test_rates_to_opportunities(self) -> None:
        """Should convert positive funding rates to basis trade opportunities."""
        rates = [
            FundingRateEntry(
                symbol="ETH",
                venue="binance",
                funding_rate=0.0003,
                annualized_rate=32.85,  # ~0.03% per 8h × 3 × 365
                mark_price=3000.0,
                open_interest_usd=5_000_000_000,
            ),
        ]
        opps = self.source._rates_to_opportunities(rates, underlying="ETH")
        assert len(opps) == 1
        assert opps[0].is_delta_neutral
        assert opps[0].total_apy > 2.0

    def test_filters_low_rates(self) -> None:
        """Should filter out low funding rates."""
        rates = [
            FundingRateEntry(
                symbol="ETH",
                venue="binance",
                funding_rate=0.00001,
                annualized_rate=1.1,
                mark_price=3000.0,
            ),
        ]
        opps = self.source._rates_to_opportunities(rates, underlying="ETH")
        assert len(opps) == 0

    def test_funding_arb_detection(self) -> None:
        """Should detect cross-venue funding rate arbitrage."""
        rates = [
            FundingRateEntry(
                symbol="ETH",
                venue="binance",
                funding_rate=0.0005,
                annualized_rate=54.75,
                mark_price=3000.0,
                open_interest_usd=5_000_000_000,
            ),
            FundingRateEntry(
                symbol="ETH",
                venue="dydx",
                funding_rate=-0.0002,
                annualized_rate=-17.52,
                mark_price=3000.0,
                open_interest_usd=1_000_000_000,
            ),
        ]
        arbs = self.source._find_funding_arbs(rates, underlying="ETH")
        assert len(arbs) == 1
        assert arbs[0].total_apy > 5.0
        assert "funding-arb" in arbs[0].tags

    def test_no_arb_small_spread(self) -> None:
        """Should not surface arbs with small spreads."""
        rates = [
            FundingRateEntry("ETH", "binance", 0.0001, 10.95, mark_price=3000.0, open_interest_usd=1e9),
            FundingRateEntry("ETH", "bybit", 0.00009, 9.855, mark_price=3000.0, open_interest_usd=1e9),
        ]
        arbs = self.source._find_funding_arbs(rates, underlying="ETH")
        assert len(arbs) == 0  # Spread < 5%
