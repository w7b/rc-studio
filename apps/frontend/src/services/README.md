# Frontend services

Components call domain operations such as `campaignService.retry(id, token)` and
`accountService.updateDetails(details)`. Keep API endpoint strings, HTTP verbs,
download URLs, and response-to-file conversion in this directory.

- `http.js` owns JSON transport, same-origin credentials, cache behavior, CSRF,
  and session-expiry handling. Only services import it.
- Domain files group operations by responsibility: session, account, campaigns,
  consultations, references, media, administration, integrations, brand kit, and
  system diagnostics.
- `files.js` handles browser upload encoding and restored image files.
- Components retain presentation state, validation, navigation, and polling
  lifecycles. Read methods accept `{ signal }` for an `AbortController` where the
  caller needs request cancellation. Aborts propagate unchanged.

Use a named operation for a new request rather than passing endpoint strings
through component props. Administrative confirmation flows pass service functions
and payloads; they do not choose HTTP routes. Download and OAuth navigation use
the corresponding service URL builder.

Run `node --test tests/*.test.js` from `apps/frontend`. The service tests exercise
CSRF rotation, errors, cancellation, uploads, and draft restoration. The boundary
test rejects network calls and endpoint definitions outside this directory.
