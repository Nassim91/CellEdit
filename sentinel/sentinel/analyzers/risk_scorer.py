"""Risk scoring engine — aggregates risk signals into a unified score."""

from __future__ import annotations

from sentinel.models.opportunity import YieldOpportunity
from sentinel.models.protocol import Protocol, ProtocolRisk, RiskLevel
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)

# Risk weight configuration
WEIGHTS = {
    "smart_contract": 0.30,
    "operational": 0.20,
    "market": 0.20,
    "yield_sustainability": 0.15,
    "liquidity": 0.15,
}


class RiskScorer:
    """Unified risk scoring for yield opportunities.

    Combines protocol-level risk with opportunity-specific risk factors
    to produce a single 0-1 risk score and risk level classification.
    """

    def score_opportunity(
        self,
        opportunity: YieldOpportunity,
        protocol: Protocol | None = None,
    ) -> float:
        """Compute risk score for a yield opportunity.

        Returns:
            Risk score 0 (safest) to 1 (riskiest).
        """
        scores: dict[str, float] = {}

        # 1. Smart contract risk
        if protocol:
            scores["smart_contract"] = protocol.risk.smart_contract_score
        else:
            scores["smart_contract"] = opportunity.smart_contract_risk

        # 2. Operational risk
        if protocol:
            scores["operational"] = protocol.risk.operational_score
        else:
            scores["operational"] = 0.5  # Unknown = medium

        # 3. Market risk (based on TVL and IL)
        scores["market"] = self._market_risk(opportunity)

        # 4. Yield sustainability
        scores["yield_sustainability"] = self._yield_sustainability_risk(opportunity)

        # 5. Liquidity risk
        scores["liquidity"] = self._liquidity_risk(opportunity)

        # Weighted sum
        total = sum(scores[k] * WEIGHTS[k] for k in WEIGHTS)

        logger.debug(
            "risk_scorer.score",
            opportunity=opportunity.id,
            scores=scores,
            total=f"{total:.3f}",
        )

        return max(0.0, min(1.0, total))

    def classify(self, score: float) -> RiskLevel:
        """Classify a risk score into a risk level."""
        if score < 0.15:
            return RiskLevel.MINIMAL
        if score < 0.35:
            return RiskLevel.LOW
        if score < 0.55:
            return RiskLevel.MEDIUM
        if score < 0.75:
            return RiskLevel.HIGH
        return RiskLevel.CRITICAL

    def _market_risk(self, opp: YieldOpportunity) -> float:
        """Assess market risk based on TVL, IL, and token volatility."""
        score = 0.3  # Base

        # TVL-based risk
        if opp.tvl_usd < 1_000_000:
            score += 0.25
        elif opp.tvl_usd < 10_000_000:
            score += 0.15
        elif opp.tvl_usd > 1_000_000_000:
            score -= 0.1

        # IL risk
        il_map = {"none": 0.0, "low": 0.05, "medium": 0.15, "high": 0.25, "very_high": 0.35}
        score += il_map.get(opp.il_risk.value, 0.15)

        return max(0.0, min(1.0, score))

    def _yield_sustainability_risk(self, opp: YieldOpportunity) -> float:
        """Assess risk of yield being unsustainable (too-good-to-be-true)."""
        score = 0.2  # Base

        # Extremely high APY is suspicious
        if opp.total_apy > 100:
            score += 0.4
        elif opp.total_apy > 50:
            score += 0.25
        elif opp.total_apy > 20:
            score += 0.1

        # High reward APY relative to base = mostly incentive-driven
        if opp.base_apy > 0 and opp.reward_apy > opp.base_apy * 3:
            score += 0.15

        # Points/airdrop farming is inherently speculative
        if "points" in opp.tags or "airdrop" in opp.tags:
            score += 0.1

        # Historical stability (if we have 7d vs 30d data)
        if opp.apy_7d_avg and opp.apy_30d_avg:
            volatility = abs(opp.apy_7d_avg - opp.apy_30d_avg) / max(opp.apy_30d_avg, 0.01)
            if volatility > 0.5:
                score += 0.15

        return max(0.0, min(1.0, score))

    def _liquidity_risk(self, opp: YieldOpportunity) -> float:
        """Assess liquidity/exit risk."""
        score = 0.2  # Base

        # Low TVL = harder to exit large positions
        if opp.tvl_usd < 500_000:
            score += 0.3
        elif opp.tvl_usd < 5_000_000:
            score += 0.15

        # Capacity constraints
        if opp.available_capacity_usd is not None and opp.available_capacity_usd < 100_000:
            score += 0.2

        # High utilization in lending = potential withdrawal issues
        if opp.utilization_rate and opp.utilization_rate > 90:
            score += 0.2

        return max(0.0, min(1.0, score))
