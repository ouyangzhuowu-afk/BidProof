"""Business use cases.

Routes translate HTTP to these calls; services own the workflow and never read request
objects, so the same code path serves an interactive request and a queued job.
"""
