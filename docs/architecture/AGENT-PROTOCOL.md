# Agent Communication Protocol

## 1. Purpose

This document defines the common communication, state and handoff protocol used by all agents in the AI Software Factory.

Its purpose is to ensure that specialized agents can collaborate without relying on implicit conversational context.

All important workflow information must be represented explicitly through project artifacts and state.

---

## 2. Core Principle

Agents must not assume that another agent remembers previous conversations.

The project's files and state are the source of truth.

```text
Conversation ≠ Source of Truth
Repository   = Source of Truth
```

---

## 3. Standard Agent Contract

Every agent interaction follows:

```text
INPUT
  ↓
VALIDATION
  ↓
WORK
  ↓
OUTPUT
  ↓
HANDOFF
```

### Input

Artifacts and information required to perform the task.

### Validation

The agent verifies that required inputs exist and are sufficiently clear.

### Work

The agent performs only the responsibilities defined by its contract.

### Output

The agent produces explicit artifacts or changes.

### Handoff

The agent reports its result and identifies the next expected workflow state.

---

## 4. Standard Status Model

All workflow units use one of the following statuses:

```text
NOT_STARTED
READY
IN_PROGRESS
BLOCKED
REVIEW_REQUIRED
APPROVED
FAILED
COMPLETED
```

### NOT_STARTED

Work has not started.

### READY

All required inputs are available.

### IN_PROGRESS

An agent is actively working on the item.

### BLOCKED

Work cannot continue because a dependency, decision or artifact is missing.

### REVIEW_REQUIRED

Agent work is complete but requires review or approval.

### APPROVED

The required reviewer or human has approved the result.

### FAILED

A required validation or quality gate failed.

### COMPLETED

The work and required validations are complete.

---

## 5. Project State

Every project using the Factory should maintain a machine-readable state file.

Recommended location:

```text
.factory/state.yaml
```

Example:

```yaml
factory_version: "1.0"

project:
  id: rideflow
  name: RideFlow
  phase: development

iteration:
  type: sprint
  id: sprint-01

work_item:
  id: US-001
  title: Request a ride

agents:
  product:
    status: APPROVED

  ux_ui:
    status: APPROVED

  architect:
    status: APPROVED

  developer:
    status: COMPLETED

  qa:
    status: FAILED
    blockers:
      - BUG-004

  security:
    status: COMPLETED

  devops:
    status: BLOCKED
    blockers:
      - QA_GATE_FAILED

  sre:
    status: NOT_STARTED

approvals:
  production_deployment: false
```

---

## 6. State Ownership

Agents may update only the state related to their own work unless explicitly authorized by the Orchestrator.

For example:

- Developer updates development status.
- QA updates QA status.
- Security updates security status.
- DevOps updates deployment status.

An agent must not mark another agent's work as approved.

---

## 7. Artifact References

State should reference artifacts rather than duplicating large amounts of information.

Example:

```yaml
artifacts:
  product_requirements:
    path: knowledge/project/requirements.md

  architecture:
    path: knowledge/architecture/system-design.md

  design:
    path: knowledge/ux-ui/design-system.md

  qa_report:
    path: reports/qa/US-001.md
```

---

## 8. Standard Handoff

Every significant agent handoff should communicate:

```yaml
handoff:
  from: developer
  to: qa

  work_item: US-001

  status: REVIEW_REQUIRED

  summary: >
    Ride request functionality implemented.

  artifacts:
    - src/features/rides/
    - tests/rides/

  validations:
    unit_tests: passed
    integration_tests: passed

  blockers: []

  risks: []

  requires_human_approval: false
```

The exact storage mechanism may evolve in later Factory versions.

---

## 9. Blockers

Agents must never silently work around missing critical information.

A blocker should identify:

```yaml
blocker:
  id: BLOCK-001
  type: MISSING_REQUIREMENT
  owner: product
  description: >
    Cancellation behavior after driver assignment is undefined.
  blocking: developer
```

Possible blocker categories include:

```text
MISSING_REQUIREMENT
DESIGN_AMBIGUITY
ARCHITECTURE_DECISION
SECURITY_RISK
TEST_FAILURE
DEPENDENCY_FAILURE
INFRASTRUCTURE_FAILURE
HUMAN_DECISION
```

---

## 10. Quality Gates

Workflow progression is controlled by explicit gates.

Typical feature workflow:

```text
PRODUCT APPROVED
       ↓
UX/UI APPROVED
       ↓
ARCHITECTURE APPROVED
       ↓
DEVELOPMENT COMPLETED
       ↓
QA PASSED
       ↓
SECURITY PASSED
       ↓
DEPLOYMENT READY
```

A later stage must not bypass a failed mandatory gate.

---

## 11. Human Approval Gates

Human approval must be represented explicitly.

Example:

```yaml
approvals:
  architecture:
    required: true
    approved: true

  production_deployment:
    required: true
    approved: false
```

Agents must never infer approval from silence.

---

## 12. Agent Failure

If an agent cannot complete its work, it must:

1. Stop the affected workflow.
2. Mark its status as `BLOCKED` or `FAILED`.
3. Explain the reason.
4. Identify the responsible owner when possible.
5. Avoid inventing missing information.
6. Notify the Orchestrator.

---

## 13. Retry Loop

Failed work may return to a previous agent.

Example:

```text
Developer
    ↓
QA
    ↓
FAILED
    ↓
Developer
    ↓
Fix
    ↓
QA
    ↓
COMPLETED
```

A retry must preserve the defect or blocker history.

---

## 14. Traceability

Important work should be traceable to a work item.

Examples:

```text
EPIC-001
US-001
BUG-004
SEC-002
ADR-003
INC-001
```

Code changes, tests, defects and architectural decisions should reference relevant identifiers when practical.

---

## 15. Repository as Shared Memory

The repository acts as the initial shared memory system of Factory V1.

Agents should read relevant artifacts before performing significant work.

Typical shared context:

```text
knowledge/
├── project/
├── architecture/
├── ux-ui/
├── engineering/
└── decisions/
```

Later Factory versions may introduce persistent databases, retrieval systems or external knowledge stores.

---

## 16. Idempotency

Whenever practical, agent workflows should be safe to execute more than once.

Agents should inspect existing artifacts before creating duplicates or overwriting approved work.

---

## 17. Conflict Resolution

When agents disagree:

```text
Agent A
   ↓
Conflict
   ↑
Agent B
   ↓
Orchestrator
   ↓
Impact Analysis
   ↓
Human Decision if required
```

The Orchestrator coordinates resolution but must not override mandatory human approval gates.

---

## 18. Definition of Done

The communication protocol is correctly followed when:

- Agent inputs are explicit.
- Outputs are explicit.
- State is machine-readable.
- Blockers are visible.
- Handoffs are traceable.
- Quality gates cannot be silently bypassed.
- Human approvals are explicit.
- Agents do not depend on hidden conversational memory.
- Failed work can safely return to the responsible agent.
