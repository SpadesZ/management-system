# File Path: backend/app/services/masking.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1


def mask_api_key(secret: str) -> str:
    normalized = secret.strip()
    if len(normalized) <= 8:
        return "****"
    return f"{normalized[:3]}****{normalized[-4:]}"
