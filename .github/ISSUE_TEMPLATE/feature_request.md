---
name: Feature request
about: Suggest an idea for CyberRisk AI
title: "[Feature] "
labels: enhancement
assignees: ""
---

## Problem

A clear and concise description of the problem or gap this feature would
address. (e.g. *"Underwriters need to model a portfolio of clients, not just
a single firm."*)

## Proposed solution

A clear description of what you'd like to happen, and how it should behave.

## Alternative approaches

What alternatives you've considered, and why they don't fit as well.

## Impact

Who would benefit and how. (e.g. *"Insurance brokers could run book-level
correlated exposure."*)

## Scope

- [ ] This touches the **quantitative engine** (scoring / simulation /
      metrics / policy transform)
- [ ] This touches the **AI agent** (LLM layer, tools, RAG)
- [ ] This touches the **web / API** layer
- [ ] This is **docs / CI / DX** only

> **Note for engine changes:** the pipeline is deterministic when seeded.
> Proposals that change the numbers must keep seeded reproducibility and add
> tests in the validation suite.

## Additional context

Any references, prior art, or screenshots that help us understand the ask.
