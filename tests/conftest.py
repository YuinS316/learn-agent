import os
import sys

# Ensure env vars exist before any imports trigger Settings()
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("ANTHROPIC_MODEL", "test-model")
os.environ.setdefault("ANTHROPIC_BASE_URL", "https://test.api.com")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_BASE_URL", "https://test.api.com")

# Make src importable without path hacks
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
