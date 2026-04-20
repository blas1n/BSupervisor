# Anomaly Detection E2E Checklist

## Cost Anomalies
- [x] Detects cost spike (5x above 7-day average)
- [x] Does not flag normal cost variation
- [x] New agent with no history does not trigger anomaly

## Event Frequency Anomalies
- [x] Detects event count spike (10x above 7-day average)
- [x] Does not flag normal event frequency

## Combined Detection
- [x] detect_all returns both cost and event anomalies

## API
- [x] GET /api/anomalies returns empty list when no anomalies
- [x] GET /api/anomalies returns anomaly details when detected
- [x] Response includes agent_id, metric, current_value, baseline_mean, multiplier
