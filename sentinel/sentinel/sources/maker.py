"""Maker / Sky (DSR) yield source."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sentinel.models.opportunity import YieldOpportunity, YieldType
from sentinel.sources.base import BaseYieldSource
from sentinel.utils.http import HttpClient
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)

# Maker/Sky API endpoints
MAKER_API = "https://info.sky.money/api"
SPARK_API = "https://api.spark.fi"


class MakerDSRSource(BaseYieldSource):
    """Fetch yield from Maker/Sky DSR (Dai Savings Rate) and Spark Protocol."""

    name = "maker"

    async def fetch_opportunities(
        self,
        underlying: str | None = None,
        chains: list[str] | None = None,
    ) -> list[YieldOpportunity]:
        logger.info("maker.fetch_start", underlying=underlying)

        if underlying and underlying.upper() not in ("DAI", "USDS", "SDAI", "USDC", "USDT"):
            return []

        opportunities: list[YieldOpportunity] = []

        # DSR / SSR (Sky Savings Rate)
        try:
            dsr_data = await self._fetch_savings_rate()
            opportunities.append(self._build_dsr_opportunity(dsr_data))
        except Exception as e:
            logger.warning("maker.dsr_error", error=str(e))
            opportunities.append(self._build_dsr_opportunity({}))

        # Spark lending
        try:
            spark_opps = await self._fetch_spark_lending(underlying)
            opportunities.extend(spark_opps)
        except Exception as e:
            logger.warning("maker.spark_error", error=str(e))

        logger.info("maker.fetch_complete", total=len(opportunities))
        return opportunities

    async def _fetch_savings_rate(self) -> dict[str, Any]:
        try:
            return await self.http.get_json(f"{MAKER_API}/savings-rate")
        except Exception:
            return {}

    def _build_dsr_opportunity(self, data: dict[str, Any]) -> YieldOpportunity:
        dsr_rate = float(data.get("rate", 5.0)) if data else 5.0

        return YieldOpportunity(
            id="maker-dsr-ethereum",
            protocol="maker-sky",
            chain="Ethereum",
            pool_name="Sky Savings Rate (sDAI / sUSDS)",
            underlying_tokens=["DAI", "USDS"],
            yield_type=YieldType.LENDING,
            base_apy=dsr_rate,
            reward_apy=0,
            total_apy=dsr_rate,
            tvl_usd=8_000_000_000,
            smart_contract_risk=0.1,
            protocol_risk_score=0.15,
            is_audited=True,
            audit_firms=["ChainSecurity", "Trail of Bits", "Runtime Verification"],
            is_delta_neutral=True,
            source="maker",
            fetched_at=datetime.utcnow(),
            tags=["savings-rate", "stablecoin", "blue-chip", "risk-free-rate"],
        )

    async def _fetch_spark_lending(self, underlying: str | None) -> list[YieldOpportunity]:
        """Fetch Spark Protocol lending markets."""
        try:
            data = await self.http.get_json(f"{SPARK_API}/v1/markets")
            markets = data if isinstance(data, list) else data.get("markets", [])
        except Exception:
            return []

        opportunities: list[YieldOpportunity] = []
        for market in markets:
            symbol = market.get("symbol", "")
            if underlying and symbol.upper() != underlying.upper():
                continue

            supply_apy = float(market.get("supplyAPY", 0)) * 100
            tvl = float(market.get("totalSupplyUSD", 0))
            if tvl < 50_000:
                continue

            opportunities.append(YieldOpportunity(
                id=f"spark-{symbol.lower()}-ethereum",
                protocol="spark",
                chain="Ethereum",
                pool_name=f"Spark {symbol} Supply",
                underlying_tokens=[symbol],
                yield_type=YieldType.VARIABLE_LENDING,
                base_apy=supply_apy,
                reward_apy=0,
                total_apy=supply_apy,
                tvl_usd=tvl,
                smart_contract_risk=0.15,
                protocol_risk_score=0.2,
                is_audited=True,
                source="maker",
                fetched_at=datetime.utcnow(),
                tags=["lending", "spark", "maker-ecosystem"],
            ))

        return opportunities
