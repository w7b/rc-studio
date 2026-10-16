import re
from agents import AgentHooks

class ProgressHooks(AgentHooks):
    def __init__(self, journal, role, model, *, save_output=True):
        self.save_output = save_output
        self.journal = journal
        self.role = role
        self.model = model

    async def on_start(self, context, agent):
        self.journal.current_agent = agent.name
        self.journal.emit("started", agent.name)

    async def on_end(self, context, agent, output):
        if self.save_output:
            self.journal.save(self.role, output)
        self.journal.emit("completed", agent.name)

    async def on_llm_start(self, context, agent, system_prompt, input_items):
        self.journal.current_agent = agent.name
        self.journal.emit("thinking", agent.name)

    async def on_llm_end(self, context, agent, response):
        self.journal.record_usage(agent.name, self.model, response.usage)
        summary = []
        for item in response.output:
            entry = {'type': getattr(item, 'type', 'unknown')}
            status = getattr(item, 'status', None)
            if status in ('completed', 'incomplete', 'in_progress'):
                entry['status'] = status
            content = getattr(item, 'content', None) or []
            entry['content_types'] = [getattr(part, 'type', 'unknown') for part in content]
            summary.append(entry)
        response_id = getattr(response, 'response_id', None)
        self.journal.emit('response_received', agent.name, model=self.model,
                          response_id=response_id if isinstance(response_id, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,150}', response_id) else None,
                          summary=summary, input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens)
