import argparse
import hashlib
import importlib.metadata
import json
import sys
import time
from pathlib import Path

from . import __version__
from .errors import BuildError, Diagnostic
from .export import render, report, write_json
from .frontend import elaborate
from .graph import build_graph, neighborhood
from .library import read_libraries

OUTPUTS = ("graph.json", "graph.dot", "graph.svg", "summary.json", "diagnostics.json", "manifest.json", "report.html", "frontend.log")


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def parser():
    root = argparse.ArgumentParser(description="Convert structural Verilog and Liberty libraries into a validated dependency DAG.")
    root.add_argument("--version", action="version", version=__version__)
    sub = root.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="Analyze a structural circuit")
    build.add_argument("--lib", action="append", required=True, type=Path, help="Liberty file; repeat for multiple libraries")
    build.add_argument("--netlist", action="append", required=True, type=Path, help="Verilog file; repeat for multiple files")
    build.add_argument("--top", help="Top module (inferred only when unique)")
    build.add_argument("--yosys", help="Yosys or yowasp-yosys executable")
    build.add_argument("--timeout", type=positive, default=120, help="Seconds per frontend invocation")
    cone = sub.add_parser("cone", help="Export a bounded pin/instance neighborhood from graph.json")
    cone.add_argument("graph", type=Path)
    cone.add_argument("--node", required=True, help="Exact pin label, node ID, or instance name")
    cone.add_argument("--direction", choices=["fanin", "fanout", "both"], default="both")
    cone.add_argument("--depth", type=positive, default=4, help="Number of graph edges to traverse")
    for command in (build, cone):
        command.add_argument("--out", type=Path, required=True)
        command.add_argument("--dot", help="Graphviz dot executable")
        command.add_argument("--render-limit", type=positive, default=400)
        command.add_argument("--no-render", action="store_true", help="Write DOT but skip SVG")
    return root


def prepare_output(out, inputs):
    resolved_inputs = {p.resolve() for p in inputs}
    for name in OUTPUTS:
        target = out / name
        if target.resolve() in resolved_inputs:
            raise BuildError("OUTPUT_COLLISION", f"Output would overwrite input {target}")
        if target.is_symlink():
            raise BuildError("OUTPUT_SYMLINK", f"Refusing to overwrite symlink {target}")
    out.mkdir(parents=True, exist_ok=True)
    for name in OUTPUTS:
        (out / name).unlink(missing_ok=True)


def main(argv=None):
    args = parser().parse_args(argv)
    started = time.perf_counter()
    diagnostics = []
    summary = {"top": getattr(args, "top", None), "valid_dag": False}
    manifest = {"tool_version": __version__, "python": sys.version.split()[0], "inputs": [], "dependencies": {}}
    output_ready = False
    try:
        inputs = args.lib + args.netlist if args.command == "build" else [args.graph]
        # Read before clearing previous results; report missing input without stale success artifacts.
        prepare_output(args.out, inputs)
        output_ready = True
        for path in inputs:
            data = path.read_bytes()
            manifest["inputs"].append({"path": str(path.resolve()), "sha256": hashlib.sha256(data).hexdigest()})
        for dependency in ("networkx", "liberty-parser", "yowasp-yosys"):
            try:
                manifest["dependencies"][dependency] = importlib.metadata.version(dependency)
            except importlib.metadata.PackageNotFoundError:
                pass
        if args.command == "build":
            tick = time.perf_counter()
            cells = read_libraries(args.lib)
            library_seconds = time.perf_counter() - tick
            tick = time.perf_counter()
            module, top, version, log = elaborate(args.netlist, cells, args.top, args.yosys, args.timeout)
            frontend_seconds = time.perf_counter() - tick
            (args.out / "frontend.log").write_text(log)
            tick = time.perf_counter()
            result, summary, diagnostics = build_graph(module, cells, top)
            manifest.update({"yosys": version, "top": top, "mode": result["mode"],
                             "timings_seconds": {"library": library_seconds, "frontend": frontend_seconds,
                                                 "graph_and_analysis": time.perf_counter() - tick}})
        else:
            original = json.loads(args.graph.read_text())
            if not isinstance(original, dict) or original.get("schema_version") != 1:
                raise BuildError("GRAPH_SCHEMA", "Expected netlist-dag graph schema version 1")
            required = {"top", "valid_dag", "acyclic", "nodes", "edges", "control_connections",
                        "instances", "nets", "cycles", "topological_order"}
            if not required <= original.keys():
                raise BuildError("GRAPH_SCHEMA", f"Missing graph fields: {sorted(required - original.keys())}")
            try:
                node_ids = {n["id"] for n in original["nodes"]}
                if len(node_ids) != len(original["nodes"]):
                    raise ValueError("duplicate node IDs")
                if any(e["source"] not in node_ids or e["target"] not in node_ids
                       for e in original["edges"] + original["control_connections"]):
                    raise ValueError("edges reference missing nodes")
            except (KeyError, TypeError, ValueError) as error:
                raise BuildError("GRAPH_SCHEMA", f"Malformed graph records: {error}") from error
            result = neighborhood(original, args.node, args.direction, args.depth)
            # A cone is a view; parent validity is retained and no whole-design statistics are claimed.
            result["view"] = {"node": args.node, "direction": args.direction, "depth": args.depth}
            selected = {n["id"] for n in result["nodes"]}
            result["topological_order"] = [n for n in result["topological_order"] if n in selected]
            result["parent_valid_dag"] = original["valid_dag"]
            result["cycles"] = [c for c in original["cycles"] if set(c["nodes"]) <= selected]
            result["instances"] = [i for i in result["instances"] if i["name"] in {n.get("instance") for n in result["nodes"]}]
            result["nets"] = [{**n, "drivers": [x for x in n["drivers"] if x in selected],
                               "sinks": [x for x in n["sinks"] if x in selected]} for n in result["nets"]
                              if selected.intersection(n["drivers"] + n["sinks"])]
            summary = {"top": original["top"] + " · cone: " + args.node, "valid_dag": original["valid_dag"],
                       "nodes": len(result["nodes"]), "edges": len(result["edges"]), "view": result["view"],
                       "longest_logic_path": result.get("longest_logic_path")}
            if not original["valid_dag"]:
                diagnostics.append(Diagnostic("INVALID_PARENT", "The source graph is not a validated DAG"))
        write_json(args.out / "graph.json", result)
        tick = time.perf_counter()
        warning = render(result, args.out, args.dot, 0 if args.no_render else args.render_limit)
        if warning and not args.no_render:
            diagnostics.append(warning)
        manifest.setdefault("timings_seconds", {})["render"] = time.perf_counter() - tick
    except BuildError as error:
        diagnostics.append(error.diagnostic)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        diagnostics.append(Diagnostic("INPUT_OUTPUT_ERROR", str(error)))
    except (KeyError, TypeError) as error:
        if args.command != "cone":
            raise
        diagnostics.append(Diagnostic("GRAPH_SCHEMA", f"Malformed graph records: {error}"))
    if not output_ready:
        for diagnostic in diagnostics:
            print(f"{diagnostic.code}: {diagnostic.message}", file=sys.stderr)
        return 2
    summary["errors"] = sum(d.severity == "error" for d in diagnostics)
    summary["warnings"] = sum(d.severity == "warning" for d in diagnostics)
    if summary["errors"]:
        summary["valid_dag"] = False
    manifest["elapsed_seconds"] = time.perf_counter() - started
    try:
        write_json(args.out / "summary.json", summary)
        write_json(args.out / "diagnostics.json", [d.to_dict() for d in diagnostics])
        write_json(args.out / "manifest.json", manifest)
        report(args.out, summary, diagnostics)
    except OSError as error:
        print(f"OUTPUT_ERROR: {error}", file=sys.stderr)
        return 2
    for diagnostic in diagnostics:
        print(f"{diagnostic.severity.upper()} {diagnostic.code}: {diagnostic.message}", file=sys.stderr)
        if "details" in diagnostic.context:
            print(diagnostic.context["details"], file=sys.stderr)
    print(f"{'VALID DAG' if summary['valid_dag'] else 'INVALID'}: {summary.get('top') or 'input'} | "
          f"{summary.get('nodes', 0)} nodes, {summary.get('edges', 0)} edges | {args.out.resolve() / 'report.html'}")
    return 0 if summary["valid_dag"] else 2
