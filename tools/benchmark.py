"""Measure a generated buffer chain; invoke separately for each size."""
import argparse
import json
import resource
import sys
from pathlib import Path

from netlist_dag.cli import main


def benchmark(count):
    root = Path(__file__).resolve().parents[1]
    folder = root / "results/benchmark" / str(count)
    folder.mkdir(parents=True, exist_ok=True)
    circuit = folder / "chain.v"
    lines = ["module chain(input a,output y);", f"wire [{count}:0] n;", "assign n[0]=a;", f"assign y=n[{count}];"]
    lines.extend(f"BUF u{i}(.A(n[{i}]),.Y(n[{i+1}]));" for i in range(count))
    lines.append("endmodule")
    circuit.write_text("\n".join(lines))
    status = main(["build", "--lib", str(root / "examples/tiny.lib"), "--netlist", str(circuit),
                   "--out", str(folder / "output"), "--no-render"])
    summary = json.loads((folder / "output/summary.json").read_text())
    assert status == 0 and summary["instances"] == count
    assert summary["logic_depth"] == count and summary["edges"] == 2 * count + 1
    manifest = json.loads((folder / "output/manifest.json").read_text())
    measurement = {"cells": count, "nodes": summary["nodes"], "edges": summary["edges"],
                   "elapsed_seconds": manifest["elapsed_seconds"], "timings_seconds": manifest["timings_seconds"],
                   "python_peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 ** 2 if sys.platform == "darwin" else 1024)}
    (folder / "measurement.json").write_text(json.dumps(measurement, indent=2) + "\n")
    print(json.dumps(measurement, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cells", type=int, default=10000)
    args = parser.parse_args()
    if args.cells < 1:
        parser.error("--cells must be positive")
    benchmark(args.cells)
