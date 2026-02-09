# Patch Drops - Quick Code Upload

## What is a Patch Drop?

A patch drop is a temporary way to share code if you are:
- Not Git-ready yet
- Need to share a spike or prototype quickly
- Blocked on setup but have working code

## Location

Put your patch in: `/patch_drops/YYYY-MM-DD/{your-name}-ws{#}-{topic}/`

Example:
```
/patch_drops/2026-02-04/aryan-ws5-retry-logic/
```

## Required Contents

Every patch drop must include a README.md with:

1. What it is - Brief description
2. How to run - Exact commands to test it
3. Expected output - What should happen when it works
4. Known issues - What is broken or incomplete

## The 48-Hour Rule

Patch drops must be promoted to a real branch and PR within 48 hours.

Promotion means:
1. Create a proper branch: `ws{#}/{your-name}/{feature}`
2. Move code from patch_drops/ to proper location (e.g., services/)
3. Open a Pull Request to main
4. Get it reviewed and merged

If not promoted within 48 hours:
- Patch gets moved to `/patch_drops/archived/`
- Not treated as active work
- Will not count toward DoD

## Example Workflow

Day 1 (Tuesday 2pm):
Upload your code to patch_drops, create README.md, commit and push

Day 2 (Wednesday 2pm):
Create proper branch, move code to correct location, open PR

Day 3 (Thursday):
PR reviewed, merged to main, promotion complete

## When to Use Patch Drops

Good reasons:
- Git setup blocked, need to share code now
- Quick spike or prototype to show approach
- Waiting for help with branches but have working code

Bad reasons:
- Avoiding code review
- Trying to skip PR process

## README.md Template
```markdown
# [Feature Name]

## What it is
[One sentence description]

## How to run
cd patch_drops/YYYY-MM-DD/yourname-ws#-topic/
python my_script.py

## Expected output
[What should happen when it works]

## Known issues
- [List any bugs or incomplete parts]

## Promotion plan
- [ ] Create branch: ws#/yourname/feature
- [ ] Move to proper location
- [ ] Open PR
- [ ] Target merge date: [date]
```

## Need Help?

Ask Aryan for:
- Git setup assistance
- Branch creation help
- PR process walkthrough

Patch drops are temporary. Real work lives in branches, PRs, and main.
