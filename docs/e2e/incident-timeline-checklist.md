# Incident Timeline E2E Checklist

## Incident Creation
- [x] Blocked event automatically creates an incident
- [x] Allowed event does not create an incident
- [x] Multiple blocks from same agent within window merge into one incident
- [x] Different agents create separate incidents
- [x] Events outside time window create new incidents

## Timeline
- [x] Timeline includes surrounding events from same agent
- [x] Timeline excludes events from other agents
- [x] Timeline is ordered by timestamp

## API
- [x] GET /api/incidents returns list of incidents
- [x] GET /api/incidents/{id} returns detail with timeline
- [x] GET /api/incidents/{id} for nonexistent → 404
- [x] POST /api/incidents/{id}/resolve marks incident as resolved

## Data Model
- [x] Incident has agent_id, title, status, severity, event_count, started_at
- [x] IncidentStatus has OPEN and RESOLVED values
