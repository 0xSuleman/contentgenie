# Module: Tracking

## Goal
The `tracking` module records LLM usage and stores token estimates in the content database.

## File: api_tracking.py

### Class: APITracker
This class wraps `llm_completion`, estimates token usage, and stores it under `api_llm`.

## File: cost_analytics.py

Prints simple aggregate LLM token usage when historical usage data is available.
