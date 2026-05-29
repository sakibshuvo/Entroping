"""OpenAPI-to-Hurl compiler boundary.

This module owns only OpenAPI operation/schema translation. It must not call
LLMs, invoke Hurl, write files directly, or apply merge behavior.
"""

