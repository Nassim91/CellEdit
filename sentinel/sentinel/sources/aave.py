"""Aave V3 yield source — lending and borrowing rates across chains."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sentinel.models.chain import Chain
from sentinel.models.opportunity import YieldOpportunity, YieldType
from sentinel.sources.base import BaseYieldSource
from sentinel.utils.http import HttpClient
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)

# Aave V3 subgraph endpoints per chain
AAVE_V3_SUBGRAPHS: dict[str, str] = {
    "ethereum": "https://api.thegraph.com/subgraphs/name/aave/protocol-v3",
    "arbitrum": "https://api.thegraph.com/subgraphs/name/aave/protocol-v3-arbitrum",
    "optimism": "https://api.thegraph.com/subgraphs/name/aave/protocol-v3-optimism",
    "polygon": "https://api.thegraph.com/subgraphs/name/aave/protocol-v3-polygon",
    "avalanche": "https://api.thegraph.com/subgraphs/name/aave/protocol-v3-avalanche",
    "base": "https://api.thegraph.com/subgraphs/name/aave/protocol-v3-base",
}

# Aave V3 API (alternative to subgraph)
AAVE_API_URL = "https://aave-api-v2.aave.com"

RESERVES_QUERY = """
{
  reserves(where: { isActive: true }) {
    id
    symbol
    name
    decimals
    liquidityRate
    variableBorrowRate
    stableBorrowRate
    totalATokenSupply
    totalCurrentVariableDebt
    availableLiquidity
    utilizationRate
    price {
      priceInEth
    }
  }
}
"""


class AaveSource(BaseYieldSource):
    """Fetch lending/borrowing yields from Aave V3 across multiple chains."""

    name = "aave"

    def __init__(self, http: HttpClient | None = None) -> None:
        super().__init__(http)

    async def fetch_opportunities(
        self,
        underlying: str | None = None,
        chains: list[str] | None = None,
    ) -> list[YieldOpportunity]:
        """Fetch Aave V3 lending rates across all supported chains."""
        logger.info("aave.fetch_start", underlying=underlying, chains=chains)

        target_chains = chains or list(AAVE_V3_SUBGRAPHS.keys())
        all_opportunities: list[YieldOpportunity] = []

        for chain in target_chains:
            if chain not in AAVE_V3_SUBGRAPHS:
                continue
            try:
                opps = await self._fetch_chain(chain, underlying)
                all_opportunities.extend(opps)
            except Exception as e:
                logger.warning("aave.chain_error", chain=chain, error=str(e))

        logger.info("aave.fetch_complete", total=len(all_opportunities))
        return all_opportunities

    async def _fetch_chain(self, chain: str, underlying: str | None) -> list[YieldOpportunity]:
        """Fetch reserves for a single chain via The Graph."""
        url = AAVE_V3_SUBGRAPHS[chain]
        result = await self.http.get_json(url, params=None)

        # For subgraph, we'd POST a GraphQL query. Fallback to API.
        # Using the REST API approach for simplicity:
        reserves = await self._fetch_reserves_api(chain)

        opportunities: list[YieldOpportunity] = []
        for reserve in reserves:
            opp = self._parse_reserve(reserve, chain, underlying)
            if opp is not None:
                opportunities.append(opp)

        return opportunities

    async def _fetch_reserves_api(self, chain: str) -> list[dict[str, Any]]:
        """Fetch reserves data from Aave's REST API."""
        chain_id_map = {
            "ethereum": 1, "arbitrum": 42161, "optimism": 10,
            "polygon": 137, "avalanche": 43114, "base": 8453,
        }
        chain_id = chain_id_map.get(chain)
        if chain_id is None:
            return []

        try:
            data = await self.http.get_json(
                f"{AAVE_API_URL}/data/reserves-data",
                params={"chainId": chain_id},
            )
            return data if isinstance(data, list) else data.get("reserves", [])
        except Exception as e:
            logger.debug("aave.api_fallback_error", chain=chain, error=str(e))
            return []

    def _parse_reserve(
        self, reserve: dict[str, Any], chain: str, underlying: str | None
    ) -> YieldOpportunity | None:
        """Parse an Aave reserve into a YieldOpportunity."""
        symbol = reserve.get("symbol", "").upper()

        if underlying and symbol != underlying.upper():
            # Also check without W prefix (WETH -> ETH)
            if not (symbol.startswith("W") and symbol[1:] == underlying.upper()):
                return None

        # Rates are in RAY (1e27) in subgraph, or percentage in API
        supply_apy = self._to_apy(reserve.get("liquidityRate") or reserve.get("supplyAPY", 0))
        reward_apy = self._to_apy(reserve.get("rewardAPY", 0))
        total_liquidity = float(reserve.get("totalLiquidity", 0) or reserve.get("availableLiquidity", 0))
        utilization = float(reserve.get("utilizationRate", 0) or 0)

        # Price in USD
        price_usd = float(reserve.get("priceInUsd", 0) or reserve.get("price", {}).get("usd", 0) or 0)
        tvl_usd = total_liquidity * price_usd if price_usd > 0 else total_liquidity

        if tvl_usd < 50_000:
            return None

        return YieldOpportunity(
            id=f"aave-v3-{chain}-{symbol.lower()}",
            protocol="aave-v3",
            chain=Chain(chain).defillama_id if chain in [c.value for c in Chain] else chain,
            pool_name=f"Aave V3 {symbol} Supply",
            underlying_tokens=[symbol],
            yield_type=YieldType.VARIABLE_LENDING,
            base_apy=supply_apy,
            reward_apy=reward_apy,
            total_apy=supply_apy + reward_apy,
            tvl_usd=tvl_usd,
            utilization_rate=utilization * 100 if utilization < 1 else utilization,
            il_risk="none",
            smart_contract_risk=0.15,  # Aave is battle-tested
            protocol_risk_score=0.15,
            is_audited=True,
            audit_firms=["Trail of Bits", "OpenZeppelin", "Certora", "SigmaPrime"],
            is_delta_neutral=False,
            hedging_available=True,
            source="aave",
            fetched_at=datetime.utcnow(),
            tags=["lending", "blue-chip", "variable-rate"],
        )

    @staticmethod
    def _to_apy(rate: float | str) -> float:
        """Convert rate to APY percentage."""
        rate = float(rate)
        if rate > 1e20:
            # RAY format (1e27)
            return (rate / 1e27) * 100
        if rate > 1:
            return rate  # Already percentage
        return rate * 100  # Decimal to percentage
