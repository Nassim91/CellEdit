"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from sentinel.models.chain import Chain


class RPCConfig(BaseModel):
    """RPC endpoint configuration per chain."""

    ethereum: str = "https://eth.llamarpc.com"
    arbitrum: str = "https://arb1.arbitrum.io/rpc"
    optimism: str = "https://mainnet.optimism.io"
    base: str = "https://mainnet.base.org"
    polygon: str = "https://polygon-rpc.com"
    avalanche: str = "https://api.avax.network/ext/bc/C/rpc"
    bsc: str = "https://bsc-dataseed.binance.org"

    def get_rpc(self, chain: Chain) -> str | None:
        return getattr(self, chain.value, None)


class TwitterConfig(BaseModel):
    """Twitter API configuration."""

    bearer_token: str | None = None
    api_key: str | None = None
    api_secret: str | None = None
    enabled: bool = False

    # Scraping parameters
    max_tweets_per_query: int = 100
    influencer_min_followers: int = 10_000
    search_queries: list[str] = Field(
        default_factory=lambda: [
            "DeFi yield",
            "yield farming",
            "liquid staking",
            "restaking",
            "Pendle",
            "Morpho",
            "EigenLayer",
            "Ethena",
            "basis trade crypto",
            "delta neutral DeFi",
            "new DeFi protocol",
            "DeFi alpha",
        ]
    )


class DefiLlamaConfig(BaseModel):
    """DeFiLlama API configuration."""

    base_url: str = "https://yields.llama.fi"
    api_url: str = "https://api.llama.fi"
    coins_url: str = "https://coins.llama.fi"
    stablecoins_url: str = "https://stablecoins.llama.fi"
    request_timeout: int = 30
    max_retries: int = 3


class FilterConfig(BaseModel):
    """Default filters for yield discovery."""

    min_tvl_usd: float = 100_000
    min_apy: float = 0.5
    max_risk_score: float = 0.8
    max_protocol_age_days: int | None = None
    min_protocol_age_days: int = 0
    excluded_protocols: list[str] = Field(default_factory=list)
    excluded_chains: list[str] = Field(default_factory=list)
    only_audited: bool = False


class Settings(BaseModel):
    """Global Sentinel settings."""

    # Chains to scan
    enabled_chains: list[Chain] = Field(
        default_factory=lambda: [
            Chain.ETHEREUM,
            Chain.ARBITRUM,
            Chain.OPTIMISM,
            Chain.BASE,
            Chain.POLYGON,
            Chain.AVALANCHE,
            Chain.BSC,
        ]
    )

    # Sub-configs
    rpc: RPCConfig = Field(default_factory=RPCConfig)
    twitter: TwitterConfig = Field(default_factory=TwitterConfig)
    defillama: DefiLlamaConfig = Field(default_factory=DefiLlamaConfig)
    filters: FilterConfig = Field(default_factory=FilterConfig)

    # Output
    report_output_dir: Path = Path("./reports")
    log_level: str = "INFO"

    # Performance
    max_concurrent_requests: int = 10
    cache_ttl_seconds: int = 300


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
