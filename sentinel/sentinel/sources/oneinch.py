"""1inch Yield source — DEX aggregator yield discovery."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sentinel.models.opportunity import YieldOpportunity, YieldType
from sentinel.sources.base import BaseYieldSource
from sentinel.utils.http import HttpClient
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)

ONEINCH_API = "https://api.1inch.dev"

# 1inch supported chain IDs
CHAIN_IDS: dict[str, int] = {
    "ethereum": 1,
    "arbitrum": 42161,
    "optimism": 10,
    "base": 8453,
    "polygon": 137,
    "avalanche": 43114,
    "bsc": 56,
}


class OneInchYieldSource(BaseYieldSource):
    """Fetch yield opportunities from 1inch earn/fusion products.

    1inch provides:
    - Fusion+ swap surplus yield
    - Staking yields
    - LP opportunities via their aggregated routing
    """

    name = "1inch"

    def __init__(self, http: HttpClient | None = None, api_key: str | None = None) -> None:
        super().__init__(http)
        self.api_key = api_key

    async def fetch_opportunities(
        self,
        underlying: str | None = None,
        chains: list[str] | None = None,
    ) -> list[YieldOpportunity]:
        logger.info("1inch.fetch_start", underlying=underlying)

        target_chains = chains or list(CHAIN_IDS.keys())
        opportunities: list[YieldOpportunity] = []

        for chain in target_chains:
            chain_id = CHAIN_IDS.get(chain)
            if chain_id is None:
                continue

            try:
                data = await self.http.get_json(
                    f"{ONEINCH_API}/earn/v1.0/{chain_id}/yields",
                )
                yields = data if isinstance(data, list) else data.get("data", [])

                for y in yields:
                    opp = self._parse_yield(y, chain, underlying)
                    if opp:
                        opportunities.append(opp)

            except Exception as e:
                logger.debug("1inch.chain_error", chain=chain, error=str(e))

        logger.info("1inch.fetch_complete", count=len(opportunities))
        return opportunities

    def _parse_yield(
        self, data: dict[str, Any], chain: str, underlying: str | None
    ) -> YieldOpportunity | None:
        token = data.get("token", {})
        symbol = token.get("symbol", "") if isinstance(token, dict) else str(token)

        if underlying and symbol.upper() != underlying.upper():
            return None

        apy = float(data.get("apy", 0) or 0) * 100
        tvl = float(data.get("tvl", 0) or 0)

        if apy <= 0 or tvl < 50_000:
            return None

        return YieldOpportunity(
            id=f"1inch-{chain}-{symbol.lower()}",
            protocol="1inch",
            chain=chain.title(),
            pool_name=f"1inch Earn {symbol}",
            underlying_tokens=[symbol],
            yield_type=YieldType.VAULT,
            base_apy=apy,
            reward_apy=0,
            total_apy=apy,
            tvl_usd=tvl,
            smart_contract_risk=0.3,
            protocol_risk_score=0.3,
            is_audited=True,
            source="1inch",
            fetched_at=datetime.utcnow(),
            tags=["aggregator"],
        )
