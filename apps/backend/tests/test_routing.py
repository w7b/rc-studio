import asyncio
import json

import pytest
from agents import AgentOutputSchema, ModelBehaviorError

from realcenter_marketing.infrastructure.agents_sdk.team_factory import build_team, load_manifest
from realcenter_marketing.domain.campaigns import Campaign, CampaignBrief, CopyPack, SocialPlan
from realcenter_marketing.bootstrap.campaigns import create_campaign, save_campaign


def test_director_calls_specialists_and_preserves_outputs(settings, demo, tmp_path):
    result = asyncio.run(create_campaign(CampaignBrief(request="Crie uma campanha para o final de semana da Real Center."), settings, model=demo))
    assert [call[0] for call in demo.calls] == [
        "DirectorReview", "SocialPlan", "DirectorReview", "CopyPack",
        "DirectorReview", "CreativeBrief", "DirectorReview",
    ]
    assert result.delegation_log == ["social_media", "copywriter", "creative"]
    assert result.social.model_dump() == demo.responses["SocialPlan"]
    assert result.copywriting.model_dump() == {**demo.responses["CopyPack"], 'carousel_cards': []}
    expected_creative = json.loads(json.dumps(demo.responses['CreativeBrief']))
    for asset in expected_creative['assets']:
        if asset['format'] == 'stories': asset['dimensions'] = '1080x1920 px (9:16)'
        if asset['format'] == 'feed': asset['dimensions'] = '1080x1350 px (4:5)'
    assert result.creative.model_dump() == expected_creative
    copy_context = next(c[1] for c in demo.calls if c[0] == "CopyPack")
    creative_context = next(c[1] for c in demo.calls if c[0] == "CreativeBrief")
    assert demo.responses["SocialPlan"]["strategy"] in copy_context
    assert demo.responses["CopyPack"]["headline"] in creative_context
    assert all("Brand Kit" in call[1] for call in demo.calls)
    path = save_campaign(result, tmp_path)
    assert Campaign.model_validate_json(path.read_text(encoding="utf-8")) == result
    assert save_campaign(result, tmp_path) != path


def test_only_current_specialist_enabled(settings, demo):
    team = build_team(settings, model=demo)
    assert [t.is_enabled(None, team.director) for t in team.director.tools] == [True, False, False]
    team.delegation_log.append("social_media")
    assert [t.is_enabled(None, team.director) for t in team.director.tools] == [False, True, False]


def test_tools_match_manifests_and_future_agents_are_disabled(settings, demo):
    team = build_team(settings, model=demo)
    assert not team.director.handoffs
    for role, agent in {"marketing_director": team.director, **team.specialists}.items():
        assert {t.name for t in agent.tools} == set(load_manifest(settings.project_root, role).allowed_tools)
        AgentOutputSchema(agent.output_type)
    assert all(not agent.tools for agent in team.specialists.values())
    for role in ["performance", "marketing_analyst"]:
        assert load_manifest(settings.project_root, role).status == "planned"
        assert role not in team.specialists


def test_early_director_completion_is_rejected(settings, demo):
    original = demo.get_response

    async def no_tools(*args, **kwargs):
        kwargs["tools"] = []
        return await original(*args, **kwargs)

    demo.get_response = no_tools
    with pytest.raises(ValueError, match="sem concluir"):
        asyncio.run(create_campaign(CampaignBrief(request="Campanha"), settings, model=demo))


def test_mismatched_stories_are_rejected(settings, demo):
    demo.responses["CopyPack"]["stories"][0]["number"] = 99
    with pytest.raises(ValueError, match="corresponder"):
        asyncio.run(create_campaign(CampaignBrief(request="Campanha"), settings, model=demo))


def test_invalid_specialist_output_fails(settings, demo):
    demo.responses["SocialPlan"]["stories"] = []
    with pytest.raises(ModelBehaviorError):
        asyncio.run(create_campaign(CampaignBrief(request="Campanha"), settings, model=demo))
    assert "CopyPack" not in [call[0] for call in demo.calls]


def test_outputs_forbid_extra_fields_and_blank_content(demo):
    data = dict(demo.responses["CopyPack"], price=10)
    with pytest.raises(ValueError):
        CopyPack.model_validate(data)
    with pytest.raises(ValueError):
        CampaignBrief(request="  ")
    data = json.loads(json.dumps(demo.responses["SocialPlan"]))
    data["stories"][1]["number"] = 1
    with pytest.raises(ValueError, match="consecutivos"):
        SocialPlan.model_validate(data)


def test_live_requires_configuration(settings):
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        asyncio.run(create_campaign(CampaignBrief(request="Campanha"), settings))
