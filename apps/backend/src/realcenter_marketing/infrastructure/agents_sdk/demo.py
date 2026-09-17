"""Modelo roteirizado: exercita o SDK sem rede; não produz conteúdo com IA."""
import json
from pathlib import Path
from uuid import uuid4

from agents import Model, ModelResponse, Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText


class DemoModel(Model):
    def __init__(self, fixture: Path):
        self.responses = json.loads(fixture.read_text(encoding="utf-8"))
        self.calls = []

    async def get_response(self, system_instructions, input, model_settings, tools,
                           output_schema, handoffs, tracing, **kwargs):
        name = output_schema.output_type.__name__
        self.calls.append((name, system_instructions, input))
        # Every specialist tool stays in the request so the prompt prefix can be cached,
        # so the scripted Director advances the sequence itself instead of relying on
        # the SDK to hide the tools it must not call yet.
        turn = sum(1 for call in self.calls if call[0] == "DirectorReview")
        if name == "DirectorReview" and tools and turn <= len(tools):
            output = ResponseFunctionToolCall(
                type="function_call", name=tools[turn - 1].name, call_id=uuid4().hex,
                arguments=json.dumps({"input": "Campanha institucional de final de semana; sem ofertas confirmadas."}),
            )
        else:
            output = ResponseOutputMessage(
                id=uuid4().hex, type="message", role="assistant", status="completed",
                content=[ResponseOutputText(type="output_text", annotations=[],
                                           text=json.dumps(self.responses[name], ensure_ascii=False))],
            )
        return ModelResponse(output=[output], usage=Usage(), response_id=None)

    async def stream_response(self, *args, **kwargs):
        raise NotImplementedError("Demonstração usa somente Runner.run")
        yield  # pragma: no cover
