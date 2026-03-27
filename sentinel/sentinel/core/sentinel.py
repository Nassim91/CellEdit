"""Sentinel Agent — the main orchestrator that ties everything together.

Given an underlying token and a target size, Sentinel will:
1. Discover all yield opportunities across chains and protocols
2. Analyze protocols for risk and operational security
3. Score and rank opportunities by risk-adjusted yield
4. Generate market-neutral strategy recommendations
5. Scrape social sentiment for alpha and momentum signals
6. Produce a comprehensive report for asset managers
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from sentinel.analyzers.protocol_analyzer import ProtocolAnalyzer
from sentinel.analyzers.risk_scorer import RiskScorer
from sentinel.config.settings import Settings, get_settings
from sentinel.core.aggregator import YieldAggregator
from sentinel.models.opportunity import YieldOpportunity
from sentinel.models.report import SentinelReport
from sentinel.models.sentiment import ProtocolMomentum
from sentinel.reports.generator import ReportGenerator
from sentinel.scrapers.sentiment_analyzer import SentimentAnalyzer
from sentinel.scrapers.twitter_scraper import TwitterScraper
from sentinel.strategies.engine import StrategyEngine
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)


class SentinelAgent:
    """The Sentinel Yield Intelligence Agent.

    Usage:
        agent = SentinelAgent()
        report = await agent.analyze("ETH", size_usd=1_000_000)
        agent.print_report(report)
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.aggregator = YieldAggregator(self.settings)
        self.protocol_analyzer = ProtocolAnalyzer()
        self.risk_scorer = RiskScorer()
        self.strategy_engine = StrategyEngine()
        self.twitter_scraper = TwitterScraper(config=self.settings.twitter)
        self.sentiment_analyzer = SentimentAnalyzer()
        self.report_generator = ReportGenerator(self.settings.report_output_dir)

    async def analyze(
        self,
        underlying: str,
        size_usd: float,
        chains: list[str] | None = None,
        include_sentiment: bool = True,
        top_n: int = 25,
    ) -> SentinelReport:
        """Run a full Sentinel analysis.

        Args:
            underlying: Token symbol (e.g., "ETH", "USDC", "WBTC")
            size_usd: Target allocation size in USD
            chains: Optional chain filter
            include_sentiment: Whether to scrape Twitter for sentiment
            top_n: Number of top opportunities to include in report

        Returns:
            Complete SentinelReport with opportunities, strategies, and sentiment.
        """
        report_id = f"sentinel-{underlying.lower()}-{uuid.uuid4().hex[:8]}"

        logger.info(
            "sentinel.analyze_start",
            report_id=report_id,
            underlying=underlying,
            size_usd=size_usd,
        )

        chain_list = chains or [c.value for c in self.settings.enabled_chains]

        # Phase 1: Discover yield opportunities (parallel)
        logger.info("sentinel.phase_1", phase="yield_discovery")
        opportunities = await self.aggregator.discover(underlying, size_usd, chain_list)

        # Phase 2: Protocol analysis and risk scoring (parallel)
        logger.info("sentinel.phase_2", phase="risk_analysis")
        opportunities = await self._enrich_with_risk(opportunities)

        # Phase 3: Strategy generation
        logger.info("sentinel.phase_3", phase="strategy_generation")
        strategies = self.strategy_engine.generate_strategies(opportunities, underlying, size_usd)

        # Phase 4: Social sentiment (parallel, optional)
        sentiment_summary = None
        trending_protocols: list[str] = []
        sentiment_signals: list[dict[str, Any]] = []

        if include_sentiment:
            logger.info("sentinel.phase_4", phase="sentiment_analysis")
            try:
                sentiment_data = await self._analyze_sentiment(opportunities)
                sentiment_summary = sentiment_data.get("summary", "")
                trending_protocols = sentiment_data.get("trending", [])
                sentiment_signals = sentiment_data.get("signals", [])
            except Exception as e:
                logger.warning("sentinel.sentiment_error", error=str(e))

        # Phase 5: Build report
        logger.info("sentinel.phase_5", phase="report_generation")

        # Select top opportunities
        top_opportunities = opportunities[:top_n]

        # Generate warnings
        warnings = self._check_concentration(top_opportunities, size_usd)

        report = SentinelReport(
            report_id=report_id,
            generated_at=datetime.utcnow(),
            underlying=underlying,
            target_size_usd=size_usd,
            chains_analyzed=chain_list,
            total_opportunities_found=len(opportunities),
            opportunities=opportunities,
            top_opportunities=top_opportunities,
            strategies=strategies,
            sentiment_summary=sentiment_summary,
            trending_protocols=trending_protocols,
            sentiment_signals=sentiment_signals,
            concentration_warnings=warnings,
        )

        logger.info(
            "sentinel.analyze_complete",
            report_id=report_id,
            opportunities=len(opportunities),
            strategies=len(strategies),
            top_apy=f"{top_opportunities[0].total_apy:.2f}%" if top_opportunities else "N/A",
        )

        return report

    async def _enrich_with_risk(
        self, opportunities: list[YieldOpportunity]
    ) -> list[YieldOpportunity]:
        """Analyze protocols and update risk scores on opportunities."""
        # Get unique protocols to analyze
        protocol_slugs = list({opp.protocol for opp in opportunities})

        # Batch analyze protocols
        protocols = await self.protocol_analyzer.analyze_batch(protocol_slugs)

        # Update risk scores
        for opp in opportunities:
            protocol = protocols.get(opp.protocol)
            risk_score = self.risk_scorer.score_opportunity(opp, protocol)
            opp.protocol_risk_score = risk_score
            opp.smart_contract_risk = risk_score

        # Re-sort by risk-adjusted APY
        opportunities.sort(key=lambda o: o.risk_adjusted_apy, reverse=True)

        return opportunities

    async def _analyze_sentiment(
        self, opportunities: list[YieldOpportunity]
    ) -> dict[str, Any]:
        """Analyze social sentiment for top protocols in our opportunity set."""
        # Get top protocols by TVL
        protocol_tvl: dict[str, float] = {}
        for opp in opportunities:
            protocol_tvl[opp.protocol] = protocol_tvl.get(opp.protocol, 0) + opp.tvl_usd

        top_protocols = sorted(protocol_tvl.keys(), key=lambda p: protocol_tvl[p], reverse=True)[:10]

        # Compute momentum for each
        tasks = [
            self.twitter_scraper.compute_protocol_momentum(p, hours=24)
            for p in top_protocols
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        momentums: list[ProtocolMomentum] = []
        for result in results:
            if isinstance(result, ProtocolMomentum):
                momentums.append(result)

        # Build summary
        trending = [m.protocol for m in momentums if m.is_trending]
        bullish = [m for m in momentums if m.bullish_pct > 0.6]
        bearish = [m for m in momentums if m.bearish_pct > 0.4]

        summary_parts = []
        if trending:
            summary_parts.append(f"Trending on CT: {', '.join(trending)}.")
        if bullish:
            summary_parts.append(f"Strong bullish sentiment: {', '.join(m.protocol for m in bullish)}.")
        if bearish:
            summary_parts.append(f"Caution — bearish signals: {', '.join(m.protocol for m in bearish)}.")
        if not summary_parts:
            summary_parts.append("No strong sentiment signals detected in the past 24h.")

        signals = []
        for m in momentums:
            signals.append({
                "protocol": m.protocol,
                "momentum": m.momentum_score,
                "mentions": m.total_mentions,
                "bullish_pct": m.bullish_pct,
                "bearish_pct": m.bearish_pct,
                "is_trending": m.is_trending,
            })

        return {
            "summary": " ".join(summary_parts),
            "trending": trending,
            "signals": signals,
        }

    def _check_concentration(
        self, opportunities: list[YieldOpportunity], size_usd: float
    ) -> list[str]:
        """Check for portfolio concentration risks."""
        warnings: list[str] = []

        if not opportunities:
            warnings.append("No yield opportunities found matching your criteria.")
            return warnings

        # Single protocol dominance
        protocol_count: dict[str, int] = {}
        for opp in opportunities[:10]:
            protocol_count[opp.protocol] = protocol_count.get(opp.protocol, 0) + 1

        for protocol, count in protocol_count.items():
            if count >= 5:
                warnings.append(
                    f"High concentration in {protocol} ({count} of top 10 opportunities). "
                    "Consider diversifying across protocols."
                )

        # Single chain dominance
        chain_count: dict[str, int] = {}
        for opp in opportunities[:10]:
            chain_count[opp.chain] = chain_count.get(opp.chain, 0) + 1

        for chain, count in chain_count.items():
            if count >= 7:
                warnings.append(
                    f"Heavy concentration on {chain} ({count} of top 10). "
                    "Cross-chain diversification recommended."
                )

        # Size vs TVL warnings
        for opp in opportunities[:5]:
            if size_usd > opp.tvl_usd * 0.1:
                warnings.append(
                    f"Your size (${size_usd:,.0f}) is >{10}% of {opp.protocol} {opp.pool_name} "
                    f"TVL (${opp.tvl_usd:,.0f}). Consider splitting across venues."
                )

        # Unsustainable yield warnings
        for opp in opportunities[:5]:
            if opp.total_apy > 50:
                warnings.append(
                    f"{opp.protocol} {opp.pool_name} shows {opp.total_apy:.0f}% APY — "
                    "this may be unsustainable or incentive-driven."
                )

        return warnings

    def print_report(self, report: SentinelReport) -> None:
        """Print report to console with rich formatting."""
        self.report_generator.print_console_report(report)

    def export_report(self, report: SentinelReport, fmt: str = "json") -> str:
        """Export report to file. Returns the file path."""
        if fmt == "html":
            path = self.report_generator.export_html(report)
        else:
            path = self.report_generator.export_json(report)
        return str(path)

    async def close(self) -> None:
        """Clean up all resources."""
        await self.aggregator.close()
        await self.protocol_analyzer.close()
        await self.twitter_scraper.close()
