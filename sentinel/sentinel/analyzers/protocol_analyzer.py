"""Protocol analysis engine — TVL trends, risk assessment, and due diligence."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sentinel.models.protocol import Protocol, ProtocolCategory, ProtocolRisk
from sentinel.utils.http import HttpClient
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)

# Known protocol risk profiles (pre-computed for blue-chip protocols)
KNOWN_PROTOCOLS: dict[str, dict[str, Any]] = {
    "aave-v3": {
        "category": ProtocolCategory.LENDING,
        "audit_count": 10,
        "audit_firms": ["Trail of Bits", "OpenZeppelin", "Certora", "SigmaPrime", "Peckshield"],
        "has_bug_bounty": True,
        "bug_bounty_size_usd": 10_000_000,
        "is_upgradeable": True,
        "has_timelock": True,
        "timelock_delay_hours": 24,
        "has_governance": True,
        "time_live_days": 1200,
    },
    "compound-v3": {
        "category": ProtocolCategory.LENDING,
        "audit_count": 8,
        "audit_firms": ["OpenZeppelin", "Trail of Bits", "ChainSecurity"],
        "has_bug_bounty": True,
        "bug_bounty_size_usd": 5_000_000,
        "is_upgradeable": True,
        "has_timelock": True,
        "has_governance": True,
        "time_live_days": 1500,
    },
    "morpho-blue": {
        "category": ProtocolCategory.LENDING,
        "audit_count": 5,
        "audit_firms": ["Spearbit", "Trail of Bits"],
        "has_bug_bounty": True,
        "is_upgradeable": False,
        "has_governance": False,
        "time_live_days": 365,
    },
    "pendle": {
        "category": ProtocolCategory.YIELD_TOKENIZATION,
        "audit_count": 4,
        "audit_firms": ["Ackee", "Dedaub"],
        "has_bug_bounty": True,
        "is_upgradeable": True,
        "has_timelock": True,
        "has_governance": True,
        "time_live_days": 800,
    },
    "eigenlayer": {
        "category": ProtocolCategory.RESTAKING,
        "audit_count": 5,
        "audit_firms": ["Sigma Prime", "Trail of Bits", "Consensys Diligence"],
        "has_bug_bounty": True,
        "is_upgradeable": True,
        "has_timelock": True,
        "time_live_days": 500,
    },
    "ethena": {
        "category": ProtocolCategory.DERIVATIVES,
        "audit_count": 3,
        "audit_firms": ["Zellic", "Quantstamp"],
        "has_bug_bounty": True,
        "is_upgradeable": True,
        "is_centralized": True,  # Centralized custody of collateral
        "time_live_days": 300,
    },
    "maker-sky": {
        "category": ProtocolCategory.CDP,
        "audit_count": 15,
        "audit_firms": ["ChainSecurity", "Trail of Bits", "Runtime Verification", "ABDK"],
        "has_bug_bounty": True,
        "bug_bounty_size_usd": 10_000_000,
        "is_upgradeable": True,
        "has_timelock": True,
        "timelock_delay_hours": 48,
        "has_governance": True,
        "time_live_days": 2000,
    },
    "lido": {
        "category": ProtocolCategory.LIQUID_STAKING,
        "audit_count": 12,
        "audit_firms": ["Statemind", "Certora", "ChainSecurity", "Hexens", "Oxorio"],
        "has_bug_bounty": True,
        "bug_bounty_size_usd": 2_000_000,
        "is_upgradeable": True,
        "has_timelock": True,
        "has_governance": True,
        "time_live_days": 1400,
    },
}

# Known exploit history for risk assessment
EXPLOIT_HISTORY: dict[str, list[dict[str, Any]]] = {
    "euler": [{"date": "2023-03-13", "loss_usd": 197_000_000, "recovered": True}],
    "curve": [{"date": "2023-07-30", "loss_usd": 70_000_000, "recovered_pct": 73}],
    "balancer": [{"date": "2023-08-22", "loss_usd": 2_100_000}],
}


class ProtocolAnalyzer:
    """Analyzes DeFi protocols for risk, TVL trends, and operational security."""

    def __init__(self, http: HttpClient | None = None) -> None:
        self.http = http or HttpClient()
        self._defillama_api = "https://api.llama.fi"

    async def analyze(self, protocol_slug: str) -> Protocol:
        """Full protocol analysis including TVL, risk, and due diligence."""
        logger.info("protocol_analyzer.analyze", protocol=protocol_slug)

        # Fetch TVL and basic info from DeFiLlama
        dl_data = await self._fetch_defillama_protocol(protocol_slug)

        # Get known risk profile or build one
        known = KNOWN_PROTOCOLS.get(protocol_slug, {})

        # Build risk profile
        risk = self._build_risk(known, dl_data, protocol_slug)

        # Build protocol model
        protocol = Protocol(
            name=dl_data.get("name", protocol_slug),
            slug=protocol_slug,
            category=known.get("category", ProtocolCategory.OTHER),
            chains=dl_data.get("chains", []),
            url=dl_data.get("url"),
            logo_url=dl_data.get("logo"),
            twitter_handle=dl_data.get("twitter"),
            tvl_usd=float(dl_data.get("tvl", 0) or 0),
            tvl_change_7d_pct=self._calc_tvl_change(dl_data, 7),
            tvl_change_30d_pct=self._calc_tvl_change(dl_data, 30),
            market_cap_usd=float(dl_data.get("mcap", 0) or 0) or None,
            fdv_usd=float(dl_data.get("fdv", 0) or 0) or None,
            risk=risk,
            defillama_id=dl_data.get("id"),
            gecko_id=dl_data.get("gecko_id"),
        )

        logger.info(
            "protocol_analyzer.complete",
            protocol=protocol_slug,
            risk_level=risk.risk_level.value,
            risk_score=f"{risk.overall_risk_score:.2f}",
        )

        return protocol

    async def analyze_batch(self, slugs: list[str]) -> dict[str, Protocol]:
        """Analyze multiple protocols."""
        import asyncio

        tasks = [self.analyze(slug) for slug in slugs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        protocols: dict[str, Protocol] = {}
        for slug, result in zip(slugs, results):
            if isinstance(result, Protocol):
                protocols[slug] = result
            else:
                logger.warning("protocol_analyzer.batch_error", protocol=slug, error=str(result))

        return protocols

    async def _fetch_defillama_protocol(self, slug: str) -> dict[str, Any]:
        """Fetch protocol data from DeFiLlama."""
        try:
            return await self.http.get_json(f"{self._defillama_api}/protocol/{slug}")
        except Exception as e:
            logger.warning("protocol_analyzer.defillama_error", slug=slug, error=str(e))
            return {"name": slug, "slug": slug}

    def _build_risk(
        self, known: dict[str, Any], dl_data: dict[str, Any], slug: str
    ) -> ProtocolRisk:
        """Build a comprehensive risk profile."""
        exploits = EXPLOIT_HISTORY.get(slug, [])
        total_losses = sum(e.get("loss_usd", 0) for e in exploits)

        tvl = float(dl_data.get("tvl", 0) or 0)

        return ProtocolRisk(
            audit_count=known.get("audit_count", 0),
            audit_firms=known.get("audit_firms", []),
            has_bug_bounty=known.get("has_bug_bounty", False),
            bug_bounty_size_usd=known.get("bug_bounty_size_usd"),
            is_open_source=known.get("is_open_source", True),
            time_live_days=known.get("time_live_days", 0),
            is_upgradeable=known.get("is_upgradeable", True),
            has_timelock=known.get("has_timelock", False),
            timelock_delay_hours=known.get("timelock_delay_hours"),
            multisig_threshold=known.get("multisig_threshold"),
            has_governance=known.get("has_governance", False),
            is_centralized=known.get("is_centralized", False),
            tvl_usd=tvl,
            tvl_change_7d_pct=self._calc_tvl_change(dl_data, 7),
            tvl_change_30d_pct=self._calc_tvl_change(dl_data, 30),
            exploit_history=exploits,
            total_exploit_losses_usd=total_losses,
        )

    def _calc_tvl_change(self, dl_data: dict[str, Any], days: int) -> float | None:
        """Calculate TVL percentage change over N days from DeFiLlama historical data."""
        tvl_history = dl_data.get("tvl", [])
        if not isinstance(tvl_history, list) or len(tvl_history) < 2:
            return None

        current = float(tvl_history[-1].get("totalLiquidityUSD", 0))
        if current == 0:
            return None

        target_ts = (datetime.utcnow() - timedelta(days=days)).timestamp()
        closest = min(tvl_history, key=lambda x: abs(float(x.get("date", 0)) - target_ts))
        past = float(closest.get("totalLiquidityUSD", 0))

        if past == 0:
            return None

        return ((current - past) / past) * 100

    async def close(self) -> None:
        await self.http.close()
