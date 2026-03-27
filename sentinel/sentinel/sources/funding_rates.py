"""Perpetual futures funding rate source — CEX and DEX funding rates for basis trade analysis.

Aggregates funding rates from:
- Binance (USDT-margined perps)
- Bybit (USDT and USDC perps)
- dYdX v4 (decentralized perps)
- Hyperliquid (decentralized perps on L1)

These rates are critical for:
1. Basis trade strategies (spot long + perp short)
2. Funding rate arbitrage between venues
3. Market sentiment indicator (positive = bullish, negative = bearish)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sentinel.models.opportunity import YieldOpportunity, YieldType
from sentinel.sources.base import BaseYieldSource
from sentinel.utils.http import HttpClient
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)

# API endpoints
BINANCE_API = "https://fapi.binance.com"
BYBIT_API = "https://api.bybit.com"
DYDX_API = "https://indexer.dydx.trade"
HYPERLIQUID_API = "https://api.hyperliquid.xyz"

# Common perp trading pairs
TRACKED_SYMBOLS = [
    "BTC", "ETH", "SOL", "ARB", "OP", "AVAX", "MATIC", "LINK",
    "MKR", "AAVE", "UNI", "CRV", "LDO", "PENDLE", "ENA", "EIGEN",
    "DYDX", "GMX", "SNX", "RUNE", "INJ", "TIA", "JTO", "JUP",
    "WLD", "STRK", "NEAR", "ATOM", "DOT", "SUI", "APT", "SEI",
]


class FundingRateEntry:
    """A single funding rate observation."""

    def __init__(
        self,
        symbol: str,
        venue: str,
        funding_rate: float,
        annualized_rate: float,
        next_funding_time: datetime | None = None,
        mark_price: float = 0.0,
        open_interest_usd: float = 0.0,
    ) -> None:
        self.symbol = symbol
        self.venue = venue
        self.funding_rate = funding_rate  # Per-period rate (8h for CEX, 1h for some DEX)
        self.annualized_rate = annualized_rate
        self.next_funding_time = next_funding_time
        self.mark_price = mark_price
        self.open_interest_usd = open_interest_usd


class FundingRatesSource(BaseYieldSource):
    """Aggregates perpetual futures funding rates from CEX and DEX venues.

    Funding rates represent the cost of holding a perpetual position.
    When positive: longs pay shorts → basis trade opportunity (short perp, long spot).
    When negative: shorts pay longs → reverse basis trade.

    A consistently positive funding rate can be captured as yield by:
    1. Buying spot asset (or yield-bearing variant like stETH)
    2. Shorting perpetual future of same size
    3. Collecting funding payments while being delta-neutral
    """

    name = "funding_rates"

    def __init__(
        self,
        http: HttpClient | None = None,
        binance_enabled: bool = True,
        bybit_enabled: bool = True,
        dydx_enabled: bool = True,
        hyperliquid_enabled: bool = True,
        min_annualized_rate: float = 2.0,
    ) -> None:
        super().__init__(http)
        self.binance_enabled = binance_enabled
        self.bybit_enabled = bybit_enabled
        self.dydx_enabled = dydx_enabled
        self.hyperliquid_enabled = hyperliquid_enabled
        self.min_annualized_rate = min_annualized_rate

    async def fetch_opportunities(
        self,
        underlying: str | None = None,
        chains: list[str] | None = None,
    ) -> list[YieldOpportunity]:
        """Fetch funding rate opportunities across all enabled venues."""
        logger.info("funding_rates.fetch_start", underlying=underlying)

        all_rates: list[FundingRateEntry] = []

        # Fetch from all venues in parallel
        import asyncio

        tasks = []
        if self.binance_enabled:
            tasks.append(self._fetch_binance(underlying))
        if self.bybit_enabled:
            tasks.append(self._fetch_bybit(underlying))
        if self.dydx_enabled:
            tasks.append(self._fetch_dydx(underlying))
        if self.hyperliquid_enabled:
            tasks.append(self._fetch_hyperliquid(underlying))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                all_rates.extend(result)
            elif isinstance(result, Exception):
                logger.debug("funding_rates.venue_error", error=str(result))

        # Convert to yield opportunities
        opportunities = self._rates_to_opportunities(all_rates, underlying)

        # Also generate cross-venue arbitrage opportunities
        arb_opps = self._find_funding_arbs(all_rates, underlying)
        opportunities.extend(arb_opps)

        logger.info("funding_rates.fetch_complete", total=len(opportunities))
        return opportunities

    async def _fetch_binance(self, underlying: str | None) -> list[FundingRateEntry]:
        """Fetch funding rates from Binance USDT-M futures."""
        try:
            data = await self.http.get_json(
                f"{BINANCE_API}/fapi/v1/premiumIndex",
                cache_ttl=60,  # Update every minute
            )
        except Exception as e:
            logger.warning("funding_rates.binance_error", error=str(e))
            return []

        rates: list[FundingRateEntry] = []
        for item in data:
            symbol = item.get("symbol", "")
            # Extract base symbol (e.g., BTCUSDT -> BTC)
            base = symbol.replace("USDT", "").replace("BUSD", "")

            if underlying and base.upper() != underlying.upper():
                continue
            if base not in TRACKED_SYMBOLS:
                continue

            rate = float(item.get("lastFundingRate", 0))
            annualized = rate * 3 * 365 * 100  # 8h funding × 3 × 365

            rates.append(FundingRateEntry(
                symbol=base,
                venue="binance",
                funding_rate=rate,
                annualized_rate=annualized,
                mark_price=float(item.get("markPrice", 0)),
                next_funding_time=datetime.fromtimestamp(
                    int(item.get("nextFundingTime", 0)) / 1000
                ) if item.get("nextFundingTime") else None,
            ))

        return rates

    async def _fetch_bybit(self, underlying: str | None) -> list[FundingRateEntry]:
        """Fetch funding rates from Bybit."""
        try:
            data = await self.http.get_json(
                f"{BYBIT_API}/v5/market/tickers",
                params={"category": "linear"},
                cache_ttl=60,
            )
        except Exception as e:
            logger.warning("funding_rates.bybit_error", error=str(e))
            return []

        rates: list[FundingRateEntry] = []
        tickers = data.get("result", {}).get("list", [])

        for item in tickers:
            symbol = item.get("symbol", "")
            base = symbol.replace("USDT", "").replace("USDC", "").replace("PERP", "")

            if underlying and base.upper() != underlying.upper():
                continue
            if base not in TRACKED_SYMBOLS:
                continue

            rate = float(item.get("fundingRate", 0))
            annualized = rate * 3 * 365 * 100

            oi = float(item.get("openInterest", 0))
            mark = float(item.get("markPrice", 0))

            rates.append(FundingRateEntry(
                symbol=base,
                venue="bybit",
                funding_rate=rate,
                annualized_rate=annualized,
                mark_price=mark,
                open_interest_usd=oi * mark if mark > 0 else 0,
            ))

        return rates

    async def _fetch_dydx(self, underlying: str | None) -> list[FundingRateEntry]:
        """Fetch funding rates from dYdX v4."""
        try:
            data = await self.http.get_json(
                f"{DYDX_API}/v4/perpetualMarkets",
                cache_ttl=60,
            )
        except Exception as e:
            logger.warning("funding_rates.dydx_error", error=str(e))
            return []

        rates: list[FundingRateEntry] = []
        markets = data.get("markets", {})

        for ticker, info in markets.items():
            base = ticker.replace("-USD", "")

            if underlying and base.upper() != underlying.upper():
                continue
            if base not in TRACKED_SYMBOLS:
                continue

            # dYdX uses 1-hour funding periods
            rate = float(info.get("nextFundingRate", 0))
            annualized = rate * 24 * 365 * 100

            oi = float(info.get("openInterest", 0))
            price = float(info.get("oraclePrice", 0))

            rates.append(FundingRateEntry(
                symbol=base,
                venue="dydx",
                funding_rate=rate,
                annualized_rate=annualized,
                mark_price=price,
                open_interest_usd=oi * price if price > 0 else 0,
            ))

        return rates

    async def _fetch_hyperliquid(self, underlying: str | None) -> list[FundingRateEntry]:
        """Fetch funding rates from Hyperliquid."""
        try:
            data = await self.http.post_json(
                f"{HYPERLIQUID_API}/info",
                json_body={"type": "metaAndAssetCtxs"},
            )
        except Exception as e:
            logger.warning("funding_rates.hyperliquid_error", error=str(e))
            return []

        rates: list[FundingRateEntry] = []

        if not isinstance(data, list) or len(data) < 2:
            return rates

        meta = data[0]
        asset_ctxs = data[1]
        universe = meta.get("universe", [])

        for i, asset in enumerate(universe):
            symbol = asset.get("name", "")

            if underlying and symbol.upper() != underlying.upper():
                continue
            if symbol not in TRACKED_SYMBOLS:
                continue

            if i >= len(asset_ctxs):
                continue

            ctx = asset_ctxs[i]
            rate = float(ctx.get("funding", 0))
            annualized = rate * 24 * 365 * 100  # Hyperliquid: hourly funding

            mark = float(ctx.get("markPx", 0))
            oi = float(ctx.get("openInterest", 0))

            rates.append(FundingRateEntry(
                symbol=symbol,
                venue="hyperliquid",
                funding_rate=rate,
                annualized_rate=annualized,
                mark_price=mark,
                open_interest_usd=oi * mark if mark > 0 else 0,
            ))

        return rates

    def _rates_to_opportunities(
        self, rates: list[FundingRateEntry], underlying: str | None
    ) -> list[YieldOpportunity]:
        """Convert funding rates into basis trade yield opportunities."""
        opportunities: list[YieldOpportunity] = []

        # Group by symbol to find best venue
        symbol_rates: dict[str, list[FundingRateEntry]] = {}
        for r in rates:
            symbol_rates.setdefault(r.symbol, []).append(r)

        for symbol, venue_rates in symbol_rates.items():
            # Find venue with highest positive annualized rate
            positive_rates = [r for r in venue_rates if r.annualized_rate > self.min_annualized_rate]
            if not positive_rates:
                continue

            best = max(positive_rates, key=lambda r: r.annualized_rate)

            # Average across venues for more stable estimate
            avg_rate = sum(r.annualized_rate for r in positive_rates) / len(positive_rates)
            total_oi = sum(r.open_interest_usd for r in venue_rates)

            opportunities.append(YieldOpportunity(
                id=f"basis-{symbol.lower()}-{best.venue}",
                protocol=f"basis-trade-{best.venue}",
                chain="Cross-venue",
                pool_name=f"{symbol} Basis Trade ({best.venue.title()})",
                underlying_tokens=[symbol],
                yield_type=YieldType.BASIS_TRADE,
                base_apy=0,
                reward_apy=best.annualized_rate,
                total_apy=best.annualized_rate,
                apy_7d_avg=avg_rate,
                tvl_usd=total_oi,
                smart_contract_risk=0.2 if best.venue in ("binance", "bybit") else 0.3,
                protocol_risk_score=0.25,
                is_delta_neutral=True,
                hedging_available=True,
                funding_rate=best.funding_rate,
                source="funding_rates",
                fetched_at=datetime.utcnow(),
                tags=["basis-trade", "delta-neutral", "funding-rate", f"venue:{best.venue}"],
                extra={
                    "venues": {r.venue: r.annualized_rate for r in venue_rates},
                    "best_venue": best.venue,
                    "avg_annualized_rate": avg_rate,
                    "total_open_interest_usd": total_oi,
                },
            ))

        return opportunities

    def _find_funding_arbs(
        self, rates: list[FundingRateEntry], underlying: str | None
    ) -> list[YieldOpportunity]:
        """Find cross-venue funding rate arbitrage opportunities.

        When venue A has positive funding and venue B has negative funding,
        you can long on B (receive funding) and short on A (receive funding),
        capturing both sides.
        """
        opportunities: list[YieldOpportunity] = []

        # Group by symbol
        symbol_rates: dict[str, list[FundingRateEntry]] = {}
        for r in rates:
            symbol_rates.setdefault(r.symbol, []).append(r)

        for symbol, venue_rates in symbol_rates.items():
            if len(venue_rates) < 2:
                continue

            # Sort by annualized rate
            sorted_rates = sorted(venue_rates, key=lambda r: r.annualized_rate)
            lowest = sorted_rates[0]
            highest = sorted_rates[-1]

            spread = highest.annualized_rate - lowest.annualized_rate

            # Only surface significant spreads (>5% annualized)
            if spread < 5.0:
                continue

            opportunities.append(YieldOpportunity(
                id=f"funding-arb-{symbol.lower()}-{highest.venue}-{lowest.venue}",
                protocol="funding-arb",
                chain="Cross-venue",
                pool_name=f"{symbol} Funding Arb: {highest.venue} vs {lowest.venue}",
                underlying_tokens=[symbol],
                yield_type=YieldType.FUNDING_RATE,
                base_apy=spread,
                reward_apy=0,
                total_apy=spread,
                tvl_usd=min(
                    highest.open_interest_usd,
                    lowest.open_interest_usd,
                ) if highest.open_interest_usd and lowest.open_interest_usd else 0,
                smart_contract_risk=0.35,
                protocol_risk_score=0.35,
                is_delta_neutral=True,
                hedging_available=True,
                source="funding_rates",
                fetched_at=datetime.utcnow(),
                tags=["funding-arb", "delta-neutral", "cross-venue"],
                extra={
                    "long_venue": lowest.venue,
                    "long_rate": lowest.annualized_rate,
                    "short_venue": highest.venue,
                    "short_rate": highest.annualized_rate,
                    "spread": spread,
                },
            ))

        return opportunities

    async def fetch_all_rates(self, underlying: str | None = None) -> list[FundingRateEntry]:
        """Fetch raw funding rates from all venues (for use by strategy engine)."""
        import asyncio

        tasks = []
        if self.binance_enabled:
            tasks.append(self._fetch_binance(underlying))
        if self.bybit_enabled:
            tasks.append(self._fetch_bybit(underlying))
        if self.dydx_enabled:
            tasks.append(self._fetch_dydx(underlying))
        if self.hyperliquid_enabled:
            tasks.append(self._fetch_hyperliquid(underlying))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_rates: list[FundingRateEntry] = []
        for result in results:
            if isinstance(result, list):
                all_rates.extend(result)
        return all_rates
