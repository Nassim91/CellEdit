"""Vaults.fyi meta-aggregator — comprehensive vault and yield data across DeFi.

Vaults.fyi is one of the best yield aggregators, covering:
- Lending vaults (Morpho, Aave, Compound, Euler, etc.)
- LP vaults (Yearn, Beefy, Sommelier, etc.)
- Restaking vaults (EigenLayer, Symbiotic)
- Stablecoin vaults (Maker, Ethena, etc.)

Using this as a primary source avoids the need to maintain individual protocol connectors.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sentinel.models.opportunity import ImpermanentLossRisk, YieldOpportunity, YieldType
from sentinel.sources.base import BaseYieldSource
from sentinel.utils.http import HttpClient
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)

VAULTS_FYI_API = "https://api.vaults.fyi/v1"

# Map vaults.fyi categories to our YieldType
CATEGORY_MAP = {
    "lending": YieldType.LENDING,
    "vault": YieldType.VAULT,
    "lp": YieldType.AMM_LP,
    "staking": YieldType.LIQUID_STAKING,
    "restaking": YieldType.RESTAKING,
    "yield_tokenization": YieldType.YIELD_TOKENIZATION,
    "basis_trade": YieldType.BASIS_TRADE,
    "rwa": YieldType.RWA,
}


class VaultsFyiSource(BaseYieldSource):
    """Fetch yield data from Vaults.fyi API.

    This is a high-quality meta-aggregator that provides:
    - Accurate APY data with historical averages
    - TVL and capacity information
    - Risk scores and audit status
    - Cross-chain vault discovery

    Endpoints:
    - GET /vaults — list all vaults with filtering
    - GET /vaults/{address}?chain={chain} — detailed vault info
    - GET /detailed/summary — aggregated yield overview
    """

    name = "vaults_fyi"

    def __init__(
        self,
        http: HttpClient | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(http)
        self.api_key = api_key
        self._headers = {"X-API-Key": api_key} if api_key else {}

    async def fetch_opportunities(
        self,
        underlying: str | None = None,
        chains: list[str] | None = None,
    ) -> list[YieldOpportunity]:
        logger.info("vaults_fyi.fetch_start", underlying=underlying, chains=chains)

        opportunities: list[YieldOpportunity] = []

        try:
            # Fetch all vaults
            params: dict[str, Any] = {"limit": 500, "sort_by": "tvl", "sort_order": "desc"}
            if underlying:
                params["token"] = underlying.upper()
            if chains:
                params["network"] = ",".join(chains)

            data = await self.http.get_json(f"{VAULTS_FYI_API}/vaults", params=params)
            vaults = data.get("data", []) if isinstance(data, dict) else data

            for vault in vaults:
                try:
                    opp = self._parse_vault(vault, underlying, chains)
                    if opp:
                        opportunities.append(opp)
                except Exception:
                    continue

        except Exception as e:
            logger.warning("vaults_fyi.fetch_error", error=str(e))
            # Fallback to detailed summary endpoint
            try:
                opportunities = await self._fetch_summary(underlying, chains)
            except Exception as e2:
                logger.error("vaults_fyi.summary_fallback_error", error=str(e2))

        logger.info("vaults_fyi.fetch_complete", count=len(opportunities))
        return opportunities

    async def _fetch_summary(
        self, underlying: str | None, chains: list[str] | None
    ) -> list[YieldOpportunity]:
        """Fallback: fetch from detailed summary endpoint."""
        data = await self.http.get_json(f"{VAULTS_FYI_API}/detailed/summary")
        vaults = data.get("data", []) if isinstance(data, dict) else data
        return [
            opp for vault in vaults
            if (opp := self._parse_vault(vault, underlying, chains)) is not None
        ]

    def _parse_vault(
        self, vault: dict[str, Any], underlying: str | None, chains: list[str] | None
    ) -> YieldOpportunity | None:
        """Parse a vaults.fyi vault into a YieldOpportunity."""
        token = vault.get("token", {})
        token_symbol = token.get("symbol", "") if isinstance(token, dict) else str(token)
        chain = vault.get("network", vault.get("chain", "ethereum"))

        if underlying and token_symbol.upper() != underlying.upper():
            return None
        if chains and chain.lower() not in [c.lower() for c in chains]:
            return None

        tvl = float(vault.get("tvl", vault.get("tvlUsd", 0)) or 0)
        if tvl < 100_000:
            return None

        # APY data
        apy_data = vault.get("apy", {})
        if isinstance(apy_data, (int, float)):
            base_apy = float(apy_data)
            reward_apy = 0.0
        else:
            base_apy = float(apy_data.get("base", apy_data.get("net", 0)) or 0)
            reward_apy = float(apy_data.get("reward", apy_data.get("bonus", 0)) or 0)

        total_apy = base_apy + reward_apy
        apy_7d = vault.get("apy7d") or vault.get("apyMean7d")
        apy_30d = vault.get("apy30d") or vault.get("apyMean30d")

        protocol = vault.get("protocol", vault.get("project", "unknown"))
        category = vault.get("category", "vault").lower()
        yield_type = CATEGORY_MAP.get(category, YieldType.VAULT)

        address = vault.get("address", "")

        return YieldOpportunity(
            id=f"vaultsfyi-{protocol}-{chain}-{address[:10]}",
            protocol=protocol,
            chain=chain,
            pool_name=vault.get("name", f"{protocol} {token_symbol}"),
            underlying_tokens=[token_symbol],
            url=vault.get("url"),
            yield_type=yield_type,
            base_apy=base_apy,
            reward_apy=reward_apy,
            total_apy=total_apy,
            apy_7d_avg=float(apy_7d) if apy_7d else None,
            apy_30d_avg=float(apy_30d) if apy_30d else None,
            tvl_usd=tvl,
            available_capacity_usd=float(vault.get("capacity")) if vault.get("capacity") else None,
            smart_contract_risk=float(vault.get("riskScore", 0.4) or 0.4),
            protocol_risk_score=float(vault.get("riskScore", 0.4) or 0.4),
            is_audited=vault.get("audited", None),
            audit_firms=vault.get("auditors", []) or [],
            source="vaults_fyi",
            fetched_at=datetime.utcnow(),
            tags=self._build_tags(vault),
        )

    def _build_tags(self, vault: dict[str, Any]) -> list[str]:
        tags = []
        if vault.get("stablecoin"):
            tags.append("stablecoin")
        if vault.get("featured"):
            tags.append("featured")
        category = vault.get("category", "")
        if category:
            tags.append(category.lower())
        return tags
