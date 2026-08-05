"""Vercel entry point for Soundcheck's frozen read-only API contract."""

from soundcheck.api.app import create_app

app = create_app()
