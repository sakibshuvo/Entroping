"""Traffic-to-Hurl compiler boundary.

This module will convert redacted, normalized traffic sessions into Hurl test
models. It must not own proxy capture, SQLite persistence, or report writing.
"""

