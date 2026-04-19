# Explainable Block E2E Checklist

## Rule Evaluation with Explanations
- [x] POST /api/events with sensitive file delete → response includes structured explanation
- [x] POST /api/events with dangerous shell → explanation shows matched pattern
- [x] POST /api/events with DB rule match → explanation includes custom rule details
- [x] POST /api/events with safe action → explanation is null
- [x] Cost threshold warning → explanation includes agent cost and threshold

## Explanation Structure
- [x] Explanation includes rule_name, rule_description, rule_type
- [x] Explanation includes matched_field, matched_value, matched_pattern
- [x] Explanation includes severity (critical/high/medium/low/warning)
- [x] Explanation includes suggestion (when available)

## Persistence
- [x] Blocked event's explanation_json is stored in DB
- [x] Allowed event's explanation_json is null

## False Positive Feedback
- [x] POST /api/events/{id}/feedback with is_false_positive=true → 200 OK
- [x] Feedback on nonexistent event → 404
- [x] Feedback stored in event's feedback_json column

## Backward Compatibility
- [x] Existing tests still pass (RuleResult.reason still works)
- [x] EventResponse still has event_id, allowed, reason fields
