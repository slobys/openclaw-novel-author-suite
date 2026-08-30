---
name: "video-reference-asset-safety"
description: "Validate video references, route views, landmarks, and scene continuity."
---

# Video Reference Asset Safety

Use this procedure when preparing or reviewing image references for a video model.

## Shared dispatch gate

1. Classify every candidate by intended role. Keep `design_sheet` assets for design review and admit only `video_reference` assets to video inputs. **Check:** every candidate has exactly one role, and no `design_sheet` appears in video inputs.

2. Inspect each `video_reference` for one visual subject, one view, and one state. Exclude panels, thumbnails, alternate poses, and text labels. **Check:** every admitted reference satisfies all six observations.

3. Check asset granularity separately from layout. Treat an image containing multiple independently usable props as an asset collection even when it has no panels or text. **Check:** every admitted prop reference represents one independent prop or one approved locked group.

4. Approve a locked prop group only when the story always uses the complete group together and its final arrangement is fixed. Otherwise, create one clean reference per core prop and describe nonessential clutter in the scene prompt. **Check:** every group is documented as indivisible and arrangement-locked or split into individual references.

5. Resolve the active production revision before reading, generating, or citing a prompt or reference source. Record each candidate's source path, role, reference scope, visual observations, and whether it contains multiple independent assets. Gate dispatch on those observations rather than filenames or numbering. **Check:** every cited source belongs to the active revision, and every dispatch decision is traceable to its source and recorded visual properties.

6. Test the gate with one eligible single-subject reference and one ineligible design sheet or collection before relying on it. **Check:** the eligible case passes and the ineligible case is excluded from video inputs.

## Character or animal coverage branch

Use this branch when a newly approved recurring person or animal needs reusable angle coverage.

1. Keep the approved three-quarter view as the parent. Generate front, left profile, right profile, and back as separate derivatives, each containing one subject, one view, and one state. Record parent lineage. **Check:** the pack has five separately identified views and every derivative links to the approved parent.

2. Before reviewing derivatives, compare the declared reference payload with the generator's execution record. Require evidence that every expected parent arrived as a populated input; manifests and upstream declarations show intent only. **Check:** every derivative job links to the parent reference actually received by the generator.

3. If a parent was missing at execution, reject the affected derivative batch, preserve the approved parent as authoritative, and gate retries on a probe job that proves reference delivery. **Check:** no unreferenced derivative is registered and no retry proceeds before a successful probe.

4. Separate stable identity from scene-specific state. Preserve identity-defining face, hair, clothing, and body proportions; include temporary marks, damage, props, or actions only when the pack explicitly targets that state. **Check:** the pack scope records whether each transient feature is retained or omitted.

5. Review every derivative independently against the parent, then compare all accepted views side by side for identity consistency and genuinely distinct viewpoints. Register each accepted view separately only when it passes the shared dispatch gate and identity review. Verify that its canonical file exists and its digest matches the registry before reuse. **Check:** every registered angle has an individual decision, the pack has one cross-view consistency decision, and every registry entry resolves to a digest-matching canonical file.

## Asynchronous episode-reference branch

Use this branch when episode references, especially route or environment images, are generated asynchronously before video dispatch.

1. Plan and review the asset stage independently from video dispatch. When correcting a missing location change, assign every expected environment image a distinct route-anchor role and attach digest evidence to each approved reference lock. **Check:** every planned environment has a route-anchor role and a digest-backed lock.

2. Validate the asset handoff with a dry run before submission. Treat submission acceptance and numeric progress as generation state only, not asset approval. **Check:** the handoff dry run passes and video dispatch remains held.

3. After the terminal callback, match the current task identifier and expected asset count. Compare the declared reference payload with the generator's execution record and require evidence that every expected reference arrived as a populated input. **Check:** the callback belongs to the current task, the count matches, and every expected reference has execution evidence.

4. Treat adjacent short-drama clips as one continuous physical space unless the script records a location change, time jump, or motivated transition. Reuse the prior approved environment authority when characters remain in place; change framing, lens, camera height, or viewing direction without inventing a new location. **Check:** every adjacent clip records either the inherited location identity or explicit evidence for a location change.

5. Allow multiple clean environment references for the same location when the plot changes viewpoint or a character travels far enough to reveal a new route position. Give each reference a distinct route-anchor role such as departure, path, turn, reveal, or arrival; treat it as a new camera or character position inside the same geography rather than a reset of the scene. **Check:** every new environment reference has a route-anchor role, a reason for the new view, and a traceable predecessor or location authority.

6. Build an environment continuity map before dispatch. For every clip or environment reference, record the inherited location ID, camera position and viewing direction, character position, route direction, visible landmark identities, landmark world-side relationships, expected screen position and scale, distance change, and any justified occlusion. **Check:** all clips resolve into one non-contradictory spatial map and every planned position change is caused by visible movement or an explicit transition.

7. Lock landmark identity and geography across all views of the same location. Preserve each signature landmark's silhouette, geometry, relative side, topology, and relationship to shorelines, paths, vegetation, structures, horizon, and light direction. Let screen position, scale, overlap, and visibility change only through explainable camera angle, parallax, distance, elevation, framing, or occlusion; never let a landmark disappear, move, mirror, or change shape without that evidence. **Check:** every landmark change has a geometric explanation, and unexplained absence or mutation blocks video dispatch.

8. Inspect every output independently, then compare the full route or scene sequence side by side. When a view must continue at the exact destination shown previously, resolve the prior approved final-arrival frame to its canonical file and digest and use that frame as the environment authority instead of generating an approximation. Compare rendering style, landmark silhouettes, shoreline or path topology, vegetation clusters, horizon, light direction, and screen-space arrangement against both the authority and the continuity map. **Check:** every image has an individual decision, the sequence has one cross-image continuity decision, and every exact-destination continuation cites a digest-matching authoritative frame.

9. When a route reference or annotation defines movement, translate it into a screen-space motion lock before video dispatch: record the visible start region, visible end region, near-to-far or far-to-near depth change, expected subject-size change, and landmark parallax. State the intended trajectory positively and name the opposite trajectory as a blocking reversal. Verify the lock against the reference, the continuity map, and the handoff dry run. **Check:** the recorded start, end, depth, scale, and parallax cues agree, and the dry run preserves that direction.

10. Record each missing reference, unexplained landmark change, or material visual mismatch as a blocking risk. Identify the affected images and obtain an explicit approval or rejection when the mismatch cannot be resolved from spatial evidence. When the user selects a replacement, bind that decision to the replacement's canonical identity, file, and digest, then hand the recorded decision to the session that owns the production checkpoint. Treat handoff acceptance or pending delivery as transfer state, not proof that the gate closed. **Check:** the selected replacement and user decision are traceable in both the visible progress record and the authoritative handoff, and dispatch remains held until checkpoint evidence confirms closure.

11. After the authoritative checkpoint closes the gate, promote the selected replacement as the active environment authority and remove superseded references from the active set. Trace and rebuild every derived manifest, mapping, spatial plan, prompt, and video task; mark old derivatives and job identifiers stale before creating a fresh job. Verify the fresh execution record contains only the selected authority before submission, and avoid duplicate triggering while the authoritative handoff is pending. **Check:** the dependency trace is complete, stale jobs cannot advance, the fresh execution evidence resolves only to the selected digest, and exactly one dispatch path remains active.

## Decision reference

- `design_sheet`: retain for review; exclude from video inputs.
- Single character, prop, or environment subject in one view and state: eligible when it also has no panels, thumbnails, or text.
- Multi-prop catalog or asset collection: retain for asset review; exclude from video inputs.
- Locked prop group: eligible only as the complete fixed arrangement; do not use it as a reference for one member.
- Background clutter: describe it in the scene prompt instead of creating an ambiguous collection reference.
