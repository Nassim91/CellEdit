"""Yield data source connectors.

Architecture:
- Primary meta-aggregators (DeFiLlama, Vaults.fyi) for broad coverage
- Native protocol sources (Aave, Compound, Morpho, Pendle) for deeper data
- Yield aggregator sources (Yearn, Zapper, 1inch) for vault yields
- Ecosystem sources (EigenLayer, Ethena, Maker, Lido) for specialized yields
- Market sources (Funding Rates, Convex/Curve) for basis trades and boosted yields
"""

from sentinel.sources.base import BaseYieldSource
from sentinel.sources.defillama import DefiLlamaSource
from sentinel.sources.vaults_fyi import VaultsFyiSource
from sentinel.sources.aave import AaveSource
from sentinel.sources.compound import CompoundSource
from sentinel.sources.pendle import PendleSource
from sentinel.sources.morpho import MorphoSource
from sentinel.sources.yearn import YearnSource
from sentinel.sources.eigenlayer import EigenLayerSource
from sentinel.sources.ethena import EthenaSource
from sentinel.sources.maker import MakerDSRSource
from sentinel.sources.zapper import ZapperSource
from sentinel.sources.oneinch import OneInchYieldSource
from sentinel.sources.funding_rates import FundingRatesSource
from sentinel.sources.convex_curve import ConvexCurveSource
from sentinel.sources.lido import LidoSource

__all__ = [
    "AaveSource",
    "BaseYieldSource",
    "CompoundSource",
    "ConvexCurveSource",
    "DefiLlamaSource",
    "EigenLayerSource",
    "EthenaSource",
    "FundingRatesSource",
    "LidoSource",
    "MakerDSRSource",
    "MorphoSource",
    "OneInchYieldSource",
    "PendleSource",
    "VaultsFyiSource",
    "YearnSource",
    "ZapperSource",
]
