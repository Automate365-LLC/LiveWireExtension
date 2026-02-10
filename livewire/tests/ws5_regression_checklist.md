# WS5 Regression Checklist

## A365 Push Endpoint

### Happy Path
- [ ] POST /api/a365/push returns 200 with valid payload
- [ ] Summary field correctly populated
- [ ] Tasks array correctly formatted
- [ ] Tags array correctly formatted
- [ ] Timestamp generated in ISO format
- [ ] Source field set to "livewire"

### Edge Cases
- [ ] Empty tasks array handled
- [ ] Empty tags array handled
- [ ] Empty summary handled
- [ ] Long summary (1000+ chars) handled
- [ ] Special characters in summary handled
- [ ] Special characters in tasks handled
- [ ] Special characters in tags handled
- [ ] Null values handled gracefully
- [ ] Missing fields handled gracefully

### Error Handling
- [ ] Invalid JSON returns proper error
- [ ] Malformed payload returns proper error
- [ ] Exception during push logged
- [ ] Retry logic attempts 3 times
- [ ] Final failure returns error response

## Guardrails Engine

### Debounce
- [ ] Cards blocked within debounce window (30s default)
- [ ] Cards allowed after debounce window passes
- [ ] Debounce timer resets after each card

### Dedupe
- [ ] Consecutive identical objection types blocked
- [ ] Different objection types allowed
- [ ] Alternating objection types allowed

### Rate Limit
- [ ] Max 3 cards per 5 minutes enforced
- [ ] 4th card within 5 minutes blocked
- [ ] Cards allowed after 5 minute window

### Reset
- [ ] Reset clears last_card_time
- [ ] Reset clears recent_objections
- [ ] Reset clears objection_timestamps
- [ ] Cards work normally after reset

### Stats
- [ ] get_stats returns cards_shown_last_5min
- [ ] get_stats returns last_card_time
- [ ] get_stats returns recent_objections list

## Integration Flow

### End-to-End
- [ ] Objection detected → endpoint called
- [ ] Guardrails check performed
- [ ] Allowed cards shown to user
- [ ] Blocked cards logged but not shown
- [ ] A365 push triggered for allowed cards
- [ ] Push payload contains correct data

### Multiple Objections
- [ ] Multiple objections in single call handled
- [ ] Rapid succession objections handled
- [ ] Long conversation (10+ objections) handled

## Performance

### Response Time
- [ ] A365 push completes in < 2 seconds
- [ ] Guardrails check completes in < 100ms
- [ ] Objection endpoint responds in < 500ms

### Resource Usage
- [ ] No memory leaks after 100+ objections
- [ ] Deque max length enforced (10 items)
- [ ] No excessive logging volume

## API Contract

### Request Format
- [ ] A365 endpoint accepts summary (string)
- [ ] A365 endpoint accepts tasks (array)
- [ ] A365 endpoint accepts tags (array)
- [ ] Objection endpoint accepts type (string)
- [ ] Objection endpoint accepts data (dict)

### Response Format
- [ ] Success returns status: "success"
- [ ] Error returns status: "error"
- [ ] Blocked returns status: "blocked"
- [ ] Mock flag present in development
- [ ] Proper HTTP status codes used

## Documentation
- [ ] API endpoints documented
- [ ] Guardrail rules documented
- [ ] Configuration options documented
- [ ] Error codes documented