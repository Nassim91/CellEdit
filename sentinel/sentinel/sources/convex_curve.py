"""Convex/Curve yield source — CRV and CVX boosted vaults.

Convex Finance wraps Curve LP positions to maximize CRV rewards,
providing some of the deepest liquidity yields in DeFi for stablecoins.

Data sources:
- Convex API for vault yields and TVL
- Curve API for pool APYs and gauge weights
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sentinel.models.opportunity import ImpermanentLossRisk, YieldOpportunity, YieldType
from sentinel.sources.base import BaseYieldSource
from sentinel.utils.http import HttpClient
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)

CURVE_API = "https://api.curve.fi/v1"
CONVEX_API = "https://api.convexfinance.com/api"

# Curve chain identifiers
CURVE_CHAINS: dict[str, str] = {
    "ethereum": "ethereum",
    "arbitrum": "arbitrum",
    "optimism": "optimism",
    "base": "base",
    "polygon": "polygon",
    "avalanche": "avalanche",
}

STABLECOINS = {"USDC", "USDT", "DAI", "FRAX", "LUSD", "GHO", "PYUSD", "USDE", "CRVUSD", "MKUSD"}


class ConvexCurveSource(BaseYieldSource):
    """Fetch yield data from Curve pools and Convex vaults.

    Curve provides base swap fees + CRV rewards.
    Convex boosts CRV rewards (up to 2.5x) and adds CVX rewards.
    """

    name = "convex_curve"

    async def fetch_opportunities(
        self,
        underlying: str | None = None,
        chains: list[str] | None = None,
    ) -> list[YieldOpportunity]:
        logger.info("convex_curve.fetch_start", underlying=underlying)

        target_chains = chains or list(CURVE_CHAINS.keys())
        opportunities: list[YieldOpportunity] = []

        for chain in target_chains:
            curve_chain = CURVE_CHAINS.get(chain)
            if curve_chain is None:
                continue

            try:
                pools = await self._fetch_curve_pools(curve_chain)
                for pool in pools:
                    opp = self._parse_pool(pool, chain, underlying)
                    if opp:
                        opportunities.append(opp)
            except Exception as e:
                logger.warning("convex_curve.chain_error", chain=chain, error=str(e))

        # Fetch Convex-specific boosted yields (Ethereum only)
        if not chains or "ethereum" in chains:
            try:
                convex_opps = await self._fetch_convex_vaults(underlying)
                opportunities.extend(convex_opps)
            except Exception as e:
                logger.warning("convex_curve.convex_error", error=str(e))

        logger.info("convex_curve.fetch_complete", count=len(opportunities))
        return opportunities

    async def _fetch_curve_pools(self, chain: str) -> list[dict[str, Any]]:
        """Fetch all Curve pools for a chain."""
        try:
            data = await self.http.get_json(
                f"{CURVE_API}/getPools/{chain}/main",
                cache_ttl=600,
            )
            return data.get("data", {}).get("poolData", []) if isinstance(data, dict) else []
        except Exception:
            # Fallback to alternative endpoint
            try:
                data = await self.http.get_json(
                    f"{CURVE_API}/getSubgraphData/{chain}",
                    cache_ttl=600,
                )
                return data.get("data", []) if isinstance(data, dict) else []
            except Exception:
                return []

    async def _fetch_convex_vaults(self, underlying: str | None) -> list[YieldOpportunity]:
        """Fetch Convex Finance boosted Curve vaults."""
        try:
            data = await self.http.get_json(
                f"{CONVEX_API}/get-pools",
                cache_ttl=600,
            )
        except Exception:
            return []

        pools = data if isinstance(data, list) else data.get("pools", [])
        opportunities: list[YieldOpportunity] = []

        for pool in pools:
            opp = self._parse_convex_pool(pool, underlying)
            if opp:
                opportunities.append(opp)

        return opportunities

    def _parse_pool(
        self, pool: dict[str, Any], chain: str, underlying: str | None
    ) -> YieldOpportunity | None:
        """Parse a Curve pool into a yield opportunity."""
        coins = pool.get("coins", [])
        symbols = [c.get("symbol", "") for c in coins if isinstance(c, dict)]
        if not symbols:
            symbols = pool.get("coinsAddresses", [])

        if underlying:
            if not any(s.upper() == underlying.upper() for s in symbols):
                return None

        tvl = float(pool.get("usdTotal", 0) or pool.get("tvl", 0) or 0)
        if tvl < 100_000:
            return None

        # APY breakdown
        apy_data = pool.get("gaugeCrvApy", [0, 0]) if isinstance(pool.get("gaugeCrvApy"), list) else [0, 0]
        base_apy = float(pool.get("poolAPY", 0) or pool.get("apy", 0) or 0)
        crv_apy = float(apy_data[0]) if len(apy_data) > 0 else 0

        total_apy = base_apy + crv_apy
        if total_apy <= 0:
            return None

        pool_name = pool.get("name", "-".join(symbols))
        pool_addr = pool.get("address", "")

        # IL risk based on token composition
        upper_symbols = {s.upper() for s in symbols}
        is_stable_pool = upper_symbols.issubset(STABLECOINS)
        il_risk = ImpermanentLossRisk.LOW if is_stable_pool else ImpermanentLossRisk.MEDIUM

        return YieldOpportunity(
            id=f"curve-{chain}-{pool_addr[:10]}",
            protocol="curve",
            chain=chain.title(),
            pool_name=f"Curve {pool_name}",
            underlying_tokens=symbols,
            yield_type=YieldType.AMM_LP,
            base_apy=base_apy,
            reward_apy=crv_apy,
            total_apy=total_apy,
            tvl_usd=tvl,
            il_risk=il_risk,
            smart_contract_risk=0.15,
            protocol_risk_score=0.15,
            is_audited=True,
            audit_firms=["Trail of Bits", "Quantstamp", "MixBytes"],
            source="convex_curve",
            fetched_at=datetime.utcnow(),
            tags=["curve", "amm"] + (["stablecoin"] if is_stable_pool else []),
        )

    def _parse_convex_pool(
        self, pool: dict[str, Any], underlying: str | None
    ) -> YieldOpportunity | None:
        """Parse a Convex vault into a yield opportunity."""
        name = pool.get("name", "")
        symbols = [s.strip() for s in name.split("/") if s.strip()] or [name]

        if underlying:
            if not any(s.upper() == underlying.upper() for s in symbols):
                return None

        tvl = float(pool.get("tvl", 0) or 0)
        if tvl < 100_000:
            return None

        base_apy = float(pool.get("crvApy", 0) or 0)
        cvx_apy = float(pool.get("cvxApy", 0) or 0)
        extra_apy = float(pool.get("extraRewardsApy", 0) or 0)
        total_apy = base_apy + cvx_apy + extra_apy

        if total_apy <= 0:
            return None

        pool_id = pool.get("id", pool.get("address", "unknown"))

        upper_symbols = {s.upper() for s in symbols}
        is_stable = upper_symbols.issubset(STABLECOINS)

        return YieldOpportunity(
            id=f"convex-{pool_id}",
            protocol="convex",
            chain="Ethereum",
            pool_name=f"Convex {name}",
            underlying_tokens=symbols,
            yield_type=YieldType.VAULT,
            base_apy=base_apy,
            reward_apy=cvx_apy + extra_apy,
            total_apy=total_apy,
            tvl_usd=tvl,
            il_risk=ImpermanentLossRisk.LOW if is_stable else ImpermanentLossRisk.MEDIUM,
            smart_contract_risk=0.18,
            protocol_risk_score=0.18,
            is_audited=True,
            audit_firms=["MixBytes", "PeckShield"],
            source="convex_curve",
            fetched_at=datetime.utcnow(),
            tags=["convex", "boosted", "curve"] + (["stablecoin"] if is_stable else []),
        )
