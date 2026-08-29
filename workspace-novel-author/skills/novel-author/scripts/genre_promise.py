#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


def load_rows(path):
    p=Path(path)
    if not p.exists(): return []
    rows=[]
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            v=json.loads(line)
            if isinstance(v,dict): rows.append(v)
    return rows


def main():
    ap=argparse.ArgumentParser(description="Rolling genre/reader-experience promise gate")
    ap.add_argument("--profile",required=True); ap.add_argument("--signature-ledger",required=True); ap.add_argument("--current-signature",required=True); ap.add_argument("--receipt"); ap.add_argument("--window",type=int,default=5)
    args=ap.parse_args()
    profile=json.loads(Path(args.profile).read_text(encoding="utf-8")); current=json.loads(Path(args.current_signature).read_text(encoding="utf-8"))
    if not isinstance(profile,dict) or not isinstance(current,dict): raise SystemExit("profile/current signature must be objects")
    body_sha=str(current.get("bodySha256","")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", body_sha): raise SystemExit("current signature requires hexadecimal bodySha256")
    primary=profile.get("primaryExperiences")
    if not isinstance(primary,dict) or not primary: raise SystemExit("profile.primaryExperiences must be a non-empty object")
    rows=load_rows(args.signature_ledger)
    chapter=current.get("chapterNo")
    rows=[r for r in rows if isinstance(r.get("chapterNo"),int) and (not isinstance(chapter,int) or r["chapterNo"]<chapter)]
    rows=(rows[-max(0,args.window-1):] if args.window>1 else [])+[current]
    warnings=[]; hard=[]; metrics={}
    current_scores=current.get("experienceScores", {})
    if not isinstance(current_scores, dict):
        current_scores={}
    for name in primary:
        if not isinstance(current_scores.get(name), (int, float)):
            hard.append(f"CURRENT_EXPERIENCE_SCORE_MISSING:{name}")
    for name,spec in primary.items():
        if not isinstance(spec,dict): spec={"target":float(spec),"floor":float(spec)-2}
        target=float(spec.get("target",7)); floor=float(spec.get("floor",max(0,target-2)))
        vals=[]
        for row in rows:
            scores=row.get("experienceScores",{})
            val=scores.get(name) if isinstance(scores,dict) else None
            if isinstance(val,(int,float)): vals.append(float(val))
        if not vals:
            warnings.append(f"EXPERIENCE_SCORE_MISSING:{name}"); metrics[name]={"samples":0}; continue
        avg=sum(vals)/len(vals); tail=vals[-3:]
        metrics[name]={"samples":len(vals),"average":round(avg,2),"target":target,"floor":floor,"last":vals[-1]}
        if avg<floor: warnings.append(f"PRIMARY_EXPERIENCE_BELOW_FLOOR:{name}:{avg:.2f}<{floor:.2f}")
        severe_floor=max(0,floor-2)
        if len(tail)>=3 and all(v<severe_floor for v in tail): hard.append(f"PRIMARY_EXPERIENCE_SEVERE_DRIFT:{name}")
        elif len(vals)>=args.window and avg<severe_floor: hard.append(f"PRIMARY_EXPERIENCE_WINDOW_COLLAPSE:{name}")
    gate_pass=not hard
    receipt={"genreGateVersion":"v1.1","chapterNo":chapter,"bodySha256":body_sha,"window":args.window,"metrics":metrics,"warnings":warnings,"hardBlocks":hard,"genreGatePass":gate_pass,"pass":gate_pass,"genrePass":gate_pass,"hardBlock":not gate_pass,"severeDrift":not gate_pass}
    if args.receipt:
        out=Path(args.receipt); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(receipt,ensure_ascii=False)); return 0 if receipt["genreGatePass"] else 2

if __name__=="__main__": sys.exit(main())
