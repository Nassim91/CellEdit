"""Report generator — produces structured reports for asset managers.

Outputs:
- Console (Rich tables)
- JSON (machine-readable)
- HTML (styled for sharing)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sentinel.models.opportunity import YieldOpportunity
from sentinel.models.report import SentinelReport, StrategyRecommendation
from sentinel.models.sentiment import ProtocolMomentum
from sentinel.utils.logging import get_logger

logger = get_logger(__name__)


class ReportGenerator:
    """Generates Sentinel analysis reports in multiple formats."""

    def __init__(self, output_dir: Path | None = None) -> None:
        self.output_dir = output_dir or Path("./reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def print_console_report(self, report: SentinelReport) -> None:
        """Print a rich formatted report to the console."""
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()

        # Header
        console.print()
        console.print(Panel(
            f"[bold cyan]SENTINEL YIELD REPORT[/]\n"
            f"[dim]Underlying:[/] [bold]{report.underlying}[/]  |  "
            f"[dim]Size:[/] [bold]${report.target_size_usd:,.0f}[/]  |  "
            f"[dim]Generated:[/] {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"[dim]Chains:[/] {', '.join(report.chains_analyzed)}  |  "
            f"[dim]Opportunities Found:[/] [bold green]{report.total_opportunities_found}[/]",
            title="Sentinel",
            border_style="cyan",
        ))

        # Top Opportunities Table
        if report.top_opportunities:
            table = Table(title="Top Yield Opportunities", show_lines=True)
            table.add_column("Rank", style="dim", width=4)
            table.add_column("Protocol", style="cyan", width=15)
            table.add_column("Chain", width=12)
            table.add_column("Pool", width=25)
            table.add_column("Type", width=15)
            table.add_column("Base APY", justify="right", style="green")
            table.add_column("Reward APY", justify="right", style="yellow")
            table.add_column("Total APY", justify="right", style="bold green")
            table.add_column("TVL", justify="right")
            table.add_column("Risk", justify="center")

            for i, opp in enumerate(report.top_opportunities[:20], 1):
                risk_color = self._risk_color(opp.protocol_risk_score)
                table.add_row(
                    str(i),
                    opp.protocol,
                    opp.chain,
                    opp.pool_name[:25],
                    opp.yield_type.value,
                    f"{opp.base_apy:.2f}%",
                    f"{opp.reward_apy:.2f}%",
                    f"{opp.total_apy:.2f}%",
                    self._format_usd(opp.tvl_usd),
                    f"[{risk_color}]{opp.protocol_risk_score:.2f}[/]",
                )

            console.print(table)

        # Strategy Recommendations
        if report.strategies:
            console.print()
            console.print("[bold cyan]Strategy Recommendations[/]")
            console.print()

            for i, strat in enumerate(report.strategies, 1):
                risk_color = self._risk_level_color(strat.risk_level.value)
                market_neutral = "[green]YES[/]" if strat.is_market_neutral else "[dim]NO[/]"

                console.print(Panel(
                    f"[bold]{strat.name}[/]\n\n"
                    f"{strat.description}\n\n"
                    f"[dim]Expected APY:[/] [bold green]{strat.expected_net_apy:.2f}%[/]  |  "
                    f"[dim]Risk:[/] [{risk_color}]{strat.risk_level.value.upper()}[/]  |  "
                    f"[dim]Market Neutral:[/] {market_neutral}  |  "
                    f"[dim]Confidence:[/] {strat.confidence:.0%}\n\n"
                    f"[dim]Steps:[/]\n" +
                    "\n".join(f"  {j}. {leg}" for j, leg in enumerate(strat.legs_description, 1)) +
                    "\n\n[dim]Risk Factors:[/] " +
                    ", ".join(strat.risk_factors),
                    title=f"Strategy #{i}",
                    border_style="yellow",
                ))

        # Sentiment Summary
        if report.sentiment_summary:
            console.print()
            console.print(Panel(
                f"{report.sentiment_summary}\n\n"
                f"[dim]Trending Protocols:[/] {', '.join(report.trending_protocols) or 'None'}",
                title="Social Sentiment",
                border_style="magenta",
            ))

        # Warnings
        if report.concentration_warnings:
            console.print()
            for warning in report.concentration_warnings:
                console.print(f"  [yellow]WARNING:[/] {warning}")

        console.print()

    def export_json(self, report: SentinelReport, filename: str | None = None) -> Path:
        """Export report as JSON."""
        if filename is None:
            filename = f"sentinel_{report.underlying}_{report.generated_at.strftime('%Y%m%d_%H%M')}.json"

        path = self.output_dir / filename
        data = report.model_dump(mode="json")
        path.write_text(json.dumps(data, indent=2, default=str))

        logger.info("report.exported_json", path=str(path))
        return path

    def export_html(self, report: SentinelReport, filename: str | None = None) -> Path:
        """Export report as styled HTML."""
        if filename is None:
            filename = f"sentinel_{report.underlying}_{report.generated_at.strftime('%Y%m%d_%H%M')}.html"

        path = self.output_dir / filename
        html = self._render_html(report)
        path.write_text(html)

        logger.info("report.exported_html", path=str(path))
        return path

    def _render_html(self, report: SentinelReport) -> str:
        """Render HTML report using Jinja2 template."""
        from jinja2 import Template

        template = Template(HTML_TEMPLATE)
        return template.render(
            report=report,
            format_usd=self._format_usd,
            risk_color_hex=self._risk_color_hex,
            now=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        )

    @staticmethod
    def _format_usd(amount: float) -> str:
        if amount >= 1_000_000_000:
            return f"${amount / 1_000_000_000:.1f}B"
        if amount >= 1_000_000:
            return f"${amount / 1_000_000:.1f}M"
        if amount >= 1_000:
            return f"${amount / 1_000:.0f}K"
        return f"${amount:.0f}"

    @staticmethod
    def _risk_color(score: float) -> str:
        if score < 0.2:
            return "green"
        if score < 0.4:
            return "yellow"
        if score < 0.6:
            return "orange3"
        return "red"

    @staticmethod
    def _risk_level_color(level: str) -> str:
        return {"minimal": "green", "low": "green", "medium": "yellow", "high": "orange3", "critical": "red"}.get(level, "white")

    @staticmethod
    def _risk_color_hex(score: float) -> str:
        if score < 0.2:
            return "#22c55e"
        if score < 0.4:
            return "#eab308"
        if score < 0.6:
            return "#f97316"
        return "#ef4444"


# ── HTML Template ──

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sentinel Report — {{ report.underlying }} | {{ now }}</title>
<style>
  :root { --bg: #0f172a; --card: #1e293b; --text: #e2e8f0; --accent: #06b6d4; --green: #22c55e; --yellow: #eab308; --red: #ef4444; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Inter', -apple-system, sans-serif; background: var(--bg); color: var(--text); padding: 2rem; line-height: 1.6; }
  .container { max-width: 1200px; margin: 0 auto; }
  h1 { color: var(--accent); font-size: 2rem; margin-bottom: 0.5rem; }
  h2 { color: var(--accent); font-size: 1.3rem; margin: 2rem 0 1rem; border-bottom: 1px solid #334155; padding-bottom: 0.5rem; }
  .header { background: var(--card); padding: 2rem; border-radius: 12px; margin-bottom: 2rem; }
  .meta { display: flex; gap: 2rem; flex-wrap: wrap; margin-top: 1rem; color: #94a3b8; }
  .meta span { font-weight: 600; color: var(--text); }
  table { width: 100%; border-collapse: collapse; background: var(--card); border-radius: 8px; overflow: hidden; margin-bottom: 2rem; }
  th { background: #334155; padding: 0.75rem 1rem; text-align: left; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: #94a3b8; }
  td { padding: 0.75rem 1rem; border-top: 1px solid #334155; }
  tr:hover { background: #334155; }
  .apy { color: var(--green); font-weight: 700; }
  .risk-low { color: var(--green); }
  .risk-medium { color: var(--yellow); }
  .risk-high { color: var(--red); }
  .strategy-card { background: var(--card); padding: 1.5rem; border-radius: 12px; margin-bottom: 1rem; border-left: 4px solid var(--accent); }
  .strategy-card h3 { color: var(--text); margin-bottom: 0.5rem; }
  .badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
  .badge-neutral { background: #065f46; color: #6ee7b7; }
  .badge-risk { background: #7c2d12; color: #fdba74; }
  .steps { margin: 1rem 0; padding-left: 1.5rem; }
  .steps li { margin: 0.3rem 0; color: #cbd5e1; }
  .footer { text-align: center; color: #475569; margin-top: 3rem; font-size: 0.85rem; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Sentinel Yield Intelligence Report</h1>
    <div class="meta">
      <div>Underlying: <span>{{ report.underlying }}</span></div>
      <div>Target Size: <span>${{ "{:,.0f}".format(report.target_size_usd) }}</span></div>
      <div>Chains: <span>{{ report.chains_analyzed | join(', ') }}</span></div>
      <div>Opportunities: <span>{{ report.total_opportunities_found }}</span></div>
      <div>Generated: <span>{{ now }}</span></div>
    </div>
  </div>

  {% if report.market_summary %}
  <h2>Market Context</h2>
  <p>{{ report.market_summary }}</p>
  {% endif %}

  <h2>Top Yield Opportunities</h2>
  <table>
    <thead>
      <tr>
        <th>#</th><th>Protocol</th><th>Chain</th><th>Pool</th><th>Type</th>
        <th>Base APY</th><th>Reward APY</th><th>Total APY</th><th>TVL</th><th>Risk</th>
      </tr>
    </thead>
    <tbody>
    {% for opp in report.top_opportunities[:25] %}
      <tr>
        <td>{{ loop.index }}</td>
        <td>{{ opp.protocol }}</td>
        <td>{{ opp.chain }}</td>
        <td>{{ opp.pool_name[:30] }}</td>
        <td>{{ opp.yield_type.value }}</td>
        <td class="apy">{{ "%.2f" | format(opp.base_apy) }}%</td>
        <td>{{ "%.2f" | format(opp.reward_apy) }}%</td>
        <td class="apy">{{ "%.2f" | format(opp.total_apy) }}%</td>
        <td>{{ format_usd(opp.tvl_usd) }}</td>
        <td style="color: {{ risk_color_hex(opp.protocol_risk_score) }}">{{ "%.2f" | format(opp.protocol_risk_score) }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>

  {% if report.strategies %}
  <h2>Strategy Recommendations</h2>
  {% for strat in report.strategies %}
  <div class="strategy-card">
    <h3>{{ loop.index }}. {{ strat.name }}</h3>
    <p>{{ strat.description }}</p>
    <div style="margin-top: 0.75rem;">
      <span class="apy">{{ "%.2f" | format(strat.expected_net_apy) }}% Expected APY</span>
      &nbsp;|&nbsp;
      <span class="risk-{{ strat.risk_level.value }}">{{ strat.risk_level.value | upper }} risk</span>
      &nbsp;|&nbsp;
      {% if strat.is_market_neutral %}<span class="badge badge-neutral">MARKET NEUTRAL</span>{% endif %}
      Confidence: {{ "%.0f" | format(strat.confidence * 100) }}%
    </div>
    <ol class="steps">
    {% for leg in strat.legs_description %}
      <li>{{ leg }}</li>
    {% endfor %}
    </ol>
    <p style="color: #94a3b8; font-size: 0.85rem; margin-top: 0.5rem;">
      Risk factors: {{ strat.risk_factors | join(', ') }}
    </p>
  </div>
  {% endfor %}
  {% endif %}

  {% if report.sentiment_summary %}
  <h2>Social Sentiment</h2>
  <p>{{ report.sentiment_summary }}</p>
  {% if report.trending_protocols %}
  <p style="margin-top: 0.5rem;"><strong>Trending:</strong> {{ report.trending_protocols | join(', ') }}</p>
  {% endif %}
  {% endif %}

  {% if report.concentration_warnings %}
  <h2>Warnings</h2>
  {% for w in report.concentration_warnings %}
  <p style="color: var(--yellow);">{{ w }}</p>
  {% endfor %}
  {% endif %}

  <div class="footer">
    <p>Generated by Sentinel Yield Intelligence Agent v0.1.0</p>
    <p>This report is for informational purposes only. Not financial advice.</p>
  </div>
</div>
</body>
</html>"""
