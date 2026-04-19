# Rule Template Packs E2E Checklist

## Pack Registry
- [x] At least 3 packs available (healthcare, financial, langchain)
- [x] Each pack has id, name, description, category, rule_count
- [x] No duplicate rule names within a pack

## Pack API
- [x] GET /api/rule-packs lists all available packs
- [x] GET /api/rule-packs/{id} returns pack detail with rules
- [x] GET /api/rule-packs/{id} for nonexistent → 404

## Installation
- [x] POST /api/rule-packs/{id}/install creates rules in DB
- [x] Installed rules are marked as built_in
- [x] Re-installing skips already existing rules
- [x] POST /api/rule-packs/{id}/install for nonexistent → 404
