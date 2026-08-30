#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate Scene Asset Handoff -> shot bindings -> video prompt manifest.

Usage:
  python validate_shot_scene_bindings.py \
    --handoff handoffs/scene_asset_handoff.json \
    --assets assets/actual_asset_manifest.json \
    --shots shots/shot_scene_bindings.json \
    --prompts video_prompts/video_prompt_manifest.json \
    --out gates/shot_scene_binding_gate.json

Exit 0: passed
Exit 2: failed validation
Exit 1: input/runtime error
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

BAD_STATUS={"rejected","failed","blocked","missing","invalid"}

def load(path):
    with open(path,'r',encoding='utf-8') as f: return json.load(f)

def asset_map(doc):
    rows=doc.get('assets',[]) if isinstance(doc,dict) else []
    out={}; dup=[]
    for a in rows:
        aid=a.get('asset_id') if isinstance(a,dict) else None
        if not aid: continue
        if aid in out: dup.append(aid)
        out[aid]=a
    return out, sorted(set(dup))

def fail(msg, errors): errors.append(msg)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--handoff',required=True)
    ap.add_argument('--assets',required=True)
    ap.add_argument('--shots',required=True)
    ap.add_argument('--prompts',required=True)
    ap.add_argument('--scene-index',help='script/scene_index.json；AUTO 模式必须提供')
    ap.add_argument('--out')
    args=ap.parse_args()
    try:
        hand=load(args.handoff); assets=load(args.assets); shots=load(args.shots); prompts=load(args.prompts)
        scene_index=load(args.scene_index) if args.scene_index else None
    except Exception as e:
        print(f'input error: {e}',file=sys.stderr); return 1

    errors=[]; warnings=[]
    if hand.get('gate_passed') is not True: fail('scene_asset_handoff.gate_passed must be true',errors)
    hb=hand.get('scene_bindings')
    if not isinstance(hb,dict) or not hb: fail('scene_asset_handoff.scene_bindings must be a non-empty object',errors); hb={}

    amap, asset_dups=asset_map(assets)
    if asset_dups: fail('duplicate asset_ids: '+', '.join(asset_dups),errors)

    expected_scene_ids=[]
    if scene_index is not None:
        index_rows=scene_index.get('scenes')
        if not isinstance(index_rows,list) or not index_rows:
            fail('scene_index.scenes must be a non-empty array',errors); index_rows=[]
        for row in index_rows:
            scene_id=row.get('scene_id') if isinstance(row,dict) else None
            if not scene_id: fail('scene_index scene without scene_id',errors)
            else: expected_scene_ids.append(scene_id)
        if len(expected_scene_ids)!=len(set(expected_scene_ids)):
            fail('scene_index contains duplicate scene_ids',errors)
    else:
        warnings.append('未提供权威 scene_index；仅执行 legacy shot scope coverage')

    def binding_assets(binding):
        values=binding.get('allowed_location_asset_ids')
        if values is None:
            values=[binding.get('primary_location_asset_id'),*(binding.get('supporting_location_asset_ids') or [])]
        return {str(value) for value in values if value} if isinstance(values,list) else set()

    def binding_anchor_map(binding):
        rows=binding.get('route_anchors') or []
        return {str(row.get('route_anchor_id')):row for row in rows if isinstance(row,dict) and row.get('route_anchor_id')}

    shot_rows=shots.get('shots',[]) if isinstance(shots,dict) else []
    seen_shots={}; shot_dups=[]; valid_shots=0; scene_ids_in_shots=set()
    for s in shot_rows:
        sid=s.get('shot_id')
        if not sid: fail('shot without shot_id',errors); continue
        if sid in seen_shots: shot_dups.append(sid)
        seen_shots[sid]=s
        scene=s.get('scene_id'); scene_ids_in_shots.add(scene)
        b=hb.get(scene)
        if not b:
            fail(f'{sid}: scene_id {scene!r} missing from scene handoff',errors); continue
        ok=True
        for f in ('scene_id','location_id','sub_location_id'):
            expected = scene if f=='scene_id' else b.get(f)
            if s.get(f)!=expected:
                fail(f'{sid}: {f} mismatch: got {s.get(f)!r}, expected {expected!r}',errors); ok=False
        allowed=binding_assets(b)
        la=s.get('location_asset_id')
        if la not in allowed:
            fail(f'{sid}: location_asset_id {la!r} is not allowed for scene {scene!r}',errors); ok=False
        anchors=binding_anchor_map(b)
        anchor_id=s.get('route_anchor_id')
        if anchors or len(allowed)>1:
            anchor=anchors.get(str(anchor_id))
            if not anchor:
                fail(f'{sid}: route_anchor_id {anchor_id!r} missing or invalid',errors); ok=False
            elif anchor.get('location_asset_id')!=la:
                fail(f'{sid}: route anchor asset {anchor.get("location_asset_id")!r} does not match {la!r}',errors); ok=False
        a=amap.get(la)
        if not a:
            fail(f'{sid}: location_asset_id {la!r} missing from actual_asset_manifest',errors); ok=False
        elif str(a.get('status','')).lower() in BAD_STATUS:
            fail(f'{sid}: location asset {la!r} has blocked status {a.get("status")!r}',errors); ok=False
        if ok: valid_shots+=1
    if shot_dups: fail('duplicate shot_ids: '+', '.join(sorted(set(shot_dups))),errors)

    # AUTO coverage is always measured against the authoritative screenplay scene index.
    scope_scenes=set(expected_scene_ids) if scene_index is not None else {x for x in scene_ids_in_shots if x}
    covered_scenes={x for x in scope_scenes if x in hb}
    missing_shot_scenes={x for x in scope_scenes if x not in scene_ids_in_shots}
    unexpected_shot_scenes={x for x in scene_ids_in_shots if x and scene_index is not None and x not in scope_scenes}
    for scene in sorted(missing_shot_scenes):
        fail(f'authoritative scene {scene!r} has no shots',errors)
    for scene in sorted(unexpected_shot_scenes):
        fail(f'shots contain scene {scene!r} not declared by scene_index',errors)
    scene_cov=(len(covered_scenes)/len(scope_scenes)) if scope_scenes else 0.0
    shot_ratio=(valid_shots/len(shot_rows)) if shot_rows else 0.0

    clip_rows=prompts.get('clips',[]) if isinstance(prompts,dict) else []
    clip_ids=set(); clip_dups=[]; valid_clips=0; shot_consumption={}
    for c in clip_rows:
        cid=c.get('clip_id')
        if not cid: fail('clip without clip_id',errors); continue
        if cid in clip_ids: clip_dups.append(cid)
        clip_ids.add(cid)
        ok=True
        scene=c.get('scene_id'); b=hb.get(scene)
        if not b:
            fail(f'{cid}: scene_id {scene!r} missing from scene handoff',errors); ok=False
        else:
            expected={'location_id':b.get('location_id'),'sub_location_id':b.get('sub_location_id')}
            for f,v in expected.items():
                if c.get(f)!=v:
                    fail(f'{cid}: {f} mismatch: got {c.get(f)!r}, expected {v!r}',errors); ok=False
            allowed=binding_assets(b)
            if c.get('location_asset_id') not in allowed:
                fail(f'{cid}: location_asset_id {c.get("location_asset_id")!r} is not allowed for scene {scene!r}',errors); ok=False
            anchors=binding_anchor_map(b)
            anchor_id=c.get('route_anchor_id')
            if anchors or len(allowed)>1:
                anchor=anchors.get(str(anchor_id))
                if not anchor:
                    fail(f'{cid}: route_anchor_id {anchor_id!r} missing or invalid',errors); ok=False
                elif anchor.get('location_asset_id')!=c.get('location_asset_id'):
                    fail(f'{cid}: route anchor asset does not match location_asset_id',errors); ok=False
        dur=c.get('duration')
        if not isinstance(dur,int) or not 4 <= dur <= 15:
            fail(f'{cid}: duration must be integer 4..15, got {dur!r}',errors); ok=False
        prompt=c.get('prompt')
        if not isinstance(prompt,str) or not prompt.strip():
            fail(f'{cid}: prompt is empty',errors); ok=False
        elif not prompt.startswith('不要出现BGM，不要出现字幕'):
            fail(f'{cid}: prompt must start with 不要出现BGM，不要出现字幕',errors); ok=False
        refs=c.get('reference_asset_ids')
        if not isinstance(refs,list) or not refs:
            fail(f'{cid}: reference_asset_ids must be a non-empty array',errors); ok=False; refs=[]
        if len(refs)!=len(set(refs)):
            fail(f'{cid}: duplicate reference_asset_ids',errors); ok=False
        for rid in refs:
            if rid not in amap:
                fail(f'{cid}: reference asset {rid!r} missing from actual_asset_manifest',errors); ok=False
        la=c.get('location_asset_id'); mode=c.get('background_reference_mode')
        if la not in amap:
            fail(f'{cid}: location asset {la!r} missing from actual_asset_manifest',errors); ok=False
        if mode=='location_asset':
            if la not in refs:
                fail(f'{cid}: location_asset mode requires {la!r} in reference_asset_ids',errors); ok=False
        elif mode=='scene_keyframe':
            kf=c.get('scene_keyframe_asset_id')
            if not kf:
                fail(f'{cid}: scene_keyframe mode requires scene_keyframe_asset_id',errors); ok=False
            elif kf not in amap:
                fail(f'{cid}: keyframe {kf!r} missing from actual_asset_manifest',errors); ok=False
            else:
                if kf not in refs:
                    fail(f'{cid}: keyframe {kf!r} missing from reference_asset_ids',errors); ok=False
                meta=amap[kf].get('metadata') or {}
                lineage=meta.get('source_location_asset_id') or meta.get('base_location_asset_id') or meta.get('location_asset_id')
                if lineage!=la:
                    fail(f'{cid}: keyframe lineage {lineage!r} does not match location_asset_id {la!r}',errors); ok=False
                if str(amap[kf].get('status','')).lower() in BAD_STATUS or str(meta.get('review_status','')).lower() in BAD_STATUS:
                    fail(f'{cid}: keyframe {kf!r} is not approved',errors); ok=False
        else:
            fail(f'{cid}: invalid background_reference_mode {mode!r}',errors); ok=False

        ids=c.get('shot_ids')
        if not isinstance(ids,list) or not ids:
            fail(f'{cid}: shot_ids must be a non-empty array',errors); ok=False; ids=[]
        if len(ids)!=len(set(ids)):
            fail(f'{cid}: duplicate shot_ids inside clip',errors); ok=False
        for sid in ids:
            shot_consumption.setdefault(sid,[]).append(cid)
            s=seen_shots.get(sid)
            if not s:
                fail(f'{cid}: unknown shot_id {sid!r}',errors); ok=False; continue
            if s.get('scene_id')!=scene:
                fail(f'{cid}: shot {sid} belongs to scene {s.get("scene_id")!r}, not {scene!r}',errors); ok=False
            if s.get('location_asset_id')!=la:
                fail(f'{cid}: shot {sid} uses location asset {s.get("location_asset_id")!r}, not {la!r}',errors); ok=False
            if c.get('route_anchor_id')!=s.get('route_anchor_id'):
                fail(f'{cid}: shot {sid} route_anchor_id does not match clip',errors); ok=False
        if ok: valid_clips+=1
    if clip_dups: fail('duplicate clip_ids: '+', '.join(sorted(set(clip_dups))),errors)

    unassigned=[sid for sid in seen_shots if sid not in shot_consumption]
    duplicated_assign=[sid for sid,cs in shot_consumption.items() if len(cs)>1]
    if unassigned: fail('unassigned shots: '+', '.join(sorted(unassigned)),errors)
    if duplicated_assign: fail('shots assigned to multiple clips: '+', '.join(sorted(duplicated_assign)),errors)
    prompt_ratio=(valid_clips/len(clip_rows)) if clip_rows else 0.0

    passed=(not errors and scene_cov==1.0 and shot_ratio==1.0 and prompt_ratio==1.0)
    report={
        'schema_version':'1.0','passed':passed,
        'authoritative_scene_index_used':scene_index is not None,
        'scene_count_in_scope':len(scope_scenes),'covered_scene_count':len(covered_scenes),
        'shot_count':len(shot_rows),'valid_shot_count':valid_shots,
        'clip_count':len(clip_rows),'valid_clip_count':valid_clips,
        'scene_coverage_ratio':round(scene_cov,6),
        'shot_binding_ratio':round(shot_ratio,6),
        'prompt_binding_ratio':round(prompt_ratio,6),
        'missing_location_assets':sorted({m.split("'")[1] for m in errors if 'location_asset_id' in m and 'missing from actual_asset_manifest' in m and "'" in m}) if errors else [],
        'unassigned_shots':sorted(unassigned),
        'missing_shot_scene_ids':sorted(missing_shot_scenes),
        'unexpected_shot_scene_ids':sorted(unexpected_shot_scenes),
        'duplicate_shot_assignments':sorted(duplicated_assign),
        'errors':errors,'warnings':warnings
    }
    text=json.dumps(report,ensure_ascii=False,indent=2)
    if args.out:
        p=Path(args.out); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text+'\n',encoding='utf-8')
    print(text)
    return 0 if passed else 2

if __name__=='__main__':
    raise SystemExit(main())
