import asyncio

from agents import ModelProvider
from pydantic import SecretStr

from realcenter_marketing.domain.campaigns import CampaignBrief
from realcenter_marketing.bootstrap.settings import Settings
from realcenter_marketing.bootstrap.campaigns import create_campaign


def test_timeout_accepts_twenty_minutes(tmp_path, monkeypatch):
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "1200")
    assert Settings.load(tmp_path).timeout_seconds == 1200


def test_env_loading_and_environment_precedence(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=fixture-secret\nOPENAI_MODEL=fixture-model\nMAX_TURNS=8\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MAX_TURNS", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "environment-model")
    settings = Settings.load(tmp_path)
    assert settings.model == "environment-model"
    assert settings.max_turns == 8
    assert settings.api_key.get_secret_value() == "fixture-secret"
    assert "fixture-secret" not in repr(settings)


def test_live_provider_is_inherited_by_all_specialists(settings, demo, monkeypatch):
    from realcenter_marketing.infrastructure.agents_sdk import runtime as workflow
    seen_models = []

    class OfflineProvider(ModelProvider):
        def get_model(self, model_name):
            seen_models.append(model_name)
            return demo

    def provider_factory(*, openai_client, use_responses=None):
        # The runtime now builds the client itself, so each run owns its connection pool.
        assert openai_client.api_key == "fixture-secret"
        return OfflineProvider()

    monkeypatch.setattr(workflow, "OpenAIProvider", provider_factory)
    settings.api_key = SecretStr("fixture-secret")
    settings.model = "fixture-model"
    result = asyncio.run(create_campaign(CampaignBrief(request="Campanha"), settings))
    assert result.execution_mode == "live"
    # Plan, three specialists, review: one call each, no Director re-reads.
    assert len(seen_models) == 5
    assert set(seen_models) == {"fixture-model"}
