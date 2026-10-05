# OLYMPUS 0.4.7 - Context Intelligence

## Goal
Provide small, explainable, high-relevance repository context to the Agent Runtime without injecting whole files or the whole repository.

## Implemented
- Symbol-aware relevance ranking.
- Import dependency and reverse-dependent graph.
- Automatic related-test discovery.
- Graph expansion from strongest task matches.
- Explainable per-file ranking reasons and scores.
- Focused snippets around task terms/symbols instead of always taking file headers.
- Strict global file/character/line budgets preserved.
- Shell entrypoint discovery remains supported.

## Runtime contract
Mission -> RepoMap -> relevance + graph -> bounded focused context -> Planner.

Context selection remains deterministic and local. No model call is required to build context.

## Validation
- Focused Context Intelligence tests: PASS.
- Targetless and Agent Runtime compatibility tests: PASS.
- Full suite: 449 tests, 0 failures, 0 errors, 4 environment-gated skips.
