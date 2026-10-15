# Orchestration audit: provider-loop bounds

> The LLM proposes. The engine verifies. Evidence decides.
>
> An infinite provider-consuming loop is never acceptable.

`get_next_agent` returns any agent whose status is `READY` or `FAILED`, and
`run_workflow` loops until it returns `None`. An agent that fails is
therefore re-selected. Without a bound, each re-selection costs a provider
call.

This file records, per agent, whether that cycle is bounded.

## Status reachability

`RESULT_STATUS_TO_AGENT_STATUS` maps an `AgentResult` onto exactly two
workflow statuses: `BLOCKED` and `REVIEW_REQUIRED`. Both stop
`get_next_agent`. `FAILED` — the one status that makes an agent be
re-selected — is written by `run_next_agent` only for the five validation
agents, from their own evidence.

## The eight agents

| Agent | Bounded? | Limit | Explicit recovery | Provider-loop risk |
|---|---|---|---|---|
| `product` | No | — | plain `retry` only | None reachable: cannot reach `FAILED` from a result |
| `ux_ui` | No | — | plain `retry` only | None reachable: cannot reach `FAILED` from a result |
| `architect` | No | — | plain `retry` only | None reachable: cannot reach `FAILED` from a result |
| `developer` | Yes | `MAX_DEVELOPER_REPLANS = 3` | `retry developer --reset-replan-budget` | Bounded |
| `qa` | Yes | `MAX_QA_RETRIES = 2` | `retry qa --reset-replan-budget` | Bounded |
| `security` | Yes | `MAX_SECURITY_RETRIES = 2` | `retry security --reset-replan-budget` | Bounded |
| `devops` | Yes | `MAX_DEVOPS_RETRIES = 2` | `retry devops --reset-replan-budget` | Bounded |
| `sre` | Yes | `MAX_SRE_RETRIES = 2` | `retry sre --reset-replan-budget` | Bounded |

Every agent the runtime can set to `FAILED` on its own is budgeted. The
three upstream agents carry no budget, but no autonomous path puts them in
`FAILED` either: an operator can put them there with `set-status`, and the
next run then reaches `REVIEW_REQUIRED` or `BLOCKED` and stops. That is a
latent gap in the recovery vocabulary, not an active provider loop, and it
is deliberately out of scope here.

## Why the bounds differ

The Developer's limit is higher because a Developer replan **rewrites the
product**: the next cycle validates something new.

QA, Security, DevOps and SRE never write to the governed workspace, so a
repeated cycle re-evaluates identical artifacts with an identical prompt.
Two is the tightest bound that still allows one honest retry of a
genuinely transient check.

SRE is the strictest case of the four. `SREResult` declares `summary`,
`passed`, `findings`, `test_commands`, `blockers`, `observability_ready`
and `incident_readiness` — and no file changes at all, not even the
unapplied `changes[]` that DevOps declares. `run_sre_validation` executes
only the commands the agent names.

## The budget mechanism

`replan_guard.BUDGET_FIELDS` names, per budgeted agent, the three persisted
fields holding its counters. The operator reset — eligibility, audit trail,
CLI flag — is written once against that registry rather than once per
agent.

Each guard follows the same shape:

1. `assert_<agent>_retry_budget(state)` runs in `run_next_agent` **before**
   `run_agent`, so an exhausted budget costs neither an agent run nor a
   validation call.
2. It reads persisted counters only. Restarting the CLI cannot reopen it.
3. `advance_<agent>_retry_state(...)` runs when a cycle ends — the only
   moment where two consecutive cycles are both known — and is recorded
   before the status is chosen, so a bounded stop keeps the evidence.
4. A successful cycle zeroes the count and clears the signature.

## Failure signatures

Signatures are built from deterministic structured information only:
engine reason codes, engine-observed check outcomes, the failing command
strings, and counts derived from already-declared policy.

Summaries, finding identifiers, titles, categories, descriptions,
recommendations, blocker messages, rollback prose and runbook prose never
reach a signature. Severity and status remain model assertions; where they
participate it is only through the agent's already-declared policy
(`BLOCKING_FINDING_SEVERITIES`, an exact `RESOLVED` status), which claims
nothing the gate does not already claim.

Where repetition could not be made reliably structural, the hard count
bound carries the guarantee on its own.

## Explicit recovery

An ordinary `retry <agent>` sets the agent back to `READY` and does **not**
touch the counters — otherwise repeated retries would recreate the
unbounded loop the budget exists to prevent.

`retry <agent> --reset-replan-budget` is the operator's deliberate act. It
is refused unless the agent is `FAILED` **and** its budget is exhausted, it
preserves every diagnostic, and it appends an entry to
`replan_budget_resets` in the persisted state. It calls no provider.
