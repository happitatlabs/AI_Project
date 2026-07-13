# Daily Agent Roadmap

## Phase 1: Daily Check-in Core

Status: Complete in this PR.

Scope:

- Store one DailyState per authenticated user and local date.
- Validate sleep, wake count, pain, mood, safety, hydration, energy, daily brick, and notes inputs.
- Create, read, update, and list daily records by date range.
- Enforce `(user_id, date)` uniqueness in the application and SQLite schema.
- Keep medication data as user-entered morning/evening checkboxes only.

Out of scope:

- Diagnosis, medication advice, dosage decisions, and medical history modeling.
- Green/Yellow/Orange/Red risk analysis.
- Notifications, push, emergency contact, calendar, HealthKit, or external AI calls.

## Phase 2: Risk Analyzer

Planned. Define explicit safety policy, risk language, tests, and escalation boundaries before implementation.

## Phase 3: Morning and Evening Check-in

Planned. Add guided check-in flows using the Phase 1 storage contract.

## Phase 4: Weekly Report

Planned. Summarize user-entered daily records without introducing diagnosis or medical advice.

## Phase 5: Reminder and Alert Integration

Planned. Integrate reminders or alerts only after privacy, consent, and safety behavior are specified and tested.
