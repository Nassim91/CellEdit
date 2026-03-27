"""DeFi protocol models and risk assessment."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProtocolCategory(str, Enum):
    LENDING = "lending"
    DEX = "dex"
    YIELD = "yield"
    LIQUID_STAKING = "liquid_staking"
    RESTAKING = "restaking"
    BRIDGE = "bridge"
    DERIVATIVES = "derivatives"
    OPTIONS = "options"
    YIELD_TOKENIZATION = "yield_tokenization"
    RWA = "rwa"
    CDP = "cdp"
    INSURANCE = "insurance"
    OTHER = "other"


class ProtocolRisk(BaseModel):
    """Risk assessment for a DeFi protocol."""

    # Smart contract risk
    audit_count: int = 0
    audit_firms: list[str] = Field(default_factory=list)
    has_bug_bounty: bool = False
    bug_bounty_size_usd: float | None = None
    is_open_source: bool = True
    time_live_days: int = 0

    # Operational risk
    is_upgradeable: bool = True
    has_timelock: bool = False
    timelock_delay_hours: float | None = None
    multisig_threshold: str | None = None  # e.g., "3/5"
    has_governance: bool = False
    is_centralized: bool = False

    # Market risk
    tvl_usd: float = 0.0
    tvl_change_7d_pct: float | None = None
    tvl_change_30d_pct: float | None = None
    liquidity_depth_usd: float | None = None

    # Historical incidents
    exploit_history: list[dict[str, Any]] = Field(default_factory=list)
    total_exploit_losses_usd: float = 0.0

    @property
    def smart_contract_score(self) -> float:
        """Score 0-1 where 0=safest, 1=riskiest."""
        score = 0.5
        if self.audit_count >= 3:
            score -= 0.2
        elif self.audit_count >= 1:
            score -= 0.1
        if self.has_bug_bounty:
            score -= 0.1
        if self.time_live_days > 365:
            score -= 0.1
        elif self.time_live_days < 90:
            score += 0.15
        if self.total_exploit_losses_usd > 0:
            score += 0.2
        return max(0.0, min(1.0, score))

    @property
    def operational_score(self) -> float:
        """Score 0-1 where 0=safest, 1=riskiest."""
        score = 0.5
        if self.has_timelock:
            score -= 0.15
        if self.has_governance:
            score -= 0.1
        if self.is_centralized:
            score += 0.2
        if not self.is_upgradeable:
            score -= 0.15  # Immutable = safer
        return max(0.0, min(1.0, score))

    @property
    def overall_risk_score(self) -> float:
        return 0.6 * self.smart_contract_score + 0.4 * self.operational_score

    @property
    def risk_level(self) -> RiskLevel:
        s = self.overall_risk_score
        if s < 0.15:
            return RiskLevel.MINIMAL
        if s < 0.35:
            return RiskLevel.LOW
        if s < 0.55:
            return RiskLevel.MEDIUM
        if s < 0.75:
            return RiskLevel.HIGH
        return RiskLevel.CRITICAL


class Protocol(BaseModel):
    """A DeFi protocol tracked by Sentinel."""

    name: str
    slug: str
    category: ProtocolCategory
    chains: list[str] = Field(default_factory=list)
    url: str | None = None
    logo_url: str | None = None
    twitter_handle: str | None = None

    # Metrics
    tvl_usd: float = 0.0
    tvl_change_7d_pct: float | None = None
    tvl_change_30d_pct: float | None = None
    market_cap_usd: float | None = None
    fdv_usd: float | None = None

    # Risk
    risk: ProtocolRisk = Field(default_factory=ProtocolRisk)

    # DeFiLlama metadata
    defillama_id: str | None = None
    gecko_id: str | None = None

    # Timestamps
    launched_at: datetime | None = None
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    @property
    def age_days(self) -> int | None:
        if self.launched_at is None:
            return None
        return (datetime.utcnow() - self.launched_at).days
