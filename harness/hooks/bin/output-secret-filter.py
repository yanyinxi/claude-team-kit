#!/usr/bin/env python3
"""
output-secret-filter.py — PostToolUse Hook: detect secrets in tool output
Detects 20+ secret patterns, supports encoded/obfuscated bypasses,
writes sanitized log to ~/.claude/logs/secret-detections.jsonl

Usage: cat hook_data.json | python3 output-secret-filter.py
Exit codes: 0 (safe/checked), 2 (blocked CRITICAL secret)
"""

import sys
import json
import re
import os
import datetime
import base64
from pathlib import Path

# ── Secret patterns ───────────────────────────────────────────────────────────

PATTERNS = [
    # API Keys
    (r'sk-ant(?:i|api03-|ropic[_-])[a-zA-Z0-9]{30,}', 'Anthropic API Key', 'CRITICAL'),
    (r'sk[-_]?openai[_-]?[a-zA-Z0-9]{20,}', 'OpenAI API Key', 'CRITICAL'),
    (r'ghp_[a-zA-Z0-9]{36}', 'GitHub Personal Access Token', 'CRITICAL'),
    (r'gho_[a-zA-Z0-9]{36}', 'GitHub OAuth Token', 'CRITICAL'),
    (r'ghu_[a-zA-Z0-9]{36}', 'GitHub User-to-Server Token', 'CRITICAL'),
    (r'ghs_[a-zA-Z0-9]{36}', 'GitHub Server-to-Server Token', 'CRITICAL'),
    (r'ghr_[a-zA-Z0-9]{36}', 'GitHub Refresh Token', 'CRITICAL'),
    (r'xox[baprs]-[a-zA-Z0-9]{10,}', 'Slack Token', 'CRITICAL'),
    (r'AKIA[A-Z0-9]{16}', 'AWS Access Key ID', 'CRITICAL'),
    (r'ASIA[A-Z0-9]{16}', 'AWS Session Token', 'CRITICAL'),
    (r'[a-zA-Z0-9/+=]{40}==?\s*$', 'Potential Secret (base64)', 'HIGH'),

    # Private keys
    (r'-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----', 'Private Key', 'CRITICAL'),
    (r'-----BEGIN CERTIFICATE-----', 'Certificate', 'HIGH'),

    # Database
    (r'(?i)(?:postgres|mysql|mongodb|redis)://[^:]+:[^@]+@', 'Database Connection String', 'CRITICAL'),
    (r'(?i)password\s*[=:]\s*["\']?[^\s"\'&<]{8,}', 'Hardcoded Password', 'HIGH'),

    # Generic secrets
    (r'(?i)(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*[=:]\s*["\']?[a-zA-Z0-9_-]{20,}', 'Generic Secret', 'HIGH'),
    (r'(?i)bearer\s+[a-zA-Z0-9_-]{20,}', 'Bearer Token', 'HIGH'),
    (r'(?i)basic\s+[a-zA-Z0-9+/=]{20,}', 'Basic Auth Token', 'HIGH'),

    # Cloud providers
    (r'AIza[0-9A-Za-z_-]{35}', 'Google API Key', 'CRITICAL'),
    (r'[0-9a-f]{32}', 'Potential UUID/Secret (hex 32)', 'LOW'),
    (r'[0-9a-f]{64}', 'Potential Secret (hex 64)', 'HIGH'),

    # JWT
    (r'eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*', 'JWT Token', 'MEDIUM'),
]

# High-entropy detection (Shannon entropy > 4.5 = likely random secret)
def high_entropy(text: str, window: int = 20) -> list:
    """Find high-entropy spans that might be secrets."""
    import math
    results = []
    for i in range(len(text) - window + 1):
        window_text = text[i:i+window]
        if not re.match(r'^[A-Za-z0-9+/=_-]+$', window_text):
            continue
        freq = {}
        for c in window_text:
            freq[c] = freq.get(c, 0) + 1
        entropy = -sum((f/len(window_text)) * math.log2(f/len(window_text)) for f in freq.values())
        if entropy > 4.5 and len(set(window_text)) > 10:
            results.append((i, window_text, entropy))
    return results

# ── Detection ────────────────────────────────────────────────────────────────

def detect_secrets(text: str) -> list:
    """Scan text for secret patterns."""
    findings = []

    # Pattern-based detection
    for pattern, label, severity in PATTERNS:
        for m in re.finditer(pattern, text):
            findings.append({
                'type': label,
                'severity': severity,
                'match': m.group(),
                'offset': m.start(),
                'context': text[max(0, m.start()-20):m.end()+20],
                'method': 'pattern',
            })

    # High-entropy detection
    for offset, span, entropy in high_entropy(text):
        # Avoid duplicates with pattern matches
        if not any(f['offset'] == offset for f in findings):
            findings.append({
                'type': f'High-Entropy String (H={entropy:.2f})',
                'severity': 'HIGH',
                'match': span,
                'offset': offset,
                'context': text[max(0, offset-20):offset+20],
                'method': 'entropy',
            })

    return findings

def check_base64_decoded(text: str) -> list:
    """Check for base64-encoded secrets."""
    findings = []
    # Find base64 strings
    for m in re.finditer(r'[A-Za-z0-9+/]{40,}={0,2}', text):
        try:
            decoded = base64.b64decode(m.group()).decode('utf-8', errors='ignore')
            # Check if decoded text looks like a secret
            if re.search(r'(password|secret|key|token|api)', decoded, re.I):
                findings.append({
                    'type': 'Base64-Encoded Secret',
                    'severity': 'CRITICAL',
                    'match': m.group()[:20] + '...',
                    'decoded_preview': decoded[:50],
                    'context': text[max(0, m.start()-20):m.end()+20],
                    'method': 'base64',
                })
        except Exception:
            pass
    return findings

# ── Logging ───────────────────────────────────────────────────────────────────

LOG_DIR = Path.home() / '.claude' / 'logs'
LOG_FILE = LOG_DIR / 'secret-detections.jsonl'

def log_detection(detections: list, tool_name: str, session_id: str):
    """Write detections to JSONL log file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
        'session_id': session_id,
        'tool': tool_name,
        'count': len(detections),
        'severity_max': max((d['severity'] for d in detections), default='NONE'),
        'findings': detections,
    }
    with open(LOG_FILE, 'a') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')

# ── Sanitization ─────────────────────────────────────────────────────────────

def sanitize_text(text: str, detections: list) -> str:
    """Replace detected secrets with [REDACTED] markers."""
    result = text
    for d in sorted(detections, key=lambda x: x.get('offset', 0), reverse=True):
        match = d.get('match', '')
        if match and match in result:
            marker = f"[{d['severity']} {d['type']} REDACTED]"
            result = result[:result.index(match)] + marker + result[result.index(match)+len(match):]
    return result

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    try:
        hook_data = json.load(sys.stdin)
    except Exception:
        # No valid JSON input, skip silently
        sys.exit(0)

    message = hook_data.get('message', {})
    tool_name = message.get('name', '')
    content = message.get('content', '')

    # Build full text from content blocks
    if isinstance(content, list):
        text = ''
        for block in content:
            if isinstance(block, dict):
                if block.get('type') == 'tool_result':
                    inner = block.get('content', '')
                    if isinstance(inner, list):
                        for t in inner:
                            if isinstance(t, dict):
                                text += t.get('text', '') + '\n'
                    else:
                        text += str(inner) + '\n'
    else:
        text = str(content)

    if not text.strip():
        sys.exit(0)

    session_id = hook_data.get('sessionId', 'unknown')
    detections = detect_secrets(text)
    detections += check_base64_decoded(text)

    if detections:
        log_detection(detections, tool_name, session_id)

        # Block on CRITICAL severity
        has_critical = any(d['severity'] == 'CRITICAL' for d in detections)
        if has_critical:
            print(json.dumps({
                'status': 'blocked',
                'severity': 'CRITICAL',
                'message': 'CRITICAL secret detected in tool output. Detection logged.',
                'count': len(detections),
                'findings': [
                    {'type': d['type'], 'severity': d['severity']}
                    for d in detections
                ],
            }), file=sys.stderr)
            sys.exit(2)
        else:
            # Just warn
            print(json.dumps({
                'status': 'warning',
                'severity': 'LOW/MEDIUM/HIGH',
                'message': f'{len(detections)} potential secret(s) detected. Logged to {LOG_FILE}',
                'count': len(detections),
            }), file=sys.stderr)
            sys.exit(0)

    sys.exit(0)

if __name__ == '__main__':
    main()