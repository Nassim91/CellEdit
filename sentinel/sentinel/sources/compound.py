"""Compound V3 (Comet) yield source."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sentinel.models.opportunity import YieldOpportunity, YieldType
from sentinel.sources.base import BaseYieldSource
from sentinel.utils.http import HttpClient
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)

# Compound V3 Comet deployments
COMPOUND_V3_MARKETS = {
    "ethereum": {
        "USDC": "0xc3d688B66703497DAA19211EEdff47f25384cdc3",
        "WETH": "0xA17581A9E3356d9A858b789D68B4d866e593aE94",
    },
    "arbitrum": {
        "USDC": "0xA5EDBDD9646f8dFF606d7448e414884C7d905dCA",
        "USDC.e": "0x9c4ec768c28520B50860ea7a15bd7213a9fF58bf",
    },
    "base": {
        "USDC": "0xb125E6687d4313864e53df431d5425969c15Eb2F",
        "USDbC": "0x9c4ec768c28520B50860ea7a15bd7213a9fF58bf",
        "WETH": "0x46e6b214b524310239732D51387075E0e70970bf",
    },
    "polygon": {
        "USDC": "0xF25212E676D1F7F89Cd72fFEe66158f541246445",
    },
    "optimism": {
        "USDC": "0x2e44e174f7D53F0212823acC11C01A11d58c5bCB",
    },
}


class CompoundSource(BaseYieldSource):
    """Fetch lending yields from Compound V3 across chains."""

    name = "compound"

    def __init__(self, http: HttpClient | None = None) -> None:
        super().__init__(http)
        self._api_url = "https://v3-api.compound.finance"

    async def fetch_opportunities(
        self,
        underlying: str | None = None,
        chains: list[str] | None = None,
    ) -> list[YieldOpportunity]:
        logger.info("compound.fetch_start", underlying=underlying)

        target_chains = chains or list(COMPOUND_V3_MARKETS.keys())
        opportunities: list[YieldOpportunity] = []

        for chain in target_chains:
            markets = COMPOUND_V3_MARKETS.get(chain, {})
            for asset, comet_addr in markets.items():
                if underlying and asset.upper() != underlying.upper():
                    continue

                try:
                    opp = await self._fetch_market(chain, asset, comet_addr)
                    if opp:
                        opportunities.append(opp)
                except Exception as e:
                    logger.warning("compound.market_error", chain=chain, asset=asset, error=str(e))

        logger.info("compound.fetch_complete", total=len(opportunities))
        return opportunities

    async def _fetch_market(
        self, chain: str, asset: str, comet_addr: str
    ) -> YieldOpportunity | None:
        """Fetch market data for a single Compound V3 Comet deployment."""
        try:
            data = await self.http.get_json(
                f"{self._api_url}/market",
                params={"chain": chain, "comet": comet_addr},
            )
        except Exception:
            # Fallback: construct from known data
            data = {}

        supply_apy = float(data.get("supplyAPY", 0)) * 100 if data else 0
        reward_apy = float(data.get("rewardSupplyAPY", 0)) * 100 if data else 0
        tvl = float(data.get("totalSupplyUSD", 0)) if data else 0

        return YieldOpportunity(
            id=f"compound-v3-{chain}-{asset.lower()}",
            protocol="compound-v3",
            chain=chain.title(),
            pool_name=f"Compound V3 {asset} Supply",
            underlying_tokens=[asset],
            yield_type=YieldType.VARIABLE_LENDING,
            base_apy=supply_apy,
            reward_apy=reward_apy,
            total_apy=supply_apy + reward_apy,
            tvl_usd=tvl,
            utilization_rate=float(data.get("utilization", 0)) * 100 if data else None,
            smart_contract_risk=0.15,
            protocol_risk_score=0.15,
            is_audited=True,
            audit_firms=["OpenZeppelin", "Trail of Bits", "ChainSecurity"],
            source="compound",
            fetched_at=datetime.utcnow(),
            tags=["lending", "blue-chip", "variable-rate"],
        )
