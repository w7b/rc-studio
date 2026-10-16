"""Usage accounting using public Standard-tier list prices, in US dollars."""
from decimal import Decimal


TEXT_PRICES = {
    "gpt-6-astra": {"input": Decimal("10"), "cached": Decimal("1"), "cache_write": Decimal("12.5"), "output": Decimal("50")},
    # https://developers.openai.com/api/docs/models/gpt-6-luna
    "gpt-6-luna": {"input": Decimal("0.1"), "cached": Decimal("0.01"), "cache_write": Decimal("0.125"), "output": Decimal("0.5")},
    "gpt-5.6-sol": {"input": Decimal("4"), "cached": Decimal("0.4"), "output": Decimal("20")},
    "gpt-5.6-terra": {"input": Decimal("2"), "cached": Decimal("0.2"), "output": Decimal("12")},
}

# Standard tier, medium quality, per image and per working canvas. Image and text
# inputs may add cost. The studio renders custom canvases (1088x1088, 1152x1440,
# 1152x1536, 1152x2048, 1536x800) that have no published price here, so they report
# an unknown cost instead of a wrong one; add them when the price is confirmed.
IMAGE_PRICES = {
    "gpt-image-2": {"1024x1536": Decimal("0.041")},
}

PRICING_SOURCE = "https://developers.openai.com/api/docs/models/gpt-6-astra"
LONG_CONTEXT_MODELS = {"gpt-6-astra", "gpt-6-luna"}


def text_cost(model, input_tokens, cached_tokens, cache_write_tokens, output_tokens):
    if input_tokens == cached_tokens == cache_write_tokens == output_tokens == 0:
        return Decimal("0")
    prices = TEXT_PRICES.get(model)
    if not prices:
        return None
    uncached = max(input_tokens - cached_tokens - cache_write_tokens, 0)
    total = Decimal(uncached) * prices["input"]
    total += Decimal(cached_tokens) * prices["cached"]
    total += Decimal(cache_write_tokens) * prices.get("cache_write", prices["input"])
    output_rate = prices["output"]
    # The GPT-6 family applies long-context rates to requests over 272K input tokens:
    # 2x on input and cache, 1.5x on output (stated on the Astra and Luna model pages).
    if model in LONG_CONTEXT_MODELS and input_tokens > 272_000:
        total *= Decimal("2")
        output_rate *= Decimal("1.5")
    total += Decimal(output_tokens) * output_rate
    return total / Decimal(1_000_000)


def image_cost(model, size):
    """None when that canvas has no published price.

    Pricing belongs here, not at the call site: an unpriced render must be reported
    as unknown, never as zero, and never gated by a size the studio cannot produce.
    """
    return IMAGE_PRICES.get(model, {}).get(size)
