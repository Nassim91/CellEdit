# Sentinel — DeFi Yield Intelligence Agent

Sentinel is an autonomous agent that discovers, analyzes, and reports **all yield opportunities** for a given underlying asset and allocation size across DeFi protocols and chains. It produces market-neutral strategy recommendations and sentiment analysis to help asset managers allocate capital efficiently.

## Features

- **Cross-Chain Yield Discovery** — Scans 12+ chains (Ethereum, Arbitrum, Optimism, Base, Polygon, Avalanche, BSC, Solana, etc.)
- **12 Data Sources** — DeFiLlama, Vaults.fyi, Aave, Compound, Morpho, Pendle, Yearn, Zapper, 1inch, EigenLayer, Ethena, Maker/Sky
- **Protocol Risk Analysis** — Smart contract risk, operational security, audit history, exploit track record
- **Market-Neutral Strategies** — Basis trades, delta-neutral LP, fixed yield (Pendle PT), restaking stacks, cross-chain spreads
- **Social Sentiment** — X/Twitter scraping for DeFi alpha, protocol momentum, new protocol discovery
- **Professional Reports** — Console (Rich), JSON, and styled HTML reports for asset managers

## Architecture

```
sentinel/
├── sentinel/
│   ├── core/           # Main agent orchestrator + yield aggregator
│   ├── sources/        # Data source connectors (12 sources)
│   │   ├── defillama   # Primary meta-aggregator (thousands of pools)
│   │   ├── vaults_fyi  # Vault-focused meta-aggregator
│   │   ├── aave        # Aave V3 lending rates (6 chains)
│   │   ├── compound    # Compound V3 Comet markets
│   │   ├── morpho      # Morpho Blue vaults + isolated markets
│   │   ├── pendle      # PT (fixed yield) / YT (leveraged yield) / LP
│   │   ├── yearn       # Automated yield vaults (yDaemon API)
│   │   ├── eigenlayer  # Restaking + LRT + AVS yields
│   │   ├── ethena      # sUSDe basis trade yield
│   │   ├── maker       # DSR/SSR + Spark lending
│   │   ├── zapper      # Cross-protocol vault discovery
│   │   └── oneinch     # 1inch earn products
│   ├── analyzers/      # Protocol risk scoring + analysis
│   ├── strategies/     # Market-neutral strategy engine
│   ├── scrapers/       # X/Twitter sentiment + momentum
│   ├── reports/        # Report generation (console/JSON/HTML)
│   ├── models/         # Pydantic data models
│   ├── config/         # Settings and chain configuration
│   └── utils/          # HTTP client, logging
├── pyproject.toml      # Project config & dependencies
└── .env.example        # Environment variables template
```

## Quick Start

```bash
# Install
cd sentinel
pip install -e .

# Scan for ETH yield opportunities with $1M allocation
sentinel scan ETH --size 1000000

# Scan USDC across specific chains, export HTML report
sentinel scan USDC --size 5000000 --chains ethereum,arbitrum,base --format html

# Analyze protocol risk
sentinel protocols aave-v3 morpho-blue pendle eigenlayer

# Track social sentiment
sentinel sentiment pendle eigenlayer ethena --hours 48

# Discover new protocols via Twitter buzz
sentinel discover-protocols --hours 72
```

## Strategy Types

| Strategy | Description | Market Neutral | Risk |
|----------|-------------|:--------------:|------|
| Single-Sided Lending | Supply to Aave/Compound/Morpho | No* | Low |
| Stable LP | Stablecoin-only liquidity provision | Yes | Low |
| Basis Trade | Spot + perp short (Ethena, etc.) | Yes | Medium |
| Fixed Yield | Pendle PT — locked rate to maturity | No* | Low |
| Restaking Stack | ETH → LST → LRT → AVS | No | Medium |
| Cross-Chain Spread | Same asset, different chain yields | No* | Medium |
| Diversified Portfolio | Spread across protocols/chains | No* | Low |

*Market-neutral when underlying is a stablecoin.

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Key settings:
- `TWITTER_BEARER_TOKEN` — Required for sentiment analysis (optional, falls back to web scraping)
- `RPC_*` — Custom RPC endpoints (public RPCs used as defaults)
- `REPORT_OUTPUT_DIR` — Where to save exported reports

## Data Source Priority

Sentinel uses a layered approach to maximize coverage while minimizing API calls:

1. **Meta-aggregators** (DeFiLlama, Vaults.fyi) — Broadest coverage, thousands of pools
2. **Native protocol sources** (Aave, Compound, Morpho, Pendle) — Deeper data, more accurate APYs
3. **Yield aggregators** (Yearn, Zapper, 1inch) — Automated vault yields
4. **Ecosystem sources** (EigenLayer, Ethena, Maker) — Specialized yields (restaking, basis trades)

Results are deduplicated, with native source data preferred over aggregator data when both are available.

## Disclaimer

This tool is for informational purposes only. It is not financial advice. Always do your own research and risk assessment before allocating capital to DeFi protocols.
