#!/usr/bin/env python3
import argparse, json, sys
from pathlib import Path

from runtime_io import atomic_write_text, file_lock


def load(path):
    if not path.exists():
        return []
    text = path.read_text(encoding='utf-8').strip()
    if not text:
        return []
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
    except json.JSONDecodeError:
        pass
    out = []
    for line in text.splitlines():
        if line.strip():
            obj = json.loads(line)
            if isinstance(obj, dict):
                out.append(obj)
    return out


def main():
    ap = argparse.ArgumentParser(description='Upsert chapter signature telemetry')
    ap.add_argument('ledger_file')
    ap.add_argument('signature_json')
    args = ap.parse_args()
    ledger = Path(args.ledger_file)
    sig_path = Path(args.signature_json)
    sig = json.loads(sig_path.read_text(encoding='utf-8'))
    if not isinstance(sig, dict) or not isinstance(sig.get('chapterNo'), int):
        raise SystemExit('signature json must be an object with integer chapterNo')
    with file_lock(ledger):
        rows = load(ledger)
        previous = ledger.read_text(encoding='utf-8') if ledger.exists() else None
        by = {int(r['chapterNo']): r for r in rows if isinstance(r.get('chapterNo'), int)}
        by[sig['chapterNo']] = sig
        out = [by[k] for k in sorted(by)]
        if previous is not None:
            atomic_write_text(
                ledger.with_name(ledger.name + '.bak'),
                previous,
                backup=False,
            )
        atomic_write_text(
            ledger,
            '\n'.join(json.dumps(x, ensure_ascii=False) for x in out) + '\n',
            backup=False,
        )
    print(json.dumps({'ok': True, 'ledger': str(ledger), 'count': len(out), 'chapterNo': sig['chapterNo']}, ensure_ascii=False))

if __name__ == '__main__':
    sys.exit(main())
