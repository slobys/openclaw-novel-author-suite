#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from body_contract import canonical_body_sha256


def load(path):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data,dict): raise SystemExit(f"receipt must be object: {path}")
    return data


def main():
    ap=argparse.ArgumentParser(description="Combine independent-review and genre-experience receipts")
    ap.add_argument("--body-file",required=True); ap.add_argument("--independent-receipt",required=True); ap.add_argument("--genre-receipt",required=True); ap.add_argument("--receipt")
    args=ap.parse_args(); sha=canonical_body_sha256(Path(args.body_file)); independent=load(args.independent_receipt); genre=load(args.genre_receipt); reasons=[]
    if independent.get("independentAuditPass") is not True: reasons.append("INDEPENDENT_AUDIT_NOT_PASS")
    if independent.get("bodySha256")!=sha: reasons.append("INDEPENDENT_AUDIT_BODY_HASH_MISMATCH")
    if genre.get("genreGatePass") is not True: reasons.append("GENRE_PROMISE_GATE_NOT_PASS")
    if genre.get("bodySha256")!=sha: reasons.append("GENRE_PROMISE_BODY_HASH_MISMATCH")
    receipt={"qualityGateVersion":"v1.0","createdAt":datetime.now(timezone.utc).isoformat(),"chapterNo":genre.get("chapterNo"),"bodySha256":sha,"qualityPass":not reasons,"reasons":reasons,"genreWarnings":genre.get("warnings",[])}
    if args.receipt:
        out=Path(args.receipt); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(receipt,ensure_ascii=False)); return 0 if receipt["qualityPass"] else 2

if __name__=="__main__": sys.exit(main())
