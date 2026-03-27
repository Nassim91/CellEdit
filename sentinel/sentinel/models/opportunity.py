"""Yield opportunity data models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class YieldType(str, Enum):
    """Classification of yield sources."""

    # Lending / Borrowing
    LENDING = "lending"
    VARIABLE_LENDING = "variable_lending"
    FIXED_LENDING = "fixed_lending"

    # Liquidity Provision
    AMM_LP = "amm_lp"
    CONCENTRATED_LP = "concentrated_lp"

    # Staking
    NATIVE_STAKING = "native_staking"
    LIQUID_STAKING = "liquid_staking"
    RESTAKING = "restaking"

    # Structured
    VAULT = "vault"
    YIELD_TOKENIZATION = "yield_tokenization"
    OPTIONS_VAULT = "options_vault"

    # Basis / Funding
    BASIS_TRADE = "basis_trade"
    FUNDING_RATE = "funding_rate"

    # Points / Incentives
    POINTS_FARMING = "points_farming"
    AIRDROP_FARMING = "airdrop_farming"
    LIQUIDITY_MINING = "liquidity_mining"

    # Other
    RWA = "rwa"
    INSURANCE = "insurance"
    OTHER = "other"


class ImpermanentLossRisk(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class YieldOpportunity(BaseModel):
    """A single yield opportunity discovered by Sentinel."""

    # Identity
    id: str = Field(description="Unique identifier: protocol-chain-pool")
    protocol: str
    chain: str
    pool_name: str
    underlying_tokens: list[str]
    url: str | None = None

    # Yield metrics
    yield_type: YieldType
    base_apy: float = Field(description="Base APY without incentives (percent)")
    reward_apy: float = Field(0.0, description="Additional reward/incentive APY (percent)")
    total_apy: float = Field(description="Total APY = base + reward (percent)")
    apy_7d_avg: float | None = Field(None, description="7-day average APY")
    apy_30d_avg: float | None = Field(None, description="30-day average APY")
    apy_history: list[dict[str, Any]] | None = Field(None, description="Historical APY snapshots")

    # Capacity
    tvl_usd: float = Field(description="Total value locked in USD")
    available_capacity_usd: float | None = Field(None, description="Remaining capacity before diminishing returns")
    utilization_rate: float | None = Field(None, description="For lending: current utilization %")

    # Risk
    il_risk: ImpermanentLossRisk = ImpermanentLossRisk.NONE
    smart_contract_risk: float = Field(0.5, ge=0, le=1, description="Smart contract risk score 0-1")
    protocol_risk_score: float = Field(0.5, ge=0, le=1, description="Overall protocol risk 0-1")
    is_audited: bool | None = None
    audit_firms: list[str] = Field(default_factory=list)

    # Market-neutral relevance
    is_delta_neutral: bool = False
    hedging_available: bool = False
    funding_rate: float | None = Field(None, description="Current funding rate for basis trades")

    # Metadata
    source: str = Field(description="Data source: defillama, on-chain, manual")
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    tags: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)

    @property
    def risk_adjusted_apy(self) -> float:
        """Simple risk-adjusted yield: APY * (1 - risk_score)."""
        return self.total_apy * (1 - self.protocol_risk_score)

    def matches_underlying(self, token: str) -> bool:
        """Check if this opportunity involves the given token."""
        normalized = token.upper()
        return any(t.upper() == normalized for t in self.underlying_tokens)

    def fits_size(self, size_usd: float) -> bool:
        """Check if the opportunity can absorb the given allocation size."""
        if self.available_capacity_usd is not None:
            return size_usd <= self.available_capacity_usd
        # Heuristic: don't be more than 5% of TVL
        return size_usd <= self.tvl_usd * 0.05
