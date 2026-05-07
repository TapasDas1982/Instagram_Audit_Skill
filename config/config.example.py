"""
Configuration template for the Instagram Audit Skill.

Copy this file to config/config.py and fill in real values.
config.py is gitignored and MUST be chmod 600 on the deploy box.

    cp config/config.example.py config/config.py
    chmod 600 config/config.py    # on Linux

Never commit config.py. Never log MYSQL["password"], META["app_secret"],
META["long_lived_token"], or BREVO["password"].
"""

# MySQL — reuse the studio MySQL host, isolate to its own database
MYSQL = {
    "host": "localhost",
    "port": 3306,
    "user": "ig_audit_user",
    "password": "REPLACE_ME",
    "database": "ig_audit",
}

# Meta Graph API — Phase 2 onwards. Leave as None until the Meta App is ready.
META = {
    "app_id": None,
    "app_secret": None,
    "long_lived_token": None,
    "token_expires_at": None,        # ISO 8601 string, e.g. "2026-07-06T00:00:00"
    "ig_user_id": None,              # The Instagram Business account ID (numeric)
    "page_id": None,                 # Linked Facebook Page ID
    "graph_api_version": "v21.0",
}

# Brevo SMTP — Phase 4 batch email delivery
BREVO = {
    "host": "smtp-relay.brevo.com",
    "port": 587,
    "user": "REPLACE_ME",
    "password": "REPLACE_ME",
    "from_address": "audits@twistnturns.in",
    "to_addresses": ["tapash@twistnturns.in"],
}

# Audit settings
AUDIT = {
    "default_period_days": 30,
    "cache_ttl_hours": 24,
    "report_output_dir": "./output",
    "rubric_path": "./references/scoring_weights.json",
    "log_path": "./logs/ig_audit.log",
}
