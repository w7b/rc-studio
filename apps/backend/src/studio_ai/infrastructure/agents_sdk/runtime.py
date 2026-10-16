from studio_ai.application.orchestration import AgentResult, SPECIALIST_STEPS
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from agents import OpenAIProvider, RunConfig, Runner
from openai import AsyncOpenAI

from studio_ai.infrastructure.agents_sdk.team_factory import build_team
from studio_ai.infrastructure.agents_sdk.output_repair import run_with_repair
from studio_ai.domain.campaigns import Campaign, CampaignBrief, CampaignPlan, DirectorReview, CarouselCard
from studio_ai.infrastructure.model_catalog import provider_for
from studio_ai.application.diagnostics import error_details


def build_provider(settings, option=None):
    """A private client per run, never the SDK's process-wide one.

    The SDK keeps one module-level httpx client (`openai_provider.shared_http_client`)
    whose pooled connections belong to the event loop that opened them. Every campaign
    and every briefing consultation runs inside its own `asyncio.run` loop, so a
    connection left over from an earlier, already-closed loop makes the pool raise
    RuntimeError('Event loop is closed') the next time it closes that connection.
    An own AsyncOpenAI carries its own pool, which dies with its own loop.

    The transport belongs to the provider record, not to a branch here: only OpenAI's own
    endpoint serves the Responses API, so every compatible gateway is marked for Chat
    Completions in the catalog and a new one needs no edit in this file.
    """
    provider = provider_for(option.provider if option is not None else 'openai')
    base_url = settings.base_url_for(provider)
    client = AsyncOpenAI(api_key=settings.credential(provider.id), timeout=settings.timeout_seconds,
                         **({'base_url': base_url} if base_url else {}))
    return OpenAIProvider(openai_client=client, use_responses=provider.use_responses)


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
    """model permite testes offline exercitarem o mesmo Runner.

    The pipeline walks SPECIALIST_STEPS itself. Nothing here asks a model to decide the
    order: it never did — the delegation guard refused every out-of-turn call — so the
    sequence is written where it always lived in practice, and no agent needs tool
    calling and structured output at the same time to run a campaign.
    """
    if model is None:
        if option and option.provider != 'openai':
            settings.validate_provider(option)
        else:
            settings.validate_live()
    team = build_team(settings, model=model, model_name=option.model if option else None,
                      option=option, journal=journal, brief=brief)
    config = RunConfig(tracing_disabled=True)
    provider = None
    if model is None:
        provider = build_provider(settings, option)
        config.model_provider = provider

    async def run(agent, user_input):
        # A per-agent deadline, not only the run's. One agent was measured sitting on a
        # single call for 15 minutes and then failing on malformed output: with only the
        # run-wide timeout (80 min by default) that reads as a hang, and the operator
        # cannot tell a slow model from a stuck one.
        try:
            async with asyncio.timeout(settings.agent_timeout_seconds):
                return await Runner.run(agent, user_input, max_turns=settings.max_turns,
                                        run_config=config)
        except TimeoutError:
            raise TimeoutError(
                f'{agent.name} não respondeu em {settings.agent_timeout_seconds}s. '
                'A execução foi interrompida para não consumir o tempo dos demais agentes.'
            ) from None

    try:
        async with asyncio.timeout(settings.timeout_seconds):
            plan = CampaignPlan.model_validate(
                (await run_with_repair(run, team.planner, brief.model_dump_json(), journal)).final_output)
            for role, schema in SPECIALIST_STEPS:
                assignment = plan.for_role(role).model_dump_json()
                result = await run_with_repair(run, team.specialists[role], assignment, journal)
                # Validated before the next specialist starts, so a bad delivery stops
                # the run instead of becoming the input of the one after it.
                team.outputs[role] = schema.model_validate(result.final_output)
                team.delegation_log.append(role)
            deliveries = json.dumps({role: value.model_dump() for role, value in team.outputs.items()},
                                    ensure_ascii=False)
            review = await run_with_repair(run, team.reviewer, deliveries, journal)
    except BaseException as exc:
        if journal:
            journal.emit("failed", journal.current_agent, **error_details(exc))
        raise
    finally:
        await close_provider(provider)
    return AgentResult(review.final_output, team.outputs, team.delegation_log)
