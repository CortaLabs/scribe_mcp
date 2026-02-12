"""
Example bridge plugins for reference and testing.

This package contains example implementations of Scribe bridge plugins:
- hello_world_plugin: Minimal example demonstrating bridge lifecycle
"""

from .hello_world_plugin import HelloWorldBridgePlugin, create_plugin

__all__ = ["HelloWorldBridgePlugin", "create_plugin"]
