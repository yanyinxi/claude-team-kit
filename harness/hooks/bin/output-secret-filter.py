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
    if len(text) < window:
        return []
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

            # ── 1. Direct secret keyword detection ──────────────────────────────
            direct_keywords = [
                (r'(?i)(password|secret|api[_-]?key|access[_-]?token|auth[_-]?token|bearer|private[_-]?key)', 'Direct Keyword Match'),
                (r'(?i)(mysql|mongodb|postgres|redis|connection)', 'Database Keyword Match'),
            ]
            for pattern, label in direct_keywords:
                for kw in re.finditer(pattern, decoded):
                    findings.append({
                        'type': f'Base64-Encoded {label}',
                        'severity': 'CRITICAL',
                        'match': m.group()[:20] + '...',
                        'decoded_preview': decoded[:50],
                        'context': text[max(0, m.start()-20):m.end()+20],
                        'method': 'base64',
                    })
                    break  # one match per string is enough

            # ── 2. Leetspeak / case-variant bypass detection ─────────────────
            # Patterns like p@ssw0rd, PASSWORD, p@ssw0rd! (common bypass chars)
            leet_patterns = [
                r'(?i)p[\@x]ssw[o0]rd',          # p@ssw0rd / passworD
                r'(?i)passw[o0]rd',               # passw0rd
                r'(?i)s3cr3t',                    # s3cr3t
                r'(?i)adm1n',                     # adm1n
                r'(?i)s3cr3t',                   # s3cr3t
                r'(?i)pr1v[ao]te',               # pr1vate
                r'(?i)[a-z]*[0-9@][a-z]*[0-9@][a-z]*',  # generic: any word with 2+ leet chars
            ]
            for lp in leet_patterns:
                if re.search(lp, decoded):
                    findings.append({
                        'type': 'Base64-Encoded (Leetspeak Bypass)',
                        'severity': 'HIGH',
                        'match': m.group()[:20] + '...',
                        'decoded_preview': decoded[:50],
                        'context': text[max(0, m.start()-20):m.end()+20],
                        'method': 'base64-leet',
                    })
                    break

            # ── 3. URL-encoded secret patterns (%XX sequences) ────────────────
            # If decoded text still contains %-encoded strings like %40 (== @)
            # and those resolve to a keyword, treat as secret
            url_encoded_secrets = re.findall(
                r'%[0-9A-Fa-f]{2}.*?(?:password|secret|token|key|auth)',
                decoded, re.I
            )
            if url_encoded_secrets:
                findings.append({
                    'type': 'Base64-Encoded (URL-Encoded Secret)',
                    'severity': 'CRITICAL',
                    'match': m.group()[:20] + '...',
                    'decoded_preview': decoded[:80],
                    'context': text[max(0, m.start()-20):m.end()+20],
                    'method': 'base64-url',
                })

            # ── 4. Base16 (hex) encoded secret detection ──────────────────────
            # Detect hex strings that look like encoded credentials:
            # e.g., 70617373776f7264 == "password" in hex
            hex_secret_patterns = [
                (r'^[0-9a-f]{8,32}$', 'Hex string (potential hex-encoded secret)'),
            ]
            for hex_re, label in hex_secret_patterns:
                # Check if this hex decodes to ASCII letters
                try:
                    # Try interpreting as hex encoding of ASCII text
                    hex_clean = re.sub(r'[^0-9a-f]', '', decoded.lower())
                    if len(hex_clean) >= 8 and len(hex_clean) % 2 == 0:
                        ascii_bytes = bytes.fromhex(hex_clean)
                        ascii_text = ascii_bytes.decode('ascii', errors='ignore')
                        # If it decodes to printable ASCII keywords, flag it
                        if re.search(r'(password|secret|token|key|api)', ascii_text, re.I):
                            findings.append({
                                'type': f'Base64-Encoded (Base16→{label})',
                                'severity': 'HIGH',
                                'match': m.group()[:20] + '...',
                                'decoded_preview': ascii_text[:50],
                                'context': text[max(0, m.start()-20):m.end()+20],
                                'method': 'base16',
                            })
                except Exception:
                    pass

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