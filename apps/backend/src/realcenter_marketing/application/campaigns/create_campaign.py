from realcenter_marketing.domain.campaigns import Campaign, CampaignBrief, DirectorReview, CarouselCard
from realcenter_marketing.application.orchestration import SPECIALIST_STEPS
from .ports import AgentRuntime, Journal

async def create_campaign(brief: CampaignBrief, runtime: AgentRuntime, *, demo=False, journal: Journal | None = None) -> Campaign:
    result = await runtime(brief)
    required = {role for role, _ in SPECIALIST_STEPS}
    if set(result.outputs) != required:
        raise ValueError("Director encerrou sem concluir todos os especialistas; campanha não salva")
    if demo and brief.publication.kind == 'carousel':
        result.outputs['copywriter'].carousel_cards = [CarouselCard(number=i, headline=f'Card {i} · Demonstração',
            body='Exemplo fixo, sem API.', visual='Layout de demonstração', cta='Confira')
            for i in range(1, brief.publication.slides + 1)]
        if journal:
            journal.save('copywriter', result.outputs['copywriter'])
    # Dimension strings are application-owned, never trusted to model recall.
    for asset in result.outputs['creative'].assets:
        if asset.format == 'stories':
            asset.dimensions = '1080x1920 px (9:16)'
        elif asset.format == 'feed':
            from realcenter_marketing.domain.publications import PRESETS
            pub = brief.publication
            p = PRESETS[pub.preset] if pub.kind in ('feed', 'carousel') else PRESETS['feed_portrait']
            asset.dimensions = f'{p["width"]}x{p["height"]} px ({p["ratio"]})'
    if journal:
        journal.save('creative', result.outputs['creative'])
    return Campaign(
        execution_mode="demo" if demo else "live", brief=brief,
        director=DirectorReview.model_validate(result.director),
        social=result.outputs["social_media"], copywriting=result.outputs["copywriter"],
        creative=result.outputs["creative"], delegation_log=result.delegation_log,
    )
