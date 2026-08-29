#!/usr/bin/env python3
"""Dependency-free three-tier memory index with lightweight TF-IDF retrieval.

Records are derived retrieval aids, never authoritative story facts.
"""
import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

from runtime_io import atomic_write_text, file_lock

SHA_RE=re.compile(r"[0-9a-fA-F]{64}")
TIERS={"short","mid","long"}


def load_rows(path):
    path=Path(path)
    if not path.exists(): return []
    rows=[]
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value=json.loads(line)
            if isinstance(value,dict): rows.append(value)
    return rows


def tokens(text):
    text=str(text or "").lower()
    ascii_words=re.findall(r"[a-z0-9_]+", text)
    han="".join(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", text))
    grams=[]
    if han:
        grams.extend(han[i:i+2] for i in range(max(0,len(han)-1)))
        grams.extend(han[i:i+3] for i in range(max(0,len(han)-2)))
        if len(han)==1: grams.append(han)
    return ascii_words+grams


def validate(record):
    if not isinstance(record,dict): raise SystemExit("memory record must be an object")
    for key in ("memoryId","projectId","tier","text","sourceRef","sourceSha256"):
        if not isinstance(record.get(key),str) or not record[key].strip(): raise SystemExit(f"{key} is required")
    if record["tier"] not in TIERS: raise SystemExit("tier must be short, mid or long")
    if not SHA_RE.fullmatch(record["sourceSha256"]): raise SystemExit("sourceSha256 must be sha256")
    if record.get("chapterNo") is not None and (not isinstance(record["chapterNo"],int) or record["chapterNo"]<1):
        raise SystemExit("chapterNo must be null or positive integer")
    for key in ("entities","tags"):
        if key in record and not isinstance(record[key],list): raise SystemExit(f"{key} must be a list")
    return record


def cmd_upsert(args):
    ledger=Path(args.ledger); record=validate(json.loads(Path(args.record_json).read_text(encoding="utf-8")))
    with file_lock(ledger):
        rows=load_rows(ledger); prev=ledger.read_text(encoding="utf-8") if ledger.exists() else None
        by={str(r.get("memoryId")):r for r in rows if r.get("memoryId")}
        by[record["memoryId"]]=record
        out=sorted(by.values(), key=lambda r:(r.get("projectId",""), r.get("chapterNo") or 0, r.get("memoryId","")))
        if prev is not None: atomic_write_text(ledger.with_name(ledger.name+".bak"), prev, backup=False)
        atomic_write_text(ledger,"\n".join(json.dumps(x,ensure_ascii=False) for x in out)+"\n",backup=False)
    print(json.dumps({"ok":True,"memoryId":record["memoryId"],"count":len(out)},ensure_ascii=False))


def text_for(row):
    return " ".join([row.get("text",""), " ".join(map(str,row.get("entities",[]))), " ".join(map(str,row.get("tags",[])))])


def tfidf_scores(rows, query):
    qtokens=tokens(query)
    if not qtokens: return [0.0]*len(rows)
    docs=[tokens(text_for(r)) for r in rows]
    n=len(docs); df=Counter()
    for d in docs:
        for tok in set(d): df[tok]+=1
    def vec(ts):
        counts=Counter(ts); total=max(1,sum(counts.values())); out={}
        for tok,c in counts.items():
            out[tok]=(c/total)*(math.log((n+1)/(df.get(tok,0)+1))+1.0)
        return out
    qv=vec(qtokens); qn=math.sqrt(sum(v*v for v in qv.values())) or 1.0
    scores=[]
    for d in docs:
        dv=vec(d); dn=math.sqrt(sum(v*v for v in dv.values())) or 1.0
        dot=sum(qv.get(k,0.0)*v for k,v in dv.items())
        scores.append(dot/(qn*dn))
    return scores


def cmd_context(args):
    rows=[r for r in load_rows(args.ledger) if r.get("projectId")==args.project]
    if args.through is not None:
        rows=[r for r in rows if r.get("chapterNo") is None or r.get("chapterNo")<=args.through]
    short=sorted([r for r in rows if r.get("tier")=="short"], key=lambda r:r.get("chapterNo") or 0, reverse=True)[:args.short]
    mid=sorted([r for r in rows if r.get("tier")=="mid"], key=lambda r:r.get("chapterNo") or 0, reverse=True)[:args.mid]
    long_rows=[r for r in rows if r.get("tier")=="long"]
    scores=tfidf_scores(long_rows,args.query)
    ranked=sorted(zip(scores,long_rows), key=lambda x:(x[0], x[1].get("chapterNo") or 0), reverse=True)[:args.long]
    long=[dict(r, retrievalScore=round(score,4)) for score,r in ranked if score>0]
    result={"projectId":args.project,"query":args.query,"throughChapter":args.through,"short":short,"mid":mid,"long":long}
    if args.output:
        out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))


def cmd_verify(args):
    errors=[]; seen=set(); rows=load_rows(args.ledger)
    for r in rows:
        try: validate(r)
        except SystemExit as exc: errors.append(str(exc)); continue
        if r["memoryId"] in seen: errors.append(f"duplicate memoryId:{r['memoryId']}")
        seen.add(r["memoryId"])
    result={"ok":not errors,"rows":len(rows),"errors":errors}; print(json.dumps(result,ensure_ascii=False)); return 0 if result["ok"] else 2


def main():
    ap=argparse.ArgumentParser(description="Three-tier novel memory index")
    sub=ap.add_subparsers(dest="cmd",required=True)
    p=sub.add_parser("upsert"); p.add_argument("ledger"); p.add_argument("record_json"); p.set_defaults(func=cmd_upsert)
    p=sub.add_parser("context"); p.add_argument("ledger"); p.add_argument("--project",required=True); p.add_argument("--query",required=True); p.add_argument("--through",type=int); p.add_argument("--short",type=int,default=5); p.add_argument("--mid",type=int,default=12); p.add_argument("--long",type=int,default=8); p.add_argument("--output"); p.set_defaults(func=cmd_context)
    p=sub.add_parser("verify"); p.add_argument("ledger"); p.set_defaults(func=cmd_verify)
    args=ap.parse_args(); result=args.func(args); return result if isinstance(result,int) else 0

if __name__=="__main__": sys.exit(main())
