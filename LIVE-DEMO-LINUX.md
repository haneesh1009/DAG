# Transfer and run the analyzer on Linux

This package contains the actual analyzer source, demo inputs, tests, an offline viewer, and presentation notes. A new Python environment and native tools must be installed on the receiving laptop. The Mac's `.venv` and native binaries are intentionally not copied.

## 1. Transfer

Copy `Circuit-Atlas-Live-Analyzer.zip` to the Linux laptop using a USB drive, approved shared drive, or file attachment. On the laptop, save it to Downloads and extract it with the file manager. Open the extracted `Circuit-Atlas-Live-Analyzer` folder. If extraction created an extra outer folder, enter the inner folder containing `pyproject.toml`.

Open a terminal in that folder using the file manager's “Open in Terminal” action, or type `cd ` and drag the folder into the terminal, then press Enter. Run `ls`; you should see `pyproject.toml`, `src`, `examples`, `tests`, and this guide.

To transfer over SSH instead, use your actual Linux username, hostname/IP and destination with `scp`. A USB drive or shared folder is usually simpler if SSH is not already configured.

## 2. Install once, before the presentation

First identify the distribution:

```sh
cat /etc/os-release
```

For **Ubuntu/Debian**, the following commands install Python, its environment support, Yosys (Verilog frontend) and Graphviz (diagram renderer):

```sh
sudo apt update
sudo apt install python3 python3-venv python3-pip yosys graphviz
python3 --version
yosys -V
dot -V
```

For another distribution, use its package manager or ask your administrator for the same tools; do not assume `apt` is available. The project declares Python 3.9+. The existing validation used Python 3.9.6, Yosys 0.69 and Graphviz 16.1.0 on macOS, so validate the actual versions installed on this Linux laptop before presenting. Python 3.11 or 3.12 is a conservative choice for this dependency set if you have multiple interpreters installed.

From the project folder, create a local environment and install the project:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m netlist_dag --version
.venv/bin/python -m pytest -q
```

If choosing a specific Python, replace only the environment-creation command with `python3.11 -m venv .venv` or `python3.12 -m venv .venv` before installing. No environment activation is needed: each command explicitly uses `.venv/bin/python`.

Initial installation needs internet access unless your organization already supplies these dependencies. Once installed, analyzing the included files works offline. The public Nangate library is intentionally excluded, so its optional compatibility test will skip until fetched. All other required tests should pass; inspect any failure before presenting.

Official installation references: [Yosys](https://yosyshq.readthedocs.io/projects/yosys/en/stable/getting_started/installation.html) and [Graphviz](https://graphviz.org/download/). Project-specific Python packages are pinned in `pyproject.toml`.

## 3. Run your first real analysis

From the same project directory:

```sh
sh tools/run_live_demo.sh demo
```

This wrapper runs the real command:

```sh
.venv/bin/python -m netlist_dag build \
  --lib examples/tiny.lib \
  --netlist examples/demo.v \
  --out results/live-demo
```

Expected: `VALID DAG`, 24 nodes and 23 edges. The generated summary reports 6 cells, 1 register, and depth 3. The report is `results/live-demo/report.html`.

Open that report in your regular browser. If local SVG embedding does not display correctly, or you prefer a local browser address, use a second terminal in the project folder:

```sh
.venv/bin/python -m http.server 8787 --bind 127.0.0.1 --directory results
```

Then open **http://127.0.0.1:8787/live-demo/report.html** in the Linux laptop's browser. This is served only on your laptop, not the public internet. Leave that terminal running; Ctrl+C stops it. If port 8787 is already in use, choose another unused port and use that same number in the browser URL.

## 4. A reliable live demonstration

Use one terminal for analyzer commands and another for the optional local report server.

1. Show `examples/demo.v` and `examples/tiny.lib` in a text editor. Explain “wiring description” versus “parts catalog.”
2. Run `sh tools/run_live_demo.sh demo`. Show the freshly generated report, its counts, and the three-stage highlighted path.
3. Run `sh tools/run_live_demo.sh branch`. Open or refresh `http://127.0.0.1:8787/live-branch/report.html`. It has 3 cells, 13 nodes, 13 edges and depth 2.
4. Run `sh tools/run_live_demo.sh loop`. This deliberately prints `INVALID` and a `COMBINATIONAL_LOOP` diagnostic. Exit code 2 is expected, not a broken installation. Open `http://127.0.0.1:8787/live-loop/report.html` to explain the failure.
5. Return to the valid demo. Explain that the register separates Q from D, so normal registered feedback is not a combinational cycle.

Every command regenerates results from the input files. Changing between these inputs and showing valid/invalid outcomes is a genuine live analyzer demonstration. No file upload form or public website is needed.

For an optional visible edit, copy `examples/branch.v` to `examples/my_demo.v`, change a gate instance name, and rerun the analyzer using that file and a new output directory. The new name should appear while the depth stays 2. This is a simple way to demonstrate that the report comes from the input you just changed.

The report is the CLI's generated report, not the polished site's interactive explorer. The offline explorer and hosted site contain precomputed examples and do not automatically import fresh CLI output.

## 5. Analyze another netlist

Place a matching library and a flat structural gate-level netlist under a new `inputs` directory. Substitute your actual filenames and top module:

```sh
mkdir -p inputs
.venv/bin/python -m netlist_dag build \
  --lib inputs/cells.lib \
  --netlist inputs/design.v \
  --top top_module_name \
  --out results/my-design
```

You can omit `--top` only if exactly one root design module can be inferred. Cell types and pin names must match the library. Unsupported behavioral logic, latch/reset/scan/enable semantics, unknown cells and invalid connections may be rejected; see README.md. A failure report can be a correct analyzer result.

Use a dedicated output directory: the analyzer replaces its managed result files when reusing that directory. Keep source `.lib` and `.v` files outside it.

For a larger graph, full JSON and DOT are still written when SVG rendering exceeds the default 400-node limit. Use a bounded cone:

```sh
.venv/bin/python -m netlist_dag cone results/live-demo/graph.json \
  --node state/D --direction fanin --depth 4 --out results/live-cone
```

Cone depth counts graph edges, including wires; it is not the number of gate stages. A cone is a view, not a fresh whole-design validation.

## 6. What to say while it runs

“I am now running the analyzer against the actual library and netlist. It resolves the pins and wiring, validates the dependency graph, and generates this report. The orange route counts combinational gate stages. It does not report nanoseconds or timing slack.”

For the OpenTimer connection and questions, read `PRESENTATION-GUIDE.md` included in this package. It separates the implemented longest-path feature from future timing and incremental-analysis ideas.

## 7. Backup and troubleshooting

- `offline-demo/Circuit-Atlas.html`: open in a regular desktop browser for the packaged interactive presentation without installing anything. It does not parse new files.
- `No module named netlist_dag`: check that you are using `.venv/bin/python` and that editable installation completed in this folder.
- Missing Yosys: install it and check `yosys -V`; the CLI also accepts `--yosys /absolute/path/to/yosys`.
- Missing diagram: inspect `diagnostics.json`; install Graphviz and confirm `dot -V`. The CLI accepts `--dot /absolute/path/to/dot`.
- Dependency installation failure: check Python version and the first installation error; do not copy the Mac environment as a fix.
- No admin permissions on a managed laptop: ask IT to supply Python, Yosys and Graphviz, or use a machine where they are already installed. Keep the offline viewer available.
- Unknown cells: confirm the `.lib` belongs to the netlist's actual cell library.
- Live setup still unverified: rehearse on the receiving laptop before the meeting. A successful run on the originating Mac does not establish that laptop's compatibility.
