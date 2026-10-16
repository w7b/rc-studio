"""Bound image prompts without truncating campaign facts or revision instructions."""
import json
import re

from studio_ai.application.errors import ImageRequestLimitError

# https://developers.openai.com/api/reference/resources/images/methods/edit
MAX_IMAGE_PROMPT_CHARS = 32_000
MAX_IMAGE_REFERENCES = 16


def fit_image_prompt(instructions, brand_documents, reference_roles, limit=MAX_IMAGE_PROMPT_CHARS):
    # A renderer that receives no input image is never told that images were attached.
    suffix = ('\nImagens de entrada, em ordem: ' + json.dumps(reference_roles, ensure_ascii=False)
              if reference_roles else '')
    start = instructions + '\nBrand Kit:\n'
    budget = limit - len(start) - len(suffix)
    full_brand = '\n'.join(brand_documents.values())
    if len(full_brand) <= budget:
        return start + full_brand + suffix, False

    # Keep full paragraphs in source order. Round-robin gives every guide space
    # (identity, palette, typography, visual direction) before its later examples.
    # Attach headings to their paragraph so selection cannot leave orphan headings.
    documents = []
    for content in brand_documents.values():
        blocks, heading = [], ''
        for paragraph in re.split(r'\n\s*\n', content.strip()):
            if all(line.startswith('#') for line in paragraph.splitlines()):
                heading += paragraph + '\n\n'
            else:
                blocks.append(heading + paragraph)
                heading = ''
        if heading:
            blocks.append(heading.rstrip())
        documents.append(blocks)
    selected = [[] for _ in documents]
    used = 0
    for index in range(max(map(len, documents), default=0)):
        for target, blocks in zip(selected, documents):
            if index >= len(blocks):
                continue
            block = blocks[index]
            cost = len(block) + (2 if used else 0)
            if used + cost <= budget:
                target.append(block)
                used += cost
    # Never silently send a request without any part of a nonempty guide.
    if any(blocks and not kept for blocks, kept in zip(documents, selected)):
        raise ImageRequestLimitError('prompt', len(start) + len(full_brand) + len(suffix), limit)
    result = start + '\n\n'.join(block for blocks in selected for block in blocks) + suffix
    if len(result) > limit:
        raise ImageRequestLimitError('prompt', len(result), limit)
    return result, True


def brand_essence(brand_documents, budget):
    """Leading paragraphs of each guide, round-robin, inside a hard budget.

    A small text encoder silently truncates whatever does not fit, so sending the whole
    Brand Kit would drop the headline instead of the least important guide. Selecting by
    source order keeps each guide's principles, which open every document.
    """
    documents = []
    for content in brand_documents.values():
        blocks = [block.strip() for block in re.split(r'\n\s*\n', content.strip())
                  if block.strip() and not all(line.startswith('#')
                                               for line in block.splitlines())]
        documents.append(blocks)
    selected, used = [], 0
    for index in range(max(map(len, documents), default=0)):
        for blocks in documents:
            if index >= len(blocks):
                continue
            block = ' '.join(blocks[index].split())
            cost = len(block) + (1 if used else 0)
            if used + cost <= budget:
                selected.append(block)
                used += cost
    return ' '.join(selected)


def compact_image_prompt(headline, cta, visual_direction, publication, brand_documents, limit,
                         described='a marca do Brand Kit'):
    """Self-contained prompt for a text-to-image renderer working under a small budget.

    No product photo, logo or style reference reaches such a model, so the piece is
    described in words only and nothing in the text claims an attachment.
    """
    width, height = publication.dimensions
    head = (f'Arte publicitária de {publication.kind} {width}x{height} px para {described}, '
            f'com texto em português. Headline: "{headline}". CTA: "{cta}". ')
    tail = ' Não invente preço, desconto, validade, endereço nem produto ausente.'
    room = limit - len(head) - len(tail)
    if room <= 0:
        return (head + tail)[:limit], True
    direction = ' '.join((visual_direction or '').split())[:room // 2]
    if direction:
        head += 'Direção visual: ' + direction + ' '
    label = 'Estilo da marca: '
    essence = brand_essence(brand_documents, limit - len(head) - len(tail) - len(label))
    if essence:
        head += label + essence
    return (head + tail)[:limit], True
