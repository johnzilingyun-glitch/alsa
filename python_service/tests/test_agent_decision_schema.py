import os
import sys

import pytest
from pydantic import ValidationError

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from python_service.app.decision.schemas import AgentDecisionOutput, ConflictLevel


def test_agent_decision_output_requires_evidence_backed_claims():
    output = AgentDecisionOutput.model_validate(
        {
            "agent_role": "Fundamental Analyst",
            "run_id": "run_1",
            "snapshot_id": "snap_1",
            "as_of_date": "2026-05-25T15:00:00Z",
            "claims": [
                {
                    "claim_id": "claim_1",
                    "statement": "Margins improved year over year.",
                    "direction": "bullish",
                    "horizon": "6m",
                    "confidence": 0.72,
                    "evidence_ids": ["ev_1"],
                    "numeric_support": {"gross_margin_delta": 0.024},
                    "falsification_condition": "Gross margin falls below prior-year level.",
                    "risk_flags": ["single_quarter_inference"],
                }
            ],
            "score_contribution": {"quality": 0.68, "risk_penalty": 0.25},
            "position_impact": {"direction": "increase", "max_weight_delta": 0.01},
            "conflict_level": "C1",
        }
    )

    assert output.claims[0].evidence_ids == ["ev_1"]
    assert output.conflict_level == ConflictLevel.C1


def test_agent_decision_output_rejects_claim_without_evidence():
    with pytest.raises(ValidationError):
        AgentDecisionOutput.model_validate(
            {
                "agent_role": "Bull Advocate",
                "run_id": "run_1",
                "snapshot_id": "snap_1",
                "as_of_date": "2026-05-25T15:00:00Z",
                "claims": [
                    {
                        "claim_id": "claim_1",
                        "statement": "This will go up.",
                        "direction": "bullish",
                        "horizon": "3m",
                        "confidence": 0.9,
                        "evidence_ids": [],
                        "numeric_support": {},
                        "falsification_condition": "Price goes down.",
                        "risk_flags": [],
                    }
                ],
                "score_contribution": {"quality": 0.5},
                "position_impact": {"direction": "increase", "max_weight_delta": 0.02},
            }
        )
