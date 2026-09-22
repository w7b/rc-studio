import asyncio
import json

import pytest
from agents import AgentOutputSchema, ModelBehaviorError

from realcenter_marketing.infrastructure.agents_sdk.team_factory import build_team, load_manifest
from realcenter_marketing.domain.campaigns import Campaign, CampaignBrief, CopyPack, SocialPlan
from realcenter_marketing.bootstrap.campaigns import create_campaign, save_campaign


def test_director_plans_then_specialists_run_then_director_reviews(settings, demo, tmp_path):
    result = asyncio.run(create_campaign(CampaignBrief(request="Crie uma campanha para o final de semana da Real Center."), settings, model=demo))
    # One plan, one call per specialist, one review. The Director no longer re-reads a
    # growing conversation between every delegation.
    assert [call[0] for call in demo.calls] == [
        "CampaignPlan", "SocialPlan", "CopyPack", "CreativeBrief", "DirectorReview",
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


def test_no_agent_is_given_a_tool(settings, demo):
    """This is what lets a model outside OpenAI direct a campaign.

    Several providers disable tool calling as soon as the answer is constrained to a
    schema. The old Director needed both at once, which disqualified every model that
    made that trade. Nothing in the team holds a tool now, so the trade never comes up.
    """
    team = build_team(settings, model=demo)
    agents = {"planner": team.planner, "reviewer": team.reviewer, **team.specialists}
    for name, agent in agents.items():
        assert not agent.tools, f'{name} recebeu tools'
        assert not agent.handoffs, f'{name} recebeu handoffs'
        AgentOutputSchema(agent.output_type)
    # The manifest is the source of that claim, not just the construction above.
    assert not load_manifest(settings.project_root, "marketing_director").allowed_tools
    for role in ["performance", "marketing_analyst"]:
        assert load_manifest(settings.project_root, role).status == "active"
        assert role not in team.specialists


def test_specialists_run_in_order_and_a_failure_stops_the_pipeline(settings, demo):
    """Order used to be enforced by refusing out-of-turn tool calls. It is the loop now,
    and a specialist never starts before the previous delivery has validated."""
    demo.responses["CopyPack"]["stories"][0]["number"] = 99
    with pytest.raises(ValueError, match="corresponder"):
        asyncio.run(create_campaign(CampaignBrief(request="Campanha"), settings, model=demo))
    names = [call[0] for call in demo.calls]
    assert names.index("SocialPlan") < names.index("CopyPack") < names.index("CreativeBrief")


def test_an_incomplete_run_is_never_saved(settings, demo):
    """A runtime that returns fewer deliveries than the pipeline promises is refused."""
    from realcenter_marketing.application.campaigns.create_campaign import create_campaign as compose
    from realcenter_marketing.application.orchestration import AgentResult

    async def truncated(_brief):
        return AgentResult(demo.responses["DirectorReview"], {"social_media": object()}, ["social_media"])

    with pytest.raises(ValueError, match="sem concluir"):
        asyncio.run(compose(CampaignBrief(request="Campanha"), truncated, demo=True))


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
