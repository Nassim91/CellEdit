"""DeFiLlama yield data source — the primary aggregator for cross-chain yield discovery."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sentinel.models.chain import Chain
from sentinel.models.opportunity import ImpermanentLossRisk, YieldOpportunity, YieldType
from sentinel.sources.base import BaseYieldSource
from sentinel.utils.http import HttpClient
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)

# Map DeFiLlama project slugs to categories
CATEGORY_MAP: dict[str, YieldType] = {
    "Dexes": YieldType.AMM_LP,
    "Lending": YieldType.LENDING,
    "CDP": YieldType.LENDING,
    "Liquid Staking": YieldType.LIQUID_STAKING,
    "Yield": YieldType.VAULT,
    "Farm": YieldType.LIQUIDITY_MINING,
    "Yield Aggregator": YieldType.VAULT,
    "Derivatives": YieldType.BASIS_TRADE,
    "Options": YieldType.OPTIONS_VAULT,
    "RWA": YieldType.RWA,
    "Insurance": YieldType.INSURANCE,
    "Restaking": YieldType.RESTAKING,
}

# Tokens considered stable — used for IL risk assessment
STABLECOINS = {"USDC", "USDT", "DAI", "FRAX", "LUSD", "GHO", "PYUSD", "USDE", "CRVUSD", "MKUSD", "EUSD"}


class DefiLlamaSource(BaseYieldSource):
    """Fetches yield data from DeFiLlama's yields API.

    Endpoints used:
    - GET /pools          — All pools with current APY, TVL, tokens
    - GET /chart/{pool}   — Historical APY for a specific pool
    """

    name = "defillama"

    def __init__(
        self,
        http: HttpClient | None = None,
        base_url: str = "https://yields.llama.fi",
        api_url: str = "https://api.llama.fi",
        min_tvl: float = 100_000,
    ) -> None:
        super().__init__(http)
        self.base_url = base_url.rstrip("/")
        self.api_url = api_url.rstrip("/")
        self.min_tvl = min_tvl

    async def fetch_opportunities(
        self,
        underlying: str | None = None,
        chains: list[str] | None = None,
    ) -> list[YieldOpportunity]:
        """Fetch all yield pools from DeFiLlama, with optional filtering."""
        logger.info("defillama.fetch_pools", underlying=underlying, chains=chains)

        raw = await self.http.get_json(f"{self.base_url}/pools")
        pools: list[dict[str, Any]] = raw.get("data", []) if isinstance(raw, dict) else raw

        logger.info("defillama.pools_fetched", count=len(pools))

        # Normalize chain filter
        chain_set: set[str] | None = None
        if chains:
            chain_set = set()
            for c in chains:
                try:
                    chain_set.add(Chain(c).defillama_id)
                except ValueError:
                    chain_set.add(c)

        opportunities: list[YieldOpportunity] = []
        for pool in pools:
            try:
                opp = self._parse_pool(pool, underlying, chain_set)
                if opp is not None:
                    opportunities.append(opp)
            except Exception:
                logger.debug("defillama.parse_error", pool_id=pool.get("pool"))
                continue

        logger.info("defillama.opportunities_parsed", count=len(opportunities))
        return opportunities

    async def fetch_pool_history(self, pool_id: str) -> list[dict[str, Any]]:
        """Fetch historical APY data for a specific pool."""
        data = await self.http.get_json(f"{self.base_url}/chart/{pool_id}")
        return data.get("data", []) if isinstance(data, dict) else data

    async def fetch_protocols(self) -> list[dict[str, Any]]:
        """Fetch all protocols from DeFiLlama."""
        return await self.http.get_json(f"{self.api_url}/protocols")

    async def fetch_protocol_tvl(self, slug: str) -> dict[str, Any]:
        """Fetch TVL history for a specific protocol."""
        return await self.http.get_json(f"{self.api_url}/protocol/{slug}")

    def _parse_pool(
        self,
        pool: dict[str, Any],
        underlying: str | None,
        chain_set: set[str] | None,
    ) -> YieldOpportunity | None:
        """Parse a raw DeFiLlama pool into a YieldOpportunity, or None if filtered out."""
        tvl = pool.get("tvlUsd", 0) or 0
        if tvl < self.min_tvl:
            return None

        chain = pool.get("chain", "")
        if chain_set and chain not in chain_set:
            return None

        # Parse underlying tokens
        symbol = pool.get("symbol", "")
        tokens = [t.strip() for t in symbol.split("-") if t.strip()]
        if not tokens:
            return None

        # Filter by underlying if specified
        if underlying:
            normalized = underlying.upper()
            if not any(t.upper() == normalized for t in tokens):
                # Also check wrapped variants
                wrapped_variants = {f"W{normalized}", f"ST{normalized}", f"R{normalized}", f"CB{normalized}"}
                if not any(t.upper() in wrapped_variants for t in tokens):
                    return None

        # Determine yield type
        project_category = pool.get("category", "")
        yield_type = CATEGORY_MAP.get(project_category, YieldType.OTHER)

        # APY breakdown
        base_apy = pool.get("apyBase", 0) or 0
        reward_apy = pool.get("apyReward", 0) or 0
        total_apy = pool.get("apy", base_apy + reward_apy) or 0

        # IL risk assessment
        il_risk = self._assess_il_risk(tokens, yield_type)

        # Determine if stablecoin-only (lower risk)
        is_stable_pool = all(t.upper() in STABLECOINS for t in tokens)

        pool_id = pool.get("pool", f"{pool.get('project', 'unknown')}-{chain}-{symbol}")

        return YieldOpportunity(
            id=pool_id,
            protocol=pool.get("project", "unknown"),
            chain=chain,
            pool_name=symbol,
            underlying_tokens=tokens,
            url=pool.get("poolMeta"),
            yield_type=yield_type,
            base_apy=base_apy,
            reward_apy=reward_apy,
            total_apy=total_apy,
            apy_7d_avg=pool.get("apyMean7d"),
            apy_30d_avg=pool.get("apyMean30d"),
            tvl_usd=tvl,
            utilization_rate=pool.get("utilization"),
            il_risk=il_risk,
            smart_contract_risk=0.3 if is_stable_pool else 0.5,
            protocol_risk_score=0.3 if is_stable_pool else 0.5,
            is_audited=pool.get("audits") is not None,
            source="defillama",
            fetched_at=datetime.utcnow(),
            tags=self._build_tags(pool, is_stable_pool),
        )

    def _assess_il_risk(self, tokens: list[str], yield_type: YieldType) -> ImpermanentLossRisk:
        """Estimate impermanent loss risk based on token composition and pool type."""
        if yield_type in (YieldType.LENDING, YieldType.VARIABLE_LENDING, YieldType.FIXED_LENDING, YieldType.VAULT):
            return ImpermanentLossRisk.NONE

        if len(tokens) <= 1:
            return ImpermanentLossRisk.NONE

        upper_tokens = {t.upper() for t in tokens}
        all_stable = upper_tokens.issubset(STABLECOINS)
        if all_stable:
            return ImpermanentLossRisk.LOW

        # Correlated pairs (e.g., ETH/stETH)
        correlated_pairs = [
            {"ETH", "STETH"}, {"ETH", "WSTETH"}, {"ETH", "RETH"}, {"ETH", "CBETH"},
            {"ETH", "WETH"}, {"BTC", "WBTC"}, {"BTC", "TBTC"},
        ]
        for pair in correlated_pairs:
            if upper_tokens == pair:
                return ImpermanentLossRisk.LOW

        any_stable = bool(upper_tokens & STABLECOINS)
        if any_stable:
            return ImpermanentLossRisk.HIGH  # volatile/stable pair = high IL

        return ImpermanentLossRisk.MEDIUM  # volatile/volatile

    def _build_tags(self, pool: dict[str, Any], is_stable: bool) -> list[str]:
        tags = []
        if is_stable:
            tags.append("stablecoin")
        if pool.get("stablecoin"):
            tags.append("stablecoin")
        if pool.get("ilRisk") == "no":
            tags.append("no-il")
        if pool.get("exposure") == "single":
            tags.append("single-sided")
        if pool.get("apyReward", 0):
            tags.append("incentivized")
        return list(set(tags))
