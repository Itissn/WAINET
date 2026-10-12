# Run and demonstrate WAINET

WAINET has two modes: a working local application with persistent data and an
explicitly synthetic, read-only public presentation. The AI integration is
implemented; a real-model check needs a privately configured API key. Automated
acceptance checks substitute a model fixture and do not establish model accuracy.

## Local application

From the repository folder, using Python 3.11 or 3.12:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe server.py
```

On macOS/Linux use `.venv/bin/python`. Open http://localhost:8000. Without an API
key, uploads are saved and explicitly await AI setup. Do not expose this development
server directly to the public internet.

Create a member account through the page. Choose a community, upload a photo and
optionally enter its date and your observations. Without a trustworthy date or
other required review evidence, an observation may be saved but ineligible for
curated export. Guest uploads do not earn rewards.

## Administrator

Use `python admin_manage.py --help` for a private administrator invitation. Do
not add a role field to ordinary registration. The administration page is
http://localhost:8000/admin. Temporary administrator passwords must be changed
before access. Review source evidence before approving. Rewards and brand names
are demonstrative until an operator supplies legitimate voucher stock.

## Verification

```powershell
python -m unittest discover -v
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python browser_smoke.py
```

`browser_smoke.py --channel chrome` can instead use an already installed Chrome.
It launches a separate headless profile, creates disposable data and checks:
registration, upload, persistence, mocked model processing, sign-out,
administrator password setup, human review, JSON export and mobile layout.
External browser resources and official-data requests are isolated in this check.
It asserts no uncaught browser/server errors or missing application assets.

## Private backup and recovery

```powershell
python storage_ops.py backup data/wainet.sqlite3 data/backups/wainet-2026-10-12.sqlite3
python storage_ops.py verify data/backups/wainet-2026-10-12.sqlite3
python storage_ops.py restore data/backups/wainet-2026-10-12.sqlite3 data/restored.sqlite3
```

Choose a new backup filename each time; existing files are never overwritten.
Keep an additional private copy outside the service disk. To use the restored
database, stop the server, then run `python server.py --db data/restored.sqlite3`.
Backups contain private images, account hashes and records. Never publish them.

## Opt-in real AI check

Copy `.env.example` to `.env` and configure your own `OPENAI_API_KEY` privately.
Do not place the key in browser JavaScript, GitHub files, logs or chat. Then use an
image you are permitted to send to the provider:

```powershell
python live_check.py --image path/to/test-photo.jpg --confirm-live
```

This sends one image and description to the configured model and may incur API
charges. It does not retry automatically. Its report stays in ignored
`data/live-checks/`; review it using [EVALUATION.md](EVALUATION.md). A successful
connection alone is not evidence of classification quality or safe water.

## Public demonstration and deployment

[Open the public presentation](https://itissn.github.io/WAINET/).
The public page never receives private uploads or API keys. To rebuild a package:

```powershell
python seed_demo.py
python build_presentation.py --out presentation
```

The builder verifies synthetic-only data and includes only listed presentation
assets. Keep dated official source snapshots labelled separately. Deploying a
shared backend is a different step described in [DEPLOYMENT.md](DEPLOYMENT.md);
it needs hosting, persistent storage and approved expenditure.
