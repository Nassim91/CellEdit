"""Pendle PT arbitrage strategy evaluator.

Principal Tokens (PTs) represent the principal portion of a yield-bearing asset
at maturity. They trade at a discount to their underlying, and that discount
represents a guaranteed fixed yield if held to maturity.

Strategy:
1. Buy PT at a discount → guaranteed fixed yield at maturity
2. Compare PT implied yield vs. risk-free alternatives (DSR, T-bills)
3. Surface opportunities where PT yield significantly exceeds alternatives

Risk factors:
- Underlying protocol risk (e.g., stETH depeg)
- Pendle smart contract risk
- Opportunity cost (locked until maturity)
- Early exit may result in losses if PT price drops
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sentinel.models.opportunity import YieldOpportunity, YieldType
from sentinel.models.protocol import RiskLevel
from sentinel.models.report import StrategyRecommendation
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)

# Risk-free rate benchmarks
RISK_FREE_RATES = {
    "us_tbill_3m": 4.5,     # Approximate 3-month T-bill rate
    "maker_dsr": 5.0,       # Maker DSR (on-chain risk-free)
    "aave_usdc": 3.5,       # Aave USDC supply (conservative DeFi benchmark)
}


class PTArbitrageEvaluator:
    """Evaluates Pendle PT fixed yield opportunities against risk-free benchmarks.

    Key metrics:
    - Implied Fixed Yield: The annualized yield guaranteed by buying PT at discount
    - Spread vs Risk-Free: PT yield minus best risk-free alternative
    - Days to Maturity: Time until PT becomes redeemable at par
    - Breakeven Price: Maximum PT price at which the trade is still profitable
    """

    def __init__(
        self,
        risk_free_rate: float | None = None,
        min_spread_bps: int = 100,  # Minimum 1% spread over risk-free to recommend
    ) -> None:
        self.risk_free_rate = risk_free_rate or RISK_FREE_RATES["maker_dsr"]
        self.min_spread_bps = min_spread_bps

    def evaluate(
        self,
        opportunities: list[YieldOpportunity],
        underlying: str,
        size_usd: float,
    ) -> list[StrategyRecommendation]:
        """Find and evaluate PT arbitrage opportunities."""
        logger.info("pt_arb.evaluate", underlying=underlying, size_usd=size_usd)

        # Filter for Pendle PT opportunities
        pt_opps = [
            o for o in opportunities
            if o.yield_type == YieldType.FIXED_LENDING
            and o.protocol == "pendle"
            and "PT" in o.pool_name
            and o.fits_size(size_usd)
        ]

        if not pt_opps:
            return []

        recommendations: list[StrategyRecommendation] = []

        for pt in pt_opps:
            recommendation = self._evaluate_single_pt(pt, underlying, size_usd)
            if recommendation:
                recommendations.append(recommendation)

        # Sort by spread over risk-free
        recommendations.sort(key=lambda r: r.expected_net_apy, reverse=True)

        logger.info("pt_arb.complete", recommendations=len(recommendations))
        return recommendations

    def _evaluate_single_pt(
        self,
        pt: YieldOpportunity,
        underlying: str,
        size_usd: float,
    ) -> StrategyRecommendation | None:
        """Evaluate a single PT opportunity."""
        implied_yield = pt.total_apy
        spread = implied_yield - self.risk_free_rate

        # Only recommend if spread exceeds minimum threshold
        if spread * 100 < self.min_spread_bps:
            return None

        # Extract maturity from tags
        expiry = "unknown"
        for tag in pt.tags:
            if tag.startswith("expiry:"):
                expiry = tag.split("expiry:")[1]
                break

        # Calculate days to maturity
        days_to_maturity = self._estimate_days_to_maturity(expiry)

        # Risk assessment
        risk_level = self._assess_pt_risk(pt, days_to_maturity, spread)

        # Calculate scenario analysis
        base_case_apy = implied_yield
        bull_case_apy = implied_yield  # Fixed yield doesn't change
        bear_case_apy = implied_yield * 0.9  # Slight slippage on early exit

        # Build recommendation
        risk_factors = [
            f"Fixed until maturity ({expiry}) — early exit may reduce yield",
            f"Underlying protocol risk ({pt.pool_name})",
            "Pendle smart contract risk",
        ]

        if days_to_maturity and days_to_maturity > 180:
            risk_factors.append(f"Long lock-up period ({days_to_maturity} days)")

        if spread > 10:
            risk_factors.append("Very high spread — verify underlying asset health")

        return StrategyRecommendation(
            name=f"PT Fixed Yield: {pt.pool_name}",
            description=(
                f"Buy Pendle PT for {pt.pool_name} on {pt.chain}. "
                f"Lock in {implied_yield:.2f}% fixed yield (annualized) until {expiry}. "
                f"Spread of {spread:.2f}% over risk-free rate ({self.risk_free_rate:.1f}%). "
                f"Yield is guaranteed if held to maturity — no variable rate risk."
            ),
            strategy_type="pt_arbitrage",
            opportunities=[pt],
            legs_description=[
                f"Buy PT {pt.pool_name} at current discount",
                f"Hold until maturity ({expiry})",
                f"Redeem at par → realize {implied_yield:.2f}% fixed yield",
            ],
            expected_net_apy=base_case_apy,
            expected_apy_range=(bear_case_apy, bull_case_apy),
            confidence=0.95 if days_to_maturity and days_to_maturity < 180 else 0.85,
            min_size_usd=100,
            max_size_usd=pt.tvl_usd * 0.05,
            recommended_size_usd=min(size_usd, pt.tvl_usd * 0.02),
            risk_level=risk_level,
            risk_factors=risk_factors,
            chains_involved=[pt.chain],
            requires_bridging=pt.chain.lower() != "ethereum",
            is_market_neutral=False,
            delta_exposure=1.0 if underlying.upper() not in ("USDC", "USDT", "DAI") else 0.0,
            extra={
                "implied_yield": implied_yield,
                "risk_free_rate": self.risk_free_rate,
                "spread_bps": spread * 100,
                "days_to_maturity": days_to_maturity,
                "expiry": expiry,
                "analysis": {
                    "base_case": f"{base_case_apy:.2f}% (hold to maturity)",
                    "risk_free_comparison": f"+{spread:.2f}% vs DSR/T-bills",
                    "guarantee": "Fixed yield guaranteed at maturity",
                },
            },
        )

    def _estimate_days_to_maturity(self, expiry: str) -> int | None:
        """Estimate days to maturity from expiry string."""
        if expiry == "unknown":
            return None

        # Try parsing common formats
        for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d %b %Y", "%B %d, %Y"]:
            try:
                expiry_date = datetime.strptime(expiry, fmt)
                return max(0, (expiry_date - datetime.utcnow()).days)
            except ValueError:
                continue

        # Try extracting from descriptive format like "26DEC2025"
        try:
            expiry_date = datetime.strptime(expiry, "%d%b%Y")
            return max(0, (expiry_date - datetime.utcnow()).days)
        except ValueError:
            pass

        return None

    def _assess_pt_risk(
        self,
        pt: YieldOpportunity,
        days_to_maturity: int | None,
        spread: float,
    ) -> RiskLevel:
        """Assess risk level for a PT position."""
        # PTs are inherently low-risk (fixed yield at maturity)
        if days_to_maturity and days_to_maturity < 90:
            base_risk = RiskLevel.LOW
        elif days_to_maturity and days_to_maturity < 180:
            base_risk = RiskLevel.LOW
        elif days_to_maturity and days_to_maturity < 365:
            base_risk = RiskLevel.MEDIUM
        else:
            base_risk = RiskLevel.MEDIUM

        # Very high spreads may indicate hidden risk
        if spread > 15:
            return RiskLevel.HIGH

        return base_risk
