"""Local audit trail; never records credentials, prompts or raw provider responses."""
import json
import threading
import traceback
import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError
from realcenter_marketing.infrastructure.observability.costs import PRICING_SOURCE, image_cost, text_cost
from realcenter_marketing.application.diagnostics import error_details


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
        temporary.replace(target)

    def record_usage(self, agent, model, usage):
        details = usage.input_tokens_details
        cached = int(getattr(details, "cached_tokens", 0) or 0)
        cache_write = int(getattr(details, "cache_write_tokens", 0) or 0)
        cost = text_cost(model, usage.input_tokens, cached, cache_write, usage.output_tokens)
        with self._usage_lock:
            data = self._usage()
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
