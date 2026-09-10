import asyncio
import json

import pytest
from agents import ModelBehaviorError, Usage
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

from realcenter_marketing.infrastructure.observability.journal import RunJournal
from realcenter_marketing.infrastructure.observability.costs import text_cost
from realcenter_marketing.domain.campaigns import CampaignBrief
from realcenter_marketing.bootstrap.campaigns import create_campaign


def test_each_agent_is_visible_and_caption_is_exported(settings, demo, tmp_path):
    events = []
    journal = RunJournal(tmp_path / "run", events.append)
    brief = CampaignBrief(request="Campanha", confirmed_facts=["Produto confirmado exclusivo"])
    campaign = asyncio.run(create_campaign(brief, settings, model=demo, journal=journal))
    assert [e["agent"] for e in events if e["event"] == "started"] == [
        "Marketing Director", "Social Media Senior", "Copywriter Senior", "Creative Producer"]
    assert len([e for e in events if e["event"] == "completed"]) == 4
    assert (journal.directory / "legenda-feed.txt").read_text(encoding="utf-8").strip() == campaign.copywriting.feed_caption
    for role in ("social_media", "copywriter", "creative", "marketing_director"):
        assert json.loads((journal.directory / f"{role}.json").read_text(encoding="utf-8"))
    assert all("Produto confirmado exclusivo" in call[1] for call in demo.calls)


def test_failure_preserves_prior_deliverables_and_safe_diagnostics(settings, demo, tmp_path):
    demo.responses["CreativeBrief"]["assets"] = []
    journal = RunJournal(tmp_path / "run")
    with pytest.raises(ModelBehaviorError):
        asyncio.run(create_campaign(CampaignBrief(request="Campanha"), settings, model=demo, journal=journal))
    assert (journal.directory / "copywriter.json").exists()
    assert (journal.directory / "legenda-feed.txt").exists()
    assert not (journal.directory / "campaign.json").exists()
    event = json.loads((journal.directory / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert event["agent"] == "Creative Producer"
    assert event["error_type"] == "ModelBehaviorError"
    # SDK redacts model validation payloads by default, including the cause.
    assert "input" not in event


def test_usage_and_astra_cost_are_recorded_per_agent(tmp_path):
    journal = RunJournal(tmp_path / "run")
    usage = Usage(requests=1, input_tokens=10_000, output_tokens=1_000, total_tokens=11_000,
                  input_tokens_details=InputTokensDetails(cached_tokens=2_000, cache_write_tokens=0),
                  output_tokens_details=OutputTokensDetails(reasoning_tokens=400))
    journal.record_usage("Copywriter Senior", "gpt-6-astra", usage)
    data = json.loads((journal.directory / "usage.json").read_text(encoding="utf-8"))
    assert data["text"]["input_tokens"] == 10_000
    assert data["text"]["cached_input_tokens"] == 2_000
    assert data["text"]["output_tokens"] == 1_000
    assert data["text"]["cost_usd"] == pytest.approx(.132)
    assert data["text"]["by_agent"]["Copywriter Senior"]["cost_usd"] == pytest.approx(.132)
    assert float(text_cost("gpt-6-astra", 10_000, 2_000, 0, 1_000)) == pytest.approx(.132)


def test_unknown_model_keeps_tokens_without_inventing_price(tmp_path):
    journal = RunJournal(tmp_path / "run")
    journal.record_usage("Agent", "custom-model", Usage(requests=1, input_tokens=5,
                         output_tokens=2, total_tokens=7))
    data = json.loads((journal.directory / "usage.json").read_text(encoding="utf-8"))
    assert data["text"]["total_tokens"] == 7
    assert data["text"]["cost_usd"] is None
