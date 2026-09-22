import { buildRunRequest } from '../src/features/campaigns/run-request.js';

// Values vary independently, including upload precedence and the demo spending gate.
const payloads = [];
for (const selection of ['demo', 'opaque:model']) {
  for (const product of ['', 'product-id']) {
    for (const referenceId of ['', 'reference-id']) {
      for (const uploaded of [false, true]) {
        payloads.push(
          buildRunRequest({
            request: 'Campanha de teste',
            facts: ' Confirmado \n\n Outro fato ',
            selection,
            imageModel: 'opaque:image',
            publication: { kind: 'feed', preset: 'feed_portrait', slides: 1 },
            image: true,
            product,
            referenceId,
            upload: uploaded ? 'aW1hZ2U=' : null,
            referenceUpload: uploaded ? 'cmVmZXJlbmNl' : null,
          })
        );
      }
    }
  }
}
process.stdout.write(JSON.stringify(payloads));
