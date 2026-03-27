"""Sentinel CLI — command-line interface for the yield intelligence agent.

Usage:
    sentinel scan ETH --size 1000000
    sentinel scan USDC --size 5000000 --chains ethereum,arbitrum,base
    sentinel scan ETH --size 1000000 --format html --no-sentiment
    sentinel protocols analyze aave-v3 morpho-blue pendle
    sentinel sentiment track pendle eigenlayer ethena
    sentinel discover-protocols
"""

from __future__ import annotations

import asyncio
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(
    name="sentinel",
    help="Sentinel — DeFi Yield Intelligence Agent. Discover, analyze, and report yield opportunities.",
    add_completion=False,
)
console = Console()


@app.command()
def scan(
    underlying: str = typer.Argument(help="Token symbol (e.g., ETH, USDC, WBTC)"),
    size: float = typer.Option(1_000_000, "--size", "-s", help="Target allocation size in USD"),
    chains: Optional[str] = typer.Option(None, "--chains", "-c", help="Comma-separated chain filter (e.g., ethereum,arbitrum,base)"),
    format: str = typer.Option("console", "--format", "-f", help="Output format: console, json, html"),
    no_sentiment: bool = typer.Option(False, "--no-sentiment", help="Skip Twitter sentiment analysis"),
    top: int = typer.Option(25, "--top", "-n", help="Number of top opportunities to show"),
) -> None:
    """Scan for all yield opportunities for a given token and size."""

    async def _run() -> None:
        from sentinel.core.sentinel import SentinelAgent

        console.print(f"\n[cyan]Sentinel[/] scanning yield for [bold]{underlying}[/] (${size:,.0f})...\n")

        chain_list = [c.strip() for c in chains.split(",")] if chains else None

        agent = SentinelAgent()
        try:
            report = await agent.analyze(
                underlying=underlying.upper(),
                size_usd=size,
                chains=chain_list,
                include_sentiment=not no_sentiment,
                top_n=top,
            )

            if format == "console":
                agent.print_report(report)
            elif format == "json":
                path = agent.export_report(report, "json")
                console.print(f"\n[green]Report exported to {path}[/]")
            elif format == "html":
                path = agent.export_report(report, "html")
                console.print(f"\n[green]HTML report exported to {path}[/]")
            else:
                console.print(f"[red]Unknown format: {format}[/]")

        finally:
            await agent.close()

    asyncio.run(_run())


@app.command()
def protocols(
    slugs: list[str] = typer.Argument(help="Protocol slugs to analyze (e.g., aave-v3 morpho-blue)"),
) -> None:
    """Analyze DeFi protocols for risk and operational security."""

    async def _run() -> None:
        from rich.table import Table

        from sentinel.analyzers.protocol_analyzer import ProtocolAnalyzer
        from sentinel.utils.http import HttpClient

        console.print(f"\n[cyan]Analyzing {len(slugs)} protocols...[/]\n")

        analyzer = ProtocolAnalyzer()
        try:
            results = await analyzer.analyze_batch(slugs)

            table = Table(title="Protocol Risk Analysis", show_lines=True)
            table.add_column("Protocol", style="cyan")
            table.add_column("Category")
            table.add_column("TVL", justify="right")
            table.add_column("Audits", justify="center")
            table.add_column("Bug Bounty", justify="center")
            table.add_column("Timelock", justify="center")
            table.add_column("Governance", justify="center")
            table.add_column("SC Risk", justify="right")
            table.add_column("Op Risk", justify="right")
            table.add_column("Overall", justify="right", style="bold")
            table.add_column("Level", justify="center")

            for slug, protocol in results.items():
                risk = protocol.risk
                level_color = {
                    "minimal": "green",
                    "low": "green",
                    "medium": "yellow",
                    "high": "red",
                    "critical": "bold red",
                }.get(risk.risk_level.value, "white")

                tvl_str = f"${protocol.tvl_usd / 1e9:.1f}B" if protocol.tvl_usd >= 1e9 else f"${protocol.tvl_usd / 1e6:.0f}M"

                table.add_row(
                    protocol.name,
                    protocol.category.value,
                    tvl_str,
                    str(risk.audit_count),
                    "[green]Yes[/]" if risk.has_bug_bounty else "[red]No[/]",
                    "[green]Yes[/]" if risk.has_timelock else "[red]No[/]",
                    "[green]Yes[/]" if risk.has_governance else "[dim]No[/]",
                    f"{risk.smart_contract_score:.2f}",
                    f"{risk.operational_score:.2f}",
                    f"{risk.overall_risk_score:.2f}",
                    f"[{level_color}]{risk.risk_level.value.upper()}[/]",
                )

            console.print(table)

        finally:
            await analyzer.close()

    asyncio.run(_run())


@app.command()
def sentiment(
    protocol_names: list[str] = typer.Argument(help="Protocols to track sentiment for"),
    hours: int = typer.Option(24, "--hours", "-h", help="Lookback period in hours"),
) -> None:
    """Track social sentiment and momentum for DeFi protocols."""

    async def _run() -> None:
        from rich.table import Table

        from sentinel.scrapers.twitter_scraper import TwitterScraper

        console.print(f"\n[cyan]Tracking sentiment for {len(protocol_names)} protocols ({hours}h)...[/]\n")

        scraper = TwitterScraper()
        try:
            results: list[tuple[str, Any]] = []

            for name in protocol_names:
                try:
                    momentum = await scraper.compute_protocol_momentum(name, hours=hours)
                    results.append((name, momentum))
                except Exception as e:
                    console.print(f"[red]Error for {name}: {e}[/]")

            if results:
                table = Table(title="Protocol Sentiment & Momentum", show_lines=True)
                table.add_column("Protocol", style="cyan")
                table.add_column("Mentions", justify="right")
                table.add_column("Unique Authors", justify="right")
                table.add_column("Engagement", justify="right")
                table.add_column("Influencers", justify="right")
                table.add_column("Bullish %", justify="right", style="green")
                table.add_column("Bearish %", justify="right", style="red")
                table.add_column("Momentum", justify="right")
                table.add_column("Trending", justify="center")

                for name, m in results:
                    momentum_color = "green" if m.momentum_score > 0 else "red"
                    table.add_row(
                        name,
                        str(m.total_mentions),
                        str(m.unique_authors),
                        f"{m.total_engagement:.0f}",
                        str(m.influencer_mentions),
                        f"{m.bullish_pct:.0%}",
                        f"{m.bearish_pct:.0%}",
                        f"[{momentum_color}]{m.momentum_score:+.2f}[/]",
                        "[green]YES[/]" if m.is_trending else "[dim]no[/]",
                    )

                console.print(table)

        finally:
            await scraper.close()

    asyncio.run(_run())


@app.command(name="discover-protocols")
def discover_protocols(
    hours: int = typer.Option(72, "--hours", "-h", help="Lookback period in hours"),
) -> None:
    """Discover new/emerging DeFi protocols via social buzz."""

    async def _run() -> None:
        from sentinel.scrapers.twitter_scraper import TwitterScraper

        console.print(f"\n[cyan]Discovering new DeFi protocols (last {hours}h)...[/]\n")

        scraper = TwitterScraper()
        try:
            discoveries = await scraper.discover_new_protocols(hours=hours)

            if not discoveries:
                console.print("[yellow]No new protocol discoveries in this period.[/]")
                return

            for i, disc in enumerate(discoveries[:15], 1):
                console.print(
                    f"[cyan]{i}.[/] [bold]{disc['name']}[/] — "
                    f"{disc['mentions']} mentions, "
                    f"engagement: {disc['total_engagement']:.0f}"
                )

        finally:
            await scraper.close()

    asyncio.run(_run())


if __name__ == "__main__":
    app()
