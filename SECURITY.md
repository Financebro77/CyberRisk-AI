# Security Policy

## Supported Versions

CyberRisk AI is under active development (v0.x). Security fixes are
backported to the latest release when published.

| Version | Supported |
|---|---|
| latest | ✅ |

---

## Reporting a Vulnerability

We take the security of CyberRisk AI seriously. If you believe you have
found a security vulnerability, please report it to us privately.

**Please do NOT open a public GitHub issue for a suspected vulnerability.**

### How to report

1. **Email** the security team at `<security@example.com>` (replace with the
   project maintainer's address before publishing).
   - Include the words "SECURITY" and the project name in the subject line.
2. Provide as much of the following as possible:
   - A clear description of the vulnerability and its impact.
   - The affected component/version (e.g. `src/cyberrisk/api/`, version
     `0.1.0`).
   - A minimal, self-contained proof of concept (no real client data).
   - Any suggested remediation, if you have one.

### What happens next

- We will acknowledge your report within **3 business days**.
- We will keep you informed as we triage and fix the issue.
- We will publish a fix and credit you (if you wish) in the release notes.
- If the vulnerability is disclosed responsibly, no legal action will be
  taken against the reporter.

We ask that you give us a reasonable window (at least **90 days**) to
address the issue before public disclosure.

---

## Data Protection Statement

CyberRisk AI is designed so that **no personal information is stored by the
platform**:

- **No PII storage.** The quantitative engine and the AI consultant keep
  client conversations in memory for the duration of a session and do not
  write them to persistent storage by default. Personal data supplied in a
  prompt is redacted by the input-privacy guard (see
  [`src/cyberrisk/privacy.py`](src/cyberrisk/privacy.py) and
  [`config/privacy.yaml`](config/privacy.yaml)).
- **Secrets never in the repo.** API keys are read exclusively from the
  environment or `.env` (gitignored). No credential, token, or key is
  committed to the repository.
- **No private datasets.** The repository ships source code, documentation,
  and **synthetic example data only**. Public benchmark datasets (Verizon
  DBIR, IBM Cost of a Data Breach) are referenced by calibration table, not
  bundled. Licensed or client-confidential corpora must be sourced and held
  outside version control by the operator.
- **No client-identifiable data committed.** Client firm names, engagement
  histories, and policy wordings are never committed. The repository's
  example companies are fictional.

### Your responsibilities

- **Do not upload confidential client information** into the repository,
  issues, or discussions.
- **Keep API credentials local.** Use environment variables or a local
  `.env` file; never commit them.
- **Sanitise before sharing.** If you run an assessment, redact any personal
  or client-identifying detail before pasting output anywhere.

---

## Reporting a suspected data leak

If you believe personal or client data may have been exposed through the
repository (e.g. a committed `.env`, a private dataset, or personal
information in a tracked file):

1. Do not further distribute or reproduce the data.
2. Contact the maintainers via the email above with the file path(s).
3. If a real secret was committed, **rotate it immediately** — it is
   compromised. We will remove the data from history.

---

## Security Features

- **Input privacy guard** — redacts or blocks personal data (emails, phones,
  names, local paths) before it reaches the model
  ([`src/cyberrisk/privacy.py`](src/cyberrisk/privacy.py)).
- **Sanitised logging** — log lines are scrubbed of secrets and PII before
  they are written ([`src/cyberrisk/privacy.py`](src/cyberrisk/privacy.py)).
- **Confidentiality guardrails** — the agent refuses to disclose or speculate
  about another client's data ([`src/agent/safety.py`](src/agent/safety.py)).
- **Access-tier policy** — retrieval never crosses a license tier; client-
  confidential content is engagement-scoped
  ([`knowledge/access/policies.yaml`](knowledge/access/policies.yaml)).
- **No-invention guarantee** — hallucination checks validate every model
  figure against tool outputs.
- **`.gitignore`** — blocks secrets, private data directories, derived
  artifacts, and local databases from ever entering the repository.
- **Pre-commit hooks** — optional secret/large-file detection (see
  [`.pre-commit-config.yaml`](.pre-commit-config.yaml)).
