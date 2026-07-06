"""Shared ingestion logic: severity normalization + geocoding — lands Day 5.

Every ingestor maps its source quirks locally and calls into here to emit a
schema-valid CrisisEvent (ARCHITECTURE.md §3). Seed mode bypasses this layer.
"""
