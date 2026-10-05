# OLYMPUS Skill System

Skills are versioned operational capability contracts, not prompt-only personas. Each skill declares triggers, permitted actions, constraints, dependencies, execution guidance, completion checks and a version.

Flow: `objective -> SkillResolver -> SkillPolicy + professional contract -> AgentLoop -> verifier -> executor`.

Built-in skills cover coding, testing, frontend, backend, security, documentation, product experience, visual design and accessibility. Frontend work automatically composes testing, product experience, visual design and accessibility.

The resolved contract is injected into every planning iteration. The planner must follow its guidance and satisfy its completion checks. Deterministic web-quality gates independently reject placeholders, incomplete content, default styling, missing mobile layout and basic accessibility failures before a mission can complete.

A skill policy is checked before execution. Denied actions become `BLOCKED` with `failure_kind=policy`; the executor is never called.

Future extensions: skill composition, Skill x Model x Provider routing, marketplace and organization-private skills.
