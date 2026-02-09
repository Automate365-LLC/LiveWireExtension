# LiveWire - GitHub Source-of-Truth SOP

Effective Date: February 4, 2026
Approved By: K.C. Gleaton
Integrator: Aryan Kumar
Status: Active

## Purpose

Keep one clean source of truth in GitHub while letting everyone contribute quickly without breaking the build or overwriting each other.

## Non-Negotiables

1. main is the single source of truth
2. No one pushes directly to main (ever)
3. All changes enter main via Pull Request (PR)
4. No shared workstream branches (multiple people committing to the same branch is not allowed)
5. If it is not merged into main, it is not done

## Roles

### Integrator (Merge Authority)
- Aryan Kumar = Integrator
- Aryan is the only person who merges PRs into main
- Reviews PRs for quality, conflicts, and completeness
- Makes final merge decision

### Workstream Owners (Testing Authority)
- Workstream owners do not merge (unless explicitly delegated)
- Owners run quick smoke tests (2-5 minutes)
- Approve PRs by commenting: WS# PASS

Workstream Owners:
- WS1 (Audio Capture): Tanay
- WS2 (Overlay UI): Emmanuel
- WS3 (Objection Engine): Ivan
- WS4 (Playbook RAG): Vedanshi
- WS5 (CRM Integration): Aryan
- WS6 (QA/Hardening): Emmanuel

## Contribution Paths

### Path A (Default): Personal Branch to PR to main

Branch Naming Convention:
```
ws{#}/{name}/{short-feature}
```

Examples:
- ws2/emmanuel/calm-mode-v1
- ws5/aryan/a365-push-v1
- ws3/ivan/objection-detect

Flow:

1. Pull latest main
```bash
git checkout main
git pull origin main
```

2. Create your personal branch
```bash
git checkout -b ws5/aryan/retry-logic
```

3. Make your changes and commit
```bash
git add .
git commit -m "WS5: Add retry logic with exponential backoff"
```

4. Push your branch
```bash
git push origin ws5/aryan/retry-logic
```

5. Open PR on GitHub
Go to github.com, Pull Requests, New Pull Request
Base: main, Compare: ws5/aryan/retry-logic
Fill out PR template and request review from Aryan

### Path B (Allowed for Quick Code Uploads): Patch Drop then Promote within 48 hours

When to use:
- You are not Git-ready yet
- Need to share a spike or prototype fast
- Git setup blocked but you have working code

Location:
```
/patch_drops/YYYY-MM-DD/{name}-ws{#}-{topic}/
```

Required: README.md with what it is, how to run, expected output, known issues

48-Hour Rule:
Patch drops must be promoted to a real branch and PR within 48 hours or they get archived and are not treated as active work.

See /patch_drops/README.md for full details

## PR Requirements (Minimum Standard)

Every PR must include:

1. What changed (bullets)
2. How to test (exact steps)
3. Evidence (screenshot/video/log/evidence pack)
4. Risk (what might break)

PR Template: .github/pull_request_template.md (auto-populates when you create PR)

## Testing and Approval Gate

### Workstream Owner Test is Required if PR:
- Is tagged DEMO-CRITICAL, or
- Touches core surfaces:
  - WS1: capture/STT
  - WS2: overlay/cards
  - WS5: A365 push/idempotency
  - /schema/ contracts

### Approval Requirements:

Non-Demo-Critical PR:
- 1 approval (Aryan or WS owner)
- Merge

DEMO-CRITICAL PR:
- 2 approvals:
  1. Workstream Owner comment: WS# PASS
  2. Aryan approval then merge

Timing:
- Owner review: within 24 hours
- Demo-critical reviews: completed by Thursday 3pm ET

## Smoke Tests (2-5 minutes each)

Owners approve by commenting WS# PASS after quick check:

- WS1: Frames flowing, health state streaming, evidence pack exports
- WS2: Overlay stable, transcript stable, cards not spamming
- WS3: Replay/test set triggers expected, no spam loops
- WS4: Retrieval returns top-k chunks with IDs and scores, latency logged
- WS5: Push twice results in no duplicates, artifacts readable in CRM
- WS6: Regression checks pass, evidence attached

## What We Do Not Do

- No shared branches where multiple people commit
- No direct pushes or merges into main without PR review
- Patch drops are not "shipped" - they must be promoted
- /schema/ changes require contract-owner approval

## Definition of Done

A task is not done until:

- PR merged into main
- DoD checklist met (from task spec)
- Evidence attached
- Smoke test passed (if required)

No merged PR = not done.

## Branch Creation Responsibility

Each contributor creates their own personal branch from the latest main.

This is not something K.C. or Aryan does for the team.

Rule:
Every contributor must create and push their own branch using: ws{#}/{name}/{feature}

Aryan's role: Integrator (reviews and merges PRs), not "branch admin"

Exceptions (rare):
1. Emergency hotfix: Aryan may create hotfix/YYYY-MM-DD-issue
2. Git setup blocked: contributor uses /patch_drops temporarily, branch and PR must be created within 48 hours (with help if needed)

## Step-by-Step Workflow

### For First-Time Contributors:

Step 1: Set up Git (one-time)
```bash
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

Step 2: Clone repo (one-time)
```bash
git clone https://github.com/Automate365-LLC/LiveWireExtension.git
cd LiveWireExtension
```

Step 3: Create your branch
```bash
git checkout main
git pull origin main
git checkout -b ws#/yourname/feature-name
```

Step 4: Make changes
Edit files, add new files, test your changes

Step 5: Commit
```bash
git add .
git commit -m "WS#: Clear description of what changed"
```

Step 6: Push
```bash
git push origin ws#/yourname/feature-name
```

Step 7: Create PR
- Go to GitHub repo
- Click Pull requests
- Click New pull request
- Base: main, Compare: ws#/yourname/feature-name
- Fill out template
- Request review from @akkumar9 (Aryan)

Step 8: Wait for approval
- Respond to feedback
- Make changes if requested
- Get WS owner PASS (if demo-critical)
- Get Aryan approval

Step 9: Merge
- Aryan merges your PR
- Your task is now done

## Common Scenarios

### Scenario 1: I need to update my PR based on feedback
```bash
git add .
git commit -m "Address review feedback: fix X and Y"
git push origin ws#/yourname/feature-name
```
PR automatically updates

### Scenario 2: Main changed while I was working
```bash
git checkout ws#/yourname/feature-name
git pull origin main
# Fix any conflicts
git push origin ws#/yourname/feature-name
```

### Scenario 3: I accidentally pushed to main
Contact Aryan immediately. He will revert the commit. You will need to create a proper branch and PR.

### Scenario 4: My branch is broken, start over
```bash
git checkout main
git branch -D ws#/yourname/feature-name
git push origin --delete ws#/yourname/feature-name
git checkout -b ws#/yourname/feature-name-v2
```

## Contact

Questions about:
- Workflow process: K.C. Gleaton
- Git help: Aryan Kumar
- PR review status: Aryan Kumar
- Smoke test requirements: Your workstream owner

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-04 | K.C. Gleaton | Initial SOP |

This SOP keeps our codebase clean and our team coordinated. Follow it strictly to avoid breaking the build and blocking others.
