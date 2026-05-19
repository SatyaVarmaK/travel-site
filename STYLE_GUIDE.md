# Automation Workspaces — Style Guide

This document defines how we structure, write, and review automation code that
runs under CAP. It applies to every test workspace under `projects/` and to any
new code we add to CAF.

Audience: every engineer authoring or modifying automation test code.
Read once end-to-end. Re-read sections 0, 4, and 13 before starting any new test.

---

## 0. TL;DR — the rules in one screen

Rules are split into HARD (block on violation) and SOFT (apply, don't
enforce). See section 0b for why.

### HARD rules — these are contracts, block PR on violation

1. **Data collection writes long-format CSV** through the shared
   `UnifiedCsvLogger`, 10-column schema (section 6). No private writers,
   no wide CSV.
2. **Never copy shared helpers across workspaces.** Import from CAF or
   project `_shared/`. If the helper doesn't exist there, raise it — don't
   silently copy.
3. **New code lives at canonical paths**:
   `projects/<project>/<category>/libraries/<component>/<testcase>.py` for
   Python, `projects/<project>/<category>/robot_tests/<scope>/<file>.robot`
   for Robot. Old code is grandfathered until touched.
4. **Every new Robot test case carries four tag families:**
   `category:<x>`, `component:<x>`, `scope:<tray|subrack|rack>`,
   `phase:<x>` (one per applicable phase).
5. **No hardcoded IPs, credentials, thresholds, durations, or sensor lists
   in code.** Load from `config/`. Build phase is config, never code — no
   `if phase == "ttv"` branches; hardware-path differences go behind a CAF
   driver backend selected by `config/phases/<phase>.yaml`.

### SOFT guidance — apply, don't enforce

6. **One CAP workspace per (project, category) pair.** Not per-phase, not
   per-component. (Aspirational; affects new workspaces, not migration of
   existing.)
7. **Every workspace has a real `README.md` and `CONTEXT.md`.** Auto-stubs
   are weak but not blocking — add content as the workspace matures.
8. **Auto-format on save**: `ruff format` for Python, `robotidy` for Robot.
   No bike-shedding on style — the formatter wins.
9. **AI-assisted code is reviewed like junior PRs.** Anchor prompts to a
   real existing file (section 11).
10. **Promote code into CAF only on the second consumer, not the first.**

---

## 0b. Consistency budget — how strict to be about each rule

Perfect consistency across the team is unrealistic and the wrong goal. The
right goal is **interoperable code**: any teammate can read, modify, or
combine any workspace's output without having to rewrite anything.

The HARD/SOFT split above reflects this distinction:

- **HARD rules are interface contracts.** Other code, tools, or people
  depend on them. Violations cost real time later — duplicate bug fixes,
  broken cross-workspace analysis, CAP filter failures, security gaps.
  Block PRs on these.
- **SOFT rules are implementation preferences.** No one downstream depends
  on them. Variance costs nothing measurable — a reader adapts in seconds.
  Suggest in review, don't block.

### How to apply the budget in review

- For SOFT items: if you'd say "I'd write it differently," that's not a
  blocking comment. Leave it.
- For HARD items: explain which contract is being violated and what the
  concrete downstream cost is. Block, but with reasoning.
- If you find yourself fighting over a SOFT item, drop it. The political
  capital saved is what lets you hold the line on HARD items when it
  matters.

### Triggers to tighten

If you see one of these, push harder on the relevant HARD rule:

- A bug fixed in one workspace turns out to also exist in another (rule 2).
- A cross-phase analysis requires a custom parser per data source (rule 1).
- CAP filtering doesn't work because some tests lack tags (rule 4).
- An engineer can't find where something lives (rule 3).
- A credential or IP leaks into git (rule 5).

### Triggers to loosen

If you see one of these, the rule is over-tight:

- No one can articulate the concrete benefit of a rule.
- Compliance takes longer than the inconsistency would cost.
- The rule generates constant exceptions ("we always do X *except* when...").
- You're spending more review time on the rule than you save from it.

---

## 1. The 3-layer architecture

```
+--------------------------------------------+
| Layer 1: CAF (framework)                   |  Project-agnostic.
|   CAP/CAF/platforms/, core/, ...           |  Reused across projects.
|                                            |  Owned by framework team.
+----------------+---------------------------+
                 | imports
                 v
+--------------------------------------------+
| Layer 2: Project shared                    |  Project-wide, cross-category.
|   projects/<project>/_shared/              |  Reused inside one project only.
|                                            |  Owned by project test lead.
+----------------+---------------------------+
                 | imports
                 v
+--------------------------------------------+
| Layer 3: Workspace                         |  One category of one project.
|   projects/<project>/<category>/           |  This is what CAP opens.
|                                            |  Owned by domain engineer.
+--------------------------------------------+
```

Imports only flow downward in the diagram. A workspace may import from `_shared/`
and CAF. `_shared/` may import from CAF. CAF imports from nothing.

### What goes where — decision tree

For every new file or helper, ask in order:

1. **"Would a brand-new project (different customer, different rack) want this
   code as-is?"**
   - YES → CAF.
2. **"Is it used by more than one category workspace inside this project?"**
   - YES → `projects/<project>/_shared/`.
3. **Default** → inside the workspace (`projects/<project>/<category>/`).

### Concrete examples

| Thing | Layer | Why |
|---|---|---|
| `UnifiedCsvLogger`, the 10-col schema | CAF (`platforms/common/data_logging.py`) | Every project benefits. |
| `svp_discovery.py`, SSH wrappers, poll loop | CAF (`platforms/common/`) | Pure infra. |
| Generic chamber driver (Weisstek) | CAF (`platforms/common/instruments/`) | Commercial instrument, project-agnostic. |
| Vindaloo / Chana / Katsu hardware drivers | CAF (`platforms/whitebox/<component>/`) | Hardware family outlives a single project. |
| Driver backends (RPI vs Katsu control path) | CAF (`platforms/whitebox/vindaloo/backends/`) | Same hardware, two access surfaces. |
| Corgi rack map (`corgi_rack_map.yaml`) | Project `_shared/config/` | Inventory of one customer's rack. |
| `CorgiTopology` (subclass of CAF rack orchestrator) | Project `_shared/libraries/` | Project-specific layout on a generic base. |
| Tray genealogy collector (FRU) | Project `_shared/libraries/` | Used by every category. |
| Thermal collector workflow | Workspace (`thermal/libraries/<component>/`) | Category-specific orchestration. |
| 4-corner BER report | Workspace (`si/libraries/rack/`) | Category-specific analysis. |

---

## 2. Workspace = (project, category)

A CAP workspace is the unit you open in CAP and run tests from. We define it as
**one (project, category) pair**. This is the single hardest rule to internalize
and the most important.

### Why this cut

- Engineers are domain experts (thermal, SI, power) more than component experts.
  A workspace per category matches how people actually work.
- Categories share most of their helper code, drivers, and analysis tooling
  internally; categories share little across the boundary.
- New categories appear rarely (~1-2 per year per project). The number of
  workspaces stays bounded:
  `# workspaces ≈ # projects × # active categories`.

### Standard categories

| Category | Folder | What lives here |
|---|---|---|
| **si** | `<project>/si/` | Signal integrity: 4-corner BER, PRBS sweeps, eye diagrams, lane characterization. |
| **thermal** | `<project>/thermal/` | Thermal soaks, cool-down, chamber tests, temperature sensor collection. |
| **power** | `<project>/power/` | Voltage margining, power-up inrush, busbar draw, power-sequence checks. |
| **sit** | `<project>/sit/` | System integration: end-to-end boot, JTAG, I2C, host-to-accelerator paths, functional bringup. |
| **reliability** | `<project>/reliability/` | Long-duration stress, HALT/HASS, MTBF estimation, regression soak. |
| **manufacturing** | `<project>/manufacturing/` | MP screening test subset (fast pass/fail gates). Lights up at MP phase. |

Two tests belong in the **same** workspace when:
- They share most helper libraries.
- The same engineer is likely to author and own both.
- The same analyst will look at both result sets.

If those aren't all true, split.

---

## 3. The 5 dimensions and their mechanisms

You will be asked, repeatedly, "where does this go?" There are five orthogonal
axes. Each has exactly one mechanism. Do not conflate them.

| Dimension | Examples | Mechanism |
|---|---|---|
| **Project / rack** | Corgi, NextProject | Repo subtree: `projects/<project>/` |
| **Test category** | si, thermal, power, sit | CAP workspace boundary: `projects/<project>/<category>/` |
| **Component / tray** | vindaloo, chana, katsu | Subfolder inside the workspace: `libraries/<component>/` |
| **Scope** | tray, subrack, rack | Robot tag (`scope:tray`) + folder: `robot_tests/<scope>/` |
| **Build phase** | TTV, ITV, STV, EVT, DVT, PVT, MP | Config overlay (`config/phases/<phase>.yaml`) + Robot tag (`phase:stv`) + (when hardware path changes) CAF driver backend selection |

If you find yourself wanting to encode two of these in the same mechanism (e.g.,
`projects/corgi/stv_thermal/`), stop — you're collapsing two axes and you'll
regret it within a month.

---

## 4. Standard workspace layout

Every workspace under `projects/<project>/<category>/` has this exact shape:

```
projects/<project>/<category>/
├── workspace-config.json          # CAP workspace metadata + python_path_additions
├── README.md                      # required sections (section 10)
├── CONTEXT.md                     # required sections (section 10)
├── requirements.txt               # pinned versions
│
├── config/
│   ├── <category>_config.yaml     # base configuration
│   └── phases/
│       ├── ttv.yaml               # build-phase overlays (deep-merged onto base)
│       ├── itv.yaml
│       ├── stv.yaml
│       ├── evt.yaml
│       ├── dvt.yaml
│       ├── pvt.yaml
│       └── mp.yaml
│
├── libraries/
│   ├── vindaloo/                  # per-component subfolders
│   │   ├── __init__.py
│   │   ├── <testcase>.py          # one library per test case
│   │   └── ...
│   ├── chana/
│   ├── katsu/
│   └── rack/                      # multi-component / whole-rack orchestration
│       └── <testcase>.py
│
├── robot_tests/
│   ├── tray/                      # single-tray scope
│   │   └── <component>_<scenario>.robot
│   ├── subrack/                   # one rack of a multi-rack system
│   │   └── <scope>_<scenario>.robot
│   └── rack/                      # whole-system scope
│       └── <project>_<scenario>.robot
│
└── results/                       # gitignored; CAP writes here
    └── <run_id>/                  # YYYYMMDD_HHMMSS_<phase>_<scope>/
```

### Project `_shared/`

```
projects/<project>/_shared/
├── README.md
├── libraries/
│   ├── <project>_topology.py      # rack layout, slot ordering
│   ├── tray_genealogy.py          # cross-category collectors
│   └── ...
└── config/
    ├── <project>_rack_map.yaml    # THE single rack inventory (one copy)
    └── credentials.yaml.example   # template; real creds gitignored
```

### What does NOT live in a workspace

- Shared infrastructure (SSH, CSV writer, poll loop, transport wrappers) → CAF.
- Hardware drivers for Vindaloo / Chana / Katsu → CAF.
- Anything you'd want a second workspace in this project to use → `_shared/`.
- Credentials, secrets, IPs that vary per engineer → gitignored config file.

---

## 5. File and folder naming

| Item | Convention | Example |
|---|---|---|
| Project folder | lowercase, single word | `corgi/`, `nextproject/` |
| Category folder | lowercase, single word | `thermal/`, `si/` |
| Component subfolder | lowercase, single word | `vindaloo/`, `chana/`, `katsu/`, `rack/` |
| Test-case library | `<testcase>.py`, no `_lib` suffix, no `log_` prefix unless it really is a polling collector | `voltage_margin.py`, `serdes_loopback.py`, `log_vindaloo_bmc.py` |
| Robot test file | `<component>_<scenario>.robot` for tray scope; `<project>_<scenario>.robot` for rack scope | `vindaloo_thermal.robot`, `corgi_thermal_soak.robot` |
| Config file | `<purpose>_config.yaml` | `thermal_config.yaml`, `si_config.yaml` |
| Phase overlay | `<phase>.yaml` (lowercase) | `ttv.yaml`, `stv.yaml` |
| Run output folder | `YYYYMMDD_HHMMSS_<phase>_<scope>` | `20260518_103000_stv_rack/` |
| Workspace `name` in `workspace-config.json` | `<project>_<category>` | `corgi_thermal`, `corgi_si` |

Banned in file/folder names: spaces, capital letters, version suffixes
(`*_v2.robot`), engineer initials, dates. Use git for history; don't encode it
in filenames.

---

## 6. The long-format CSV data contract

Every collector writes CSV in the long (tidy) format below. This is non-negotiable —
analytics and reporting tools across the team depend on this shape.

### The 10-column schema

| Column | Type | Meaning |
|---|---|---|
| `timestamp_utc` | ISO-8601 UTC string (`2026-05-18T15:30:00Z`) | When the sample was taken. |
| `device_class` | string | Component family. One of: `vindaloo`, `chana`, `katsu`, `chamber`, `pdu`, ... |
| `device_id` | string | Slot label. e.g. `vindaloo_03_L`, `chana_5`, `katsu_01`. Stable across runs. |
| `device_ip` | string | Management IP at sample time. Empty if not applicable. |
| `category` | string | Sensor/metric category. e.g. `power`, `thermal`, `voltage`, `current`, `ber`. |
| `metric` | string | Specific metric name. e.g. `vrm1_temp`, `ibc_pout`, `lane3_ber`. |
| `value` | float (preferred) or string | The measurement. |
| `unit` | string | Unit. e.g. `degC`, `W`, `V`, `A`, dimensionless `""`. |
| `status` | string | `ok`, `stale`, `unreachable`, `error:<short>`. |
| `fetch_ms` | int | Wall-clock ms it took to collect this sample (latency telemetry). |

### Why long-format

- Joining CSVs from different collectors is `pd.concat([a, b, c])` with no
  alignment work.
- Adding a new metric does not change the schema. Wide formats require schema
  bumps on every new sensor.
- Pandas / DuckDB / SQL queries are trivial: `df[df.metric == 'vrm1_temp']`.
- Plotting libraries (matplotlib, seaborn) prefer long-format input.

### Anti-patterns

- Wide CSV with one column per sensor. **Do not do this**, even "just for this
  one report."
- A new private CSV writer in a workspace. Use `UnifiedCsvLogger` from CAF.
- Inventing extra columns. If you genuinely need one, propose a schema bump in
  CAF — document it, get one reviewer's sign-off, then add it everywhere.

---

## 7. Build phases — config + tag + backend

Phases (TTV, ITV, STV, EVT, DVT, PVT, MP) carry three kinds of differences.
Each has exactly one mechanism. **Never branch on phase in code.**

### Mechanism A: thresholds, durations, sample sizes → `config/phases/<phase>.yaml`

Phase overlays are deep-merged onto the workspace base config at run time.

```yaml
# si_config.yaml (base, defaults are most permissive)
prbs:
  pattern: PRBS31
  duration_min: 5
ber_threshold: 1.0e-5
```

```yaml
# phases/stv.yaml (overlay)
prbs:
  duration_min: 60          # longer run on STV
ber_threshold: 1.0e-8       # tighter threshold
```

The Robot suite picks the phase via a single variable:

```robot
${PHASE}              stv
${PHASE_CONFIG}=      Load Phase Config    ${CATEGORY_CONFIG}    ${PHASE}
```

### Mechanism B: which tests run in this phase → Robot tags

Every test case carries one or more `phase:` tags listing the phases it's valid
for:

```robot
PRBS31 Lane Sweep
    [Tags]    category:si    component:vindaloo    scope:rack
    ...       phase:ttv      phase:stv             phase:evt       phase:dvt    phase:pvt
```

CAP run selection is then:
`--include category:si AND phase:stv`

### Mechanism C: hardware control path differs → CAF driver backend

When the **way you talk to the hardware** changes between phases (the classic
case: TTV uses RPI debug header, STV+ uses Katsu host through CDFP), define an
abstract driver interface in CAF and provide two backends:

```python
# CAF: platforms/whitebox/vindaloo/asic.py
from typing import Protocol

class VindalooAsic(Protocol):
    def upload_firmware(self, fw_path: str) -> None: ...
    def init_lanes(self, lanes: list[int], pattern: str) -> None: ...
    def run_prbs(self, duration_s: int) -> "PrbsResult": ...
    def read_temperatures(self) -> dict[str, float]: ...

# CAF: platforms/whitebox/vindaloo/backends/rpi.py
class RpiAsicBackend:
    """TTV control path: ASIC accessed via RPI debug header (aapl over SSH)."""
    def upload_firmware(self, fw_path): ...

# CAF: platforms/whitebox/vindaloo/backends/katsu.py
class KatsuAsicBackend:
    """STV+ control path: ASIC accessed via Katsu host through CDFP."""
    def upload_firmware(self, fw_path): ...

# CAF: platforms/whitebox/vindaloo/__init__.py
def make_vindaloo_asic(slot_cfg, *, backend: str) -> VindalooAsic:
    return {"rpi": RpiAsicBackend, "katsu": KatsuAsicBackend}[backend](slot_cfg)
```

The phase config selects the backend:

```yaml
# phases/ttv.yaml
vindaloo:
  asic_backend: rpi

# phases/stv.yaml
vindaloo:
  asic_backend: katsu
```

The test case is single-source — same code on every phase:

```python
asic = make_vindaloo_asic(slot, backend=phase_cfg["vindaloo"]["asic_backend"])
result = asic.run_prbs(duration_s=phase_cfg["prbs"]["duration_min"] * 60)
```

### Anti-patterns

- `if phase == "ttv": ...` inside a test or library — split into a backend.
- A `libraries/ttv/` or `robot_tests/stv/` folder — use tags + phase configs.
- A workspace per phase (`corgi-ttv-si/`, `corgi-stv-si/`) — one workspace per
  (project, category), period.
- Hardcoded thresholds in test code — they belong in phase configs.

---

## 8. Python conventions

- **Python 3.12+** (CAF requires it).
- **Format with `ruff format`**, lint with `ruff check`. Line length 100.
- **Type hints on every public function.** Use `from __future__ import annotations`
  if needed for forward refs.
- **No relative imports** across workspaces (`from ..other_workspace import ...`).
  If you need it, the code belongs in `_shared/` or CAF.
- **Docstrings**: triple-quoted, one-line summary, then blank line, then details.
  Document the function's contract, not its implementation.
- **Comments**: explain *why*, never *what*. If you need to comment what, rename
  the variable.
- **Logging**: use the standard `logging` module via `logger = logging.getLogger(__name__)`.
  Do not print directly except in CLI entry points.
- **Config loading**: always via the shared config loader. No `yaml.safe_load`
  scattered in library files.
- **Subprocess / SSH**: use the shared transport helpers from CAF. Do not
  reinvent paramiko / subprocess.run wrappers.
- **One library per test case**: `libraries/<component>/<testcase>.py`. The
  library exposes the keywords Robot will call. Helper functions stay
  module-private (`_leading_underscore`).

---

## 9. Robot Framework conventions

- **Format with `robotidy`**, lint with `robocop`. Both should be clean before PR.
- **Every test case has `[Documentation]`** describing intent and "SKIP IF"
  conditions when applicable.
- **Every test case has `[Tags]`** with at minimum:
  - `category:<x>`
  - `component:<x>` (or `multi` for rack-scope cross-component tests)
  - `scope:tray`, `scope:subrack`, or `scope:rack`
  - One or more `phase:<x>` tags
- **Suite-level `Documentation`** describes the suite's purpose, phase scope,
  how to run it, and how to selectively skip cases in CAP.
- **`Suite Teardown` is always safe to run mid-suite** (use `Run Keyword And
  Ignore Error` patterns for cleanup keywords).
- **No hardcoded IPs, credentials, or thresholds in `.robot` files.** Load from
  `config/`.
- **Variables**: name in `${UPPER_SNAKE}`. Local to a keyword in
  `${lower_snake}`.
- **Use `Library    ../libraries/<component>/<testcase>.py    WITH NAME    <Alias>`**
  pattern. Keep aliases short and consistent.
- **Keyword names**: capitalize each word, no underscores
  (`Run Thermal Soak`, not `Run_Thermal_Soak`).

### Reference example

The suite `corgi-thermal/robot_tests/corgi_thermal_soak.robot` is the current
gold standard — phase-tagged test cases, per-case `[Documentation]` with
"SKIP IF" guidance, safe teardown. Use it as a template until the migrated
version lives at `projects/corgi/thermal/robot_tests/rack/corgi_thermal_soak.robot`.

---

## 10. Documentation: `README.md` and `CONTEXT.md`

Every workspace has both files. Auto-generated stubs are not acceptable.

### `README.md` — required sections

```markdown
# <project> <category>

One-paragraph purpose statement.

## Layout
(tree of the workspace's folders, brief description of each)

## How to run from CAP
(one-liner instructions for the most common scenario)

## How to run a single library standalone
(server-side / dev-machine instructions for debugging one collector)

## Config keys
(table of the most relevant config.yaml keys + what they do)

## Phases supported
(list of phases with one-line notes per phase)

## Owner
(name + Slack/email of the engineer responsible)
```

Aim for two screens. Anything longer probably belongs in `CONTEXT.md`.

### `CONTEXT.md` — required sections

`CONTEXT.md` is the "hand it to a new engineer cold and they can take over"
document. The current best example is `corgi-thermal/CONTEXT.md` — mirror its
structure:

1. **Purpose** — what this workspace does and why it exists.
2. **File map** — annotated tree showing every important file.
3. **Key design decisions** — every non-obvious choice with rationale.
4. **Key functions** — table of important functions and what they do.
5. **CLI reference** — every standalone script's command-line interface.
6. **Robot suite structure** — entry-point suites, what they orchestrate.
7. **Known issues / historical fixes** — every bug you have hit and how you
   solved it. This section saves the next engineer days.
8. **Environment / SVP / rack config** — credentials structure, SVP paths,
   anything ops-related.
9. **Pending / future work** — known TODOs and design extension points.

**Update `CONTEXT.md` whenever you make a design decision or fix a tricky bug.**
This is a living document, not a one-time write.

---

## 11. Working with Gemini Code Assist

AI-assisted code is welcome. It must be reviewed like junior PR code: read it,
understand it, test it.

### Prompting rules

1. **Anchor the prompt to a real existing file in this workspace.** Always
   reference something Gemini can imitate. Example:
   *"Write a thermal collector for Chana BMC. Follow the same patterns as
   `libraries/vindaloo/thermal_collector.py`."*
2. **Paste the relevant section of this style guide** when asking for new
   files. Sections 4 (layout), 5 (naming), 6 (CSV schema), 7 (phases), and 9
   (Robot conventions) are the ones Gemini most often gets wrong.
3. **Ask for small, reviewable changes.** Single-file, single-purpose. Gemini
   drifts on large asks.
4. **Quote failing error messages verbatim** when asking for fixes. Do not
   summarize them.
5. **Never accept code that imports modules you didn't ask for.** If Gemini
   pulls in a new dependency, push back; it usually means the existing
   abstractions weren't visible to it. Re-prompt with the right context.

### Rules for the generated code

- It must follow every rule in this style guide. The fact that an AI wrote it
  is not an exception.
- It must be formatted with `ruff format` before commit.
- It must not introduce new shared abstractions. If it does, those belong in a
  separate PR to `_shared/` or CAF after team discussion.
- It must not redefine helpers that already exist in `common.py` or CAF. Search
  before accepting.

### Tip: a starter prompt template

```
Working in: <project>/<category>/
Goal: <one-sentence task>
Existing patterns to follow: <list 1-3 file paths>
Constraints:
- Long-format CSV via UnifiedCsvLogger (schema in STYLE_GUIDE section 6).
- Library path: libraries/<component>/<testcase>.py.
- Robot test must carry category:, component:, scope:, phase: tags.
- Build-phase-specific values come from config/phases/<phase>.yaml, not code.
Output: <Python file | Robot file | both>
```

---

## 12. Code review and PR conventions

### Reviewer assignment

- **Workspace PRs** — reviewed by the workspace owner (recorded in `README.md`).
- **`_shared/` PRs** — reviewed by the project test lead.
- **CAF PRs** — go through the framework team's normal CAF review process.
- **Cross-workspace PRs** — additionally require review from an owner of a
  *different* workspace. This is what builds "team awareness of each other's
  work."

### PR checklist (paste into every PR description)

The checklist is the 5 HARD rules. Reviewer must check all of them; they
take ~30 seconds combined. SOFT items are not on this list — comment if
helpful, don't block.

```markdown
- [ ] Data collection uses `UnifiedCsvLogger` / 10-column long-format CSV
      (no private writers, no wide CSV).
- [ ] No duplicated shared helpers (imports from CAF / `_shared/`, not
      local copies).
- [ ] New code lives under `projects/<project>/<category>/` in the right
      subfolder for its type.
- [ ] New Robot test cases carry `category:`, `component:`, `scope:`, and
      `phase:` tags.
- [ ] No hardcoded IPs / credentials / thresholds / sensor lists in
      committed `.py` or `.robot` files.
```

Auto-formatters (`ruff format`, `robotidy`) are expected to be set up on
save in everyone's IDE — see `.vscode/settings.json` in the repo root. They
are not on the PR checklist because they should be automatic.

### Commit messages

`<workspace-or-area>: <what>` — present tense, lowercase, ≤72 chars first line.
Body explains *why* if non-obvious.

Examples:
- `corgi/thermal: add chana BMC collector for STV`
- `corgi/_shared: fix slot ordering for trays 09-16`
- `CAF/common: promote UnifiedCsvLogger from corgi/thermal`

---

## 13. The 4-question rule for new tests

Before writing a single line for a new test case, answer these four questions:

1. **What test category does this belong to?**
   → picks workspace (`projects/<project>/<category>/`).
2. **Which component(s) does the test touch?**
   → picks subfolder (`libraries/<component>/` or `libraries/rack/` for
   multi-component).
3. **What is the scope of one run?**
   → picks robot folder (`robot_tests/tray/`, `subrack/`, or `rack/`) and
   the `scope:` tag.
4. **Which build phases is this test valid for?**
   → drives the `phase:` tags and which `config/phases/<phase>.yaml` files
   need to provide its inputs.

If you cannot answer question 1, the test does not belong in an existing
workspace. Either it fits a category you haven't created yet (rare, talk to the
project lead), or you have not understood the test's intent yet. Do not invent
a new workspace per test.

### Worked example: an STV test

> "We need to validate that Katsu can boot the Vindaloo ASIC via CDFP and that
> the boot sequence completes within 30 s."

1. Category? Functional integration → **sit**.
2. Components? Katsu drives, Vindaloo responds → **multi-component** →
   `libraries/rack/`.
3. Scope? One Katsu + one Vindaloo, smaller than full rack → **subrack** (or
   tray if it's literally one slot).
4. Phases? Only meaningful on STV+ → tags `phase:stv phase:evt phase:dvt phase:pvt`.

Result:
- New library: `projects/corgi/sit/libraries/rack/katsu_asic_boot.py`
- New robot: `projects/corgi/sit/robot_tests/subrack/katsu_asic_boot.robot`
- Tags: `category:sit component:multi scope:subrack phase:stv phase:evt phase:dvt phase:pvt`
- Add `katsu.boot_timeout_s: 30` to `config/sit_config.yaml`.

Zero ambiguity. Anyone on the team would land in the same place.

---

## 14. Promotion: when does code move into CAF?

CAF is the framework. Things in CAF are stable, generic, and reviewed by the
framework team. Promote sparingly and only when the case is clear.

### Promotion triggers (any one is enough)

- A helper that exists in two workspaces and is about to be copy-pasted into a
  third.
- A pattern that has been used unchanged in one workspace for ≥3 months and a
  second project is about to need it.
- A driver for a hardware family (Vindaloo, Chana, Katsu) once the interface
  has been stable for ≥1 month.

### Promotion non-triggers

- "It feels generic."
- "It would be nice to have everywhere." (It's not yet needed everywhere.)
- "I'm writing it from scratch and I think other projects will want it."
  Write it in the workspace first, prove it works, then promote.

### Promotion process

1. Open a PR to CAF moving the file under `platforms/common/` (or
   `platforms/whitebox/<component>/`).
2. Scrub project-specific docstrings and examples — the CAF version must read
   as generic.
3. Mark the workspace's local copy as a thin re-export for one cycle, so
   downstream imports continue to work:
   `from common.data_logging import UnifiedCsvLogger  # re-exported`
4. After one CAP release, delete the local re-export and update workspace
   imports to point directly at CAF.

### Demotion is allowed

If a file in CAF turns out to be used by only one workspace, demote it back to
that workspace. CAF should only carry weight that earns its place.

---

## Appendix: Glossary

| Term | Meaning |
|---|---|
| **CAF** | Common Automation Framework. Shipped as a submodule of CAP. Project-agnostic. |
| **CAP** | The desktop UI that opens workspaces and runs Robot tests. |
| **Project** | A customer rack / system (e.g. Corgi). One folder under `projects/`. |
| **Category** | A discipline of testing (si, thermal, power, sit, reliability, manufacturing). Defines the CAP workspace boundary. |
| **Workspace** | What CAP opens. One (project, category) pair. |
| **Component** | A hardware family within a project (e.g. Vindaloo, Chana, Katsu). |
| **Scope** | Granularity of one test run: `tray`, `subrack`, `rack`. |
| **Phase** | NPI build stage: TTV, ITV, STV, EVT, DVT, PVT, MP. |
| **Backend** | Concrete implementation of a driver interface, selected by config (e.g. `RpiAsicBackend` vs `KatsuAsicBackend`). |
| **Long-format CSV** | Tidy CSV with one row per (timestamp, device, metric, value) tuple. The schema in section 6. |
| **Promotion** | Moving a helper from a workspace or `_shared/` into CAF. |

---

*This document is itself code. Propose changes via PR; do not let it drift.*
