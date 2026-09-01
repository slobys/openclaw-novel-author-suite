#!/usr/bin/env python3
"""Validate observed Novel Engine server-side capabilities.

Accepts both the flat capability receipt and the Novel Engine 0.4.10
`novel_project_status` result.
"""

import argparse
import json
import sys
from pathlib import Path


def first(*values):
    for value in values:
        if value is not None:
            return value
    return None


def as_bool(value):
    return value is True


def version_tuple(value):
    try:
        return tuple(int(part) for part in str(value).split("-")[0].split("."))
    except (TypeError, ValueError):
        return ()


def main():
    parser = argparse.ArgumentParser(description="Validate observed novel-engine server-side gate capabilities")
    parser.add_argument("capability_json")
    parser.add_argument("--hard-min", type=int, default=2000)
    parser.add_argument("--min-engine-version", default="0.4.10")
    parser.add_argument("--receipt")
    args = parser.parse_args()

    data = json.loads(Path(args.capability_json).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("capability json must be object")

    caps = data.get("serverCapabilities") if isinstance(data.get("serverCapabilities"), dict) else data
    ledgers = data.get("storyLedgers") if isinstance(data.get("storyLedgers"), dict) else {}
    length_gate = ledgers.get("chapterLengthGate") if isinstance(ledgers.get("chapterLengthGate"), dict) else {}

    observed_min = first(
        caps.get("resolvedHardMinHanChars"),
        length_gate.get("minHanChars"),
        data.get("minChapterHanChars"),
        data.get("hardMinimumHanChars"),
    )
    try:
        observed_min_int = int(observed_min)
    except (TypeError, ValueError):
        observed_min_int = -1

    normalized = {
        "enforcedServerSide": as_bool(first(
            caps.get("serverGateVerified"),
            length_gate.get("enforcedServerSide"),
            data.get("enforcedServerSide"),
        )),
        "minChapterHanChars": observed_min_int,
        "commitRehash": as_bool(first(caps.get("hanLengthRecount"), data.get("commitRehash"))),
        "auditHashBinding": as_bool(first(caps.get("auditBodyHashBinding"), data.get("auditHashBinding"))),
        "completeAuditCoverage": as_bool(first(caps.get("completeAuditCoverage"), data.get("completeAuditCoverage"))),
        "independentQualityReceipt": as_bool(first(caps.get("independentQualityReceipt"), data.get("independentQualityReceipt"))),
        "closureReceiptRequired": as_bool(first(caps.get("closureReceiptRequired"), ledgers.get("closureReceiptRequired"), data.get("closureReceiptRequired"))),
        "requestIdRequired": as_bool(first(caps.get("requestIdRequired"), data.get("requestIdRequired"))),
        "derivedBodyHashBinding": as_bool(first(caps.get("derivedBodyHashBinding"), data.get("derivedBodyHashBinding"))),
        "requiredAuditCategoryCount": int(first(caps.get("requiredAuditCategoryCount"), len(ledgers.get("requiredAuditCategories", [])), 0)),
        "requestIdIdempotency": as_bool(first(caps.get("requestIdIdempotency"), data.get("requestIdIdempotency"))),
        "requestIdPayloadBinding": as_bool(first(caps.get("requestIdPayloadBinding"), data.get("requestIdPayloadBinding"))),
        "crashRecoverableTransactions": as_bool(first(caps.get("crashRecoverableTransactions"), data.get("crashRecoverableTransactions"))),
        "commitStatusReconciliation": as_bool(first(caps.get("commitStatusReconciliation"), data.get("commitStatusReconciliation"))),
        "revisionCas": as_bool(first(caps.get("revisionCas"), data.get("revisionCas"))),
        "projectIntegrityCheck": as_bool(first(caps.get("projectIntegrityCheck"), data.get("projectIntegrityCheck"))),
    }

    reasons = []
    engine_version = caps.get("engineVersion") or data.get("engineVersion")
    if version_tuple(engine_version) < version_tuple(args.min_engine_version):
        reasons.append("SERVER_ENGINE_VERSION_TOO_OLD")
    if not normalized["enforcedServerSide"]:
        reasons.append("SERVER_GATE_NOT_ENFORCED")
    if normalized["minChapterHanChars"] < args.hard_min:
        reasons.append("SERVER_MIN_HAN_CHARS_TOO_LOW")
    required = [
        "commitRehash",
        "auditHashBinding",
        "completeAuditCoverage",
        "independentQualityReceipt",
        "closureReceiptRequired",
        "requestIdRequired",
        "derivedBodyHashBinding",
        "requestIdIdempotency",
        "requestIdPayloadBinding",
        "crashRecoverableTransactions",
        "commitStatusReconciliation",
        "revisionCas",
        "projectIntegrityCheck",
    ]
    for key in required:
        if normalized[key] is not True:
            reasons.append(f"SERVER_CAPABILITY_MISSING:{key}")
    if normalized["requiredAuditCategoryCount"] != 17:
        reasons.append("SERVER_AUDIT_CATEGORY_COUNT_NOT_17")

    receipt = {
        "serverGateVerified": not reasons,
        "hardMinimumHanChars": args.hard_min,
        "observed": normalized,
        "engineVersion": engine_version,
        "minimumEngineVersion": args.min_engine_version,
        "reasons": reasons,
    }
    if args.receipt:
        Path(args.receipt).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt["serverGateVerified"] else 2


if __name__ == "__main__":
    sys.exit(main())
