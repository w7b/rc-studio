"""Image batching and resume policy, independent of provider and filesystem."""
from realcenter_marketing.application.diagnostics import error_details
from realcenter_marketing.application.errors import public_error
from realcenter_marketing.application.campaigns.ports import CampaignRepository, ImageGenerator


class ImageWorkflow:
    def __init__(self, repository: CampaignRepository, generate: ImageGenerator):
        self.repository, self.generate = repository, generate

    def execute(self, campaign, journal, product, changes='', base_image=None, revision_reference=None):
        journal.current_agent = 'Produção de imagem'
        journal.emit('image_started', journal.current_agent)
        try:
            carousel = campaign.brief.publication.kind == 'carousel'
            cards = campaign.copywriting.carousel_cards if carousel else [None]
            if base_image:
                number = self.repository.image_metadata(base_image).get('card')
                cards = [next((c for c in cards if c and c.number == number), None)]
                if carousel and cards == [None]:
                    raise ValueError('Card original não identificado para edição')
            batch = self.repository.carousel_files(journal) if carousel else {'files': {}}
            style = None
            for card in cards:
                key = str(card.number) if card else '1'
                previous = self.repository.existing_image(journal, batch['files'].get(key))
                if not base_image and previous:
                    style = style or previous
                    continue
                options = dict(changes=changes, base_image=base_image, card=card,
                               style_image=style, revision_reference=revision_reference) if card or base_image else {}
                path = self.generate(campaign, journal, product, **options)
                journal.emit('image_completed', journal.current_agent, file=path.name,
                             card=card.number if card else None)
                if carousel:
                    batch['files'][key] = path.name
                    self.repository.save_carousel(journal, batch)
                    style = style or path
        except Exception as exc:
            journal.emit('image_failed', journal.current_agent, **error_details(exc), message=public_error(exc))
            raise
