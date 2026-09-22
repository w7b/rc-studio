"""One specialist, one structured response and at most one format repair."""
import asyncio

from agents import RunConfig, Runner

from realcenter_marketing.domain.consultations import OUTPUT_SCHEMAS, validated_delivery
from .output_repair import run_with_repair
from .runtime import build_provider, close_provider
from .team_factory import make_agent


async def execute_consultation(request, settings, journal, *, model=None, option=None):
    agent = make_agent(settings, request.role, OUTPUT_SCHEMAS[request.role], model=model,
                       model_name=option.model if option else None, option=option,
                       journal=journal, save_output=False)
    provider = None
    config = RunConfig(tracing_disabled=True)
    try:
        if model is None:
            provider = build_provider(settings, option)
            config.model_provider = provider

        async def run(selected, user_input):
            return await Runner.run(selected, user_input, max_turns=1, run_config=config)

        async with asyncio.timeout(min(settings.timeout_seconds, 90)):
            result = await run_with_repair(run, agent, request.model_dump_json(), journal)
        return validated_delivery(request, result.final_output)
    finally:
        await close_provider(provider)
