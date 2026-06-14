"""Synchronous in-process folder runner for the full pipeline.

Transport-agnostic: composes the same stage cores the AWS Lambdas run, behind a
``DocumentSource`` abstraction so the folder source can be swapped for an
``S3PrefixSource`` without touching the orchestrator.
"""
