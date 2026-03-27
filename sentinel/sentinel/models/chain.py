"""Blockchain chain definitions and configuration."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, HttpUrl


class Chain(str, Enum):
    """Supported blockchain networks."""

    ETHEREUM = "ethereum"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"
    BASE = "base"
    POLYGON = "polygon"
    AVALANCHE = "avalanche"
    BSC = "bsc"
    SOLANA = "solana"
    BLAST = "blast"
    SCROLL = "scroll"
    ZKSYNC = "zksync"
    LINEA = "linea"
    MANTLE = "mantle"
    MODE = "mode"

    @property
    def display_name(self) -> str:
        names = {
            "ethereum": "Ethereum",
            "arbitrum": "Arbitrum One",
            "optimism": "Optimism",
            "base": "Base",
            "polygon": "Polygon PoS",
            "avalanche": "Avalanche C-Chain",
            "bsc": "BNB Chain",
            "solana": "Solana",
            "blast": "Blast",
            "scroll": "Scroll",
            "zksync": "zkSync Era",
            "linea": "Linea",
            "mantle": "Mantle",
            "mode": "Mode",
        }
        return names.get(self.value, self.value.title())

    @property
    def defillama_id(self) -> str:
        """Chain identifier used by DeFiLlama."""
        mapping = {
            "ethereum": "Ethereum",
            "arbitrum": "Arbitrum",
            "optimism": "Optimism",
            "base": "Base",
            "polygon": "Polygon",
            "avalanche": "Avalanche",
            "bsc": "BSC",
            "solana": "Solana",
            "blast": "Blast",
            "scroll": "Scroll",
            "zksync": "zkSync Era",
            "linea": "Linea",
            "mantle": "Mantle",
            "mode": "Mode",
        }
        return mapping.get(self.value, self.value.title())


class ChainConfig(BaseModel):
    """Configuration for a blockchain network."""

    chain: Chain
    rpc_url: HttpUrl
    explorer_url: HttpUrl | None = None
    multicall_address: str | None = None
    block_time_seconds: float = 12.0
    native_token: str = "ETH"
    enabled: bool = True
