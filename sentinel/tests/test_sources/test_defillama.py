"""Tests for DeFiLlama yield source."""

import pytest

from sentinel.sources.defillama import DefiLlamaSource, STABLECOINS
from sentinel.models.opportunity import ImpermanentLossRisk, YieldType


class TestDefiLlamaSource:
    """Test DeFiLlama pool parsing and filtering logic."""

    def setup_method(self) -> None:
        self.source = DefiLlamaSource(min_tvl=100_000)

    def test_parse_lending_pool(self) -> None:
        """Should correctly parse a lending pool."""
        pool = {
            "pool": "aave-v3-usdc-ethereum",
            "chain": "Ethereum",
            "project": "aave-v3",
            "symbol": "USDC",
            "tvlUsd": 2_000_000_000,
            "apy": 4.0,
            "apyBase": 3.5,
            "apyReward": 0.5,
            "category": "Lending",
        }
        opp = self.source._parse_pool(pool, underlying="USDC", chain_set=None)
        assert opp is not None
        assert opp.protocol == "aave-v3"
        assert opp.yield_type == YieldType.LENDING
        assert opp.total_apy == 4.0
        assert opp.base_apy == 3.5

    def test_filter_by_tvl(self) -> None:
        """Should filter out pools below min TVL."""
        pool = {
            "pool": "tiny-pool",
            "chain": "Ethereum",
            "project": "tiny",
            "symbol": "USDC",
            "tvlUsd": 50_000,
            "apy": 10.0,
            "apyBase": 10.0,
        }
        opp = self.source._parse_pool(pool, underlying=None, chain_set=None)
        assert opp is None

    def test_filter_by_underlying(self) -> None:
        """Should filter out pools not matching the underlying."""
        pool = {
            "pool": "eth-pool",
            "chain": "Ethereum",
            "project": "aave",
            "symbol": "ETH",
            "tvlUsd": 1_000_000_000,
            "apy": 3.0,
            "apyBase": 3.0,
        }
        opp = self.source._parse_pool(pool, underlying="USDC", chain_set=None)
        assert opp is None

    def test_filter_by_chain(self) -> None:
        """Should filter out pools not on the target chain."""
        pool = {
            "pool": "bsc-pool",
            "chain": "BSC",
            "project": "venus",
            "symbol": "USDC",
            "tvlUsd": 500_000_000,
            "apy": 5.0,
            "apyBase": 5.0,
        }
        opp = self.source._parse_pool(pool, underlying=None, chain_set={"Ethereum"})
        assert opp is None

    def test_il_risk_assessment_stables(self) -> None:
        """Stablecoin-only pools should have low IL risk."""
        il = self.source._assess_il_risk(["USDC", "USDT"], YieldType.AMM_LP)
        assert il == ImpermanentLossRisk.LOW

    def test_il_risk_assessment_volatile_stable(self) -> None:
        """Volatile/stable pairs should have high IL risk."""
        il = self.source._assess_il_risk(["ETH", "USDC"], YieldType.AMM_LP)
        assert il == ImpermanentLossRisk.HIGH

    def test_il_risk_assessment_correlated(self) -> None:
        """Correlated pairs like ETH/stETH should have low IL risk."""
        il = self.source._assess_il_risk(["ETH", "STETH"], YieldType.AMM_LP)
        assert il == ImpermanentLossRisk.LOW

    def test_il_risk_none_for_lending(self) -> None:
        """Lending pools should have no IL risk."""
        il = self.source._assess_il_risk(["USDC"], YieldType.LENDING)
        assert il == ImpermanentLossRisk.NONE

    def test_wrapped_token_matching(self) -> None:
        """Should match wrapped variants (WETH when searching ETH)."""
        pool = {
            "pool": "weth-pool",
            "chain": "Ethereum",
            "project": "aave",
            "symbol": "WETH",
            "tvlUsd": 1_000_000_000,
            "apy": 2.0,
            "apyBase": 2.0,
        }
        opp = self.source._parse_pool(pool, underlying="ETH", chain_set=None)
        assert opp is not None
