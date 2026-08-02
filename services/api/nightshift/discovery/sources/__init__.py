"""Front-ends that produce candidate board tokens.

Each source knows how to find tokens and nothing else — no provider APIs, no
database, no notion of whether a token is any good. Classification is
`validate.py`'s job, and keeping that boundary is what lets these be tested
against recorded files with no network at all.
"""
