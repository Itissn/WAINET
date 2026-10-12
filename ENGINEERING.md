# Engineering review and reproducible checks

This is a community-evidence prototype, built with AI assistance. The public
GitHub Pages site contains synthetic, precomputed demonstration data. It does not
run the Python backend or a live model. The application must not infer safe water
conditions from photographs. No user adoption, model accuracy, cost saving or
production availability has been measured.

## System boundaries

```text
Browser photo + optional text
    -> same-origin Python HTTP API -> image/input validation -> SQLite evidence
    -> pending queue -> single AI worker -> Responses API
    -> envelope + application-schema validation -> pending HUMAN review
    -> eligible approved observations -> community summaries / consented exports

API -> generated request ID + allowlisted structured event
Worker -> generated operation ID + outcome + safe failure category
```

Sessions, role checks, CSRF controls, human review, audit records and transactional
reward allocation predate the reliability changes. Their existing tests remain
part of the regression suite. Separate official monitoring data is not generated
by the model. See [README](README.md), [DATABASE](DATABASE.md) and [SOURCES](SOURCES.md).

## Reliability changes

| Concern | Implementation | Evidence |
| --- | --- | --- |
| Oversized or malformed provider response | `ai_transport.py`: 256 KiB response cap, envelope/type checks, JSON parsing; `server.analyze`: domain validation | `TransportTests` |
| Timeouts, refusal, rate limits and other failures | Fixed safe categories; one provider attempt; preserve evidence and withhold analysis | `TransportTests`, `WorkerFailureTests` |
| Request troubleshooting without logging personal data | Server-generated `X-Request-ID`, allowlisted route labels, method/status/duration | `RequestTraceTests` |
| Storage unavailable during health check | Safe HTTP 503 JSON response rather than an aborted request | `RequestTraceTests` |
| Repeatable regression checks | GitHub Actions on push/PR/manual run, Python 3.11 and 3.12, no API secret | `.github/workflows/tests.yml` |

The 60-second urllib timeout is a socket-operation timeout, **not an end-to-end
deadline**. Slow progress may still hold the sole worker longer. A production
implementation needs a cancellable client/job deadline and queue supervision.

No automatic retry is made inside one model attempt. A timed-out call might
already have been billed. Existing startup recovery requeues `processing` rows,
and `--retry-failed` requeues failed rows; either can incur another request. This
is at-least-once processing, not provider-level exactly-once execution. Review
the failure category and billing implications before retrying.

## Run the checks (no model API calls)

Use a virtual environment and install `requirements.txt`, then:

```powershell
python -m unittest test_reliability -v
python -m unittest discover -v
```

The first command injects provider failures, malformed responses and a database
outage. The second runs the full existing suite plus those new checks. All model
responses in these tests are mocked. Passing these tests proves the tested
software behaviours, **not model accuracy or prompt-injection resistance**.
The reliability baseline passed GitHub CI on Python 3.11 and 3.12. Subsequent
changes must pass their own checks; consult the repository's latest Actions run.
`browser_smoke.py` also verifies the complete account/upload/admin-review/export
journey against a temporary server. `presentation_smoke.py` checks the actual
packaged read-only website. Both use headless Chromium; see START_HERE.md.

## Trace a local HTTP request

Start with a disposable database and no real API key. In PowerShell:

```powershell
$env:OPENAI_API_KEY = ''
python server.py --db "$env:TEMP\wainet-local-demo.sqlite3"
```

In another terminal:

```powershell
curl.exe -i http://localhost:8000/api/health
```

Expected: HTTP 200, an `X-Request-ID` header and JSON fields `storage`,
`aiConfigured`, `adminConfigured`. The corresponding `http_request` JSON log on
stderr uses the same ID. It means the HTTP process and a database read worked;
it does not test database writes, model availability or worker progress.
Storage errors produce 503 with `{"error":"Storage is temporarily unavailable."}`.

The log's `duration_ms` is local elapsed time. Its HTTP `status` is the selected
response status, not proof the client received every byte. AI events have a
separate operation ID, not distributed tracing across a queue.

Do not add request bodies, image data, GPS, email addresses, cookies, authorization
headers, raw query strings, raw provider errors or prompt text to logs. Unknown
routes become `other`; unknown methods become `OTHER`. Telemetry is opt-in when
the module is embedded and configured automatically by `python server.py`.

## Why keep this architecture for this change?

The project already had an API, durable evidence and access controls. Replacing
the framework would increase scope without demonstrating better failure
behaviour. The provider adapter is separately testable and reusable; the domain
schema and human-review rules remain in the application.

There is no retrieval requirement in the current photo-classification flow, so
adding RAG or an agent framework merely for keywords would not solve a user
problem. If source-grounded coastal guidance is later added, treat it as a
separate feature with dated trusted sources, citations, abstention and evaluation.

## Next production work, in order

1. Collect a consented or synthetic labelled evaluation set. Measure relevance,
   text/image conflict detection, unsupported safety claims and adversarial cases;
   retain failures as regression cases. Do not equate schema validity with truth.
2. Evaluate an actual model in a separately approved, budget-limited run. Record
   model/prompt versions, latency and cost. No live verification is claimed here.
3. Replace `http.server` with a supported production application server; introduce
   deadlines, upload/concurrency limits and a durable supervised job queue.
4. Add operational alerts, scheduled private backups, retention/deletion controls,
   secrets management and account recovery before real public usage.
   A local backup/restore command and recovery regression test now exist in
   `storage_ops.py` and `test_storage_ops.py`; off-site operation still needs setup.
5. For a regulated enterprise, assess SSO, fine-grained authorization, data
   residency, security review and audit requirements with that organisation.

## References

- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs): incomplete outputs and refusals need explicit handling.
- [GitHub Python CI](https://docs.github.com/en/actions/tutorials/build-and-test-code/python): setup and test matrix.
- [Python HTTP server](https://docs.python.org/3/library/http.server.html): prototype server limitations.
