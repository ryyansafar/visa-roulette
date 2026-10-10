# Design polish pass (run AFTER the base build is finished)

Do not start this until the booth flow works end to end. Then improve the design with an independent critic.

## Procedure, one iteration
1. Capture a screenshot of the current design.
2. Invoke the critic in a fresh context with only the screenshot. No code, no implementation details, no earlier
   iterations or critiques. Use a Fable 5 subagent (Agent tool, `model: "fable"`).
3. The critic evaluates the aesthetic the design is going for, imagines how a top design studio would execute that
   aesthetic, outlines the biggest gaps, and gives a score out of 10 for how close the design is to that
   studio-level quality bar.
4. Apply the critic's highest-impact fixes, then repeat with a new screenshot and a fresh critic.

## Critic prompt (use the same text every iteration)
> You are shown a screenshot of a design. First say what aesthetic it is going for. Then imagine how a top design
> studio would execute that aesthetic, and outline the biggest gaps between this design and that execution.
> Finish with a score out of 10 for how close it is to studio-level quality.
>
> Think at a high level about overall structure and composition, and also look at the fine details. Watch for
> patterns that feel overdone, excessive, or obviously AI-generated, and penalize them. Give tight, specific
> feedback, not vague prose. Be bold and opinionated; do not rely on what is safe or easy.

## Completion rule (kept out of the critic prompt on purpose)
The work is complete only when the critic independently scores the design 9/10 or higher. Do not mention this
threshold to the critic, so its scoring stays objective.
