"""AI consultant agent (Phase E).

Generates consultant-style risk recommendations by consuming the outputs
of the scoring engine, loss model, and policy transform.  Deliberately
implemented LAST: it must reason over validated quantitative outputs, so it
builds on Phases 2-4 rather than being a black box bolted on top of raw
model internals.

The agent also runs an INFORMATION-ELICITATION phase first (elicitation.py):
it refuses to advise until the client has provided the eight dimensions a
broker needs (industry, revenue, customer data, technology dependency,
security controls, prior incidents, existing coverage, risk appetite),
asks for anything missing, and explains why each piece matters.
"""
