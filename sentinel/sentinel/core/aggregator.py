"""Cross-chain yield aggregator — discovers and ranks all yield opportunities."""

from __future__ import annotations

import asyncio
from typing import Any

from sentinel.config.settings import Settings, get_settings
from sentinel.models.opportunity import YieldOpportunity
from sentinel.sources.aave import AaveSource
from sentinel.sources.base import BaseYieldSource
from sentinel.sources.compound import CompoundSource
from sentinel.sources.defillama import DefiLlamaSource
from sentinel.sources.eigenlayer import EigenLayerSource
from sentinel.sources.ethena import EthenaSource
from sentinel.sources.maker import MakerDSRSource
from sentinel.sources.morpho import MorphoSource
from sentinel.sources.oneinch import OneInchYieldSource
from sentinel.sources.pendle import PendleSource
from sentinel.sources.vaults_fyi import VaultsFyiSource
from sentinel.sources.yearn import YearnSource
from sentinel.sources.zapper import ZapperSource
from sentinel.utils.http import HttpClient
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)


class YieldAggregator:
    """Aggregates yield opportunities from all data sources with cross-chain support.

    This is the heart of the Sentinel agent — it queries every configured source
    in parallel, deduplicates results, applies filters, and ranks opportunities.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._http = HttpClient(
            timeout=self.settings.defillama.request_timeout,
            max_retries=self.settings.defillama.max_retries,
        )
        self._sources: list[BaseYieldSource] = self._build_sources()

    def _build_sources(self) -> list[BaseYieldSource]:
        """Initialize all yield data sources.

        Sources are organized in layers:
        1. Meta-aggregators (DeFiLlama, Vaults.fyi) — broad coverage
        2. Native protocol sources (Aave, Compound, Morpho, Pendle) — deeper data
        3. Yield aggregators (Yearn, Zapper, 1inch) — vault yields
        4. Ecosystem sources (EigenLayer, Ethena, Maker) — specialized yields
        """
        return [
            # Layer 1: Meta-aggregators (highest coverage)
            DefiLlamaSource(
                http=self._http,
                base_url=self.settings.defillama.base_url,
                api_url=self.settings.defillama.api_url,
                min_tvl=self.settings.filters.min_tvl_usd,
            ),
            VaultsFyiSource(http=self._http),

            # Layer 2: Native protocol sources (deeper data, more accurate APYs)
            AaveSource(http=self._http),
            CompoundSource(http=self._http),
            MorphoSource(http=self._http),
            PendleSource(http=self._http),

            # Layer 3: Yield aggregators
            YearnSource(http=self._http),
            ZapperSource(http=self._http),
            OneInchYieldSource(http=self._http),

            # Layer 4: Ecosystem-specific sources
            EigenLayerSource(http=self._http),
            EthenaSource(http=self._http),
            MakerDSRSource(http=self._http),
        ]

    async def discover(
        self,
        underlying: str,
        size_usd: float,
        chains: list[str] | None = None,
    ) -> list[YieldOpportunity]:
        """Discover all yield opportunities for an underlying asset and size.

        Args:
            underlying: Token symbol (e.g., "ETH", "USDC")
            size_usd: Target allocation size in USD
            chains: Optional chain filter. Defaults to all enabled chains.

        Returns:
            Sorted list of yield opportunities, best risk-adjusted yield first.
        """
        chain_list = chains or [c.value for c in self.settings.enabled_chains]

        logger.info(
            "aggregator.discover",
            underlying=underlying,
            size_usd=size_usd,
            chains=chain_list,
        )

        # Query all sources in parallel
        tasks = [
            self._safe_fetch(source, underlying, chain_list)
            for source in self._sources
        ]
        results = await asyncio.gather(*tasks)

        # Flatten results
        all_opportunities: list[YieldOpportunity] = []
        for source_name, opps in results:
            logger.info("aggregator.source_result", source=source_name, count=len(opps))
            all_opportunities.extend(opps)

        # Deduplicate (same protocol + chain + pool can appear in both DeFiLlama and native source)
        deduped = self._deduplicate(all_opportunities)

        # Apply filters
        filtered = self._apply_filters(deduped, underlying, size_usd)

        # Sort by risk-adjusted APY descending
        filtered.sort(key=lambda o: o.risk_adjusted_apy, reverse=True)

        logger.info(
            "aggregator.discover_complete",
            total_raw=len(all_opportunities),
            deduped=len(deduped),
            filtered=len(filtered),
        )

        return filtered

    async def _safe_fetch(
        self, source: BaseYieldSource, underlying: str, chains: list[str]
    ) -> tuple[str, list[YieldOpportunity]]:
        """Safely fetch from a source, catching errors."""
        try:
            opps = await asyncio.wait_for(
                source.fetch_opportunities(underlying=underlying, chains=chains),
                timeout=self.settings.defillama.request_timeout,
            )
            return (source.name, opps)
        except asyncio.TimeoutError:
            logger.warning("aggregator.source_timeout", source=source.name)
            return (source.name, [])
        except Exception as e:
            logger.warning("aggregator.source_error", source=source.name, error=str(e))
            return (source.name, [])

    def _deduplicate(self, opportunities: list[YieldOpportunity]) -> list[YieldOpportunity]:
        """Remove duplicate opportunities, preferring native source data over aggregator data."""
        seen: dict[str, YieldOpportunity] = {}

        for opp in opportunities:
            # Create a dedup key based on protocol + chain + pool
            key = f"{opp.protocol}:{opp.chain}:{opp.pool_name}".lower()

            if key not in seen:
                seen[key] = opp
            else:
                existing = seen[key]
                # Prefer native source over defillama
                if existing.source == "defillama" and opp.source != "defillama":
                    seen[key] = opp

        return list(seen.values())

    def _apply_filters(
        self,
        opportunities: list[YieldOpportunity],
        underlying: str,
        size_usd: float,
    ) -> list[YieldOpportunity]:
        """Apply configuration filters to opportunities."""
        filters = self.settings.filters
        result: list[YieldOpportunity] = []

        for opp in opportunities:
            # Min TVL
            if opp.tvl_usd < filters.min_tvl_usd:
                continue

            # Min APY
            if opp.total_apy < filters.min_apy:
                continue

            # Max risk
            if opp.protocol_risk_score > filters.max_risk_score:
                continue

            # Excluded protocols
            if opp.protocol.lower() in {p.lower() for p in filters.excluded_protocols}:
                continue

            # Excluded chains
            if opp.chain.lower() in {c.lower() for c in filters.excluded_chains}:
                continue

            # Only audited
            if filters.only_audited and not opp.is_audited:
                continue

            # Size capacity check
            if not opp.fits_size(size_usd):
                continue

            result.append(opp)

        return result

    async def close(self) -> None:
        """Clean up HTTP connections."""
        await self._http.close()
