from realcenter_marketing.application.orchestration import AgentResult
import asyncio
from pathlib import Path
from uuid import uuid4

from agents import OpenAIProvider, RunConfig, Runner
from openai import AsyncOpenAI

from realcenter_marketing.infrastructure.agents_sdk.team_factory import build_team
from realcenter_marketing.domain.campaigns import Campaign, CampaignBrief, DirectorReview, CarouselCard
from realcenter_marketing.application.diagnostics import error_details


def build_provider(settings, option=None):
    """A private client per run, never the SDK's process-wide one.

    The SDK keeps one module-level httpx client (`openai_provider.shared_http_client`)
    whose pooled connections belong to the event loop that opened them. Every campaign
    and every briefing consultation runs inside its own `asyncio.run` loop, so a
    connection left over from an earlier, already-closed loop makes the pool raise
    RuntimeError('Event loop is closed') the next time it closes that connection.
    An own AsyncOpenAI carries its own pool, which dies with its own loop.

    NVIDIA NIM speaks Chat Completions only, so the Responses API is disabled there.
    """
    if option is not None and option.provider == 'nvidia':
        client = AsyncOpenAI(api_key=settings.credential('nvidia'),
                             base_url=settings.nvidia_base_url,
                             timeout=settings.timeout_seconds)
        return OpenAIProvider(openai_client=client, use_responses=False)
    client = AsyncOpenAI(api_key=settings.credential('openai'), timeout=settings.timeout_seconds)
    return OpenAIProvider(openai_client=client)


async def close_provider(provider):
    """Release the run's own sockets while its loop is still alive."""
    if provider is None:
        return
    try:
        await provider.aclose()
    finally:
        client = getattr(provider, '_client', None)
        if client is not None:
            await client.close()


async def execute_campaign(brief: CampaignBrief, settings, *, model=None, option=None, journal=None) -> AgentResult:
    """model permite testes offline exercitarem o mesmo Runner e suas tools."""
    if model is None:
        if option and option.provider != 'openai':
            settings.validate_provider(option)
        else:
            settings.validate_live()
    team = build_team(settings, model=model, model_name=option.model if option else None,
                      journal=journal, brief=brief)
    config = RunConfig(tracing_disabled=True)
    provider = None
    if model is None:
        provider = build_provider(settings, option)
        config.model_provider = provider
    try:
        async with asyncio.timeout(settings.timeout_seconds):
            result = await Runner.run(team.director, brief.model_dump_json(),
                                      max_turns=settings.max_turns, run_config=config)
    except BaseException as exc:
        if journal:
            journal.emit("failed", journal.current_agent, **error_details(exc))
        raise
    finally:
        await close_provider(provider)
    return AgentResult(result.final_output, team.outputs, team.delegation_log)
