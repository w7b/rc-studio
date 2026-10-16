// A catalog id is `provider:model`, and the model half may itself contain colons:
// HuggingFace pins an inference provider or a routing policy that way, as in
// `huggingface:openai/gpt-oss-120b:groq`. Splitting on every colon and keeping the last
// piece would label that campaign "groq".
export function modelLabel(id) {
  if (!id) return '';
  const separator = id.indexOf(':');
  return separator === -1 ? id : id.slice(separator + 1);
}

// Labels carry the model's own name only; the provider becomes the group it sits under,
// so the form stays clean without losing which key a model needs. Order follows the
// catalog, which keeps the server default first.
export function groupByProvider(options) {
  const groups = new Map();
  for (const option of options) {
    const label = option.provider_label || option.provider;
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(option);
  }
  return [...groups.entries()];
}
