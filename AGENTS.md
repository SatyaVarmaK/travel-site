# AGENTS.md — Rules for AI Coding Assistants

You are an AI assistant generating code in this repository (Gemini Code Assist,
Cursor, Copilot, Claude, etc.). Follow every rule below. If anything is
ambiguous, stop and ask the human; do not guess. For rationale and longer
explanations, see [STYLE_GUIDE.md](STYLE_GUIDE.md).

---

## 1. HARD rules — refuse to violate

These are contracts. Other code, tools, or people depend on them. If a request
would require violating a HARD rule, stop and ask the human using section 11
format.

1. **Data collection writes long-format CSV via `UnifiedCsvLogger`** with the
   10-column schema in section 6. No private CSV writers. No wide-format CSV.
2. **Never duplicate shared helpers across workspaces.** Import from CAF
   (`common.*`, `whitebox.*`, `parsers.*`) or from
   `projects/<project>/_shared/`. If the helper does not appear to exist
   there, STOP and ask before creating it. Never silently copy a helper from
   another workspace.
3. **New code lives at the canonical paths:**
   - Libraries: `projects/<project>/<category>/libraries/<component>/<testcase>.py`
   - Robot tests: `projects/<project>/<category>/robot_tests/<scope>/<file>.robot`
   - Configs: `projects/<project>/<category>/config/`
   - Existing code outside this path is grandfathered; do not propose moving
     it unless asked.
4. **Every new Robot test case carries four tag families:**
   `category:<x>`, `component:<x>`, `scope:<tray|subrack|rack>`,
   `phase:<x>` (one or more).
5. **No hardcoded IPs, credentials, thresholds, durations, or sensor lists in
   `.py` or `.robot` files.** Load from `config/`.
6. **Build phase is config, never code.** No `if phase == "ttv":` branches.
   Differences go in `config/phases/<phase>.yaml` and (when the hardware path
   changes) in a CAF driver backend selected by config.
7. **Never introduce a new shared abstraction unilaterally.** If you think a
   helper should be promoted to `_shared/` or CAF, say so in your response and
   ask the human; do not modify those layers in the same change.

---

## 1b. SOFT guidance — apply, don't enforce

These are best practices that improve readability and reduce review time.
Apply them when you generate code, but do NOT audit existing code for them
and do NOT block generation if a request conflicts with them. If the user
asks about one, suggest the preferred approach in a sentence and move on.

- **Anchor pattern**: when generating a new file, cite the existing file
  whose style you are imitating (see section 12). Helpful but not enforced.
- **Formatting**: Python via `ruff format` (line length 100), Robot via
  `robotidy`. These run on save in the engineer's IDE — do not propose
  reformatting unrelated lines.
- **Type hints** on public Python functions. Suggest, don't enforce.
- **Naming style**, **docstring style**, **comment density**, **helper
  placement within a file**, **f-string vs `.format()`**, **loops vs
  comprehensions** — all engineer preference. Match the local file's
  style; if no precedent, pick a reasonable default and move on.

The full rationale for HARD vs SOFT lives in `STYLE_GUIDE.md` section 0b
("Consistency budget").

---

## 2. Repository layout

```
Workspaces/                              # repo root
├── AGENTS.md                            # this file
├── STYLE_GUIDE.md                       # full reference
├── pyproject.toml                       # ruff config
│
├── projects/
│   ├── <project>/                       # e.g. corgi/
│   │   ├── _shared/                     # project-wide, cross-category
│   │   │   ├── libraries/               # topology, genealogy collectors, ...
│   │   │   └── config/                  # rack map, credentials template
│   │   ├── si/                          # === CAP workspace ===
│   │   ├── thermal/                     # === CAP workspace ===
│   │   ├── power/                       # === CAP workspace ===
│   │   ├── sit/                         # === CAP workspace ===
│   │   └── reliability/                 # === CAP workspace ===
│   └── <next_project>/
│       └── ...
│
└── _workspace_template/                 # cookiecutter for new workspaces
```

A single workspace (`projects/<project>/<category>/`) always has this shape:

```
<workspace>/
├── workspace-config.json
├── README.md
├── CONTEXT.md
├── requirements.txt
├── AGENTS.md                            # per-workspace overrides (section 13)
├── config/
│   ├── <category>_config.yaml           # base
│   └── phases/{ttv,itv,stv,evt,dvt,pvt,mp}.yaml
├── libraries/
│   ├── <component>/<testcase>.py        # e.g. vindaloo/serdes_loopback.py
│   └── rack/<testcase>.py               # multi-component orchestration
├── robot_tests/
│   ├── tray/<component>_<scenario>.robot
│   ├── subrack/<scope>_<scenario>.robot
│   └── rack/<project>_<scenario>.robot
└── results/                             # gitignored, CAP writes here
```

CAF (separate submodule, do not modify in this repo):
```
CAP/CAF/platforms/
├── common/                              # data_logging, transports, svp, ...
├── whitebox/<component>/                # vindaloo/, chana/, katsu/ drivers + backends
└── parsers/                             # generic validators
```

---

## 3. Where to put a new file — decision tree

Run through these checks in order and stop at the first match.

| Question | If YES, file goes to |
|---|---|
| Would a brand-new project (different rack) want this code unchanged? | **CAF** — raise as a separate change to the framework team, do not modify CAF in a workspace PR. |
| Is the helper used by two or more category workspaces inside the same project? | **`projects/<project>/_shared/libraries/`** |
| Is it a test case library for one component? | **`projects/<project>/<category>/libraries/<component>/<testcase>.py`** |
| Does it orchestrate multiple components in the same workspace? | **`projects/<project>/<category>/libraries/rack/<testcase>.py`** |
| Is it a Robot suite? | **`projects/<project>/<category>/robot_tests/<scope>/<file>.robot`** where `<scope>` is `tray`, `subrack`, or `rack`. |
| Is it config? | **`projects/<project>/<category>/config/`** — base in `<category>_config.yaml`, phase deltas in `phases/<phase>.yaml`. |
| Is it a credential, IP, or secret? | **Never commit.** Add to `config/credentials.yaml.example` as a documented template; the real file is gitignored. |

If none of these match, stop and ask the human.

---

## 4. Naming rules

| Item | Convention | Example |
|---|---|---|
| Project folder | lowercase, single word | `corgi/` |
| Category folder | lowercase, single word | `thermal/`, `si/`, `power/`, `sit/`, `reliability/`, `manufacturing/` |
| Component subfolder | lowercase, single word | `vindaloo/`, `chana/`, `katsu/`, `rack/` |
| Test-case library | `<testcase>.py` — no `_lib` suffix, no `log_` prefix unless it really is a polling collector | `voltage_margin.py`, `serdes_loopback.py`, `log_vindaloo_bmc.py` |
| Robot file (tray scope) | `<component>_<scenario>.robot` | `vindaloo_thermal.robot` |
| Robot file (rack scope) | `<project>_<scenario>.robot` | `corgi_thermal_soak.robot` |
| Config file | `<purpose>_config.yaml` | `thermal_config.yaml` |
| Phase overlay | `<phase>.yaml` (lowercase) | `ttv.yaml`, `stv.yaml` |
| Run output dir | `YYYYMMDD_HHMMSS_<phase>_<scope>` | `20260518_103000_stv_rack/` |
| `workspace-config.json` `name` | `<project>_<category>` | `corgi_thermal`, `corgi_si` |

**Banned in any file or folder name:** spaces, capital letters, version
suffixes (`_v2`), engineer initials, dates. Git holds history; filenames
do not.

---

## 5. Component, category, scope, and phase enums

Use only these values. If the human asks for one not on the list, ask before
inventing.

| Axis | Allowed values |
|---|---|
| Category | `si`, `thermal`, `power`, `sit`, `reliability`, `manufacturing` |
| Component (folder name under `libraries/`) | `vindaloo`, `chana`, `katsu`, `rack` (last is for multi-component orchestration) |
| Component (Robot `component:` tag value) | `vindaloo`, `chana`, `katsu`, or `multi` (use `multi` when a test spans more than one component, regardless of which folder its library lives in) |
| Scope | `tray`, `subrack`, `rack` |
| Phase | `ttv`, `itv`, `stv`, `evt`, `dvt`, `pvt`, `mp` |

---

## 6. Long-format CSV schema — required for every collector

Every collector writes CSV using `UnifiedCsvLogger` from CAF
(`from common.data_logging import UnifiedCsvLogger`). Do not write a private
CSV writer. Do not write wide-format CSV.

The schema is exactly 10 columns, in this order, with these names:

| # | Column | Type | Notes |
|---|---|---|---|
| 1 | `timestamp_utc` | ISO-8601 UTC string | e.g. `2026-05-18T15:30:00Z` |
| 2 | `device_class` | string | One of `vindaloo`, `chana`, `katsu`, `chamber`, `pdu`, ... |
| 3 | `device_id` | string | Slot label, stable across runs (e.g. `vindaloo_03_L`) |
| 4 | `device_ip` | string | Management IP at sample time; empty if N/A |
| 5 | `category` | string | Sensor family: `power`, `thermal`, `voltage`, `current`, `ber`, ... |
| 6 | `metric` | string | Specific metric: `vrm1_temp`, `ibc_pout`, `lane3_ber`, ... |
| 7 | `value` | float (preferred) or string | The measurement |
| 8 | `unit` | string | `degC`, `W`, `V`, `A`, dimensionless `""` |
| 9 | `status` | string | `ok`, `stale`, `unreachable`, `error:<short>` |
| 10 | `fetch_ms` | int | Wall-clock ms to collect this sample |

Adding extra columns is forbidden in workspace code. If a new column is genuinely
needed, raise it in your response and ask the human to schedule a schema bump
in CAF.

Skeleton for a new collector:

```python
from common.data_logging import UnifiedCsvLogger
from common.transports import poll_loop

def collect(phase_cfg: dict, out_dir: Path) -> None:
    logger = UnifiedCsvLogger(out_dir / "vindaloo_thermal.csv")
    def one_cycle() -> None:
        for sample in iter_samples(phase_cfg):
            logger.write(
                device_class=sample.device_class,
                device_id=sample.device_id,
                device_ip=sample.device_ip,
                category=sample.category,
                metric=sample.metric,
                value=sample.value,
                unit=sample.unit,
                status=sample.status,
                fetch_ms=sample.fetch_ms,
            )
    poll_loop(one_cycle, interval_s=phase_cfg["polling"]["interval_s"])
```

---

## 7. Build phases — config + tag + backend (never code)

Phases differ along three axes. Each axis has exactly one mechanism. Use them
together; never branch on phase in code.

### A. Thresholds, durations, sample sizes — `config/phases/<phase>.yaml`

Base config holds defaults. Phase overlay is deep-merged at run time.

```yaml
# config/si_config.yaml
prbs:
  pattern: PRBS31
  duration_min: 5
ber_threshold: 1.0e-5
```

```yaml
# config/phases/stv.yaml
prbs:
  duration_min: 60
ber_threshold: 1.0e-8
```

### B. Which tests run in this phase — Robot `[Tags]`

```robot
PRBS31 Lane Sweep
    [Tags]    category:si    component:vindaloo    scope:rack
    ...       phase:ttv      phase:stv             phase:evt
```

### C. Hardware control path differs — CAF driver backend

When the way you talk to hardware changes between phases (e.g. TTV uses an RPI
debug header to talk to the ASIC, STV+ goes through the Katsu host over CDFP),
do NOT write `if phase == "ttv":`. Use a CAF backend, selected by config:

```python
# Test code stays single-source across all phases:
from whitebox.vindaloo import make_vindaloo_asic

asic = make_vindaloo_asic(slot, backend=phase_cfg["vindaloo"]["asic_backend"])
result = asic.run_prbs(duration_s=phase_cfg["prbs"]["duration_min"] * 60)
```

```yaml
# phases/ttv.yaml:    vindaloo: { asic_backend: rpi }
# phases/stv.yaml:    vindaloo: { asic_backend: katsu }
```

If the backend you need doesn't exist in CAF yet, stop and ask the human. Do
not create the backend in the workspace.

---

## 8. Robot Framework rules

> **HARD items below:** the four `[Tags]` families (rule 4), `Suite Teardown`
> safe to rerun (data-loss hazard), loading config from YAML (rule 5),
> `Library ../libraries/<component>/<testcase>.py` import path (rule 3).
> Everything else in this section is SOFT — apply, don't enforce.

Every Robot suite you generate must:

- Have a suite-level `Documentation` describing purpose, phase scope, and how
  to skip cases in CAP.
- Have every test case carry `[Documentation]` and the four tag families.
- Use `Suite Teardown` that is safe to run mid-suite (idempotent cleanup).
- Load config from a YAML file under `config/`; never hardcode values.
- Use `Library    ../libraries/<component>/<testcase>.py    WITH NAME    <Alias>`
  with short consistent aliases.
- Use `${UPPER_SNAKE}` for variables; capitalize-each-word keyword names
  (`Run Thermal Soak`, not `Run_Thermal_Soak`).

### Skeleton — copy this for every new Robot suite

```robot
*** Settings ***
Documentation     <one-line purpose>.
...
...               Phase scope: <list applicable phases>.
...               Skip individual cases in CAP by un-ticking before Run.

Library           OperatingSystem
Library           Collections
Library           ../libraries/<component>/<testcase>.py    WITH NAME    <Alias>

Suite Setup       Run Keywords
...               Load Phase Config    ${CONFIG_FILE}    ${PHASE}     AND
...               <Alias>.Initialize
Suite Teardown    <Alias>.Cleanup For Teardown


*** Variables ***
${CONFIG_FILE}    ${CURDIR}${/}..${/}config${/}<category>_config.yaml
${PHASE}          stv


*** Test Cases ***
<Test Case Name>
    [Documentation]    <intent>.
    ...                SKIP IF: <when to skip>.
    [Tags]    category:<x>    component:<x>    scope:<x>    phase:<x>    phase:<y>
    <Alias>.<Keyword>
```

---

## 9. Python rules

> **HARD items below:** import path discipline (rule 2 — no relative
> cross-workspace, use CAF/`_shared/`), config loading via shared loader
> (rule 5), one-library-per-test-case path (rule 3). Everything else in this
> section is SOFT — apply, don't enforce.

- **Python 3.12+.** Use `from __future__ import annotations` if you need
  forward refs.
- **Format with `ruff format`**, line length 100. Lint with `ruff check`.
- **Type hints on every public function.**
- **Docstrings**: triple-quoted, one-line summary, blank line, then details.
  Document the contract, not the implementation.
- **Comments explain why, never what.** If you need to comment what, rename
  the variable.
- **Logging**: `logger = logging.getLogger(__name__)`. Do not `print` except
  in CLI entry points.
- **Imports**:
  - From CAF: `from common.<x> import ...`, `from whitebox.<component> import ...`
  - From project shared: `from <project>_topology import ...`
  - Never relative across workspaces (`from ..other_workspace import ...`).
    If you need this, the code belongs in `_shared/` — stop and ask.
- **Subprocess / SSH / HTTP**: use shared transports from CAF
  (`common.transports`). Do not reinvent paramiko or `subprocess.run` wrappers.
- **Config loading**: via the shared loader. No scattered `yaml.safe_load` in
  library code.
- **Module shape**: one library per test case. Public keywords for Robot are
  module-level functions (or methods of a single class). Internal helpers are
  `_leading_underscore`.

---

## 10. Forbidden actions

You must not do any of these. If the user asks for one of them, explain the
relevant rule and propose the correct approach instead.

| Forbidden | Correct approach |
|---|---|
| Copying `common.py`, `rack_topology.py`, `svp_discovery.py`, or any helper from one workspace into another. | Import from CAF (or `_shared/` if project-specific). If it's not there yet, stop and ask. |
| Writing wide-format CSV (one column per sensor). | Use `UnifiedCsvLogger` and the 10-column long format. |
| Creating a CAP workspace per phase (`corgi-ttv-thermal/`) or per component (`corgi-vindaloo/`). | One workspace per (project, category). Use tags and subfolders for the other axes. |
| `if phase == "ttv":` or `if phase in ("evt", "dvt"):` anywhere in test or library code. | Phase config (`config/phases/<phase>.yaml`) or CAF backend selection. |
| Hardcoding IPs, credentials, thresholds, durations, or sensor lists in `.py` or `.robot` files. | Load from `config/`. |
| Adding columns to the CSV schema in workspace code. | Propose a CAF schema bump in your response and stop. |
| Modifying CAF in the same change as a workspace PR. | Two separate PRs: CAF first (framework-team review), then workspace. |
| Introducing a new shared abstraction (new base class, new helper module in `_shared/` or CAF) without the human's go-ahead. | Generate the workspace-local version, name it in your response, and propose promotion as a follow-up. |
| Pulling in a new dependency that isn't already in `requirements.txt` or CAF's `requirements.txt`. | Stop and ask. Most needs are already covered by existing deps. |
| Renaming or moving an existing file as a side effect of a feature request. | Make the rename a separate, explicit change. |
| Editing `STYLE_GUIDE.md` or this `AGENTS.md` without the human asking. | Both files are governance; humans propose changes via PR. |

---

## 11. When ambiguous — stop and ask

If any of the following are true, do not guess; ask the human:

- The decision tree in section 3 has no match.
- The user's request implies a forbidden action (section 10).
- A required helper (CSV writer, transport, driver backend) does not appear to
  exist in CAF or `_shared/`.
- The component, category, scope, or phase the user mentions is not in section 5.
- The user's request would require changing a layer above the workspace (CAF
  or `_shared/`).

Use this exact format when you ask:

```
I need to confirm before I generate this:

Context: <one-line summary of what the user asked for>
Conflict: <which rule or unknown is blocking — cite the section, e.g. "section 5: 'multi' is not an allowed component value">
Options I see:
  1. <option 1, including which rule it satisfies>
  2. <option 2, including its trade-off>
Recommendation: <option N and why>

Which would you like?
```

Do not produce code until the human answers.

---

## 12. Anchor pattern — always cite the file you are imitating

Every time you generate a new file or substantial helper, name the existing
file whose style you are following. Format:

> **Following the style of `<path>`.** <one-line description of what you're
> taking from it.>

If no good anchor exists for what the user asked for, say so explicitly and
ask for one. Do not invent a style.

### Current gold-standard anchors (use until migration completes)

| Generating... | Anchor file |
|---|---|
| Polling data collector | `corgi-thermal/libraries/log_vindaloo_bmc.py` |
| Multi-stage soak orchestrator (push/run/pull) | `corgi-thermal/libraries/soak_runner.py` |
| Long Python analysis / report script | `corgi-thermal/libraries/generate_4corner_report.py` |
| Robot suite with phased test cases + safe teardown | `corgi-thermal/robot_tests/corgi_thermal_soak.robot` |
| Workspace `README.md` | `corgi-thermal/README.md` |
| Workspace `CONTEXT.md` (design + known-issues log) | `corgi-thermal/CONTEXT.md` |
| Shared helpers module (CSV writer, SSH, poll loop) | `corgi-thermal/libraries/common.py` |
| Configuration YAML for a workspace | `corgi-thermal/config/config.yaml` |
| `workspace-config.json` | `corgi-thermal/workspace-config.json` |
| `requirements.txt` for a workspace | `corgi-thermal/requirements.txt` |

When the migration to `projects/<project>/<category>/` completes, the per-
workspace `AGENTS.md` (section 13) overrides this table with paths inside
that workspace.

---

## 13. Per-workspace `AGENTS.md` — template

Every workspace under `projects/<project>/<category>/` ships its own
`AGENTS.md` that this repo-root file is layered with. Copy the block below
into each new workspace and fill in the slots.

```markdown
# AGENTS.md — <project> <category>

Layered on top of [../../../AGENTS.md](../../../AGENTS.md). Repo-root rules
still apply; this file only adds workspace-specific anchors and constraints.

## Workspace identity

- Project:          <project>            (e.g. corgi)
- Category:         <category>           (e.g. thermal)
- Owner:            <name> <contact>
- Status:           <active | maintenance | sunset>

## Active components in this workspace

List only the components that have libraries in this workspace today.

- vindaloo
- chana
- ...

## Phases this workspace supports

List only phases that have a `config/phases/<phase>.yaml` and at least one
test case tagged for that phase.

- stv
- evt
- dvt
- pvt

## Hardware backends (when applicable)

| Phase | <component>.<thing>_backend |
|---|---|
| ttv | rpi |
| stv | katsu |
| ... | ... |

If a phase is not listed, no backend choice is exposed for it in this
workspace.

## Anchor files — use these as the style reference

When generating a new library or suite in this workspace, follow the style
of one of these files:

| Generating... | Anchor file |
|---|---|
| Polling collector | `libraries/<component>/<file>.py` |
| Multi-component orchestrator | `libraries/rack/<file>.py` |
| Tray-scope Robot suite | `robot_tests/tray/<file>.robot` |
| Rack-scope Robot suite | `robot_tests/rack/<file>.robot` |

## Local additions and exceptions

Document any workspace-specific rule that adds to (never contradicts) the
repo-root `AGENTS.md`. Example:

- This workspace's chamber driver pre-warms for 5 minutes; do not skip the
  warm-up step in new soak suites.
- The `four_corner_report` generator must remain CLI-compatible; do not
  change its argparse interface.

If you find yourself wanting to contradict a repo-root rule, stop and ask
the human; this file may not override it.
```

---

## 14. Reference

- Full rationale for every rule: [STYLE_GUIDE.md](STYLE_GUIDE.md).
- Architecture overview, decision rule, and promotion process:
  [STYLE_GUIDE.md](STYLE_GUIDE.md) sections 1, 13, 14.
- The 4-question rule for placing a new test: [STYLE_GUIDE.md](STYLE_GUIDE.md)
  section 13.

This file is governance. Propose changes via PR; do not edit it as a side
effect of a feature change.
