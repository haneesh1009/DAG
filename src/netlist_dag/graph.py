import json
from collections import defaultdict

import networkx as nx

from .errors import BuildError, Diagnostic


def identifier(*parts):
    """Unambiguous IDs even when names contain slashes, brackets, or dots."""
    return json.dumps(parts, ensure_ascii=True, separators=(",", ":"))


def bit_index(port, position):
    offset = port.get("offset", 0)
    return offset + (len(port["bits"]) - 1 - position if port.get("upto", 0) else position)


def build_graph(module, cells, top):
    graph = nx.DiGraph()
    diagnostics = []
    drivers, sinks, aliases = defaultdict(list), defaultdict(list), defaultdict(list)
    controls = []
    instances = []
    semantic_cache = {}

    def report(code, message, severity="error", **context):
        diagnostics.append(Diagnostic(code, message, severity, context))

    for name, net in sorted(module.get("netnames", {}).items()):
        for position, bit in enumerate(net["bits"]):
            label = name if len(net["bits"]) == 1 and "offset" not in net else f"{name}[{bit_index(net, position)}]"
            aliases[bit].append(label)

    def connect(node_id, bit, driver):
        graph.nodes[node_id]["net_bit"] = bit
        (drivers if driver else sinks)[bit].append(node_id)

    for name, port in sorted(module.get("ports", {}).items()):
        direction = port["direction"]
        if direction not in ("input", "output"):
            report("UNSUPPORTED_INOUT", f"Top port {name} is bidirectional")
        for position, bit in enumerate(port["bits"]):
            index = bit_index(port, position)
            label = name if len(port["bits"]) == 1 and "offset" not in port else f"{name}[{index}]"
            node_id = identifier("port", name, index)
            graph.add_node(node_id, label=label, kind="port", pin=name, bit_index=index,
                           direction=direction, role="primary_input" if direction == "input" else "primary_output")
            connect(node_id, bit, direction == "input")

    for instance, raw in sorted(module.get("cells", {}).items()):
        kind = raw["type"]
        if kind not in cells:
            raise BuildError("UNKNOWN_CELL", f"{instance}: unsupported cell type {kind}")
        cell = cells[kind]
        if kind not in semantic_cache:
            semantic_cache[kind] = cell.semantics()
        roles, dependencies = semantic_cache[kind]
        instances.append({"name": instance, "cell_type": kind, "sequential": cell.ff is not None,
                          "state": cell.ff, "source": raw.get("attributes", {}).get("src"),
                          "pins": list(cell.pins)})
        connections = raw["connections"]
        unknown = set(connections) - set(cell.pins)
        if unknown:
            raise BuildError("UNKNOWN_PIN", f"{instance}: unknown pins {sorted(unknown)}")
        if raw.get("parameters"):
            raise BuildError("UNSUPPORTED_PARAMETER", f"{instance}: library cell parameters are unsupported")
        for pin in cell.pins.values():
            node_id = identifier("pin", instance, pin.name)
            graph.add_node(node_id, label=f"{instance}/{pin.name}", kind="pin", instance=instance,
                           cell_type=kind, pin=pin.name, bit_index=0, direction=pin.direction,
                           role=roles.get(pin.name, "data"), function=pin.function, timing_arcs=pin.timing)
            bits = connections.get(pin.name, [])
            if len(bits) > 1:
                raise BuildError("PIN_WIDTH", f"{instance}/{pin.name}: expected one bit, found {len(bits)}")
            if not bits:
                if pin.direction == "input":
                    report("UNCONNECTED_INPUT", f"{instance}/{pin.name} is unconnected", node=node_id)
                else:
                    report("UNUSED_OUTPUT", f"{instance}/{pin.name} is unconnected", "warning", node=node_id)
            else:
                connect(node_id, bits[0], pin.direction == "output")
        for output, inputs in dependencies.items():
            for input_pin in inputs:
                graph.add_edge(identifier("pin", instance, input_pin), identifier("pin", instance, output),
                               kind="cell", instance=instance, weight=1)

    nets = []
    for bit in sorted(set(drivers) | set(sinks) | set(aliases), key=lambda b: (isinstance(b, str), str(b))):
        if isinstance(bit, str):
            constant_id = identifier("constant", bit)
            graph.add_node(constant_id, label=f"1'b{bit}", kind="constant", role="constant", value=bit, net_bit=bit)
            drivers[bit].append(constant_id)
            if bit == "z":
                report("UNSUPPORTED_TRISTATE", "High-impedance constant Z is unsupported")
            elif bit == "x":
                report("UNKNOWN_VALUE", "Constant X is preserved as an unknown value", "warning")
        sources, targets = sorted(set(drivers[bit])), sorted(set(sinks[bit]))
        names = sorted(set(aliases[bit]))
        if len(sources) > 1:
            report("MULTIPLE_DRIVERS", f"Net {names or [bit]} has {len(sources)} drivers", drivers=sources, nets=names)
        if targets and not sources:
            report("MISSING_DRIVER", f"Net {names or [bit]} has no driver", sinks=targets, nets=names)
        if sources and not targets:
            for source in sources:
                if graph.nodes[source]["kind"] != "constant":
                    report("UNUSED_OUTPUT", f"{graph.nodes[source]['label']} has no loads", "warning", node=source)
        nets.append({"bit": bit, "aliases": names, "drivers": sources, "sinks": targets})
        for source in sources:
            for target in targets:
                attrs = {"kind": "wire", "net_bit": bit, "net_names": names, "weight": 0}
                if graph.nodes[target]["role"] == "clock":
                    controls.append({"source": source, "target": target, **attrs})
                else:
                    graph.add_edge(source, target, **attrs)

    cycles = []
    components = [sorted(c) for c in nx.strongly_connected_components(graph)
                  if len(c) > 1 or any(graph.has_edge(n, n) for n in c)]
    for component in sorted(components):
        edges = nx.find_cycle(graph.subgraph(component), source=component[0])
        path = [edges[0][0]] + [edge[1] for edge in edges]
        labels = [graph.nodes[node]["label"] for node in path]
        cycle = {"nodes": component, "path": path, "labels": labels,
                 "edges": [{"source": a, "target": b, **graph.edges[a, b]} for a, b in edges]}
        cycles.append(cycle)
        report("COMBINATIONAL_LOOP", "Combinational loop: " + " -> ".join(labels), cycle=cycle)
    valid = not any(d.severity == "error" for d in diagnostics)
    order, levels, predecessors = [], {}, {}
    longest_path = None
    if valid:
        order = list(nx.lexicographical_topological_sort(graph))
        for node in order:
            levels[node] = max((levels[p] + graph.edges[p, node]["weight"] for p in graph.predecessors(node)), default=0)
            parents = list(graph.predecessors(node))
            if parents:
                predecessors[node] = min(parents, key=lambda p: (-levels[p] - graph.edges[p, node]["weight"], p))
            graph.nodes[node]["logic_level"] = levels[node]
        # Choose a complete source-to-sink path. Ties use stable node IDs.
        endpoints = [n for n in order if graph.out_degree(n) == 0 and graph.nodes[n]["role"] != "clock"]
        if endpoints:
            end = min(endpoints, key=lambda n: (-levels[n], n))
            path = [end]
            while path[-1] in predecessors:
                path.append(predecessors[path[-1]])
            path.reverse()
            stages = [{"instance": graph.edges[a, b]["instance"],
                       "cell_type": graph.nodes[b]["cell_type"],
                       "input_pin": graph.nodes[a]["pin"], "output_pin": graph.nodes[b]["pin"]}
                      for a, b in zip(path, path[1:]) if graph.edges[a, b]["kind"] == "cell"]
            longest_path = {"nodes": path, "labels": [graph.nodes[n]["label"] for n in path],
                            "start": graph.nodes[path[0]]["label"], "end": graph.nodes[end]["label"],
                            "logic_depth": levels[end], "stages": stages}

    for node in graph:
        graph.nodes[node]["fan_in"] = graph.in_degree(node)
        graph.nodes[node]["fan_out"] = graph.out_degree(node)
    result = {
        "schema_version": 1, "top": top, "mode": "structural_boolean_dependencies",
        "valid_dag": valid, "acyclic": not cycles, "longest_logic_path": longest_path,
        "nodes": [{"id": n, **graph.nodes[n]} for n in sorted(graph)],
        "edges": [{"source": a, "target": b, **graph.edges[a, b]} for a, b in sorted(graph.edges)],
        "control_connections": sorted(controls, key=lambda e: (e["source"], e["target"])),
        "instances": instances, "nets": nets, "cycles": cycles, "topological_order": order,
    }
    summary = {"top": top, "valid_dag": valid, "acyclic": not cycles, "longest_logic_path": longest_path,
               "instances": len(instances), "registers": sum(i["sequential"] for i in instances),
               "nodes": len(graph), "edges": graph.number_of_edges(), "nets": len(nets),
               "control_connections": len(controls), "components": nx.number_weakly_connected_components(graph),
               "logic_depth": max(levels.values(), default=0) if valid else None,
               "loops": len(cycles), "errors": sum(d.severity == "error" for d in diagnostics),
               "warnings": sum(d.severity == "warning" for d in diagnostics)}
    return result, summary, diagnostics


def neighborhood(result, query, direction="both", depth=2):
    nodes = {n["id"]: n for n in result["nodes"]}
    seeds = {key for key, node in nodes.items() if query in (key, node["label"], node.get("instance"))}
    if not seeds:
        raise BuildError("UNKNOWN_NODE", f"No pin or instance exactly matches {query!r}")
    graph = nx.DiGraph()
    graph.add_nodes_from(nodes)
    graph.add_edges_from((e["source"], e["target"]) for e in result["edges"])
    selected = set(seeds)
    # Walk each direction independently; do not expand sibling cones by switching direction.
    for view in ([graph, graph.reverse(copy=False)] if direction == "both" else
                 [graph.reverse(copy=False)] if direction == "fanin" else [graph]):
        frontier = set(seeds)
        visited = set(seeds)
        for _ in range(depth):
            frontier = {v for u in frontier for v in view.successors(u)} - visited
            visited.update(frontier)
            selected.update(frontier)
            if not frontier:
                break
    path = result.get("longest_logic_path")
    return {**result, "longest_logic_path": path if path and set(path["nodes"]) <= selected else None, "nodes": [nodes[n] for n in sorted(selected)],
            "edges": [e for e in result["edges"] if e["source"] in selected and e["target"] in selected],
            "control_connections": [e for e in result["control_connections"] if e["source"] in selected and e["target"] in selected]}
