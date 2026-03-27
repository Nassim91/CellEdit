"""Shared test fixtures for Sentinel test suite."""

from __future__ import annotations

from datetime import datetime

import pytest

from sentinel.config.settings import Settings
from sentinel.models.chain import Chain
from sentinel.models.opportunity import ImpermanentLossRisk, YieldOpportunity, YieldType
from sentinel.models.protocol import Protocol, ProtocolCategory, ProtocolRisk
from sentinel.models.sentiment import SentimentDirection, SentimentSignal, SentimentSource


@pytest.fixture
def settings() -> Settings:
    """Default test settings."""
    return Settings()


@pytest.fixture
def sample_lending_opportunity() -> YieldOpportunity:
    """A typical Aave V3 USDC lending opportunity."""
    return YieldOpportunity(
        id="aave-v3-ethereum-usdc",
        protocol="aave-v3",
        chain="Ethereum",
        pool_name="Aave V3 USDC Supply",
        underlying_tokens=["USDC"],
        yield_type=YieldType.VARIABLE_LENDING,
        base_apy=3.5,
        reward_apy=0.5,
        total_apy=4.0,
        tvl_usd=2_000_000_000,
        utilization_rate=85.0,
        il_risk=ImpermanentLossRisk.NONE,
        smart_contract_risk=0.15,
        protocol_risk_score=0.15,
        is_audited=True,
        audit_firms=["Trail of Bits", "OpenZeppelin"],
        source="aave",
        fetched_at=datetime.utcnow(),
        tags=["lending", "blue-chip"],
    )


@pytest.fixture
def sample_basis_trade() -> YieldOpportunity:
    """An Ethena sUSDe basis trade opportunity."""
    return YieldOpportunity(
        id="ethena-susde-staking",
        protocol="ethena",
        chain="Ethereum",
        pool_name="Ethena sUSDe Staking",
        underlying_tokens=["USDe", "sUSDe"],
        yield_type=YieldType.BASIS_TRADE,
        base_apy=4.0,
        reward_apy=11.0,
        total_apy=15.0,
        tvl_usd=5_000_000_000,
        smart_contract_risk=0.3,
        protocol_risk_score=0.35,
        is_audited=True,
        is_delta_neutral=True,
        funding_rate=0.0004,
        source="ethena",
        fetched_at=datetime.utcnow(),
        tags=["basis-trade", "delta-neutral"],
    )


@pytest.fixture
def sample_pendle_pt() -> YieldOpportunity:
    """A Pendle PT fixed yield opportunity."""
    return YieldOpportunity(
        id="pendle-pt-ethereum-steth",
        protocol="pendle",
        chain="Ethereum",
        pool_name="Pendle PT stETH 26DEC2026",
        underlying_tokens=["stETH"],
        yield_type=YieldType.FIXED_LENDING,
        base_apy=5.5,
        reward_apy=0,
        total_apy=5.5,
        tvl_usd=500_000_000,
        smart_contract_risk=0.25,
        protocol_risk_score=0.25,
        is_audited=True,
        source="pendle",
        fetched_at=datetime.utcnow(),
        tags=["fixed-yield", "yield-tokenization", "expiry:26DEC2026"],
    )


@pytest.fixture
def sample_lp_opportunity() -> YieldOpportunity:
    """A volatile/stable AMM LP opportunity."""
    return YieldOpportunity(
        id="uniswap-v3-ethereum-eth-usdc",
        protocol="uniswap-v3",
        chain="Ethereum",
        pool_name="ETH/USDC 0.3%",
        underlying_tokens=["ETH", "USDC"],
        yield_type=YieldType.CONCENTRATED_LP,
        base_apy=25.0,
        reward_apy=0,
        total_apy=25.0,
        tvl_usd=200_000_000,
        il_risk=ImpermanentLossRisk.HIGH,
        smart_contract_risk=0.15,
        protocol_risk_score=0.2,
        is_audited=True,
        source="defillama",
        fetched_at=datetime.utcnow(),
        tags=["concentrated-lp"],
    )


@pytest.fixture
def sample_protocol() -> Protocol:
    """A blue-chip protocol (Aave V3)."""
    return Protocol(
        name="Aave V3",
        slug="aave-v3",
        category=ProtocolCategory.LENDING,
        chains=["Ethereum", "Arbitrum", "Optimism", "Polygon", "Avalanche", "Base"],
        tvl_usd=15_000_000_000,
        risk=ProtocolRisk(
            audit_count=10,
            audit_firms=["Trail of Bits", "OpenZeppelin", "Certora"],
            has_bug_bounty=True,
            bug_bounty_size_usd=10_000_000,
            time_live_days=1200,
            is_upgradeable=True,
            has_timelock=True,
            timelock_delay_hours=24,
            has_governance=True,
        ),
    )


@pytest.fixture
def sample_signal() -> SentimentSignal:
    """A bullish DeFi sentiment signal."""
    return SentimentSignal(
        source=SentimentSource.TWITTER,
        content="Morpho Blue vaults are printing insane yield right now. 8% on USDC with no lock-up. This is the future of DeFi lending.",
        author="DeFiAlpha",
        author_followers=50_000,
        direction=SentimentDirection.NEUTRAL,  # Will be classified by analyzer
        engagement_score=250.0,
        mentioned_protocols=["morpho"],
        mentioned_tokens=["USDC"],
    )


@pytest.fixture
def sample_opportunities(
    sample_lending_opportunity: YieldOpportunity,
    sample_basis_trade: YieldOpportunity,
    sample_pendle_pt: YieldOpportunity,
    sample_lp_opportunity: YieldOpportunity,
) -> list[YieldOpportunity]:
    """Collection of diverse yield opportunities for testing."""
    return [
        sample_lending_opportunity,
        sample_basis_trade,
        sample_pendle_pt,
        sample_lp_opportunity,
    ]
