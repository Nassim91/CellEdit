"""Market-neutral strategy engine — constructs and evaluates strategies for asset managers."""

from __future__ import annotations

from sentinel.models.opportunity import YieldOpportunity, YieldType
from sentinel.models.protocol import RiskLevel
from sentinel.models.report import StrategyRecommendation
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)


class StrategyEngine:
    """Constructs market-neutral and risk-managed strategies from yield opportunities.

    Strategy types:
    1. Single-sided lending — lowest risk, deposit into lending protocol
    2. Stable-stable LP — provide liquidity in stablecoin pairs
    3. Delta-neutral LP — LP + perp hedge
    4. Basis trade — spot long + perp short, earning funding rate
    5. Yield tokenization — buy PT for fixed yield or YT for leveraged yield
    6. Restaking stack — ETH staking + restaking + LRT
    7. Cross-chain arbitrage — same asset, different yields across chains
    """

    def generate_strategies(
        self,
        opportunities: list[YieldOpportunity],
        underlying: str,
        size_usd: float,
    ) -> list[StrategyRecommendation]:
        """Generate strategy recommendations from discovered opportunities."""
        logger.info(
            "strategy_engine.generate",
            underlying=underlying,
            size_usd=size_usd,
            opportunities=len(opportunities),
        )

        strategies: list[StrategyRecommendation] = []

        # 1. Best single-sided lending
        lending_strategy = self._best_lending(opportunities, underlying, size_usd)
        if lending_strategy:
            strategies.append(lending_strategy)

        # 2. Stablecoin LP (if underlying is a stablecoin)
        if underlying.upper() in ("USDC", "USDT", "DAI", "USDE", "FRAX", "LUSD", "GHO", "PYUSD"):
            stable_lp = self._stable_lp_strategy(opportunities, underlying, size_usd)
            if stable_lp:
                strategies.append(stable_lp)

        # 3. Delta-neutral basis trade
        basis_strategy = self._basis_trade_strategy(opportunities, underlying, size_usd)
        if basis_strategy:
            strategies.append(basis_strategy)

        # 4. Fixed yield via Pendle PT
        fixed_yield = self._fixed_yield_strategy(opportunities, underlying, size_usd)
        if fixed_yield:
            strategies.append(fixed_yield)

        # 5. Restaking stack (ETH only)
        if underlying.upper() in ("ETH", "WETH"):
            restaking = self._restaking_strategy(opportunities, underlying, size_usd)
            if restaking:
                strategies.append(restaking)

        # 6. Cross-chain yield spread
        cross_chain = self._cross_chain_strategy(opportunities, underlying, size_usd)
        if cross_chain:
            strategies.append(cross_chain)

        # 7. Diversified portfolio strategy
        diversified = self._diversified_strategy(opportunities, underlying, size_usd)
        if diversified:
            strategies.append(diversified)

        # Sort by risk-adjusted expected return
        strategies.sort(
            key=lambda s: s.expected_net_apy * (1 - (0.2 if s.risk_level == RiskLevel.HIGH else 0)),
            reverse=True,
        )

        logger.info("strategy_engine.complete", strategies=len(strategies))
        return strategies

    def _best_lending(
        self, opps: list[YieldOpportunity], underlying: str, size_usd: float
    ) -> StrategyRecommendation | None:
        """Find the best single-sided lending opportunity."""
        lending_opps = [
            o for o in opps
            if o.yield_type in (YieldType.LENDING, YieldType.VARIABLE_LENDING, YieldType.FIXED_LENDING, YieldType.VAULT)
            and o.matches_underlying(underlying)
            and o.fits_size(size_usd)
        ]

        if not lending_opps:
            return None

        # Sort by risk-adjusted APY
        lending_opps.sort(key=lambda o: o.risk_adjusted_apy, reverse=True)
        best = lending_opps[0]

        return StrategyRecommendation(
            name=f"Single-Sided Lending: {best.protocol} on {best.chain}",
            description=(
                f"Supply {underlying} to {best.protocol} on {best.chain}. "
                f"Earn {best.total_apy:.2f}% APY with minimal complexity. "
                "No impermanent loss exposure."
            ),
            strategy_type="single_sided_lending",
            opportunities=[best],
            legs_description=[f"Supply {underlying} → {best.protocol} ({best.chain})"],
            expected_net_apy=best.total_apy,
            expected_apy_range=(best.total_apy * 0.7, best.total_apy * 1.3),
            confidence=0.85,
            max_size_usd=best.tvl_usd * 0.05,
            risk_level=RiskLevel.LOW if best.protocol_risk_score < 0.3 else RiskLevel.MEDIUM,
            risk_factors=["Variable rate — APY may decrease", "Smart contract risk"],
            chains_involved=[best.chain],
            requires_bridging=best.chain.lower() != "ethereum",
            rebalancing_frequency="weekly",
            is_market_neutral=False,
            delta_exposure=1.0 if underlying.upper() not in ("USDC", "USDT", "DAI") else 0.0,
        )

    def _stable_lp_strategy(
        self, opps: list[YieldOpportunity], underlying: str, size_usd: float
    ) -> StrategyRecommendation | None:
        """Find best stablecoin LP opportunity."""
        stable_lps = [
            o for o in opps
            if o.yield_type in (YieldType.AMM_LP, YieldType.CONCENTRATED_LP)
            and "stablecoin" in o.tags
            and o.fits_size(size_usd)
        ]

        if not stable_lps:
            return None

        stable_lps.sort(key=lambda o: o.risk_adjusted_apy, reverse=True)
        best = stable_lps[0]

        return StrategyRecommendation(
            name=f"Stable LP: {best.pool_name} on {best.chain}",
            description=(
                f"Provide liquidity to {best.pool_name} on {best.chain}. "
                f"Low IL risk due to stablecoin-only composition. {best.total_apy:.2f}% APY."
            ),
            strategy_type="stable_lp",
            opportunities=[best],
            legs_description=[f"LP {best.pool_name} on {best.chain}"],
            expected_net_apy=best.total_apy,
            confidence=0.75,
            max_size_usd=best.tvl_usd * 0.03,
            risk_level=RiskLevel.LOW,
            risk_factors=["Depeg risk", "Smart contract risk", "Low IL but not zero"],
            chains_involved=[best.chain],
            is_market_neutral=True,
            delta_exposure=0.0,
        )

    def _basis_trade_strategy(
        self, opps: list[YieldOpportunity], underlying: str, size_usd: float
    ) -> StrategyRecommendation | None:
        """Construct a basis trade strategy (spot + short perp)."""
        basis_opps = [
            o for o in opps
            if o.yield_type == YieldType.BASIS_TRADE or o.is_delta_neutral
        ]

        if not basis_opps:
            return None

        basis_opps.sort(key=lambda o: o.total_apy, reverse=True)
        best = basis_opps[0]

        return StrategyRecommendation(
            name=f"Basis Trade: {best.protocol}",
            description=(
                f"Delta-neutral basis trade via {best.protocol}. "
                f"Earn {best.total_apy:.2f}% from funding rate spread. "
                "Market-neutral exposure with counterparty risk."
            ),
            strategy_type="basis_trade",
            opportunities=[best],
            legs_description=[
                f"Deposit collateral → {best.protocol}",
                "Protocol manages spot long + perp short hedge",
            ],
            expected_net_apy=best.total_apy,
            expected_apy_range=(best.total_apy * 0.3, best.total_apy * 2.0),
            confidence=0.6,
            max_size_usd=best.tvl_usd * 0.02,
            risk_level=RiskLevel.MEDIUM,
            risk_factors=[
                "Negative funding rate periods",
                "Counterparty/exchange risk",
                "Smart contract risk",
                "Potential depeg in underlying stablecoin",
            ],
            chains_involved=[best.chain],
            is_market_neutral=True,
            delta_exposure=0.0,
            hedge_instrument="perpetual futures",
        )

    def _fixed_yield_strategy(
        self, opps: list[YieldOpportunity], underlying: str, size_usd: float
    ) -> StrategyRecommendation | None:
        """Find best fixed yield via Pendle PT."""
        pt_opps = [
            o for o in opps
            if o.yield_type == YieldType.FIXED_LENDING
            and o.protocol == "pendle"
            and o.fits_size(size_usd)
        ]

        if not pt_opps:
            return None

        pt_opps.sort(key=lambda o: o.total_apy, reverse=True)
        best = pt_opps[0]

        expiry = next((t.split("expiry:")[1] for t in best.tags if t.startswith("expiry:")), "unknown")

        return StrategyRecommendation(
            name=f"Fixed Yield: Pendle PT on {best.chain}",
            description=(
                f"Buy Pendle PT for {best.pool_name} on {best.chain}. "
                f"Lock in {best.total_apy:.2f}% fixed yield until {expiry}. "
                "No variable rate risk — yield is guaranteed if held to maturity."
            ),
            strategy_type="fixed_yield",
            opportunities=[best],
            legs_description=[f"Buy PT → {best.pool_name} (expires {expiry})"],
            expected_net_apy=best.total_apy,
            confidence=0.95,
            max_size_usd=best.tvl_usd * 0.05,
            risk_level=RiskLevel.LOW,
            risk_factors=["Locked until expiry", "Smart contract risk", "Underlying protocol risk"],
            chains_involved=[best.chain],
            is_market_neutral=False,
            delta_exposure=1.0 if underlying.upper() not in ("USDC", "USDT", "DAI") else 0.0,
        )

    def _restaking_strategy(
        self, opps: list[YieldOpportunity], underlying: str, size_usd: float
    ) -> StrategyRecommendation | None:
        """Build ETH restaking stack strategy."""
        restaking_opps = [o for o in opps if o.yield_type == YieldType.RESTAKING]

        if not restaking_opps:
            return None

        # Pick best LRT + native combo
        restaking_opps.sort(key=lambda o: o.total_apy, reverse=True)
        best = restaking_opps[0]

        return StrategyRecommendation(
            name=f"ETH Restaking Stack: {best.protocol}",
            description=(
                f"ETH → Liquid Staking → {best.protocol} Restaking. "
                f"Earn {best.total_apy:.2f}% stacking yields from "
                "PoS validation + AVS services + points/incentives."
            ),
            strategy_type="restaking_stack",
            opportunities=[best],
            legs_description=[
                "ETH → stETH/cbETH (liquid staking ~3.5% APY)",
                f"stETH → {best.protocol} (restaking + {best.reward_apy:.1f}% bonus)",
            ],
            expected_net_apy=best.total_apy,
            expected_apy_range=(3.0, best.total_apy * 1.5),
            confidence=0.5,
            max_size_usd=best.tvl_usd * 0.01,
            risk_level=RiskLevel.MEDIUM,
            risk_factors=[
                "Slashing risk (validator + AVS)",
                "Smart contract risk (multiple layers)",
                "Points may not convert to meaningful rewards",
                "Withdrawal queues / liquidity risk",
            ],
            chains_involved=["Ethereum"],
            is_market_neutral=False,
            delta_exposure=1.0,
        )

    def _cross_chain_strategy(
        self, opps: list[YieldOpportunity], underlying: str, size_usd: float
    ) -> StrategyRecommendation | None:
        """Identify cross-chain yield spread opportunities."""
        # Group lending opportunities by chain
        lending_by_chain: dict[str, list[YieldOpportunity]] = {}
        for o in opps:
            if o.yield_type in (YieldType.LENDING, YieldType.VARIABLE_LENDING) and o.matches_underlying(underlying):
                lending_by_chain.setdefault(o.chain, []).append(o)

        if len(lending_by_chain) < 2:
            return None

        # Find best rate per chain
        best_per_chain: list[tuple[str, YieldOpportunity]] = []
        for chain, chain_opps in lending_by_chain.items():
            chain_opps.sort(key=lambda o: o.total_apy, reverse=True)
            best_per_chain.append((chain, chain_opps[0]))

        best_per_chain.sort(key=lambda x: x[1].total_apy, reverse=True)

        if len(best_per_chain) < 2:
            return None

        top = best_per_chain[0][1]
        second = best_per_chain[1][1]
        spread = top.total_apy - second.total_apy

        if spread < 0.5:
            return None

        return StrategyRecommendation(
            name=f"Cross-Chain Yield: {top.chain} vs {second.chain}",
            description=(
                f"Deploy to {top.protocol} on {top.chain} ({top.total_apy:.2f}%) "
                f"instead of {second.protocol} on {second.chain} ({second.total_apy:.2f}%). "
                f"Yield spread: {spread:.2f}%. Rebalance when spread inverts."
            ),
            strategy_type="cross_chain_yield",
            opportunities=[top, second],
            legs_description=[
                f"Primary: {underlying} → {top.protocol} ({top.chain}) at {top.total_apy:.2f}%",
                f"Monitor: {second.protocol} ({second.chain}) at {second.total_apy:.2f}%",
            ],
            expected_net_apy=top.total_apy,
            confidence=0.7,
            max_size_usd=min(top.tvl_usd, second.tvl_usd) * 0.03,
            risk_level=RiskLevel.MEDIUM,
            risk_factors=["Bridge risk", "Gas costs for rebalancing", "Rate convergence"],
            chains_involved=[top.chain, second.chain],
            requires_bridging=True,
            rebalancing_frequency="weekly",
            is_market_neutral=False,
            delta_exposure=1.0 if underlying.upper() not in ("USDC", "USDT", "DAI") else 0.0,
        )

    def _diversified_strategy(
        self, opps: list[YieldOpportunity], underlying: str, size_usd: float
    ) -> StrategyRecommendation | None:
        """Build a diversified portfolio across multiple protocols and chains."""
        eligible = [
            o for o in opps
            if o.matches_underlying(underlying)
            and o.fits_size(size_usd * 0.2)  # Each position = 20% max
            and o.protocol_risk_score < 0.5
        ]

        if len(eligible) < 3:
            return None

        # Pick top 5 by risk-adjusted APY, ensuring protocol diversity
        selected: list[YieldOpportunity] = []
        seen_protocols: set[str] = set()
        for o in sorted(eligible, key=lambda x: x.risk_adjusted_apy, reverse=True):
            if o.protocol not in seen_protocols:
                selected.append(o)
                seen_protocols.add(o.protocol)
            if len(selected) >= 5:
                break

        if len(selected) < 3:
            return None

        avg_apy = sum(o.total_apy for o in selected) / len(selected)
        chains = list({o.chain for o in selected})

        return StrategyRecommendation(
            name="Diversified Yield Portfolio",
            description=(
                f"Spread {underlying} across {len(selected)} protocols on {len(chains)} chains. "
                f"Average APY: {avg_apy:.2f}%. Diversification reduces single-protocol risk."
            ),
            strategy_type="diversified_portfolio",
            opportunities=selected,
            legs_description=[
                f"{o.protocol} ({o.chain}): {o.total_apy:.2f}% — ~{100/len(selected):.0f}% allocation"
                for o in selected
            ],
            expected_net_apy=avg_apy,
            expected_apy_range=(avg_apy * 0.6, avg_apy * 1.2),
            confidence=0.75,
            max_size_usd=size_usd,
            recommended_size_usd=size_usd,
            risk_level=RiskLevel.LOW,
            risk_factors=[
                "Multiple smart contract risks (diversified)",
                "Bridge risks for cross-chain positions",
                "Rebalancing gas costs",
            ],
            chains_involved=chains,
            requires_bridging=len(chains) > 1,
            rebalancing_frequency="bi-weekly",
            is_market_neutral=False,
            delta_exposure=1.0 if underlying.upper() not in ("USDC", "USDT", "DAI") else 0.0,
        )
