"""Pendle Finance yield tokenization source — fixed yield and yield trading."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sentinel.models.opportunity import YieldOpportunity, YieldType
from sentinel.sources.base import BaseYieldSource
from sentinel.utils.http import HttpClient
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)

# Pendle API endpoints
PENDLE_API = "https://api-v2.pendle.finance/core"

# Pendle supported chain IDs
PENDLE_CHAINS: dict[str, int] = {
    "ethereum": 1,
    "arbitrum": 42161,
    "optimism": 10,
    "bsc": 56,
    "mantle": 5000,
}


class PendleSource(BaseYieldSource):
    """Fetch yield tokenization opportunities from Pendle Finance.

    Pendle splits yield-bearing tokens into:
    - PT (Principal Token): fixed-yield exposure
    - YT (Yield Token): leveraged variable-yield exposure
    - LP: liquidity provision in Pendle AMM pools
    """

    name = "pendle"

    async def fetch_opportunities(
        self,
        underlying: str | None = None,
        chains: list[str] | None = None,
    ) -> list[YieldOpportunity]:
        logger.info("pendle.fetch_start", underlying=underlying)

        target_chains = chains or list(PENDLE_CHAINS.keys())
        all_opps: list[YieldOpportunity] = []

        for chain in target_chains:
            chain_id = PENDLE_CHAINS.get(chain)
            if chain_id is None:
                continue

            try:
                markets = await self._fetch_markets(chain_id)
                for market in markets:
                    opps = self._parse_market(market, chain, underlying)
                    all_opps.extend(opps)
            except Exception as e:
                logger.warning("pendle.chain_error", chain=chain, error=str(e))

        logger.info("pendle.fetch_complete", total=len(all_opps))
        return all_opps

    async def _fetch_markets(self, chain_id: int) -> list[dict[str, Any]]:
        """Fetch all active Pendle markets for a chain."""
        try:
            data = await self.http.get_json(
                f"{PENDLE_API}/v1/{chain_id}/markets",
                params={"order_by": "tvl", "limit": 100},
            )
            return data.get("results", []) if isinstance(data, dict) else data
        except Exception as e:
            logger.warning("pendle.api_error", chain_id=chain_id, error=str(e))
            return []

    def _parse_market(
        self, market: dict[str, Any], chain: str, underlying: str | None
    ) -> list[YieldOpportunity]:
        """Parse a Pendle market into PT, YT, and LP opportunities."""
        name = market.get("name", "")
        tokens = self._extract_tokens(market)

        if underlying:
            normalized = underlying.upper()
            if not any(t.upper() == normalized for t in tokens):
                return []

        tvl = float(market.get("liquidity", {}).get("usd", 0) or market.get("tvl", 0))
        if tvl < 50_000:
            return []

        market_addr = market.get("address", "unknown")
        expiry = market.get("expiry", "")

        opportunities: list[YieldOpportunity] = []

        # PT — Fixed Yield
        pt_apy = float(market.get("pt", {}).get("apy", 0) or market.get("impliedAPY", 0)) * 100
        if pt_apy > 0:
            opportunities.append(YieldOpportunity(
                id=f"pendle-pt-{chain}-{market_addr[:10]}",
                protocol="pendle",
                chain=chain.title(),
                pool_name=f"Pendle PT {name}",
                underlying_tokens=tokens,
                yield_type=YieldType.FIXED_LENDING,
                base_apy=pt_apy,
                reward_apy=0,
                total_apy=pt_apy,
                tvl_usd=tvl,
                smart_contract_risk=0.25,
                protocol_risk_score=0.25,
                is_audited=True,
                audit_firms=["Ackee", "Dedaub"],
                is_delta_neutral=False,
                source="pendle",
                fetched_at=datetime.utcnow(),
                tags=["fixed-yield", "yield-tokenization", f"expiry:{expiry}"],
            ))

        # YT — Leveraged Yield
        yt_apy = float(market.get("yt", {}).get("apy", 0) or 0) * 100
        if yt_apy != 0:
            opportunities.append(YieldOpportunity(
                id=f"pendle-yt-{chain}-{market_addr[:10]}",
                protocol="pendle",
                chain=chain.title(),
                pool_name=f"Pendle YT {name}",
                underlying_tokens=tokens,
                yield_type=YieldType.YIELD_TOKENIZATION,
                base_apy=yt_apy,
                reward_apy=0,
                total_apy=yt_apy,
                tvl_usd=tvl * 0.3,  # YT is typically a fraction of total
                smart_contract_risk=0.35,
                protocol_risk_score=0.35,
                is_audited=True,
                source="pendle",
                fetched_at=datetime.utcnow(),
                tags=["leveraged-yield", "yield-tokenization", f"expiry:{expiry}"],
            ))

        # LP — AMM liquidity provision
        lp_apy = float(market.get("lp", {}).get("apy", 0) or market.get("lpAPY", 0)) * 100
        lp_reward = float(market.get("lp", {}).get("rewardApy", 0) or 0) * 100
        if lp_apy > 0:
            opportunities.append(YieldOpportunity(
                id=f"pendle-lp-{chain}-{market_addr[:10]}",
                protocol="pendle",
                chain=chain.title(),
                pool_name=f"Pendle LP {name}",
                underlying_tokens=tokens,
                yield_type=YieldType.AMM_LP,
                base_apy=lp_apy,
                reward_apy=lp_reward,
                total_apy=lp_apy + lp_reward,
                tvl_usd=tvl,
                smart_contract_risk=0.25,
                protocol_risk_score=0.25,
                is_audited=True,
                source="pendle",
                fetched_at=datetime.utcnow(),
                tags=["lp", "yield-tokenization", f"expiry:{expiry}"],
            ))

        return opportunities

    @staticmethod
    def _extract_tokens(market: dict[str, Any]) -> list[str]:
        """Extract underlying token symbols from a Pendle market."""
        # Try different API response formats
        if "underlyingAsset" in market:
            asset = market["underlyingAsset"]
            if isinstance(asset, dict):
                return [asset.get("symbol", "UNKNOWN")]
            return [str(asset)]
        if "tokens" in market:
            return [t.get("symbol", "") for t in market["tokens"] if t.get("symbol")]
        # Parse from name as fallback
        name = market.get("name", "")
        for sep in ["/", "-", " "]:
            parts = name.split(sep)
            if len(parts) >= 1:
                return [parts[0].strip()]
        return ["UNKNOWN"]
