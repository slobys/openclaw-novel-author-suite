#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


def load_rows(path):
    p=Path(path); rows=[]
    if not p.exists(): return rows
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            v=json.loads(line)
            if isinstance(v,dict): rows.append(v)
    return rows


def main():
    ap=argparse.ArgumentParser(description="Compare stable outline beat IDs with realized chapter signatures")
    ap.add_argument("--plan",required=True); ap.add_argument("--signature-ledger",required=True); ap.add_argument("--start",type=int,required=True); ap.add_argument("--end",type=int,required=True); ap.add_argument("--output")
    args=ap.parse_args(); plan=json.loads(Path(args.plan).read_text(encoding="utf-8")); rows=load_rows(args.signature_ledger)
    chapters=plan.get("chapters",[]) if isinstance(plan,dict) else []
    planned=set(); required=set()
    for ch in chapters:
        if not isinstance(ch,dict) or not isinstance(ch.get("chapterNo"),int) or not (args.start<=ch["chapterNo"]<=args.end): continue
        for beat in ch.get("plannedBeatIds",[]): planned.add(str(beat))
        for beat in ch.get("requiredBeatIds",ch.get("plannedBeatIds",[])): required.add(str(beat))
    actual=[r for r in rows if isinstance(r.get("chapterNo"),int) and args.start<=r["chapterNo"]<=args.end]
    fulfilled=set(); deferred=set(); dropped=set(); new=set()
    for r in actual:
        fulfilled.update(map(str,r.get("fulfilledBeatIds",[]))); deferred.update(map(str,r.get("deferredBeatIds",[]))); dropped.update(map(str,r.get("droppedBeatIds",[]))); new.update(map(str,r.get("newBeatIds",[])))
    unmet=sorted(required-fulfilled-deferred)
    unknown=sorted(fulfilled-planned)
    ratio=(len(fulfilled & required)/len(required)) if required else 1.0
    risk="high" if unmet and ratio<0.5 else "medium" if unmet or dropped or deferred else "low"
    result={"range":[args.start,args.end],"risk":risk,"plannedBeatCount":len(planned),"requiredBeatCount":len(required),"requiredFulfillmentRatio":round(ratio,3),"unmetRequiredBeatIds":unmet,"deferredBeatIds":sorted(deferred),"droppedBeatIds":sorted(dropped),"newBeatIds":sorted(new),"fulfilledUnknownBeatIds":unknown,"recommendation":"adjust future 3-8 chapters; do not silently rewrite committed history" if risk!="low" else "no structural correction required"}
    if args.output:
        out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False)); return 0

if __name__=="__main__": sys.exit(main())
