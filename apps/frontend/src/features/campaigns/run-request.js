// Single serializer for the form and the backend contract test.
export function buildRunRequest({
  request,
  facts,
  selection,
  imageModel,
  publication,
  image,
  product,
  upload,
  referenceUpload,
  referenceId,
}) {
  const mode = selection === 'demo' ? 'demo' : 'live';
  return {
    request,
    confirmed_facts: facts
      .split('\n')
      .map((value) => value.trim())
      .filter(Boolean),
    mode,
    model_id: mode === 'demo' ? null : selection || null,
    image_model_id: mode === 'demo' ? null : imageModel || null,
    publication,
    generate_image: mode === 'live' && image,
    product_id: upload ? null : product || null,
    upload: upload || null,
    reference_upload: referenceUpload || null,
    reference_id: referenceUpload ? null : referenceId || null,
  };
}
