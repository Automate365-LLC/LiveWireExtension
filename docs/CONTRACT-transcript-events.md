# LiveWire Transcript Events Contract

Version: 0.2 (Draft)
Owner: Ivan Tkachov
Status: In Progress
Last Updated: February 6, 2026

## Purpose

This document defines the canonical event schema for LiveWire real-time transcript streaming. All components (WS1 capture, WS2 overlay, WS3 objection engine, WS5 CRM) must follow this contract.

## Schema Version
```json
{
  "schema_version": "0.2"
}
```

All events include schema_version to support evolution.

## Event Types

### 1. transcript_partial

Emitted during active speech (updates rapidly).

Format:
```json
{
  "type": "transcript_partial",
  "text": "this is what the speaker is currently",
  "speaker": "unknown",
  "timestamp_ms": 1738876800000,
  "session_id": "call_20260206_143000",
  "seq": 42
}
```

Fields:
- type: Always "transcript_partial"
- text: Current partial transcript (may be incomplete)
- speaker: "unknown" for Phase 2 (speaker ID in Phase 3+)
- timestamp_ms: Unix timestamp in milliseconds
- session_id: Unique call session identifier
- seq: Monotonic sequence number (increments per event)

Behavior:
- Updates replace previous partial
- Not persisted to CRM
- Used for real-time display only

### 2. transcript_final

Emitted when speech segment is finalized.

Format:
```json
{
  "type": "transcript_final",
  "text": "This is what the speaker actually said.",
  "speaker": "unknown",
  "segment_id": "seg_20260206_143000_001",
  "timestamp_ms": 1738876800000,
  "session_id": "call_20260206_143000",
  "seq": 43
}
```

Fields:
- type: Always "transcript_final"
- text: Finalized transcript text
- speaker: "unknown" for Phase 2
- segment_id: Unique ID for this transcript segment (for evidence tracking)
- timestamp_ms: Unix timestamp in milliseconds
- session_id: Unique call session identifier
- seq: Monotonic sequence number

Behavior:
- Replaces corresponding partial
- Persisted for CRM and analysis
- Referenced in card evidence

### 3. card_event

Emitted when objection engine detects trigger.

Format:
```json
{
  "type": "card_event",
  "cards": [
    {
      "card_id": "card_20260206_143000_obj_price_001",
      "type": "Objection",
      "title": "Handle pricing concern",
      "body": "Customer mentioned cost - address value",
      "evidence_segments": ["seg_20260206_143000_001"],
      "confidence": 0.85,
      "priority": 7,
      "timestamp_ms": 1738876800000
    }
  ],
  "session_id": "call_20260206_143000",
  "seq": 44
}
```

Fields:
- type: Always "card_event"
- cards: Array of 1-6 cards
- session_id: Unique call session identifier
- seq: Monotonic sequence number

Card Object:
- card_id: Unique identifier (format: card_{timestamp}_{type}_{subtype}_{seq})
- type: "Objection" | "NextStep" | "Summary" | "Risk" | "CTA"
- title: Display title (1 line, max 80 chars)
- body: Suggestion text (1-4 lines, max 200 chars)
- evidence_segments: Array of segment_id references (for explainability)
- confidence: Float 0-1 (detection confidence)
- priority: Integer 0-10 (display priority)
- timestamp_ms: Unix timestamp in milliseconds

Behavior:
- Cards with same card_id update in-place (no duplicates)
- evidence_segments links to transcript for debugging
- WS2 enforces max visible cards (UI calmness)

### 4. health_event

Emitted on connection state changes.

Format:
```json
{
  "type": "health_event",
  "state": "streaming",
  "component": "stt",
  "timestamp_ms": 1738876800000,
  "session_id": "call_20260206_143000",
  "seq": 1,
  "details": {
    "latency_ms": 245,
    "error": null
  }
}
```

Fields:
- type: Always "health_event"
- state: "idle" | "connecting" | "streaming" | "reconnecting" | "error"
- component: "capture" | "stt" | "ws" | "overlay"
- timestamp_ms: Unix timestamp in milliseconds
- session_id: Unique call session identifier
- seq: Monotonic sequence number
- details: Optional object with component-specific info

Behavior:
- Overlay shows current state
- Errors surface to user
- Logged for debugging

## Session ID Format
```
call_YYYYMMDD_HHMMSS
```

Example: call_20260206_143000

Rules:
- Unique per call session
- Included in every event
- Used for evidence pack correlation
- Format enforced by WS1

## Sequence Number Rules

- Monotonic (always increasing)
- Per session (resets on new session)
- Allows detection of lost events, out-of-order delivery, replay synchronization

Example Flow:
```
seq 1: health_event (connecting)
seq 2: health_event (streaming)
seq 3: transcript_partial
seq 4: transcript_partial
seq 5: transcript_final
seq 6: card_event
```

## Contract Change Policy

Owner: Ivan Tkachov

Change Process:
1. Propose change in /docs/CONTRACT-transcript-events.md
2. Tag PR with contract-change
3. Notify all workstream owners
4. Require approval from WS1 (Tanay), WS2 (Emmanuel), WS3 (Ivan), WS5 (Aryan)
5. Update schema_version
6. Document migration path

Breaking Changes:
- Increment schema version (0.2 to 0.3)
- Support old version for 1 sprint
- Provide upgrade guide

## Sample Event Streams

Simple Flow (1 utterance):
```json
{"type": "health_event", "state": "streaming", "seq": 1}
{"type": "transcript_partial", "text": "I think the", "seq": 2}
{"type": "transcript_partial", "text": "I think the price is", "seq": 3}
{"type": "transcript_partial", "text": "I think the price is too", "seq": 4}
{"type": "transcript_final", "text": "I think the price is too high.", "segment_id": "seg_001", "seq": 5}
{"type": "card_event", "cards": [{"type": "Objection", "title": "Price concern"}], "seq": 6}
```

Reconnect Flow:
```json
{"type": "health_event", "state": "streaming", "seq": 10}
{"type": "transcript_partial", "text": "We need to", "seq": 11}
{"type": "health_event", "state": "reconnecting", "seq": 12}
{"type": "health_event", "state": "streaming", "seq": 13}
{"type": "transcript_partial", "text": "We need to think", "seq": 14}
{"type": "transcript_final", "text": "We need to think about it.", "segment_id": "seg_002", "seq": 15}
```

## Implementation Checklist

- [ ] WS1: Emits events matching this contract
- [ ] WS2: Parses and renders events correctly
- [ ] WS3: Ingests events and generates cards per contract
- [ ] WS5: Maps events to CRM artifacts
- [ ] Tests: Sample event streams validate against schema
- [ ] Docs: This contract reviewed and approved

## References

- SOP: /docs/SOP-github-workflow.md
- Evidence Packs: /docs/evidence-pack-spec.md (TBD)
- Objection Taxonomy: /docs/objection-taxonomy.md (TBD)

## Document Status

This is a placeholder. Ivan owns the detailed schema specification.

Current Status: Draft - awaiting Ivan's CW-2 completion

Target Completion: Sprint 2, Day 2

Last updated: 2026-02-06 by Aryan Kumar (placeholder setup)
