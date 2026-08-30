# Qodo, and how to install it

This is the runbook for getting our pull requests reviewed by Qodo. It is written
to be followed top to bottom with no prior knowledge of the tool.

State at the time of writing: Qodo is **not installed** on
`Manancode/colophon-agent-harness`, and PR #1 is **open** with five commits.
Both facts are verifiable; the commands are at the bottom of this file.

---

## 1. What Qodo actually is

Qodo is a **GitHub App**. Installing an app on a repository is like giving a
second key to your flat to a specific person: they can't move in, but they get
notified when something happens, and they can leave notes.

Once installed, Qodo is subscribed to the repo's pull requests. When a PR opens
or changes, GitHub tells Qodo, Qodo reads the **diff** — the exact lines added
and removed, not the whole codebase — and posts a review comment on the PR.

That's it. It is not a test runner, not a linter you run locally, and it does
not have commit access. It reads a diff and writes an opinion in the PR
conversation.

**In plain terms:** a colleague who only reads the lines you changed, and writes
their comments where everyone can see them.

### What it writes

Findings come labelled by severity:

| Label | What it means | Our obligation |
| --- | --- | --- |
| **High** | Something is actually wrong or dangerous | Fix it, or dismiss it **in writing with a reason** |
| **Medium** | Probably worth doing | Engineering call |
| **Low** | Style, naming, tidiness | Engineering call |

The hackathon rules only bind us on the first row: **every valid High-severity
finding must be fixed or dismissed with a reason.** A silent dismissal does not
count. The reason has to be a reply on the thread.

---

## 2. Why it matters for the submission

One of the three tracks is *Best Code Quality*, judged **on the review trail** —
not on the code alone. The PR conversation is the deliverable. A PR with six
findings, four fixed and two dismissed with written reasons, is a stronger
submission than a PR with zero findings, because a clean review is
indistinguishable from a review that never ran.

So the goal is not "no findings". The goal is **a visible, honest thread**.

---

## 3. Installing it

This is the one step that needs a browser, and the one step I cannot do for you.
It needs your GitHub login.

1. Open **https://github.com/apps/qodo-code-review**
2. Click **Configure** (top right).
3. GitHub may ask you to sign in. Do that.
4. Under *Repository access*, choose **Only select repositories**.
5. Pick **`Manancode/colophon-agent-harness`** from the dropdown.
6. Click **Install** (or *Save*), and approve the permission prompt.

About two minutes. When it finishes you land on a confirmation page.

### Why "Only select repositories"

The other option is "All repositories", which would put Qodo on every repo you
own, including unrelated ones. There's no reason to do that here.

### Why the free tier works for us

Qodo's free tier covers **public** repositories. Ours is public:

```
$ gh api repos/Manancode/colophon-agent-harness --jq '{isPrivate, visibility}'
{"isPrivate":null,"visibility":"public"}
```

If the repo were private this would need a paid plan. It isn't, so it doesn't.

### What it can see

Qodo is given read access to the code and write access to pull request comments
only. It cannot push commits, cannot merge, and cannot change settings. It is a
commenter with a key, nothing more.

---

## 4. Getting PR #1 reviewed

Here is the catch, and it's the part worth knowing.

Qodo reviews PRs **as they open**. Our PR #1 was opened *before* Qodo was
installed, so Qodo never saw the event and will not retroactively review it.
Installing the app does not trigger a backlog scan.

**Fix:** ask for one. Open PR #1 and post a comment containing exactly:

```
/review
```

Qodo watches PR comments for commands, so a review starts within a minute or
two. You'd do the same thing on any later PR if a review didn't fire on its own.

### The other commands

| Command | What it does |
| --- | --- |
| `/review` | Review the current diff |
| `/describe` | Rewrite the PR title and description from the diff |
| `/improve` | Suggest concrete code changes for the diff |

`/describe` is genuinely useful on a PR whose description drifts from what the
commits actually did. `/review` is the one that matters for us.

---

## 5. What happens next

Qodo posts a review. For each finding, one of two things happens:

**We agree.** Fix it, commit, push. Qodo reviews the new diff automatically —
the loop in step 5 of the diagram — and the thread shows the finding, our fix,
and the resolution.

**We disagree.** Reply on the thread saying why, and leave the finding open. A
dismissal without a reason is worse than no response, because it reads as
ignored rather than considered.

Both outcomes are good evidence. Silence is the only bad one.

### Expect real findings

We already know of three defects in this diff that a reviewer *should* catch,
because we found them by running the thing rather than by reading it:

1. `fastmcp` 2.14 changed `add_tool` to take a `Tool` object instead of a
   function plus name/description keywords. Fixed by `_register_tool`.
2. `mcp` was pinned `>=2.0`, but 2.x renamed `McpError` to `MCPError`, which
   `fastmcp` still imports. Fixed by pinning `>=1.10,<2`.
3. Every `tools/list` example in the docs returned `400 Missing session ID`,
   because streamable HTTP requires an initialize handshake first. Replaced
   with `scripts/mcp_call.py`.

If Qodo misses all three, that's worth noting honestly in the evidence section
rather than pretending the review was clean.

---

## 6. Recording it in the README

The README has a `## Qodo Code Review Evidence` section. Once the review lands,
it needs three things:

- the PR link,
- the count of findings by severity,
- for each High finding: **fixed in commit X** or **dismissed because Y**.

Right now that section says Qodo is not installed and review is pending. That is
accurate, and it stays accurate until the review actually runs.

---

## 7. Verifying any of this

```bash
export PATH="/opt/homebrew/bin:$PATH"

# Is anything installed on the repo?
gh api repos/Manancode/colophon-agent-harness/installations
#   {"message":"Not Found",...}  -> nothing installed
#   a JSON list                  -> installed

# Is the repo public? (this is what unlocks the free tier)
gh api repos/Manancode/colophon-agent-harness --jq '{isPrivate, visibility}'

# What state is PR #1 in?
gh pr view 1 --repo Manancode/colophon-agent-harness --json number,state,url
```

### Gotchas

- **A 404 from `/installations` is not an error.** It is what "no app installed"
  looks like. It does not mean the repo is missing or that `gh` is
  unauthenticated.
- **Installing after a PR opens does not review that PR.** Say `/review`.
- **Findings can be wrong.** Qodo reads a diff without running the code. A
  finding that says "this will crash" when we have a passing test proving it
  doesn't is a valid dismissal — reply with the test name.
- **The free tier is per-repo.** If we later add a second public repo to the
  submission, install Qodo there too.
