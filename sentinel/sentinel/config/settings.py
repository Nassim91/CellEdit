"""Application settings loaded from environment variables using pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from sentinel.models.chain import Chain


class RPCConfig(BaseSettings):
    """RPC endpoint configuration per chain. Loaded from RPC_* env vars."""

    model_config = SettingsConfigDict(env_prefix="RPC_")

    ethereum: str = "https://eth.llamarpc.com"
    arbitrum: str = "https://arb1.arbitrum.io/rpc"
    optimism: str = "https://mainnet.optimism.io"
    base: str = "https://mainnet.base.org"
    polygon: str = "https://polygon-rpc.com"
    avalanche: str = "https://api.avax.network/ext/bc/C/rpc"
    bsc: str = "https://bsc-dataseed.binance.org"
    solana: str = "https://api.mainnet-beta.solana.com"

    def get_rpc(self, chain: Chain) -> str | None:
        return getattr(self, chain.value, None)


class TwitterConfig(BaseSettings):
    """Twitter API configuration. Loaded from TWITTER_* env vars."""

    model_config = SettingsConfigDict(env_prefix="TWITTER_")

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


class DefiLlamaConfig(BaseSettings):
    """DeFiLlama API configuration. Loaded from DEFILLAMA_* env vars."""

    model_config = SettingsConfigDict(env_prefix="DEFILLAMA_")

    base_url: str = "https://yields.llama.fi"
    api_url: str = "https://api.llama.fi"
    coins_url: str = "https://coins.llama.fi"
    stablecoins_url: str = "https://stablecoins.llama.fi"
    api_key: str | None = None  # Pro API key for yields endpoints
    request_timeout: int = 30
    max_retries: int = 3

    @property
    def pro_base_url(self) -> str | None:
        """Pro API URL with embedded key."""
        if self.api_key:
            return f"https://pro-api.llama.fi/{self.api_key}"
        return None

    @property
    def yields_url(self) -> str:
        """Use Pro API for yields if key is available, otherwise fallback."""
        if self.pro_base_url:
            return f"{self.pro_base_url}/yields"
        return self.base_url


class FundingRatesConfig(BaseSettings):
    """Funding rate source configuration. Loaded from FUNDING_* env vars."""

    model_config = SettingsConfigDict(env_prefix="FUNDING_")

    binance_enabled: bool = True
    bybit_enabled: bool = True
    dydx_enabled: bool = True
    hyperliquid_enabled: bool = True
    min_funding_rate_annualized: float = 2.0  # Minimum annualized rate to consider


class FilterConfig(BaseSettings):
    """Default filters for yield discovery. Loaded from FILTER_* env vars."""

    model_config = SettingsConfigDict(env_prefix="FILTER_")

    min_tvl_usd: float = 100_000
    min_apy: float = 0.5
    max_risk_score: float = 0.8
    max_protocol_age_days: int | None = None
    min_protocol_age_days: int = 0
    excluded_protocols: list[str] = Field(default_factory=list)
    excluded_chains: list[str] = Field(default_factory=list)
    only_audited: bool = False


class Settings(BaseSettings):
    """Global Sentinel settings. Auto-loaded from .env file and env vars."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

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
    funding_rates: FundingRatesConfig = Field(default_factory=FundingRatesConfig)
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
