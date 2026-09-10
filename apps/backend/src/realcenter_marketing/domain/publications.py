"""Publishing presets: one source of truth for UI, agents and image export."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

PHOTO_SOURCE = 'https://help.instagram.com/1631821640426723'
REEL_SOURCE = 'https://help.instagram.com/1038071743007909'
API_SOURCE = 'https://developers.facebook.com/docs/instagram-platform/content-publishing/'

# Export dimensions, not the generator's working canvas. 3:4 is app-oriented;
# keep API-oriented feed/carousel presets within the conservative 4:5 range.
PRESETS = {
    'feed_portrait': dict(label='Feed vertical', ratio='4:5', width=1080, height=1350, types=['feed', 'carousel'], source=PHOTO_SOURCE),
    'feed_square': dict(label='Feed quadrado', ratio='1:1', width=1080, height=1080, types=['feed', 'carousel'], source=PHOTO_SOURCE),
    'feed_landscape': dict(label='Feed horizontal', ratio='1.91:1', width=1080, height=566, types=['feed', 'carousel'], source=PHOTO_SOURCE),
    'feed_tall': dict(label='Feed alto · publicação pelo app', ratio='3:4', width=1080, height=1440, types=['feed', 'carousel'], source=PHOTO_SOURCE),
    'story': dict(label='Story', ratio='9:16', width=1080, height=1920, types=['story'], source=API_SOURCE),
    'reel_cover': dict(label='Capa de Reel', ratio='9:16', width=1080, height=1920, types=['reel_cover'], source=REEL_SOURCE),
}


class Publication(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['feed', 'story', 'carousel', 'reel_cover'] = 'feed'
    preset: Literal['feed_portrait', 'feed_square', 'feed_landscape', 'feed_tall', 'story', 'reel_cover'] = 'feed_portrait'
    slides: int = Field(default=1, ge=1, le=10)

    @model_validator(mode='after')
    def compatible(self):
        if self.kind not in PRESETS[self.preset]['types']:
            raise ValueError('Proporção incompatível com o tipo de publicação')
        if (self.kind == 'carousel' and self.slides < 2) or (self.kind != 'carousel' and self.slides != 1):
            raise ValueError('Carrossel precisa de 2 a 10 cards; demais formatos usam uma arte')
        return self

    @property
    def dimensions(self):
        p = PRESETS[self.preset]
        return p['width'], p['height']

    def instructions(self):
        w, h = self.dimensions
        return (f'Entrega escolhida: {self.kind}, {self.slides} imagem(ns), {w}x{h} px, '
                f'proporção {PRESETS[self.preset]["ratio"]}. A escolha prevalece sobre sugestões de formatos. '
                'Stories e capas de Reel: 1080x1920; mantenha texto e logo afastados das bordas. '
                'Reel é vídeo: esta execução só produz a capa estática. '
                'Carrossel: planeje e escreva cada card em sequência, com abertura, desenvolvimento e CTA; '
                'Copywriter: preencha carousel_cards com exatamente o número escolhido, numerados de 1 a N; fora de carrossel use lista vazia. '
                'todos os cards têm a mesma proporção. Não repita a mesma arte em todos os cards.')


def catalog():
    return [dict(id=key, **value) for key, value in PRESETS.items()]
