"""Morpho Blue yield source — optimized lending with curated vaults."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sentinel.models.opportunity import YieldOpportunity, YieldType
from sentinel.sources.base import BaseYieldSource
from sentinel.utils.http import HttpClient
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)

MORPHO_API = "https://blue-api.morpho.org/graphql"

VAULTS_QUERY = """
query {
  vaults(first: 100, orderBy: TotalAssetsUsd, orderDirection: Desc) {
    items {
      address
      name
      symbol
      chain {
        id
        network
      }
      asset {
        symbol
        address
        decimals
        priceUsd
      }
      state {
        totalAssetsUsd
        netApy
        netBorrowApy
        fee
        curator {
          name
        }
      }
      metadata {
        description
      }
    }
  }
}
"""

MARKETS_QUERY = """
query {
  markets(first: 100, orderBy: SupplyAssetsUsd, orderDirection: Desc) {
    items {
      uniqueKey
      loanAsset {
        symbol
        priceUsd
      }
      collateralAsset {
        symbol
      }
      state {
        supplyAssetsUsd
        borrowAssetsUsd
        supplyApy
        borrowApy
        rewards {
          supplyApr
          borrowApr
          asset {
            symbol
          }
        }
        utilization
      }
      lltv
    }
  }
}
"""


class MorphoSource(BaseYieldSource):
    """Fetch yield opportunities from Morpho Blue vaults and markets."""

    name = "morpho"

    async def fetch_opportunities(
        self,
        underlying: str | None = None,
        chains: list[str] | None = None,
    ) -> list[YieldOpportunity]:
        logger.info("morpho.fetch_start", underlying=underlying)

        opportunities: list[YieldOpportunity] = []

        # Fetch vaults
        try:
            vault_opps = await self._fetch_vaults(underlying, chains)
            opportunities.extend(vault_opps)
        except Exception as e:
            logger.warning("morpho.vaults_error", error=str(e))

        # Fetch direct markets
        try:
            market_opps = await self._fetch_markets(underlying, chains)
            opportunities.extend(market_opps)
        except Exception as e:
            logger.warning("morpho.markets_error", error=str(e))

        logger.info("morpho.fetch_complete", total=len(opportunities))
        return opportunities

    async def _fetch_vaults(
        self, underlying: str | None, chains: list[str] | None
    ) -> list[YieldOpportunity]:
        """Fetch Morpho Blue curated vaults."""
        try:
            result = await self._graphql(VAULTS_QUERY)
        except Exception:
            return []

        vaults = result.get("data", {}).get("vaults", {}).get("items", [])
        opportunities: list[YieldOpportunity] = []

        for vault in vaults:
            state = vault.get("state", {})
            asset = vault.get("asset", {})
            symbol = asset.get("symbol", "UNKNOWN")
            chain_info = vault.get("chain", {})
            chain_name = chain_info.get("network", "ethereum").lower()

            if underlying and symbol.upper() != underlying.upper():
                continue
            if chains and chain_name not in chains:
                continue

            tvl = float(state.get("totalAssetsUsd", 0) or 0)
            if tvl < 50_000:
                continue

            net_apy = float(state.get("netApy", 0) or 0) * 100
            curator = state.get("curator", {})
            curator_name = curator.get("name", "Unknown") if curator else "Unknown"

            opportunities.append(YieldOpportunity(
                id=f"morpho-vault-{chain_name}-{vault.get('address', '')[:10]}",
                protocol="morpho-blue",
                chain=chain_name.title(),
                pool_name=f"Morpho {vault.get('name', symbol)} ({curator_name})",
                underlying_tokens=[symbol],
                yield_type=YieldType.VAULT,
                base_apy=net_apy,
                reward_apy=0,
                total_apy=net_apy,
                tvl_usd=tvl,
                smart_contract_risk=0.2,
                protocol_risk_score=0.2,
                is_audited=True,
                audit_firms=["Spearbit", "Trail of Bits"],
                source="morpho",
                fetched_at=datetime.utcnow(),
                tags=["vault", "curated", f"curator:{curator_name}"],
            ))

        return opportunities

    async def _fetch_markets(
        self, underlying: str | None, chains: list[str] | None
    ) -> list[YieldOpportunity]:
        """Fetch direct Morpho Blue lending markets."""
        try:
            result = await self._graphql(MARKETS_QUERY)
        except Exception:
            return []

        markets = result.get("data", {}).get("markets", {}).get("items", [])
        opportunities: list[YieldOpportunity] = []

        for market in markets:
            loan_asset = market.get("loanAsset", {})
            collateral_asset = market.get("collateralAsset", {})
            state = market.get("state", {})

            symbol = loan_asset.get("symbol", "UNKNOWN")
            collateral = collateral_asset.get("symbol", "UNKNOWN") if collateral_asset else "UNKNOWN"

            if underlying and symbol.upper() != underlying.upper():
                continue

            tvl = float(state.get("supplyAssetsUsd", 0) or 0)
            if tvl < 50_000:
                continue

            supply_apy = float(state.get("supplyApy", 0) or 0) * 100

            # Rewards
            reward_apy = 0.0
            rewards = state.get("rewards", []) or []
            for r in rewards:
                reward_apy += float(r.get("supplyApr", 0) or 0) * 100

            lltv = float(market.get("lltv", 0) or 0)
            utilization = float(state.get("utilization", 0) or 0)

            opportunities.append(YieldOpportunity(
                id=f"morpho-market-{market.get('uniqueKey', '')[:12]}",
                protocol="morpho-blue",
                chain="Ethereum",
                pool_name=f"Morpho {symbol}/{collateral} (LLTV {lltv:.0%})",
                underlying_tokens=[symbol],
                yield_type=YieldType.LENDING,
                base_apy=supply_apy,
                reward_apy=reward_apy,
                total_apy=supply_apy + reward_apy,
                tvl_usd=tvl,
                utilization_rate=utilization * 100,
                smart_contract_risk=0.2,
                protocol_risk_score=0.2,
                is_audited=True,
                source="morpho",
                fetched_at=datetime.utcnow(),
                tags=["lending", "isolated-market", f"collateral:{collateral}"],
            ))

        return opportunities

    async def _graphql(self, query: str) -> dict[str, Any]:
        """Execute a GraphQL query against Morpho's API."""
        import json

        client = await self.http._get_client()
        resp = await client.post(
            MORPHO_API,
            json={"query": query},
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()
