#!/usr/bin/env python3
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from body_contract import canonical_body_sha256

SHA_RE=re.compile(r"[0-9a-fA-F]{64}")
BLOCKING={"error","block","blocking","fatal"}
ROLE_CHECKS={
    "continuity-auditor": {"facts","timeline","knowledgeBoundary","stateContinuity","causality","promiseContinuity","relationshipContinuity"},
    "reader-editor": {"readability","pacing","repetition","genreExperience","hookQuality","characterAgency"},
}
ROLE_PREFIX={"continuity-auditor":"CONTINUITY","reader-editor":"READER"}
PASS={"pass","passed","ok","clear","true","note","warning","warn","na","n/a","not_applicable"}
CANONICAL_STATUS={
    "pass":"pass", "passed":"pass", "ok":"pass", "clear":"pass", "true":"pass",
    "note":"note", "warning":"warning", "warn":"warning",
    "na":"not_applicable", "n/a":"not_applicable", "not_applicable":"not_applicable",
}


def status(v):
    if v is True: return "pass"
    if v is False: return "fail"
    if isinstance(v,str): return v.strip().lower()
    if isinstance(v,dict):
        if isinstance(v.get("pass"),bool): return "pass" if v["pass"] else "fail"
        for k in ("status","decision","result","conclusion"):
            if isinstance(v.get(k),str): return v[k].strip().lower()
    return None


def normalize_check(value):
    """Return the exact object shape accepted by novel_chapter_quality_record."""
    normalized=CANONICAL_STATUS.get(status(value))
    if not normalized:
        return None
    result={"status":normalized}
    if isinstance(value,dict):
        for key in ("evidence","description","summary","note"):
            if isinstance(value.get(key),str) and value[key].strip():
                result["evidence"]=value[key].strip()
                break
    return result


def engine_review(data, role):
    """Build one validated Engine review; never concatenate status and prose."""
    required=ROLE_CHECKS[role]
    checks=data.get("checks",{})
    review={
        "reviewerRole":role,
        "reviewerSessionId":str(data.get("reviewerSessionId","")).strip(),
        "bodySha256":str(data.get("bodySha256","")).lower(),
        "conclusion":"pass",
        "checks":{key:normalize_check(checks[key]) for key in sorted(required)},
        "issues":data.get("issues",[]),
    }
    if isinstance(data.get("summary"),str) and data["summary"].strip():
        review["summary"]=data["summary"].strip()
    return review


def load_review(path):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data,dict): raise SystemExit(f"review must be object: {path}")
    return data


def validate_review(data, role, writer_session, body_sha):
    reasons=[]
    prefix=ROLE_PREFIX[role]
    if str(data.get("reviewerRole","")).strip().lower()!=role: reasons.append(f"{prefix}_ROLE_MISMATCH")
    reviewer=str(data.get("reviewerSessionId","")).strip()
    if not reviewer: reasons.append(f"{prefix}_SESSION_MISSING")
    if reviewer and reviewer==writer_session: reasons.append(f"{prefix}_NOT_INDEPENDENT")
    sha=str(data.get("bodySha256","")).lower()
    if not SHA_RE.fullmatch(sha): reasons.append(f"{prefix}_BODY_HASH_MISSING")
    elif sha!=body_sha: reasons.append(f"{prefix}_BODY_HASH_MISMATCH")
    if status(data.get("conclusion"))!="pass": reasons.append(f"{prefix}_NOT_PASS")
    checks=data.get("checks")
    if not isinstance(checks,dict): reasons.append(f"{prefix}_CHECKS_MISSING")
    else:
        missing=sorted(ROLE_CHECKS[role]-set(checks))
        if missing: reasons.append(f"{prefix}_CHECKS_MISSING:"+",".join(missing))
        failed=sorted(k for k in ROLE_CHECKS[role] if k in checks and status(checks[k]) not in PASS)
        if failed: reasons.append(f"{prefix}_CHECKS_NOT_PASS:"+",".join(failed))
    issues=data.get("issues",[])
    if not isinstance(issues,list): reasons.append(f"{prefix}_ISSUES_INVALID")
    else:
        blocking=sum(1 for i in issues if isinstance(i,dict) and str(i.get("severity","")).lower() in BLOCKING)
        if blocking: reasons.append(f"{prefix}_BLOCKING_ISSUES:{blocking}")
    return reasons, reviewer


def main():
    ap=argparse.ArgumentParser(description="Bind independent continuity + reader reviews to final body")
    ap.add_argument("--body-file",required=True); ap.add_argument("--writer-session",required=True)
    ap.add_argument("--continuity-review",required=True); ap.add_argument("--reader-review",required=True); ap.add_argument("--receipt")
    args=ap.parse_args()
    body_sha=canonical_body_sha256(Path(args.body_file))
    c=load_review(args.continuity_review); r=load_review(args.reader_review)
    reasons=[]
    cr,cs=validate_review(c,"continuity-auditor",args.writer_session,body_sha); rr,rs=validate_review(r,"reader-editor",args.writer_session,body_sha)
    reasons+=cr+rr
    if cs and rs and cs==rs: reasons.append("REVIEWERS_NOT_INDEPENDENT_FROM_EACH_OTHER")
    receipt={"independentAuditVersion":"v1.1","createdAt":datetime.now(timezone.utc).isoformat(),"bodySha256":body_sha,"writerSessionId":args.writer_session,"continuityReviewerSessionId":cs,"readerReviewerSessionId":rs,"independentAuditPass":not reasons,"reasons":reasons}
    if not reasons:
        receipt["engineReviews"]={
            "continuityReview":engine_review(c,"continuity-auditor"),
            "readerReview":engine_review(r,"reader-editor"),
        }
    if args.receipt:
        out=Path(args.receipt); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(receipt,ensure_ascii=False)); return 0 if receipt["independentAuditPass"] else 2

if __name__=="__main__": sys.exit(main())
