# Contributing

Thanks for helping with Visa Roulette. This repo is being built during a hackathon, so keep changes small and easy to review.

## Ground rules
- Rules decide, AI suggests. Verdicts must come from the deterministic rules engine with a source link and "as of" date.
- Never commit secrets. Use `.env` (see `.env.example`).
- Use only sample or fake passports and documents.
- Keep files small and focused. Prefer new objects over mutating shared state.

## Workflow
1. Create a branch from `main`: `git checkout -b feat/<short-name>`
2. Commit with the format `<type>: <description>` (feat, fix, refactor, docs, test, chore, perf, ci)
3. Open a pull request and describe what changed and how you tested it

## Docs
When behaviour, setup steps or features change, update `README.md` and `PLAN.md` in the same pull request.

## Tests
`.venv/bin/python -m pytest backend/tests -q` (241 tests). The front end is vanilla ES modules with no build step; three.js is vendored in `web/vendor/`. Visa and checklist rules are unverified demo rules: add a `source_url` and `as_of` to every new one.

## Socials and support
- Portfolio: https://ryyansafar.site
- GitHub: https://github.com/ryyansafar
- Buy Me a Coffee: https://buymeacoffee.com/ryyansafar
- PayPal: https://www.paypal.com/paypalme/ryyansafar
- Razorpay: https://razorpay.me/@ryyansafar
