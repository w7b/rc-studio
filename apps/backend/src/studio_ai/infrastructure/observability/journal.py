"""Local audit trail; never records credentials, prompts or raw provider responses."""
import json
import threading
import time
import traceback
import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError
from studio_ai.infrastructure.observability.costs import PRICING_SOURCE, image_cost, text_cost
from studio_ai.application.diagnostics import error_details


USAGE_REPLACE_ATTEMPTS = 10


class RunJournal:
    def __init__(self, directory: Path, callback=None):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=False)
        self.callback = callback
        self.current_agent = None
        self._usage_lock = threading.Lock()

    @classmethod
    def resume(cls, directory):
        if not directory.is_dir():
            raise ValueError('Execução não encontrada')
        journal = cls.__new__(cls)
        journal.directory, journal.callback, journal.current_agent = directory, None, None
        journal._usage_lock = threading.Lock()
        return journal

    def emit(self, event, agent=None, **details):
        record = {"time": datetime.now(timezone.utc).isoformat(), "event": event,
                  "agent": agent, **details}
        with (self.directory / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        if self.callback:
            self.callback(record)

    def save(self, role, value):
        (self.directory / f"{role}.json").write_text(value.model_dump_json(indent=2), encoding="utf-8")
        if role == "copywriter":
            (self.directory / "legenda-feed.txt").write_text(value.feed_caption + "\n", encoding="utf-8")

    def _usage(self):
        path = self.directory / "usage.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        return {"currency": "USD", "pricing_basis": "estimated_standard_list_price",
                "pricing_source": PRICING_SOURCE, "text": {"by_agent": {}},
                "image": {"count": 0, "cost_usd": 0.0}, "total_cost_usd": 0.0}

    def _write_usage(self, data):
        target = self.directory / "usage.json"
        temporary = self.directory / "usage.tmp"
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        # On Windows a file someone is reading cannot be replaced: GET /api/usage polling
        # mid-run made the swap fail with PermissionError and took the whole campaign down.
        # The reader holds it for a moment, so wait it out instead of failing the run.
        for attempt in range(USAGE_REPLACE_ATTEMPTS):
            try:
                temporary.replace(target)
                return
            except PermissionError:
                if attempt == USAGE_REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(0.02 * (attempt + 1))

    def _usage_entries(self, data):
        if 'entries' not in data:
            from studio_ai.infrastructure.admin_metrics import events_from, timestamp, usage_record
            dates = [stamp for e in events_from(self.directory / 'events.jsonl')
                     if (stamp := timestamp(e.get('time'))) is not None]
            baseline = usage_record(data, min(dates) if dates else None)
            data['entries'] = [{**baseline, 'legacy': True}] if baseline['requests'] else []
        return data['entries']

    def record_usage(self, agent, model, usage):
        details = usage.input_tokens_details
        cached = int(getattr(details, "cached_tokens", 0) or 0)
        cache_write = int(getattr(details, "cache_write_tokens", 0) or 0)
        cost = text_cost(model, usage.input_tokens, cached, cache_write, usage.output_tokens)
        with self._usage_lock:
            data = self._usage()
            entries = self._usage_entries(data)
            entries.append({'time': datetime.now(timezone.utc).isoformat(),
                            'requests': int(usage.requests or 0), 'images': 0,
                            'input_tokens': int(usage.input_tokens or 0),
                            'output_tokens': int(usage.output_tokens or 0),
                            'cached_input_tokens': cached, 'known_cost_usd': float(cost or 0),
                            'unpriced_records': int(cost is None)})
            text = data["text"]
            text["model"] = model
            bucket = text["by_agent"].setdefault(agent, {"requests": 0, "input_tokens": 0,
                "cached_input_tokens": 0, "cache_write_input_tokens": 0,
                "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0})
            for key, value in (("requests", usage.requests), ("input_tokens", usage.input_tokens),
                               ("cached_input_tokens", cached), ("cache_write_input_tokens", cache_write),
                               ("output_tokens", usage.output_tokens), ("total_tokens", usage.total_tokens)):
                bucket[key] += int(value or 0)
            if cost is None:
                bucket["cost_usd"] = None
            elif bucket["cost_usd"] is not None:
                bucket["cost_usd"] += float(cost)
            for key in ("requests", "input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "total_tokens"):
                text[key] = sum(agent_data[key] for agent_data in text["by_agent"].values())
            costs = [agent_data["cost_usd"] for agent_data in text["by_agent"].values()]
            text["cost_usd"] = None if any(value is None for value in costs) else sum(costs)
            image_value = data["image"].get("cost_usd")
            data["total_cost_usd"] = None if text["cost_usd"] is None or image_value is None else text["cost_usd"] + image_value
            self._write_usage(data)

    def record_image_usage(self, model, size='1024x1536', usage=None):
        cost = image_cost(model, size)
        with self._usage_lock:
            data = self._usage()
            entries = self._usage_entries(data)
            entries.append({'time': datetime.now(timezone.utc).isoformat(), 'requests': 1, 'images': 1,
                            'input_tokens': int((usage or {}).get('input_tokens', 0) or 0),
                            'output_tokens': int((usage or {}).get('output_tokens', 0) or 0),
                            'known_cost_usd': float(cost or 0), 'unpriced_records': int(cost is None)})
            image = data["image"]
            image["model"], image["size"], image["quality"] = model, size, "medium"
            image["count"] += 1
            image["cost_usd"] = None if cost is None or image['cost_usd'] is None else image['cost_usd'] + float(cost)
            if usage:
                for key in ('input_tokens', 'output_tokens', 'total_tokens'):
                    image[key] = image.get(key, 0) + int(usage.get(key, 0) or 0)
            text_value = data["text"].get("cost_usd", 0.0)
            data["total_cost_usd"] = None if text_value is None or image["cost_usd"] is None else text_value + image["cost_usd"]
            self._write_usage(data)
