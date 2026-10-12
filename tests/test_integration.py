import json
from pathlib import Path

import pytest

from netlist_dag.cli import main
from netlist_dag.frontend import elaborate
from netlist_dag.graph import build_graph
from netlist_dag.library import read_libraries
from netlist_dag.errors import BuildError

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "examples/tiny.lib"


@pytest.fixture(scope="module")
def cells():
    return read_libraries([LIB])


def analyze(tmp_path, cells, verilog, top="top"):
    path = tmp_path / "input.v"
    path.write_text(verilog)
    module, selected, _, _ = elaborate([path], cells, top)
    return build_graph(module, cells, selected)


def edges_by_label(graph):
    labels = {n["id"]: n["label"] for n in graph["nodes"]}
    return {(labels[e["source"]], labels[e["target"]]) for e in graph["edges"]}


def test_exact_graph(tmp_path, cells):
    graph, summary, diagnostics = analyze(tmp_path, cells, '''module top(input a,b, output y);
    wire n; AND2 u1(.A(a),.B(b),.Y(n)); INV u2(.A(n),.Y(y)); endmodule''')
    assert not diagnostics
    assert edges_by_label(graph) == {("a", "u1/A"), ("b", "u1/B"), ("u1/A", "u1/Y"),
                                     ("u1/B", "u1/Y"), ("u1/Y", "u2/A"), ("u2/A", "u2/Y"), ("u2/Y", "y")}
    assert summary["logic_depth"] == 2
    ranks = {n: i for i, n in enumerate(graph["topological_order"])}
    assert all(ranks[e["source"]] < ranks[e["target"]] for e in graph["edges"])


def test_registered_feedback(tmp_path, cells):
    graph, summary, diagnostics = analyze(tmp_path, cells, '''module top(input clk, output q);
    wire d; INV u(.A(q),.Y(d)); DFF state(.D(d),.CLK(clk),.Q(q)); endmodule''')
    assert summary["valid_dag"]
    assert summary["registers"] == 1
    assert summary["logic_depth"] == 1
    assert ("state/D", "state/Q") not in edges_by_label(graph)
    assert len(graph["control_connections"]) == 1


@pytest.mark.parametrize("body", [
    "INV u(.A(y),.Y(y));",
    "wire n; INV u(.A(y),.Y(n)); INV v(.A(n),.Y(y));",
])
def test_loops(tmp_path, cells, body):
    graph, summary, diagnostics = analyze(tmp_path, cells, f"module top(output y); {body} endmodule")
    assert not summary["valid_dag"]
    assert summary["loops"] == 1
    assert any(d.code == "COMBINATIONAL_LOOP" for d in diagnostics)
    assert graph["cycles"][0]["path"][0] == graph["cycles"][0]["path"][-1]
    assert graph["topological_order"] == []


def test_multioutput_false_gate_cycle(tmp_path, cells):
    # Instance u feeds v, and v feeds u, but the individual pin paths are acyclic.
    graph, summary, _ = analyze(tmp_path, cells, '''module top(input a,b,output y,z);
    wire n,m; DUALBUF u(.A(a),.B(m),.Y(n),.Z(z)); DUALBUF v(.A(n),.B(b),.Y(y),.Z(m)); endmodule''')
    assert summary["valid_dag"]
    assert summary["logic_depth"] == 2
    assert ("u/B", "u/Y") not in edges_by_label(graph)


def test_hierarchy_and_bus(tmp_path, cells):
    module, top, _, _ = elaborate([ROOT / "examples/hierarchy.v"], cells)
    graph, summary, _ = build_graph(module, cells, top)
    assert top == "hierarchy"
    assert summary["instances"] == 2
    assert summary["valid_dag"]
    assert {i["name"] for i in graph["instances"]} == {"low.inverter", "high.inverter"}
    assert ("a[0]", "low.inverter/A") in edges_by_label(graph)


def test_positional_alias_constant_and_escaped_name(tmp_path, cells):
    graph, summary, _ = analyze(tmp_path, cells, '''module top(input a,output y);
    wire alias_a; assign alias_a=a; AND2 \\odd.name (alias_a,1'b1,y); endmodule''')
    assert summary["valid_dag"]
    assert ("1'b1", "odd.name/B") in edges_by_label(graph)
    assert any(set(n["aliases"]) >= {"a", "alias_a"} for n in graph["nets"])


@pytest.mark.parametrize("body,code", [
    ("wire n; INV u(.A(n),.Y(y));", "MISSING_DRIVER"),
    ("INV u(.A(a),.Y(y)); BUF v(.A(a),.Y(y));", "MULTIPLE_DRIVERS"),
    ("INV u(.Y(y));", "UNCONNECTED_INPUT"),
    ("INV u(.A(1'bz),.Y(y));", "UNSUPPORTED_TRISTATE"),
])
def test_connectivity_errors(tmp_path, cells, body, code):
    _, summary, diagnostics = analyze(tmp_path, cells, f"module top(input a,output y); {body} endmodule")
    assert not summary["valid_dag"]
    assert code in {d.code for d in diagnostics}


@pytest.mark.parametrize("verilog,code", [
    ("module top(input a,output y); MISSING u(.A(a),.Y(y)); endmodule", "UNKNOWN_CELL"),
    ("module top(input a,b,output y); assign y=a&b; endmodule", "UNSUPPORTED_BEHAVIORAL"),
    ("module top(input clk,d,output reg q); always @(posedge clk) q<=d; endmodule", "UNSUPPORTED_BEHAVIORAL"),
])
def test_frontend_errors(tmp_path, cells, verilog, code):
    with pytest.raises(BuildError) as error:
        analyze(tmp_path, cells, verilog)
    assert error.value.diagnostic.code == code


def test_ambiguous_top(tmp_path, cells):
    path = tmp_path / "modules.v"
    path.write_text("module a(); endmodule module b(); endmodule")
    with pytest.raises(BuildError, match="Specify --top"):
        elaborate([path], cells)


def test_cli_reproducibility_and_stale_cleanup(tmp_path):
    args = ["build", "--lib", str(LIB), "--netlist", str(ROOT / "examples/demo.v"), "--out", str(tmp_path), "--no-render"]
    assert main(args) == 0
    first = (tmp_path / "graph.json").read_bytes()
    assert main(args) == 0
    assert (tmp_path / "graph.json").read_bytes() == first
    (tmp_path / "graph.svg").write_text("old success")
    args[4] = str(tmp_path / "missing.v")
    assert main(args) == 2
    assert not (tmp_path / "graph.svg").exists()
    assert not (tmp_path / "graph.json").exists()
    assert not json.loads((tmp_path / "summary.json").read_text())["valid_dag"]


def test_cli_cone(tmp_path):
    source, target = tmp_path / "source", tmp_path / "cone"
    assert main(["build", "--lib", str(LIB), "--netlist", str(ROOT / "examples/demo.v"), "--out", str(source), "--no-render"]) == 0
    assert main(["cone", str(source / "graph.json"), "--node", "state/D", "--direction", "fanin", "--depth", "2", "--out", str(target), "--no-render"]) == 0
    graph = json.loads((target / "graph.json").read_text())
    labels = {n["label"] for n in graph["nodes"]}
    assert "state/D" in labels and "gate_mux/Y" in labels and "state/Q" not in labels


def test_width_is_not_silently_truncated(tmp_path, cells):
    with pytest.raises(BuildError) as error:
        analyze(tmp_path, cells, 'module top(input [1:0] a,output y); INV u(.A(a),.Y(y)); endmodule')
    assert error.value.diagnostic.code == "PIN_WIDTH"


def test_unknown_pin(tmp_path, cells):
    with pytest.raises(BuildError) as error:
        analyze(tmp_path, cells, 'module top(input a,output y); INV u(.BAD(a),.Y(y)); endmodule')
    assert error.value.diagnostic.code == "UNKNOWN_PIN"


def test_upward_bus_and_offset(tmp_path, cells):
    graph, summary, _ = analyze(tmp_path, cells, '''module top(input [4:5] a,output [4:5] y);
    BUF u(.A(a[4]),.Y(y[4])); BUF v(.A(a[5]),.Y(y[5])); endmodule''')
    assert summary["valid_dag"]
    assert ("a[4]", "u/A") in edges_by_label(graph)
    assert ("a[5]", "v/A") in edges_by_label(graph)


def test_multiple_files_and_parameterized_hierarchy(tmp_path, cells):
    child, parent = tmp_path / "child.v", tmp_path / "parent.v"
    child.write_text('''module child #(parameter W=2)(input [W-1:0] a,output [W-1:0] y);
    genvar i; generate for(i=0;i<W;i=i+1) begin: lane BUF u(.A(a[i]),.Y(y[i])); end endgenerate endmodule''')
    parent.write_text('module top(input [2:0] a,output [2:0] y); child #(.W(3)) u(.a(a),.y(y)); endmodule')
    module, top, _, _ = elaborate([child, parent], cells)
    _, summary, _ = build_graph(module, cells, top)
    assert summary["valid_dag"] and summary["instances"] == 3


def test_report_and_svg(tmp_path):
    assert main(["build", "--lib", str(LIB), "--netlist", str(ROOT / "examples/demo.v"), "--out", str(tmp_path)]) == 0
    assert "<svg" in (tmp_path / "graph.svg").read_text()
    assert "Valid DAG" in (tmp_path / "report.html").read_text()
    assert "u00b7" not in (tmp_path / "graph.svg").read_text()


def test_render_limit(tmp_path):
    assert main(["build", "--lib", str(LIB), "--netlist", str(ROOT / "examples/demo.v"), "--out", str(tmp_path), "--render-limit", "1"]) == 0
    assert not (tmp_path / "graph.svg").exists()
    assert (tmp_path / "graph.dot").exists()
    assert "RENDER_SKIPPED" in (tmp_path / "diagnostics.json").read_text()


def test_input_output_collision_preserves_input(tmp_path):
    path = tmp_path / "graph.json"
    path.write_text("original input")
    assert main(["cone", str(path), "--node", "x", "--out", str(tmp_path)]) == 2
    assert path.read_text() == "original input"


def test_nangate_real_library(tmp_path):
    real_library = ROOT / "third_party/nangate45/NangateOpenCellLibrary_typical.lib"
    if not real_library.exists():
        pytest.skip("Run tools/fetch_nangate.py to enable public-library compatibility test")
    cells = read_libraries([real_library])
    assert len(cells) == 135
    graph, summary, _ = analyze(tmp_path, cells, '''module top(input clk,a,output q);
    wire d,qn; XOR2_X1 gate(.A(a),.B(q),.Z(d)); DFF_X1 state(.D(d),.CK(clk),.Q(q),.QN(qn)); endmodule''')
    assert summary["valid_dag"] and summary["registers"] == 1
    assert len(graph["control_connections"]) == 1


def test_unconnected_hierarchical_input(tmp_path, cells):
    with pytest.raises(BuildError) as error:
        analyze(tmp_path, cells, '''module child(input a,output y); INV u(.A(a),.Y(y)); endmodule
        module top(output y); child c(.y(y)); endmodule''')
    assert error.value.diagnostic.code == "UNCONNECTED_INPUT"


def test_malformed_cone_input(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text('{"schema_version": 1}')
    assert main(["cone", str(path), "--node", "x", "--out", str(tmp_path / "out")]) == 2
    assert "GRAPH_SCHEMA" in (tmp_path / "out/diagnostics.json").read_text()


def test_longest_path_counts_gates_and_stops_at_registers(tmp_path, cells):
    graph, summary, _ = analyze(tmp_path, cells, '''module top(input clk,a,output q);
    wire n,d; AND2 u(.A(a),.B(q),.Y(n)); INV v(.A(n),.Y(d));
    DFF state(.D(d),.CLK(clk),.Q(q)); endmodule''')
    path = graph["longest_logic_path"]
    assert path == summary["longest_logic_path"]
    assert path["logic_depth"] == 2
    assert path["end"] == "state/D"
    assert path["start"] in ("a", "state/Q")
    assert [s["instance"] for s in path["stages"]] == ["u", "v"]
    assert len(path["nodes"]) == 6
    assert all((a, b) in edges_by_label(graph) for a, b in zip(path["labels"], path["labels"][1:]))
    from netlist_dag.export import to_dot
    assert to_dot(graph).count('penwidth=3') == 5


def test_longest_path_direct_connection_and_invalid_graph(tmp_path, cells):
    graph, _, _ = analyze(tmp_path, cells, 'module top(input a,output y); assign y=a; endmodule')
    assert graph["longest_logic_path"]["labels"] == ["a", "y"]
    assert graph["longest_logic_path"]["logic_depth"] == 0
    graph, summary, _ = analyze(tmp_path, cells, 'module top(output y); INV u(.A(y),.Y(y)); endmodule')
    assert graph["longest_logic_path"] is None
    assert summary["longest_logic_path"] is None


def test_longest_path_ties_and_partial_cone(tmp_path, cells):
    verilog = '''module top(input a,b,output y,z);
    INV first(.A(a),.Y(y)); INV second(.A(b),.Y(z)); endmodule'''
    graph, _, _ = analyze(tmp_path, cells, verilog)
    again, _, _ = analyze(tmp_path, cells, verilog)
    assert graph["longest_logic_path"] == again["longest_logic_path"]
    from netlist_dag.graph import neighborhood
    assert neighborhood(graph, graph["longest_logic_path"]["end"], "fanin", 1)["longest_logic_path"] is None
    assert neighborhood(graph, graph["longest_logic_path"]["end"], "fanin", 4)["longest_logic_path"] == graph["longest_logic_path"]
