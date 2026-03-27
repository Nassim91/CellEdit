"""Tests for YieldOpportunity model."""

from sentinel.models.opportunity import ImpermanentLossRisk, YieldOpportunity, YieldType


def test_risk_adjusted_apy(sample_lending_opportunity: YieldOpportunity) -> None:
    """Risk-adjusted APY should discount by risk score."""
    opp = sample_lending_opportunity
    expected = opp.total_apy * (1 - opp.protocol_risk_score)
    assert opp.risk_adjusted_apy == expected


def test_matches_underlying(sample_lending_opportunity: YieldOpportunity) -> None:
    """Should match underlying token case-insensitively."""
    assert sample_lending_opportunity.matches_underlying("USDC")
    assert sample_lending_opportunity.matches_underlying("usdc")
    assert not sample_lending_opportunity.matches_underlying("ETH")


def test_fits_size_within_tvl(sample_lending_opportunity: YieldOpportunity) -> None:
    """Should accept sizes within 5% of TVL."""
    # 5% of 2B = 100M
    assert sample_lending_opportunity.fits_size(50_000_000)
    assert sample_lending_opportunity.fits_size(100_000_000)
    assert not sample_lending_opportunity.fits_size(200_000_000)


def test_fits_size_with_capacity() -> None:
    """Should use available_capacity_usd when set."""
    opp = YieldOpportunity(
        id="test",
        protocol="test",
        chain="Ethereum",
        pool_name="Test",
        underlying_tokens=["USDC"],
        yield_type=YieldType.LENDING,
        base_apy=5.0,
        total_apy=5.0,
        tvl_usd=1_000_000_000,
        available_capacity_usd=1_000_000,
        source="test",
    )
    assert opp.fits_size(500_000)
    assert opp.fits_size(1_000_000)
    assert not opp.fits_size(2_000_000)


def test_yield_types_cover_all_categories() -> None:
    """Ensure we have yield types for all major DeFi categories."""
    assert YieldType.LENDING
    assert YieldType.AMM_LP
    assert YieldType.LIQUID_STAKING
    assert YieldType.RESTAKING
    assert YieldType.BASIS_TRADE
    assert YieldType.YIELD_TOKENIZATION
    assert YieldType.VAULT
    assert YieldType.FUNDING_RATE
