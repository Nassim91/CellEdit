"""Tests for Protocol and ProtocolRisk models."""

from sentinel.models.protocol import Protocol, ProtocolCategory, ProtocolRisk, RiskLevel


def test_risk_scoring_blue_chip() -> None:
    """Blue-chip protocol should have low risk scores."""
    risk = ProtocolRisk(
        audit_count=10,
        has_bug_bounty=True,
        time_live_days=1200,
        has_timelock=True,
        has_governance=True,
        is_upgradeable=True,
    )
    assert risk.smart_contract_score < 0.3
    assert risk.overall_risk_score < 0.3
    assert risk.risk_level in (RiskLevel.MINIMAL, RiskLevel.LOW)


def test_risk_scoring_new_protocol() -> None:
    """New unaudited protocol should have higher risk."""
    risk = ProtocolRisk(
        audit_count=0,
        has_bug_bounty=False,
        time_live_days=30,
        has_timelock=False,
        is_centralized=True,
    )
    assert risk.smart_contract_score > 0.5
    assert risk.overall_risk_score > 0.4
    assert risk.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH)


def test_risk_scoring_exploited_protocol() -> None:
    """Protocol with exploit history should be penalized."""
    risk = ProtocolRisk(
        audit_count=3,
        has_bug_bounty=True,
        time_live_days=500,
        total_exploit_losses_usd=50_000_000,
        exploit_history=[{"date": "2024-01-01", "loss_usd": 50_000_000}],
    )
    assert risk.smart_contract_score > 0.4


def test_protocol_age(sample_protocol: Protocol) -> None:
    """Protocol should report age correctly."""
    if sample_protocol.launched_at:
        assert sample_protocol.age_days is not None
        assert sample_protocol.age_days >= 0
    else:
        assert sample_protocol.age_days is None
