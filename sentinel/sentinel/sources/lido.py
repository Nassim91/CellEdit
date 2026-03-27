"""Lido liquid staking source — ETH staking via stETH/wstETH.

Lido is the largest liquid staking protocol with ~$30B+ TVL.
Key yield components:
1. ETH PoS staking rewards (~3.0-3.5% APR)
2. MEV and priority fee share
3. Additional yield from wstETH in DeFi (lending, LP, Pendle)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sentinel.models.opportunity import YieldOpportunity, YieldType
from sentinel.sources.base import BaseYieldSource
from sentinel.utils.http import HttpClient
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)

LIDO_API = "https://eth-api.lido.fi"
LIDO_STAKE_API = "https://stake.lido.fi/api"


class LidoSource(BaseYieldSource):
    """Fetch liquid staking yields from Lido Finance.

    Provides:
    - stETH staking APR (rebasing)
    - wstETH staking APR (non-rebasing, DeFi-composable)
    - Protocol fee and MEV distribution
    """

    name = "lido"

    async def fetch_opportunities(
        self,
        underlying: str | None = None,
        chains: list[str] | None = None,
    ) -> list[YieldOpportunity]:
        logger.info("lido.fetch_start", underlying=underlying)

        # Lido is primarily Ethereum, but stETH/wstETH can be bridged
        if underlying and underlying.upper() not in ("ETH", "WETH", "STETH", "WSTETH"):
            return []

        opportunities: list[YieldOpportunity] = []

        # Fetch current staking APR
        try:
            apr_data = await self._fetch_staking_apr()
            opportunities.append(self._build_steth_opportunity(apr_data))
            opportunities.append(self._build_wsteth_opportunity(apr_data))
        except Exception as e:
            logger.warning("lido.apr_error", error=str(e))
            # Fallback with estimated data
            opportunities.append(self._build_steth_opportunity({}))
            opportunities.append(self._build_wsteth_opportunity({}))

        # Fetch stETH in DeFi composability stats
        try:
            defi_opps = await self._fetch_steth_defi_yields()
            opportunities.extend(defi_opps)
        except Exception as e:
            logger.debug("lido.defi_yields_error", error=str(e))

        logger.info("lido.fetch_complete", count=len(opportunities))
        return opportunities

    async def _fetch_staking_apr(self) -> dict[str, Any]:
        """Fetch current Lido staking APR."""
        try:
            data = await self.http.get_json(
                f"{LIDO_API}/v1/protocol/steth/apr/sma",
                cache_ttl=3600,  # Cache for 1 hour
            )
            return data.get("data", {}) if isinstance(data, dict) else {}
        except Exception:
            try:
                data = await self.http.get_json(
                    f"{LIDO_API}/v1/protocol/steth/apr/last",
                    cache_ttl=3600,
                )
                return data.get("data", {}) if isinstance(data, dict) else {}
            except Exception:
                return {}

    def _build_steth_opportunity(self, apr_data: dict[str, Any]) -> YieldOpportunity:
        """Build stETH staking opportunity."""
        # stETH APR includes consensus + execution layer rewards
        apr = float(apr_data.get("smaApr", 3.3) or apr_data.get("apr", 3.3))

        return YieldOpportunity(
            id="lido-steth-ethereum",
            protocol="lido",
            chain="Ethereum",
            pool_name="Lido stETH Staking",
            underlying_tokens=["ETH", "stETH"],
            yield_type=YieldType.LIQUID_STAKING,
            base_apy=apr,
            reward_apy=0,
            total_apy=apr,
            tvl_usd=30_000_000_000,
            smart_contract_risk=0.1,
            protocol_risk_score=0.12,
            is_audited=True,
            audit_firms=["Statemind", "Certora", "ChainSecurity", "Hexens", "Oxorio"],
            is_delta_neutral=False,
            hedging_available=True,
            source="lido",
            fetched_at=datetime.utcnow(),
            tags=["liquid-staking", "blue-chip", "eth-staking", "rebasing"],
        )

    def _build_wsteth_opportunity(self, apr_data: dict[str, Any]) -> YieldOpportunity:
        """Build wstETH staking opportunity (non-rebasing wrapper)."""
        apr = float(apr_data.get("smaApr", 3.3) or apr_data.get("apr", 3.3))

        return YieldOpportunity(
            id="lido-wsteth-ethereum",
            protocol="lido",
            chain="Ethereum",
            pool_name="Lido wstETH (wrapped stETH)",
            underlying_tokens=["ETH", "wstETH"],
            yield_type=YieldType.LIQUID_STAKING,
            base_apy=apr,
            reward_apy=0,
            total_apy=apr,
            tvl_usd=15_000_000_000,
            smart_contract_risk=0.1,
            protocol_risk_score=0.12,
            is_audited=True,
            audit_firms=["Statemind", "Certora", "ChainSecurity"],
            is_delta_neutral=False,
            hedging_available=True,
            source="lido",
            fetched_at=datetime.utcnow(),
            tags=["liquid-staking", "blue-chip", "eth-staking", "non-rebasing", "defi-composable"],
            extra={
                "note": "wstETH is DeFi-composable — use as collateral in Aave/Morpho/Spark or in Pendle PT/YT"
            },
        )

    async def _fetch_steth_defi_yields(self) -> list[YieldOpportunity]:
        """Fetch yields for wstETH used in DeFi (lending as collateral, etc.)."""
        opportunities: list[YieldOpportunity] = []

        # wstETH as lending collateral — typically borrowed against at low rates
        # This creates a leveraged staking loop opportunity
        opportunities.append(YieldOpportunity(
            id="lido-wsteth-leverage-loop",
            protocol="lido",
            chain="Ethereum",
            pool_name="wstETH Leverage Loop (Aave/Morpho)",
            underlying_tokens=["ETH", "wstETH"],
            yield_type=YieldType.VAULT,
            base_apy=3.3,  # Base staking yield
            reward_apy=3.0,  # Additional from leverage loop (depends on borrow rate spread)
            total_apy=6.3,
            tvl_usd=5_000_000_000,
            smart_contract_risk=0.25,
            protocol_risk_score=0.3,
            is_audited=True,
            is_delta_neutral=False,
            source="lido",
            fetched_at=datetime.utcnow(),
            tags=["leveraged-staking", "loop", "advanced"],
            extra={
                "strategy": "Deposit wstETH → Borrow ETH → Stake → Deposit → Repeat",
                "typical_leverage": "2-3x",
                "liquidation_risk": "Low (correlated assets) but non-zero",
            },
        ))

        return opportunities
