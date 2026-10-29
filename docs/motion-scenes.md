# Coordinated motion scenes

> **Experimental finishing.** HyperKut Studio is beta. Finishing starts disabled; review the encoded result when enabling these features.


The Studio keeps the same interface and one HyperFrames compositor. Related flat layers may share a `scene` and have ids. `after` references an id in the same scene and shot. By default it schedules after that layer ends; `after_phase:"entered"` schedules after its entrance (`start + in_time`) while the earlier layer can remain visible. `delay` and `duration` accept local seconds or percentages of the final shot length. The first layer keeps explicit start/end. Cycles, missing dependencies and intervals outside the shot fail before generation when present in a planner plan.

```json
[
  {"shot_id":"SHOT_001","scene":"reveal","id":"rule","type":"vector","shape":"line","at":[0.15,0.7],"to":[0.85,0.7],"start":"5%","end":"95%","animation":"draw","in_time":0.2,"design":"tech","color":"#62e6cf","sync":"onset"},
  {"shot_id":"SHOT_001","scene":"reveal","id":"point","type":"vector","shape":"dot","at":[0.15,0.7],"after":"rule","after_phase":"entered","duration":"20%","motion_from":{"x":0},"motion_to":{"x":0.7},"ease":"smooth","color":"#62e6cf","sfx":"ui_click_soft"},
  {"shot_id":"SHOT_001","scene":"reveal","id":"title","type":"text","content":"SECATOR","after":"point","duration":"45%","position":"center","animation":"slide_up","design":"tech","safe":true,"sfx":"metal_tick"}
]
```

One onset-synced scene member requests a common shift for the whole scene, at most 150 ms, keeping all members inside the shot. Relative spacing remains unchanged. Shortening a shot rescales percentage timing. Absolute legacy layers keep their previous semantics. Explicit durations in seconds may need shortening if the shot becomes too short.

`design` provides bounded defaults: tech (clean/fine/controlled), editorial (serif/slower), pop (heavy/quick). Explicit values win. The planner chooses from the brief and references; these are not forced on every video. `motion_from` and `motion_to` support x/y offsets, scale and rotation for text, boxes/brackets and vectors. Vectors support line, dot and ring without masks or extra dependencies. This is a small 2D vocabulary, not an arbitrary UI morph or 3D scene engine.

Motion layers share one engine/Studio contract. `event_role` may be `action`, `reveal`, `narrative` or `decoration`; explicit `sfx` values must name a supported local sound. Studio checks submitted layer structure before generation and checks planner-produced layers before finishing. Relative seconds and percentages are resolved by the engine against the final shot timeline, after planning.

Explicit `sfx` uses the existing local SFX palette and assembler bus, only when sound effects are enabled. All three Studio final graphs give the assembler and compositor the same configured layers. Standalone assembly falls back to motion stored in the shot plan. Resolved scene events use that score and measured music attacks when music is available; the finishing pass measures its final audio mix. This is not stem separation or sample-accurate equivalence between separate detection passes. Duplicated manual-order shots are not a supported way to repeat one named scene.

The planner and H3 shot writer keep editable typography and graphics out of generated footage; an explicitly requested physical printed set is still allowed. Model compliance is not guaranteed.

Preview capture and technical validation still precede full encoding. The finishing report adds nonblocking readability advisories for short reading windows, nominally small text and explicit final positions near/outside the frame. These are not OCR, face detection, overlap detection or aesthetic approval. Safe wrapping in the browser remains active. No additional model call is made.
