from realcenter_marketing.application.orchestration import AgentResult
import asyncio
from pathlib import Path
from uuid import uuid4

from agents import OpenAIProvider, RunConfig, Runner

from realcenter_marketing.infrastructure.agents_sdk.team_factory import build_team
from realcenter_marketing.domain.campaigns import Campaign, CampaignBrief, DirectorReview, CarouselCard
from realcenter_marketing.application.diagnostics import error_details


async def execute_campaign(brief: CampaignBrief, settings, *, model=None, journal=None) -> AgentResult:
    """model permite testes offline exercitarem o mesmo Runner e suas tools."""
    if model is None:
        settings.validate_live()
    team = build_team(settings, model=model, journal=journal, brief=brief)
    config = RunConfig(tracing_disabled=True)
    if model is None:
        config.model_provider = OpenAIProvider(api_key=settings.api_key.get_secret_value())
    try:
        async with asyncio.timeout(settings.timeout_seconds):
            result = await Runner.run(team.director, brief.model_dump_json(),
                                      max_turns=settings.max_turns, run_config=config)
    except BaseException as exc:
        if journal:
            journal.emit("failed", journal.current_agent, **error_details(exc))
        raise
    return AgentResult(result.final_output, team.outputs, team.delegation_log)
