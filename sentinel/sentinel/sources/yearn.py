"""Yearn Finance yield source — automated yield vaults."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sentinel.models.opportunity import YieldOpportunity, YieldType
from sentinel.sources.base import BaseYieldSource
from sentinel.utils.http import HttpClient
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)

YEARN_API = "https://ydaemon.yearn.fi"

YEARN_CHAINS: dict[str, int] = {
    "ethereum": 1,
    "arbitrum": 42161,
    "optimism": 10,
    "base": 8453,
    "polygon": 137,
}


class YearnSource(BaseYieldSource):
    """Fetch yield vault data from Yearn Finance V3 (yDaemon API).

    Yearn automates yield strategies and is one of the oldest
    yield aggregators. Their API provides excellent data quality.
    """

    name = "yearn"

    async def fetch_opportunities(
        self,
        underlying: str | None = None,
        chains: list[str] | None = None,
    ) -> list[YieldOpportunity]:
        logger.info("yearn.fetch_start", underlying=underlying)

        target_chains = chains or list(YEARN_CHAINS.keys())
        opportunities: list[YieldOpportunity] = []

        for chain in target_chains:
            chain_id = YEARN_CHAINS.get(chain)
            if chain_id is None:
                continue

            try:
                vaults = await self._fetch_vaults(chain_id)
                for vault in vaults:
                    opp = self._parse_vault(vault, chain, underlying)
                    if opp:
                        opportunities.append(opp)
            except Exception as e:
                logger.warning("yearn.chain_error", chain=chain, error=str(e))

        logger.info("yearn.fetch_complete", count=len(opportunities))
        return opportunities

    async def _fetch_vaults(self, chain_id: int) -> list[dict[str, Any]]:
        """Fetch all vaults for a chain from yDaemon."""
        data = await self.http.get_json(
            f"{YEARN_API}/{chain_id}/vaults/all",
            params={"hideAlways": "true", "orderBy": "tvl", "orderDirection": "desc"},
        )
        return data if isinstance(data, list) else []

    def _parse_vault(
        self, vault: dict[str, Any], chain: str, underlying: str | None
    ) -> YieldOpportunity | None:
        token = vault.get("token", {})
        symbol = token.get("symbol", "") if isinstance(token, dict) else ""

        if underlying and symbol.upper() != underlying.upper():
            return None

        tvl = float(vault.get("tvl", {}).get("tvl", 0) or 0) if isinstance(vault.get("tvl"), dict) else float(vault.get("tvl", 0) or 0)
        if tvl < 50_000:
            return None

        # APY data from Yearn
        apy_data = vault.get("apy", {})
        if isinstance(apy_data, dict):
            net_apy = float(apy_data.get("net_apy", 0) or 0) * 100
            gross_apy = float(apy_data.get("gross_apr", 0) or 0) * 100
            points_apy = float(apy_data.get("points", {}).get("week_ago", 0) or 0) * 100 if isinstance(apy_data.get("points"), dict) else 0
        else:
            net_apy = float(apy_data or 0) * 100
            gross_apy = net_apy
            points_apy = 0

        if net_apy <= 0:
            return None

        vault_addr = vault.get("address", "")

        return YieldOpportunity(
            id=f"yearn-{chain}-{vault_addr[:10]}",
            protocol="yearn-v3",
            chain=chain.title(),
            pool_name=vault.get("name", f"Yearn {symbol}"),
            underlying_tokens=[symbol],
            url=f"https://yearn.fi/vaults/{chain}/{vault_addr}",
            yield_type=YieldType.VAULT,
            base_apy=net_apy,
            reward_apy=points_apy,
            total_apy=net_apy + points_apy,
            tvl_usd=tvl,
            smart_contract_risk=0.2,
            protocol_risk_score=0.2,
            is_audited=True,
            audit_firms=["ChainSecurity", "Trail of Bits", "Statemind"],
            source="yearn",
            fetched_at=datetime.utcnow(),
            tags=["auto-compound", "vault", "yield-aggregator"],
        )
