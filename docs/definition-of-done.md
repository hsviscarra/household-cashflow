# Definition of Done

A roadmap feature (F0 to F19) is Done only when every item holds. The next feature starts after.

- [ ] **Issue** with acceptance criteria on the GitHub Project; work on `feat/Fxx-short-name`, small PRs.
- [ ] **Tests**: unit tests for new logic (pytest, Vitest); integration tests against SQL Server in CI;
      golden tests for parsers; an end-to-end test for each new page flow; coverage on `api/app` stays ≥ 80%.
- [ ] **Migrations**: Alembic upgrade, downgrade, upgrade runs in CI.
- [ ] **CI green**: ruff, mypy, ESLint, typecheck, tests, gitleaks, image build.
- [ ] **PR**: Conventional Commit title, description with screenshots; Hernan reviews and squash-merges.
- [ ] **CD**: the merge deploys to Azure and the smoke test passes for the new git SHA.
- [ ] **Docs**: README or `docs/` updated, an ADR for any design decision, CHANGELOG entry.
- [ ] **Release**: tag `vX.Y.0` with generated release notes.
- [ ] **Acceptance**: demo with sample or real data; status set to Done on the board.
