## Summary

<!-- A short, focused description of what this PR does and why. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Engine / numerical change
- [ ] Docs / CI / DX
- [ ] Refactor (no behavior change)

## Checklist

- [ ] I have read the [contributing guidelines](../../docs/README.md) and the
      [security policy](../../SECURITY.md).
- [ ] **No secrets or personal data are introduced** — no `.env`, keys, or
      real client data. The privacy guard and security scanner must pass.
- [ ] **Engine changes keep seeded reproducibility** — the same profile +
      seed yields the same numbers, and the validation suite is updated.
- [ ] **Tests** — new/affected code has tests, and the full suite passes:
      `python -m pytest -q`
- [ ] **Formatting** — `ruff format --check .` and `ruff check .` pass.
- [ ] **Docs** — user-facing changes are reflected in the README and/or
      `docs/`.
- [ ] **No unrelated changes** — the diff is scoped to this PR's purpose.

## Test plan

<!-- How did you verify this works? Include commands, sample input, or the
tested interface (CLI / Streamlit / Web / API). -->

```bash
# e.g.
python -m pytest -q
python scripts/security_scan.py
```

## Related issues

<!-- e.g. Closes #123 -->
