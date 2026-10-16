"""Campaign delegation policy shared by the SDK adapter and composition rules."""
from dataclasses import dataclass
from typing import Any
from studio_ai.domain.campaigns import CopyPack, CreativeBrief, SocialPlan, SPECIALIST_ROLES

SPECIALIST_STEPS = tuple(zip(SPECIALIST_ROLES, (SocialPlan, CopyPack, CreativeBrief)))

def specialist_enabled(completed: list[str], index: int) -> bool:
    return completed == [role for role, _ in SPECIALIST_STEPS[:index]]

@dataclass
class AgentResult:
    director: Any
    outputs: dict
    delegation_log: list[str]
