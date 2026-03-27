"""Report data models for asset manager output."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from sentinel.models.opportunity import YieldOpportunity
from sentinel.models.protocol import RiskLevel


class StrategyRecommendation(BaseModel):
    """A recommended strategy combining one or more yield opportunities."""

    name: str
    description: str
    strategy_type: str  # e.g., "delta_neutral", "basis_trade", "single_sided_lending"

    # Legs of the strategy
    opportunities: list[YieldOpportunity]
    legs_description: list[str] = Field(default_factory=list)

    # Expected returns
    expected_net_apy: float
    expected_apy_range: tuple[float, float] | None = None
    confidence: float = Field(ge=0, le=1, description="Confidence in the estimate 0-1")

    # Size constraints
    min_size_usd: float = 0
    max_size_usd: float | None = None
    recommended_size_usd: float | None = None

    # Risk
    risk_level: RiskLevel = RiskLevel.MEDIUM
    risk_factors: list[str] = Field(default_factory=list)
    max_drawdown_estimate_pct: float | None = None

    # Execution
    chains_involved: list[str] = Field(default_factory=list)
    requires_bridging: bool = False
    estimated_gas_cost_usd: float | None = None
    rebalancing_frequency: str | None = None  # e.g., "daily", "weekly"

    # Market-neutral properties
    is_market_neutral: bool = False
    delta_exposure: float = Field(0.0, description="Net delta exposure: 0 = fully neutral")
    hedge_instrument: str | None = None


class SentinelReport(BaseModel):
    """Complete Sentinel analysis report for asset managers."""

    # Report metadata
    report_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    underlying: str
    target_size_usd: float
    chains_analyzed: list[str]

    # Market context
    market_summary: str | None = None
    underlying_price_usd: float | None = None
    underlying_market_cap_usd: float | None = None

    # All discovered opportunities
    total_opportunities_found: int
    opportunities: list[YieldOpportunity]

    # Filtered and ranked
    top_opportunities: list[YieldOpportunity] = Field(
        default_factory=list,
        description="Top opportunities filtered by size, risk, and yield",
    )

    # Strategy recommendations
    strategies: list[StrategyRecommendation] = Field(default_factory=list)

    # Social sentiment
    sentiment_summary: str | None = None
    trending_protocols: list[str] = Field(default_factory=list)
    sentiment_signals: list[dict[str, Any]] = Field(default_factory=list)

    # Risk overview
    portfolio_risk_summary: str | None = None
    concentration_warnings: list[str] = Field(default_factory=list)

    # Execution notes
    execution_notes: list[str] = Field(default_factory=list)
    estimated_total_gas_usd: float | None = None
