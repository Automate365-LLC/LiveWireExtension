# Playbook Upload Guide — WS4 v1.0

> **Authors:** Vedanshi Verma (technical), Abdou (copy review)  
> **Last updated:** March 2026 | Sprint 7

---

## What is the Playbook?

The playbook is your company's sales framework. LiveWire uses it as the
primary truth layer — every battle card shown during a live call comes
directly from this document. LiveWire will never generate advice that
isn't grounded in your playbook.

---

## Supported Formats

| Format | Supported | Notes |
|--------|-----------|-------|
| PDF | ✅ Yes | Must be exported from Word or Google Docs — not a scanned image |
| DOCX | 🔜 Coming in PH4 | |
| TXT | 🔜 Coming in PH4 | |

### How to Export a Valid PDF

**From Microsoft Word:** File → Save As → PDF

**From Google Docs:** File → Download → PDF Document

> ⚠️ Do NOT use "Print to PDF" or scan a physical document.
> These create image-based PDFs that cannot be read by LiveWire.

---

## Recommended Structure

Structure your playbook in Q&A format for best retrieval accuracy:

```
Q: How much does it cost?
A: We offer three tiers starting at $99/month...

Q: Do you integrate with Zapier?
A: Yes, we have a native one-click integration...
```

Each Q&A pair becomes one retrievable chunk. The more specific your
answers, the better LiveWire matches them to live call moments.

---

## Recommended Sections

A strong playbook should cover:

1. **Pricing** — tiers, what's included, how to handle budget objections
2. **Integrations** — what tools you connect with and how
3. **Security** — data handling, compliance, certifications
4. **Objection Handling** — common pushbacks and how to respond
5. **Guarantee / Risk Reversal** — trial periods, refund policy
6. **Discovery Questions** — next-best questions to keep calls moving

---

## What to Avoid

- Vague answers — the more specific the answer, the better the match
- Long paragraphs — keep each answer under 200 words
- Scanned or image-based PDFs — these will fail to ingest
- Multiple topics in one answer — one Q&A pair per topic works best

---

## File Size

Keep your playbook under 10MB for v0. Longer playbooks will work but
may require threshold retuning after ingestion.

---

## Resources

- This guide lives at: `docs/playbook_upload_guide.md`
- Basecamp: [link to be added later]
- Technical owner: Vedanshi Verma (WS4)