"""One opt-in real-model integration check; results stay in ignored local data/."""
import argparse
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from server import ROOT, MAX_IMAGE, COMMUNITIES, PROMPT_VERSION, SCHEMA_VERSION, analyze, load_config, validate_observation
from ai_transport import AnalysisFailure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--community", choices=sorted(COMMUNITIES), default="Lyall Bay")
    parser.add_argument("--description", default="A test observation; do not infer water safety.")
    parser.add_argument("--confirm-live", action="store_true", help="Send this image and description to OpenAI; may incur API charges.")
    args = parser.parse_args()
    if not args.confirm_live:
        parser.error("No request sent. Review image privacy and API cost, then explicitly pass --confirm-live.")
    load_config()
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        parser.error("No request sent. Configure OPENAI_API_KEY privately in .env or the environment.")
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(args.image.suffix.lower())
    if not mime or args.image.stat().st_size > MAX_IMAGE:
        parser.error("Use a supported image no larger than 5 MB.")
    record = validate_observation({"id": str(uuid4()), "community": args.community,
                                   "feelings": args.description,
                                   "photo": f"data:{mime};base64," + base64.b64encode(args.image.read_bytes()).decode()})
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    started = time.monotonic()
    try:
        result, response_id = analyze(record, key, model)
    except AnalysisFailure as error:
        parser.exit(1, f"Live check failed: {error.category}. No automatic retry was made.\n")
    output = ROOT / "data" / "live-checks" / (str(uuid4()) + ".json")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "model": model,
              "prompt_version": PROMPT_VERSION, "schema_version": SCHEMA_VERSION,
              "elapsed_seconds": round(time.monotonic() - started, 2), "response_id": response_id,
              "analysis": result, "integration_only": True,
              "notice": "Human assessment is required; this is not an accuracy score or a water-safety determination."}
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"One live response validated. Review the private report: {output}")


if __name__ == "__main__":
    main()
