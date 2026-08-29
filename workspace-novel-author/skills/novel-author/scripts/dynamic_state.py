#!/usr/bin/env python3
"""Derived dynamic-story-state ledger.

This ledger is a retrieval cache only. novel-engine remains authoritative.
Each chapter update is bound to a committed body SHA-256 and can be rebuilt.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from runtime_io import atomic_write_text, file_lock

SHA_RE = re.compile(r"[0-9a-fA-F]{64}")
DOMAINS = {
    "characters": "characterId",
    "knowledge": "knowledgeKey",
    "inventory": "itemId",
    "locations": "locationId",
}


def load_rows(path: Path):
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    rows=[]
    for line in text.splitlines():
        value=json.loads(line)
        if isinstance(value, dict):
            rows.append(value)
    return rows


def validate_update(data):
    if not isinstance(data, dict):
        raise SystemExit("state update must be an object")
    if not isinstance(data.get("projectId"), str) or not data["projectId"].strip():
        raise SystemExit("projectId is required")
    if not isinstance(data.get("chapterNo"), int) or data["chapterNo"] < 1:
        raise SystemExit("chapterNo must be a positive integer")
    sha=str(data.get("bodySha256", ""))
    if not SHA_RE.fullmatch(sha):
        raise SystemExit("bodySha256 must be a 64-character sha256")
    found=False
    for domain, key_field in DOMAINS.items():
        items=data.get(domain, [])
        if not isinstance(items, list):
            raise SystemExit(f"{domain} must be a list")
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get(key_field), str) or not item[key_field].strip():
                raise SystemExit(f"{domain} entries require non-empty {key_field}")
            found=True
    if not found:
        data.setdefault("noStateChange", True)
        if not data.get("reason"):
            raise SystemExit("empty state update requires reason")
    return data


def cmd_upsert(args):
    ledger=Path(args.ledger)
    update=validate_update(json.loads(Path(args.update_json).read_text(encoding="utf-8")))
    with file_lock(ledger):
        rows=load_rows(ledger)
        previous=ledger.read_text(encoding="utf-8") if ledger.exists() else None
        key=(update["projectId"], update["chapterNo"])
        by={(r.get("projectId"), r.get("chapterNo")): r for r in rows}
        by[key]=update
        out=sorted(by.values(), key=lambda r:(str(r.get("projectId","")), int(r.get("chapterNo",0))))
        if previous is not None:
            atomic_write_text(ledger.with_name(ledger.name+".bak"), previous, backup=False)
        atomic_write_text(ledger, "\n".join(json.dumps(x, ensure_ascii=False) for x in out)+"\n", backup=False)
    print(json.dumps({"ok": True, "ledger": str(ledger), "projectId": update["projectId"], "chapterNo": update["chapterNo"]}, ensure_ascii=False))


def merge_context(rows, project, through=None):
    selected=[r for r in rows if r.get("projectId")==project and (through is None or int(r.get("chapterNo",0))<=through)]
    selected.sort(key=lambda r:int(r.get("chapterNo",0)))
    output={"projectId": project, "throughChapter": through, "characters":{}, "knowledge":{}, "inventory":{}, "locations":{}, "sourceChapters":[]}
    for row in selected:
        output["sourceChapters"].append(row.get("chapterNo"))
        for domain, key_field in DOMAINS.items():
            for item in row.get(domain, []):
                record=dict(item)
                record["lastChangedChapter"]=row.get("chapterNo")
                record["sourceBodySha256"]=row.get("bodySha256")
                output[domain][item[key_field]]=record
    return output


def cmd_context(args):
    rows=load_rows(Path(args.ledger))
    ctx=merge_context(rows, args.project, args.through)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(ctx, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(ctx, ensure_ascii=False))


def cmd_verify(args):
    rows=load_rows(Path(args.ledger))
    errors=[]; seen=set()
    for row in rows:
        try:
            validate_update(row)
        except SystemExit as exc:
            errors.append(str(exc))
            continue
        key=(row["projectId"], row["chapterNo"])
        if key in seen:
            errors.append(f"duplicate project/chapter: {key}")
        seen.add(key)
    result={"ok": not errors, "rows": len(rows), "errors": errors}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 2


def main():
    ap=argparse.ArgumentParser(description="Derived dynamic story state ledger")
    sub=ap.add_subparsers(dest="cmd", required=True)
    p=sub.add_parser("upsert"); p.add_argument("ledger"); p.add_argument("update_json"); p.set_defaults(func=cmd_upsert)
    p=sub.add_parser("context"); p.add_argument("ledger"); p.add_argument("--project", required=True); p.add_argument("--through", type=int); p.add_argument("--output"); p.set_defaults(func=cmd_context)
    p=sub.add_parser("verify"); p.add_argument("ledger"); p.set_defaults(func=cmd_verify)
    args=ap.parse_args(); result=args.func(args); return result if isinstance(result,int) else 0

if __name__=="__main__":
    sys.exit(main())
