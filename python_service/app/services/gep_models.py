from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional
import uuid

class Gene(BaseModel):
    """
    Structured DNA unit representing a system instruction.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    fitness: float = 0.0
    feedback_logs: List[str] = Field(default_factory=list)
    version: int = 1
    created_at: datetime = Field(default_factory=datetime.now)

class Genome(BaseModel):
    """
    A population of Genes specialized for a specific expert role.
    """
    role: str
    population: List[Gene] = Field(default_factory=list)
    alpha_id: Optional[str] = None
    last_evolved: datetime = Field(default_factory=datetime.now)

    @property
    def alpha(self) -> Optional[Gene]:
        if not self.alpha_id:
            return self.population[0] if self.population else None
        return next((g for g in self.population if g.id == self.alpha_id), None)

class EvolutionaryState(BaseModel):
    """
    Global state container for all expert roles.
    """
    genomes: dict[str, Genome] = Field(default_factory=dict)
