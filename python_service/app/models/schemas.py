from pydantic import BaseModel, Field
from typing import List

class ExpertDiscussionResult(BaseModel):
    """Structured output format for intermediate AI experts in the discussion pipeline."""
    core_thesis: str = Field(description="The core investment thesis, summary of analysis, or key arguments.")
    key_metrics_extracted: List[str] = Field(description="List of key financial metrics, data points, or values extracted from facts or tools.")
    risks: List[str] = Field(description="Key risks, downside catalysts, or uncertainties identified.")
    rating: str = Field(description="Investment rating recommendation: Strong Buy, Buy, Hold, Underweight, Sell.")
    confidence: float = Field(description="Confidence score for this analysis and rating, represented as a float between 0.0 and 1.0.")
