"""Usage accounting using public Standard-tier list prices, in US dollars."""
from decimal import Decimal


TEXT_PRICES = {
    "gpt-6-astra": {"input": Decimal("10"), "cached": Decimal("1"), "cache_write": Decimal("12.5"), "output": Decimal("50")},
    "gpt-5.6-sol": {"input": Decimal("4"), "cached": Decimal("0.4"), "output": Decimal("20")},
    "gpt-5.6-terra": {"input": Decimal("2"), "cached": Decimal("0.2"), "output": Decimal("12")},
}

IMAGE_PRICES = {
    # Standard tier, 1024x1536, medium. Image inputs/text inputs may add cost.
    "gpt-image-2": Decimal("0.041"),
}

PRICING_SOURCE = "https://developers.openai.com/api/docs/models/gpt-6-astra"


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
    # GPT-6 Astra applies long-context rates to requests over 272K input tokens.
    if model == "gpt-6-astra" and input_tokens > 272_000:
        total *= Decimal("2")
        output_rate *= Decimal("1.5")
    total += Decimal(output_tokens) * output_rate
    return total / Decimal(1_000_000)


def image_cost(model):
    return IMAGE_PRICES.get(model)
