# OLYMPUS 0.4.8 — Mission Resume

Mission progress is persisted atomically under `.olympus/checkpoints/`.

Contract:
- only verified completed steps are skipped on resume;
- an interrupted active step is replayed from its beginning;
- model attempts, modified files, tests and last error are retained;
- completion is persisted explicitly as historical evidence;
- a mission fingerprint prevents a checkpoint with the same ID but different content from contaminating a run;
- starting the same already-completed mission creates a fresh run rather than silently skipping work;
- checkpoint JSON is atomically replaced to avoid partial writes.

This is intentionally mission-step recovery, not arbitrary mid-action replay. Replaying an unverified action would be unsafe without action-level idempotency guarantees.
