#!/usr/bin/env python3
import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path


def load_rows(path: Path):
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
        if isinstance(obj, dict):
            for key in ("chapters", "signatures", "items"):
                if isinstance(obj.get(key), list):
                    return [x for x in obj[key] if isinstance(x, dict)]
            return [obj]
    except json.JSONDecodeError:
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
        return rows


def longest_run(values):
    best = cur = 0
    prev = object()
    for v in values:
        if v == prev and v not in (None, ""):
            cur += 1
        else:
            cur = 1 if v not in (None, "") else 0
            prev = v
        best = max(best, cur)
    return best


def longest_truthy_run(values):
    """Return the longest consecutive run of truthy values only."""
    best = cur = 0
    for value in values:
        if value:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def dominant_share(values):
    vals = [v for v in values if v not in (None, "")]
    if not vals:
        return None, 0.0
    c = Counter(vals)
    item, count = c.most_common(1)[0]
    return item, count / len(vals)


def emotion(row, which="closingEmotion"):
    val = row.get(which)
    if isinstance(val, dict):
        name = val.get("name")
        intensity = val.get("intensity")
        return name, intensity if isinstance(intensity, (int, float)) else None
    if isinstance(val, str):
        return val, None
    return None, None


def main():
    ap = argparse.ArgumentParser(description="Detect structural narrative fatigue from chapter signatures")
    ap.add_argument("signature_file")
    ap.add_argument("--last", type=int, default=10)
    args = ap.parse_args()

    rows = load_rows(Path(args.signature_file))[-max(1, args.last):]
    warnings = []

    funcs = [r.get("function") for r in rows]
    hooks = [r.get("hookType") for r in rows]
    conflicts = [r.get("conflictMode") for r in rows]
    close_names, close_intensities = [], []
    for r in rows:
        n, i = emotion(r)
        close_names.append(n)
        if i is not None:
            close_intensities.append(float(i))

    metrics = {"chaptersAnalyzed": len(rows)}
    for label, values in (("function", funcs), ("hookType", hooks), ("conflictMode", conflicts), ("closingEmotion", close_names)):
        dom, share = dominant_share(values)
        run = longest_run(values)
        metrics[label] = {"dominant": dom, "share": round(share, 3), "longestRun": run}
        if len(rows) >= 5 and share >= 0.6:
            warnings.append(f"{label.upper()}_LOW_DIVERSITY:{dom}:{share:.2f}")
        if run >= 3:
            warnings.append(f"{label.upper()}_REPEATED_RUN:{dom}:{run}")

    scene_types = []
    for r in rows:
        st = r.get("sceneTypes", [])
        if isinstance(st, list):
            scene_types.extend(str(x) for x in st if x)
    if scene_types:
        dom, share = dominant_share(scene_types)
        metrics["sceneTypes"] = {"dominant": dom, "share": round(share, 3), "unique": len(set(scene_types))}
        if len(scene_types) >= 8 and share >= 0.5:
            warnings.append(f"SCENE_TYPE_DOMINANCE:{dom}:{share:.2f}")

    if close_intensities:
        avg = statistics.mean(close_intensities)
        std = statistics.pstdev(close_intensities) if len(close_intensities) > 1 else 0.0
        metrics["closingIntensity"] = {"mean": round(avg, 2), "stddev": round(std, 2)}
        high_run = longest_truthy_run([i >= 8 for i in close_intensities])
        if high_run >= 3:
            warnings.append(f"SUSTAINED_HIGH_INTENSITY:{high_run}")
        if len(close_intensities) >= 5 and std < 1.0:
            warnings.append(f"EMOTIONAL_INTENSITY_TOO_FLAT:{std:.2f}")

    rel_empty = sum(1 for r in rows if not r.get("relationshipActions"))
    irrev_empty = sum(1 for r in rows if not r.get("irreversibleChange"))
    metrics["relationshipActionEmptyShare"] = round(rel_empty / len(rows), 3) if rows else 0
    metrics["irreversibleChangeEmptyShare"] = round(irrev_empty / len(rows), 3) if rows else 0
    if len(rows) >= 5 and rel_empty / len(rows) >= 0.8:
        warnings.append("RELATIONSHIP_STAGNATION_RISK")
    if len(rows) >= 5 and irrev_empty / len(rows) >= 0.8:
        warnings.append("LOW_IRREVERSIBLE_CHANGE_RISK")

    promise_actions = []
    for r in rows:
        pa = r.get("promiseActions", [])
        if isinstance(pa, list):
            promise_actions.extend(str(x).lower() for x in pa)
    opens = sum(1 for x in promise_actions if ":open" in x or x.endswith("open"))
    payoffs = sum(1 for x in promise_actions if "payoff" in x and "partial" not in x)
    partials = sum(1 for x in promise_actions if "partial" in x)
    metrics["promiseActions"] = {"open": opens, "partialPayoff": partials, "payoff": payoffs, "total": len(promise_actions)}
    if opens >= 3 and (payoffs + partials) == 0:
        warnings.append("PROMISE_DEBT_RISING")

    result = {
        "risk": "high" if len(warnings) >= 5 else "medium" if len(warnings) >= 2 else "low",
        "metrics": metrics,
        "warnings": warnings,
        "note": "Structural telemetry only; semantic Arc Audit remains authoritative for quality decisions."
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
