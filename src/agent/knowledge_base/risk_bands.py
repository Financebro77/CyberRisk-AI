"""Risk band definitions and generic mitigation guidance.

These are the client-facing interpretations of the scoring bands produced
by scoring.py.  They ground the consultant agent's recommendations in
plain language that a risk manager can act on.
"""

BAND_GUIDANCE: dict[str, dict] = {
    "Low": {
        "summary": "Residual risk within appetite; controls are mature.",
        "recommendations": [
            "Maintain current controls; review annually.",
            "Consider whether cyber limit is adequate given growth.",
        ],
    },
    "Medium": {
        "summary": "Material residual risk; targeted control improvements advised.",
        "recommendations": [
            "Prioritise MFA and patch management gaps.",
            "Review third-party risk assessment cadence.",
            "Stress-test incident response plan.",
        ],
    },
    "High": {
        "summary": "Elevated residual risk; prompt remediation required.",
        "recommendations": [
            "Immediate remediation of critical vulnerabilities.",
            "Enforce least-privilege and privileged access control.",
            "Consider raising cyber limit / adding ransomware sub-limit.",
        ],
    },
    "Critical": {
        "summary": "Residual risk materially exceeds appetite.",
        "recommendations": [
            "Board-level escalation of cyber risk.",
            "Accelerated control remediation with executive sponsorship.",
            "Reassess insurance structure: higher limits, lower retentions.",
        ],
    },
}
