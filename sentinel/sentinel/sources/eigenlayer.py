"""EigenLayer restaking yield source."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sentinel.models.opportunity import YieldOpportunity, YieldType
from sentinel.sources.base import BaseYieldSource
from sentinel.utils.http import HttpClient
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)

EIGENLAYER_API = "https://api.eigenlayer.xyz"

# Known AVS (Actively Validated Services) and their estimated yields
KNOWN_AVS: list[dict[str, Any]] = [
    {"name": "EigenDA", "estimated_apy": 3.0, "risk": "low"},
    {"name": "Omni Network", "estimated_apy": 5.0, "risk": "medium"},
    {"name": "AltLayer", "estimated_apy": 4.0, "risk": "medium"},
    {"name": "Brevis", "estimated_apy": 3.5, "risk": "medium"},
    {"name": "Lagrange", "estimated_apy": 4.5, "risk": "medium"},
]

# Known Liquid Restaking Tokens
LRT_PROTOCOLS: dict[str, dict[str, Any]] = {
    "ether.fi": {
        "token": "eETH",
        "estimated_apy_boost": 2.0,
        "tvl_usd": 5_000_000_000,
        "points": True,
    },
    "renzo": {
        "token": "ezETH",
        "estimated_apy_boost": 2.5,
        "tvl_usd": 2_000_000_000,
        "points": True,
    },
    "puffer": {
        "token": "pufETH",
        "estimated_apy_boost": 2.0,
        "tvl_usd": 1_500_000_000,
        "points": True,
    },
    "kelp": {
        "token": "rsETH",
        "estimated_apy_boost": 2.0,
        "tvl_usd": 1_000_000_000,
        "points": True,
    },
    "swell": {
        "token": "rswETH",
        "estimated_apy_boost": 2.0,
        "tvl_usd": 800_000_000,
        "points": True,
    },
}


class EigenLayerSource(BaseYieldSource):
    """Fetch restaking opportunities from EigenLayer ecosystem."""

    name = "eigenlayer"

    async def fetch_opportunities(
        self,
        underlying: str | None = None,
        chains: list[str] | None = None,
    ) -> list[YieldOpportunity]:
        logger.info("eigenlayer.fetch_start", underlying=underlying)

        if underlying and underlying.upper() not in ("ETH", "WETH", "STETH", "WSTETH", "CBETH", "RETH"):
            return []  # EigenLayer is ETH-only

        opportunities: list[YieldOpportunity] = []

        # Native restaking
        opportunities.append(self._native_restaking())

        # LRT protocols
        for protocol, info in LRT_PROTOCOLS.items():
            opportunities.append(self._lrt_opportunity(protocol, info))

        # AVS yield estimates (on top of base staking)
        for avs in KNOWN_AVS:
            opportunities.append(self._avs_opportunity(avs))

        logger.info("eigenlayer.fetch_complete", total=len(opportunities))
        return opportunities

    def _native_restaking(self) -> YieldOpportunity:
        eth_staking_apy = 3.5  # Base ETH staking APY

        return YieldOpportunity(
            id="eigenlayer-native-restaking",
            protocol="eigenlayer",
            chain="Ethereum",
            pool_name="EigenLayer Native Restaking (ETH)",
            underlying_tokens=["ETH"],
            yield_type=YieldType.RESTAKING,
            base_apy=eth_staking_apy,
            reward_apy=2.0,  # Estimated AVS rewards
            total_apy=eth_staking_apy + 2.0,
            tvl_usd=15_000_000_000,
            smart_contract_risk=0.3,
            protocol_risk_score=0.3,
            is_audited=True,
            audit_firms=["Sigma Prime", "Trail of Bits"],
            source="eigenlayer",
            fetched_at=datetime.utcnow(),
            tags=["restaking", "points", "avs"],
        )

    def _lrt_opportunity(self, protocol: str, info: dict[str, Any]) -> YieldOpportunity:
        eth_staking_apy = 3.5
        total = eth_staking_apy + info["estimated_apy_boost"]

        tags = ["liquid-restaking", "restaking"]
        if info.get("points"):
            tags.append("points")

        return YieldOpportunity(
            id=f"eigenlayer-lrt-{protocol}",
            protocol=protocol,
            chain="Ethereum",
            pool_name=f"{protocol.title()} {info['token']} Restaking",
            underlying_tokens=["ETH", info["token"]],
            yield_type=YieldType.RESTAKING,
            base_apy=eth_staking_apy,
            reward_apy=info["estimated_apy_boost"],
            total_apy=total,
            tvl_usd=info["tvl_usd"],
            smart_contract_risk=0.35,
            protocol_risk_score=0.35,
            is_audited=True,
            source="eigenlayer",
            fetched_at=datetime.utcnow(),
            tags=tags,
        )

    def _avs_opportunity(self, avs: dict[str, Any]) -> YieldOpportunity:
        risk_map = {"low": 0.25, "medium": 0.4, "high": 0.6}

        return YieldOpportunity(
            id=f"eigenlayer-avs-{avs['name'].lower().replace(' ', '-')}",
            protocol="eigenlayer",
            chain="Ethereum",
            pool_name=f"EigenLayer AVS: {avs['name']}",
            underlying_tokens=["ETH"],
            yield_type=YieldType.RESTAKING,
            base_apy=3.5,  # ETH staking base
            reward_apy=avs["estimated_apy"],
            total_apy=3.5 + avs["estimated_apy"],
            tvl_usd=1_000_000_000,
            smart_contract_risk=risk_map.get(avs["risk"], 0.5),
            protocol_risk_score=risk_map.get(avs["risk"], 0.5),
            source="eigenlayer",
            fetched_at=datetime.utcnow(),
            tags=["avs", "restaking"],
        )
