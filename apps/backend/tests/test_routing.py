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


def test_out_of_order_specialist_is_refused_without_hiding_the_tool(settings, demo):
    """The tool list must not change between turns, or the cached prefix is lost.

    A whole campaign was measured at 0 cached input tokens because every Director turn
    sent a different set of tools. Order is enforced when the tool runs instead.
    """
    team = build_team(settings, model=demo)
    names = [tool.name for tool in team.director.tools]
    assert names == ['consult_social_media', 'consult_copywriter', 'consult_creative']

    async def call(tool):
        return await tool.on_invoke_tool(None, '{"input": "x"}')

    copywriter = team.director.tools[1]
    refused = asyncio.run(call(copywriter))
    assert 'fora de ordem' in refused.lower() and 'consult_social_media' in refused

    team.delegation_log.append('social_media')
    # The same tool is now the pending step, and the list never changed.
    assert [tool.name for tool in team.director.tools] == names
    assert 'fora de ordem' not in asyncio.run(call(copywriter)).lower()


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


def test_brand_kit_is_scoped_to_what_each_role_acts_on(settings):
    """The kit is repeated in every agent's instructions, on every request it makes."""
    from realcenter_marketing.infrastructure.resources import load_brand

    root = settings.project_root
    whole = json.loads(load_brand(root))
    creative = json.loads(load_brand(root, 'creative'))
    copywriter = json.loads(load_brand(root, 'copywriter'))

    def names(kit):
        # Keys are relative paths; chr(92) avoids an escape in this literal.
        return {key.split(chr(92))[-1].split('/')[-1] for key in kit}

    assert 'visual-guidelines.md' in names(creative), 'o Creative dirige a arte'
    assert 'visual-guidelines.md' not in names(copywriter), 'o Copywriter não desenha'
    assert {'brand.md', 'tone-of-voice.md'} <= names(copywriter)
    assert len(load_brand(root, 'copywriter')) < len(load_brand(root, 'creative'))
    # Folder documentation and the human review checklist never reach a prompt.
    assert not any(name.lower() in {'readme.md', 'quality-checklist.md'} for name in names(whole))
    # An unknown role keeps the whole kit rather than losing guidance silently.
    assert json.loads(load_brand(root, 'papel_inexistente')) == whole
