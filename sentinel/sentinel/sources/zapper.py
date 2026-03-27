"""Zapper yield source — portfolio tracking and yield discovery across DeFi."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sentinel.models.opportunity import YieldOpportunity, YieldType
from sentinel.sources.base import BaseYieldSource
from sentinel.utils.http import HttpClient
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)

ZAPPER_API = "https://api.zapper.xyz/v2"


class ZapperSource(BaseYieldSource):
    """Fetch yield data from Zapper's API.

    Zapper aggregates yield opportunities from hundreds of protocols
    and provides a unified view across chains. It's especially good for:
    - Vault yields (Yearn, Beefy, Harvest, etc.)
    - LP positions and their APYs
    - Protocol-specific yields
    """

    name = "zapper"

    def __init__(self, http: HttpClient | None = None, api_key: str | None = None) -> None:
        super().__init__(http)
        self.api_key = api_key

    async def fetch_opportunities(
        self,
        underlying: str | None = None,
        chains: list[str] | None = None,
    ) -> list[YieldOpportunity]:
        logger.info("zapper.fetch_start", underlying=underlying)

        opportunities: list[YieldOpportunity] = []

        try:
            # Fetch app tokens (yield-bearing positions)
            params: dict[str, Any] = {}
            if chains:
                params["network"] = chains

            data = await self.http.get_json(f"{ZAPPER_API}/apps/tokens", params=params)
            tokens = data if isinstance(data, list) else data.get("data", [])

            for token in tokens:
                opp = self._parse_app_token(token, underlying, chains)
                if opp:
                    opportunities.append(opp)

        except Exception as e:
            logger.warning("zapper.fetch_error", error=str(e))

        logger.info("zapper.fetch_complete", count=len(opportunities))
        return opportunities

    def _parse_app_token(
        self, token: dict[str, Any], underlying: str | None, chains: list[str] | None
    ) -> YieldOpportunity | None:
        """Parse a Zapper app token into a yield opportunity."""
        symbol = token.get("symbol", "")
        network = token.get("network", "ethereum")
        app_id = token.get("appId", "unknown")

        # Check underlying filter
        underlying_tokens = [t.get("symbol", "") for t in token.get("tokens", []) if t.get("symbol")]
        if not underlying_tokens:
            underlying_tokens = [symbol]

        if underlying:
            if not any(t.upper() == underlying.upper() for t in underlying_tokens):
                return None

        if chains and network.lower() not in [c.lower() for c in chains]:
            return None

        # Get APY from data props
        data_props = token.get("dataProps", {})
        apy = float(data_props.get("apy", 0) or 0)
        if apy == 0:
            return None

        tvl = float(data_props.get("liquidity", 0) or data_props.get("tvl", 0) or 0)
        if tvl < 100_000:
            return None

        return YieldOpportunity(
            id=f"zapper-{app_id}-{network}-{symbol.lower()}",
            protocol=app_id,
            chain=network,
            pool_name=f"{app_id.title()} {symbol}",
            underlying_tokens=underlying_tokens,
            yield_type=YieldType.VAULT,
            base_apy=apy,
            reward_apy=0,
            total_apy=apy,
            tvl_usd=tvl,
            smart_contract_risk=0.4,
            protocol_risk_score=0.4,
            source="zapper",
            fetched_at=datetime.utcnow(),
            tags=["zapper-discovered"],
        )
