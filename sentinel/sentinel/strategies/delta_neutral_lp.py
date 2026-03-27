"""Delta-neutral LP strategy — hedged AMM liquidity provision.

Strategy:
1. Provide liquidity in an AMM pool (earn swap fees + rewards)
2. Short the volatile asset via perpetual futures (neutralize price exposure)
3. Net yield = LP yield - hedging cost (funding rate)

This works best when:
- LP yield > funding rate cost
- The pool has high volume relative to TVL (good fee generation)
- Funding rates are low or negative (cheap to hedge)
"""

from __future__ import annotations

from sentinel.models.opportunity import YieldOpportunity, YieldType
from sentinel.models.protocol import RiskLevel
from sentinel.models.report import StrategyRecommendation
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)


class DeltaNeutralLPEvaluator:
    """Evaluates delta-neutral LP strategies by pairing AMM positions with perp hedges."""

    def __init__(self, default_funding_cost: float = 8.0) -> None:
        """
        Args:
            default_funding_cost: Default annualized funding rate cost in % for hedging.
                                  Used when live funding rate data is not available.
        """
        self.default_funding_cost = default_funding_cost

    def evaluate(
        self,
        opportunities: list[YieldOpportunity],
        underlying: str,
        size_usd: float,
        funding_rates: dict[str, float] | None = None,
    ) -> list[StrategyRecommendation]:
        """Find LP opportunities that are profitable after delta hedging.

        Args:
            opportunities: All discovered yield opportunities.
            underlying: Target token (e.g., "ETH").
            size_usd: Target allocation size.
            funding_rates: Optional dict of {symbol: annualized_funding_rate_%}.
        """
        logger.info("delta_neutral_lp.evaluate", underlying=underlying)

        # Find LP opportunities with volatile/stable pairs
        lp_opps = [
            o for o in opportunities
            if o.yield_type in (YieldType.AMM_LP, YieldType.CONCENTRATED_LP)
            and o.matches_underlying(underlying)
            and o.total_apy > 0
            and o.fits_size(size_usd)
        ]

        if not lp_opps:
            return []

        recommendations: list[StrategyRecommendation] = []

        for lp in lp_opps:
            # Determine the volatile token to hedge
            volatile_token = self._find_volatile_token(lp)
            if not volatile_token:
                continue  # Can't hedge — all tokens are stable or can't identify

            # Get funding rate for hedging
            funding_cost = self.default_funding_cost
            if funding_rates and volatile_token in funding_rates:
                funding_cost = funding_rates[volatile_token]

            # Calculate net yield after hedging
            # For a 50/50 pool, you hedge ~50% of the position
            hedge_ratio = 0.5
            hedge_cost = funding_cost * hedge_ratio  # Cost to hedge half the position
            il_adjustment = self._estimate_il_drag(lp)

            net_apy = lp.total_apy - hedge_cost - il_adjustment

            if net_apy < 1.0:
                continue  # Not worth the complexity

            recommendation = StrategyRecommendation(
                name=f"Delta-Neutral LP: {lp.pool_name}",
                description=(
                    f"Provide liquidity in {lp.pool_name} on {lp.chain} ({lp.total_apy:.1f}% APY) "
                    f"while shorting {volatile_token} perps to neutralize price exposure. "
                    f"Net yield after hedging: {net_apy:.1f}% APY."
                ),
                strategy_type="delta_neutral_lp",
                opportunities=[lp],
                legs_description=[
                    f"Deposit to {lp.pool_name} ({lp.chain}) — {lp.total_apy:.1f}% APY",
                    f"Short {volatile_token} perp ({hedge_ratio:.0%} notional) — cost ~{hedge_cost:.1f}%",
                    f"Net delta-neutral yield: ~{net_apy:.1f}% APY",
                ],
                expected_net_apy=net_apy,
                expected_apy_range=(net_apy * 0.5, net_apy * 1.5),
                confidence=0.55,
                max_size_usd=lp.tvl_usd * 0.02,
                risk_level=RiskLevel.MEDIUM,
                risk_factors=[
                    "Impermanent loss if hedge ratio drifts",
                    "Funding rate variability (cost of hedge may increase)",
                    "Rebalancing costs and slippage",
                    "Smart contract risk (LP protocol + perp venue)",
                    "Liquidation risk on perp short if undercollateralized",
                ],
                chains_involved=[lp.chain],
                rebalancing_frequency="daily",
                is_market_neutral=True,
                delta_exposure=0.0,
                hedge_instrument=f"{volatile_token} perpetual futures",
                extra={
                    "lp_apy": lp.total_apy,
                    "hedge_cost": hedge_cost,
                    "il_drag": il_adjustment,
                    "volatile_token": volatile_token,
                    "hedge_ratio": hedge_ratio,
                },
            )
            recommendations.append(recommendation)

        recommendations.sort(key=lambda r: r.expected_net_apy, reverse=True)
        logger.info("delta_neutral_lp.complete", count=len(recommendations))
        return recommendations

    def _find_volatile_token(self, lp: YieldOpportunity) -> str | None:
        """Identify the volatile token in an LP pair that needs hedging."""
        stables = {"USDC", "USDT", "DAI", "FRAX", "LUSD", "GHO", "PYUSD", "USDE", "CRVUSD"}
        volatile_tokens = [t for t in lp.underlying_tokens if t.upper() not in stables]

        if len(volatile_tokens) == 1:
            return volatile_tokens[0]
        if len(volatile_tokens) > 1:
            return volatile_tokens[0]  # Hedge the first volatile token
        return None  # All stables — no hedge needed

    def _estimate_il_drag(self, lp: YieldOpportunity) -> float:
        """Estimate annualized impermanent loss drag."""
        il_map = {
            "none": 0.0,
            "low": 0.5,
            "medium": 2.0,
            "high": 5.0,
            "very_high": 10.0,
        }
        return il_map.get(lp.il_risk.value, 2.0)
