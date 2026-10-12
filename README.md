# Netlist → DAG

A working local tool for converting a Liberty cell library and structural Verilog netlist into a validated, pin-level dependency graph. It preserves gate instances, separates register boundaries, reports combinational loops, and exports JSON, DOT, SVG, and a standalone HTML report.

## Start on another computer

- [Linux live-analyzer setup](LIVE-DEMO-LINUX.md): install dependencies, run fresh analysis, and present the generated report.
- [Live analyzer ZIP](output/Circuit-Atlas-Live-Analyzer.zip): source, tests, examples, setup instructions, and an offline viewer.
- [Offline demo ZIP](output/Circuit-Atlas-Demo.zip): extract and double-click the HTML file; no installation needed.
- [Presentation guide](output/PRESENTATION-GUIDE.md): beginner explanations, OpenTimer references, a demo script, and likely questions.

On GitHub, open a ZIP file and choose **Download raw file** to download the actual archive. The offline viewer explores packaged results; analyzing new Verilog requires the CLI. The hosted website source is maintained in a separate Sites repository.

## Run the demo on this machine

From this repository:

```sh
.venv/bin/netlist-dag build \
  --lib examples/tiny.lib \
  --netlist examples/demo.v \
  --out results/demo
```

Open `results/demo/report.html` in a browser. The demo has 6 cell instances, 1 register, 24 graph nodes, 23 data edges, and 3 combinational logic levels. The dashed clock connection is retained separately from the data DAG.

The local virtual environment and native Yosys/Graphviz have been installed. The tool also checks Homebrew's usual installation paths, so they need not be on the current shell PATH.

## Install elsewhere

Python 3.9+ plus native Yosys and Graphviz are recommended. Validated here with Python 3.9.6, Yosys 0.69, and Graphviz 16.1.0 on Apple Silicon macOS.

```sh
# macOS; on Linux use your distribution's yosys and graphviz packages.
brew install yosys graphviz
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -q
```

An optional `.[portable]` dependency provides `yowasp-yosys`. It is a fallback, not the validated backend on this machine: its first-run WebAssembly compilation was killed locally. Native Yosys is preferred when both are found. Use `--yosys /path/to/yosys` or `--dot /path/to/dot` to select tools explicitly.

## Analyze a circuit

```sh
.venv/bin/netlist-dag build \
  --lib cells.lib --netlist design.v --top top --out results/design
```

Repeat `--lib` or `--netlist` for multiple files. If `--top` is omitted, exactly one root design module must exist. Verilog files must be self-contained; `include` directives are rejected. The analyzer performs structural elaboration and hierarchy flattening without running synthesis or logic optimization.

The output directory contains:

| File | Contents |
|---|---|
| `graph.json` | Nodes, edges, net aliases, instances, sequential metadata, cycles, topological order |
| `graph.dot` | Full pin-level graph in Graphviz format |
| `graph.svg` | Diagram for circuits within the render limit |
| `summary.json` | Validity, counts, logic depth, errors and warnings |
| `diagnostics.json` | Stable diagnostic codes, descriptions, and context |
| `manifest.json` | Input SHA-256 hashes, tool/dependency versions, mode, phase durations |
| `frontend.log` | Successful Yosys import/elaboration log |
| `report.html` | Local report linking the outputs and displaying the SVG |

Exit code **0** means the circuit passed strict DAG validation; **2** means input, connectivity, or analysis failure. Rendering failures are warnings: JSON and DOT remain usable. Failed parsing/unsupported semantics produce diagnostic reports without a graph. Connectivity errors and combinational loops preserve the graph but set `valid_dag: false` and omit the topological order. Previous managed output files are removed when reusing an output directory, preventing stale successful results; use a dedicated output directory.

## Inspect a large graph

SVG rendering is limited to 400 nodes by default; change `--render-limit` or use `--no-render`. Full JSON and DOT are still exported. A bounded cone keeps diagrams manageable:

```sh
.venv/bin/netlist-dag cone results/demo/graph.json \
  --node state/D --direction fanin --depth 4 --out results/cone
```

Match an exact pin label, instance name, or JSON node ID. Depth counts graph edges, including wire and cell edges. `fanin`, `fanout`, and `both` are available. A cone inherits its parent graph's validity; it is a view, not an independent whole-design validation.

## What the graph means

Each top-level port bit, cell pin, and constant is a node. A wire edge connects the driver to every load. A cell edge connects each referenced input pin to its output pin, based on a parsed Liberty Boolean function. Multi-output cells retain independent dependencies. Grouping their pins visually never changes cycle detection.

Simple flip-flop Q/QN pins are sources; D pins are endpoints. There is no D-to-Q edge within one combinational evaluation. Clock connections are stored in `control_connections` and displayed dashed. Register feedback is therefore valid; a loop entirely through combinational logic is an error, with a representative pin/net path.

Logic levels increase only across cell edges. **Logic depth is not a timing delay.** Timing-arc metadata is retained but delay tables are not evaluated. Dependencies are syntactic and conservative; the tool does not prove path sensitizability or simplify Boolean expressions.

## Supported inputs

- Scalar standard-cell pins and vector Verilog nets/ports, including slices, ascending ranges, and offsets.
- Named or positional cell ports, wire aliases, 0/1/X constants, escaped instance names, hierarchy, and structural generate/parameterized user modules.
- Liberty Boolean names, 0/1, parentheses, prefix `!`/`~`, postfix `'`, AND `&`/`*`/adjacency, OR `+`/`|`, and XOR `^`.
- Simple edge-triggered flip-flops with a single clock literal, single data literal, and state-literal outputs.
- Multiple files, disconnected components, unused outputs, and multiple fan-out sinks.

Strictly rejected: unknown cells/pins, width mismatches, missing required drivers, multiple drivers, combinational loops, tri-state/Z and bidirectional signals, missing or unsupported output functions, latches, asynchronous set/reset flops, scan/enable/complex sequential cells, memories, library bus/bundle pins, user black boxes, and behavioral logic requiring synthesis. Power/ground `pg_pin` groups are outside the data graph. Duplicate cell definitions across files are errors. Unsupported library cells may exist as long as the selected design does not instantiate them.

Unconnected outputs and constant X are warnings; required unconnected inputs are errors. User hierarchy carrying `keep_hierarchy` is not supported and must be flattened or have that attribute removed before analysis.

## Real-library example

The public Nangate45 library is downloaded separately and excluded from source control. Its original header is preserved. The fetch helper verifies the SHA-256 of the file used during validation.

```sh
.venv/bin/python tools/fetch_nangate.py
mkdir -p results
# Use /opt/homebrew/bin/yosys here if yosys is not on PATH.
yosys -s examples/synthesize_counter.ys
.venv/bin/netlist-dag build \
  --lib third_party/nangate45/NangateOpenCellLibrary_typical.lib \
  --netlist results/counter_mapped.v --out results/counter
```

Synthesis is only for generating this test fixture; it is separate from the analyzer. The resulting counter has 11 cells, 4 registers, 47 graph nodes, 44 data edges, and 2 logic levels with this toolchain. Three unused QN outputs are correctly reported as warnings. The full library parses as 135 cells; this is not a claim that every cell type is supported.

## Validation and scale

```sh
.venv/bin/python -m pytest -q
.venv/bin/python tools/benchmark.py --cells 10000
```

Tests compare exact expected edges, sequential boundaries, real-library semantics, diagnostic codes, bus indexing, parameterized hierarchy, deterministic JSON, exports, and stale-output handling. The Nangate test skips when the separately downloaded library is absent. Graphviz is required for the SVG integration test.

Initial measured buffer-chain results (SVG disabled; includes JSON/DOT/report export):

| Cells | Graph nodes | Data edges | Elapsed | Python peak RSS |
|---:|---:|---:|---:|---:|
| 1,000 | 2,002 | 2,001 | 0.23 s | 89 MiB |
| 10,000 | 20,002 | 20,001 | 1.95 s | 263 MiB |

These are synthetic chain measurements on this machine, not promises for arbitrary circuits. Python peak RSS excludes the separate Yosys process. JSON and graph objects are held in memory; large fan-out and rendering-heavy designs need separate characterization.

## Code layout

`library.py` reads Liberty metadata and writes interface stubs; `boolean.py` parses output dependencies; `frontend.py` drives Yosys; `graph.py` builds and validates the graph; `export.py` generates diagrams/reports; `cli.py` coordinates input/output. The project is GPL-3.0-or-later and uses the GPL-licensed `liberty-parser`; see `THIRD_PARTY.md` for dependencies and public-library provenance.

## Longest logic path

The report now lists one longest source-to-sink logic path and highlights its pins and edges in orange. It shows the start, endpoint, ordered cell instances/types, and gate-stage count. Wire edges count as zero stages; cell dependency edges count as one. Register boundaries and excluded clock connections remain unchanged. Equal-depth choices are resolved deterministically by node ID. Unused logic outputs can be endpoints.

`graph.json` and `summary.json` include `longest_logic_path` with node IDs, labels, and stages. Invalid graphs have a null path. A cone retains the full-design path only when all its nodes are visible; partial cones do not claim a new longest path. This is structural depth, not a critical timing path or a delay estimate.
