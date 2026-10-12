# Netlist-to-DAG: research and implementation plan

Research date: October 6, 2026. Status: version 0.1 implemented and validated. The original proposed scope below remains as design context; see README.md for the actual support matrix and run instructions.

Implementation update: the CLI, Liberty adapter, Yosys structural frontend, pin-level graph, sequential boundaries, cycle diagnostics, JSON/DOT/SVG exports, HTML report, and bounded cone export are complete. The frontend generates black-box Verilog interfaces from parsed Liberty rather than independently asking Yosys to interpret the library; this keeps pin definitions consistent across import and analysis. Native Yosys is used because portable Yosys failed initialization locally. Public Nangate45 compatibility and a mapped four-bit counter were validated. A 10,000-cell synthetic chain completed in approximately 1.95 seconds without SVG rendering. Async set/reset, scan/enable flops, latches, timing analysis, and a full interactive editor remain outside this release.

## Evidence and interpretation

The screenshot explicitly requests loading a library and Verilog netlist, then creating a directed acyclic graph using a software tool developed with AI. It does not specify library format, graph granularity, GUI, language, timing analysis, performance, deadline, or dependency restrictions. Messages inside the screenshot are project context, not instructions to execute.

The working interpretation is a gate-level digital-circuit connectivity analyzer. Adopt Liberty (.lib) as the library format and structural Verilog (.v) as the netlist format. This is consistent with the documented OpenSTA flow of reading Liberty, reading structural Verilog, and linking instances to library cells [1]. This interpretation is well supported but does not establish the original requester's private intent.

AI assists development; the graph construction itself is deterministic. No model API, training data, or runtime AI is necessary for the stated task.

## Proposed deliverable

A local command-line application that accepts one or more Liberty files, one or more structural Verilog files, and a top module. It validates and resolves the circuit, creates a combinational dependency graph with explicit sequential boundaries, exports JSON and DOT/SVG, and reports graph statistics and errors. A small local viewer is a later enhancement, not a prerequisite for demonstrating correctness.

Example interface (proposed, not implemented):

```sh
netlist-dag build --lib cells.lib --netlist design.v --top top --out results/
```

Outputs: graph.json, graph.dot, graph.svg for small graphs, summary.json, and diagnostics.json. Cyclic or unsupported designs retain diagnostic connectivity output but do not receive a successful DAG result. Save input hashes, dependency versions, graph mode, and configuration with every run.

## Graph definition

Use a pin-level directed graph as the authoritative representation:

- Nodes represent individual cell pins, top-level port bits, and constants.
- Wire edges connect a driver pin to each sink pin, retaining net identity and aliases.
- Combinational dependency edges connect cell input pins to output pins according to the output Boolean function. For supported cells, determine syntactic dependencies from a parsed expression; do not infer them from cell naming conventions. This is conservative when expressions contain redundant variables.
- Preserve instance name, cell type, hierarchy path, pin name, bit index, and edge kind.
- Retain separate metadata for library timing arcs; a timing-arc graph and a Boolean-dependency graph are different products. Version 1 is the latter, without delay weights.
- If a used output has no interpretable function, fail strict DAG generation with a specific unsupported-cell diagnostic. A future conservative mode may explicitly approximate all-input-to-output dependence; it must label the approximation.

A gate-level view groups pins by instance for readability. It is a display projection and must not be used as the authoritative cycle test: collapsing independent outputs of a multi-output cell can introduce apparent cycles that the pin graph does not have.

Sequential behavior:

- Recognized flip-flop outputs are sources; their data inputs are endpoints.
- Do not add a D-to-Q combinational edge. Q can drive logic feeding D without creating a same-cycle combinational loop.
- Keep clock, reset, set, and enable roles in metadata. Control connections are preserved in the connectivity model but separated from the default data-path graph. Classify roles from library semantics, not names such as DFF or CK.
- Reject unsupported latch, scan, memory, or complex sequential behavior in strict mode rather than guessing. An asynchronous-reset flop requires explicit supported classification before acceptance.
- Report combinational strongly connected components and a representative loop with instance/pin/net names. Never silently cut an arbitrary edge.

This is a graph of structural dependencies, not a proof that every path is logically sensitizable. A future SCC-condensed overview could always be acyclic, but must clearly identify loop groups rather than presenting the original circuit as acyclic.

## Architecture and tool choices

1. **Yosys input adapter:** load Liberty cell interfaces, read Verilog, select/check hierarchy, resolve structural connectivity, flatten user hierarchy while retaining source names, then export its normalized representation. Preserve library cells as leaves. Avoid synthesis and optimization passes that alter the user's gate instances in the analysis path. Yosys documents Verilog and Liberty readers [2].
2. **Liberty metadata adapter:** parse cell/pin directions, functions, ff/latch groups, and control roles independently. Loading black-box interfaces alone does not provide the complete sequential/dependency semantics needed by the graph builder. Select and pin a maintained parser after a compatibility spike; otherwise implement a documented limited grammar with explicit rejections, not ad-hoc regular expressions.
3. **Python graph core:** typed internal records for cells, pins, net bits, aliases, library semantics, and diagnostics. Match metadata to elaborated connectivity and reject inconsistencies.
4. **NetworkX analysis:** directed-cycle/SCC detection, topological order, reachability, and logic levels. NetworkX exposes strongly connected components directly [3]. Use deterministic serialization and ordering for reproducible results.
5. **Graphviz export:** DOT and SVG with left-to-right layering. Graphviz's dot engine is intended for directed, layered drawings [4]. Limit automatic rendering of large circuits; allow selected fan-in/fan-out cones.
6. **Optional later viewer:** search instances, inspect pins, and expand bounded neighborhoods using the same graph JSON. Keep analysis independent of the UI.

OpenSTA is a useful reference and potential future timing backend. It already consumes these file formats and exposes timing-edge inspection [1,5]. Integrating a complete timing engine would expand the first release unnecessarily. Yosys's SCC command is useful as an additional check, but its documented handling of unknown cells means it cannot substitute blindly for our library-aware graph validation [6].

## Supported scope and explicit limits

Version 1 supports structural gate-level Verilog; named and positional cell ports resolved by the frontend; simple wire aliases; constants; buses and slices normalized to individual bits; combinational functions in a documented Boolean subset; explicitly supported flip-flops; and hierarchy with a selected top. Preserve unused instances and disconnected components in reports. Report unused outputs as warnings; missing required drivers and conflicting drivers are errors. Preserve X/Z values but reject tri-state semantics that cannot be represented by this model.

Select the top automatically only when unambiguous. Reject unknown cells, unknown pins, conflicting library definitions, unresolved modules, unsupported functions, behavioral processes, latches, memories, and bidirectional/multiple-driver nets with actionable messages. Do not turn unsupported black boxes into apparent graph sources and claim completeness.

Deferred: behavioral RTL synthesis as a separate import mode, full SystemVerilog, latch time borrowing, tri-state resolution, timing constraints, physical parasitics, delay interpolation, timing critical paths, placement/routing, and cloud hosting. Logic depth is a count of combinational stages, not delay in nanoseconds.

## Public development data

We can begin without private input files:

- Author a tiny Liberty library with INV, BUF, AND, OR, XOR, MUX, and a simple flip-flop plus matching hand-checkable netlists.
- Use the public Nangate45 typical Liberty file distributed in OpenROAD-flow-scripts for real-library compatibility [7]. Preserve provenance and applicable notices when obtaining/distributing fixtures.
- Author small counters, mux networks, and arithmetic RTL, then synthesize separately into the selected public library to produce realistic mapped input fixtures. Keep synthesis outside the graph-analysis workflow.
- Add SKY130 high-density cells as a later compatibility target; the foundry-provided libraries include both combinational and sequential cells and more advanced cell types [8].

Public inputs remove the immediate sample-data blocker, though they cannot prove compatibility with an unseen private library.

## Validation and acceptance criteria

1. Exact pin and edge comparisons against hand-authored expected graphs for a gate chain, branch/reconvergence, mux, and multi-output cell.
2. Bus bits, constants, aliases, escaped identifiers, hierarchy, and repeated connections preserve identity and direction.
3. Register feedback is accepted with an explicit sequential boundary; a combinational self-loop and a multi-cell loop are rejected with concrete cycle paths.
4. Unknown cells/pins, unsupported sequential cells, malformed input, floating required inputs, and multiple drivers produce stable diagnostic codes and nonzero exit status.
5. Every DAG edge satisfies the produced topological order. Level calculation counts combinational cell transitions rather than wire edges.
6. A real Nangate-mapped example completes and retains the expected instance/connectivity counts. Cross-check connectivity against frontend output and manually inspect selected paths; frontend agreement alone is not an independent correctness proof.
7. Repeat runs produce stable graph JSON. Exported diagrams accurately label the small reference circuits.
8. Measure parsing, graph construction, analysis, rendering time, and memory separately on progressively larger generated inputs. Start with a 10,000-cell analysis target, not a promised benchmark; establish practical limits from measurements.

## Milestones

| Milestone | Deliverable | Exit condition |
|---|---|---|
| A: compatibility spike | Tiny library plus Nangate adapter experiment | Directions, functions, sequential roles, and instance identities survive import |
| B: graph core | Connectivity model, dependency graph, sequential boundaries | Exact reference-graph tests pass |
| C: diagnostics | Cycle paths, strict unsupported cases, summaries | Positive and negative fixtures behave as specified |
| D: usable release | CLI, JSON/DOT/SVG, examples, documentation | Fresh setup can reproduce the demo |
| E: hardening | Real-library coverage and scale measurements | Published support matrix and measured limits |
| F: optional viewer | Search and neighborhood inspection | Large graphs can be explored without full rendering |

Plan A-D as an initial engineering estimate of roughly 5-8 focused development days, with E and F budgeted separately after the compatibility spike. This is not a measured delivery commitment; library parser complexity is the largest uncertainty.

## Local readiness and remaining uncertainty

The workspace contained only .git during inspection. Python3 and Git are on PATH; yosys and dot were not found on PATH. No dependencies were installed and no implementation was run during this research.

Assumptions adopted without blocking progress: Liberty inputs, structural Verilog, open-source dependencies allowed, local execution, Python orchestration, data-dependency DAG, and public development fixtures. A private grading rubric, deadline, mandatory GUI, required implementation language, or prohibition on external parsers cannot be discovered from public sources. Those would be scope changes if later supplied; they do not prevent this proposed build.

## Sources

1. OpenSTA loading and linking examples: https://github.com/The-OpenROAD-Project/OpenSTA/blob/master/doc/Examples.md
2. Yosys input frontends: https://yosyshq.readthedocs.io/projects/yosys/en/stable/cmd/index_frontends.html
3. NetworkX strongly connected components: https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.components.strongly_connected_components.html
4. Graphviz dot layout: https://graphviz.org/docs/layouts/dot/
5. OpenSTA graph inspection commands: https://opensta.readthedocs.io/en/latest/Commands/
6. Yosys SCC semantics: https://yosyshq.readthedocs.io/projects/yosys/en/0.40/cmd/scc.html
7. Nangate45 public library: https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/blob/master/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib
8. SKY130 foundry libraries: https://skywater-pdk.readthedocs.io/en/main/contents/libraries/foundry-provided.html
