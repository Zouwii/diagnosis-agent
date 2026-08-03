#!/usr/bin/env python3
"""Compatibility entry point for the migrated modular diagnosis CLI."""

from engine.interfaces.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
