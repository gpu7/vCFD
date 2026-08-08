## Summary

<!-- What does this PR change and why? -->

## Security checklist

- [ ] No secrets, tokens, private keys, or `.env` files committed
- [ ] No AWS/xAI credentials or long-lived bearer tokens in docs or scripts
- [ ] Dependency changes reviewed (lockfile / Dependabot)
- [ ] Destructive or remote-exec paths remain guarded (auth, path jail, confirm flags)

## Test plan

- [ ] `uv run pytest -q`
- [ ] (If CFD-related) mock and/or Docker OpenFOAM smoke as appropriate
