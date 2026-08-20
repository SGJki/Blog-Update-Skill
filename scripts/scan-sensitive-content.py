#!/usr/bin/env python3
"""Scan a Markdown draft for likely sensitive material.

This is a conservative blocking gate for blog-update V10. It is not a secret
scanner replacement; it highlights content that needs human review before a
conversation-derived article is published.

Exit codes:
  0 = no findings
  1 = one or more findings
  2 = invocation/file error
"""
from __future__ import annotations

import argparse
import ipaddress
import re
import sys
from pathlib import Path


PLACEHOLDER_RE = re.compile(
    r"(<[^>]*(token|secret|key|password|cookie|email)[^>]*>"
    r"|YOUR_[A-Z0-9_]*(TOKEN|SECRET|KEY|PASSWORD|COOKIE|EMAIL)[A-Z0-9_]*"
    r"|REPLACE_[A-Z0-9_]+|example\.(com|org|net)|user@example\.com)",
    re.IGNORECASE,
)

PATTERNS = [
    ("private key", re.compile(r"-----BEGIN (RSA |DSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("authorization header", re.compile(r"\bAuthorization\s*:\s*(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE)),
    ("cookie header", re.compile(r"\b(Set-)?Cookie\s*:\s*[^\s=;]+=[^;\n]{8,}", re.IGNORECASE)),
    ("aws access key", re.compile(r"\bA[KS]IA[0-9A-Z]{16}\b")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b")),
    ("openai api key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("generic secret assignment", re.compile(r"\b(api[_-]?key|secret|token|password|passwd|pwd)\b\s*[:=]\s*['\"]?([A-Za-z0-9_./+=-]{16,})", re.IGNORECASE)),
    ("email address", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
    ("absolute user path", re.compile(r"(?<!`)\b(/Users/[^\s`]+|/home/[^\s`]+|/root/[^\s`]+)")),
    ("localhost/internal host", re.compile(r"\b(localhost|[a-z0-9.-]+\.local|[a-z0-9.-]+\.internal|[a-z0-9.-]+\.corp)\b", re.IGNORECASE)),
]

URL_RE = re.compile(r"\bhttps?://([^/\s)\]}]+)", re.IGNORECASE)
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def is_placeholder(text: str) -> bool:
    return bool(PLACEHOLDER_RE.search(text))


def is_private_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def scan(path: Path) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for label, pattern in PATTERNS:
            for match in pattern.finditer(line):
                if is_placeholder(match.group(0)):
                    continue
                findings.append((line_no, label, line.strip()[:160]))
                break

        for match in IP_RE.finditer(line):
            if is_private_ip(match.group(0)):
                findings.append((line_no, "private ip address", line.strip()[:160]))
                break

        for match in URL_RE.finditer(line):
            host = match.group(1).split(":", 1)[0]
            if host in {"example.com", "example.org", "example.net"}:
                continue
            if host == "localhost" or host.endswith((".local", ".internal", ".corp")):
                findings.append((line_no, "private url", line.strip()[:160]))
                continue
            try:
                if is_private_ip(host):
                    findings.append((line_no, "private url", line.strip()[:160]))
            except ValueError:
                pass

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan a blog draft for likely sensitive content.")
    parser.add_argument("file", help="Path to Markdown draft")
    parser.add_argument("--max-findings", type=int, default=40)
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2

    findings = scan(path)
    if not findings:
        print("Sensitive Content Scan: PASS")
        return 0

    print("Sensitive Content Scan: FAIL")
    for line_no, label, snippet in findings[: args.max_findings]:
        print(f"  [BLOCKING] L{line_no} {label}: {snippet}")
    if len(findings) > args.max_findings:
        print(f"  ... and {len(findings) - args.max_findings} more findings suppressed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
