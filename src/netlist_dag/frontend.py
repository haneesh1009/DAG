"""Structural elaboration, deliberately without synthesis/optimization."""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .errors import BuildError
from .library import write_interfaces


def executable(name, supplied=None):
    if supplied:
        found = shutil.which(supplied)
        if found:
            return found
        raise BuildError("MISSING_TOOL", f"Executable not found: {supplied}")
    candidates = [name, f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}"]
    if name == "yosys":
        candidates += [str(Path(sys.executable).parent / "yowasp-yosys"), "yowasp-yosys"]
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
    raise BuildError("MISSING_TOOL", f"Install {name} or provide its executable path")


def elaborate(paths, cells, top=None, yosys=None, timeout=120):
    binary = executable("yosys", yosys)
    try:
        version = subprocess.run([binary, "-V"], capture_output=True, text=True, timeout=timeout, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise BuildError("FRONTEND_FAILED", f"Cannot start Yosys: {error}") from error
    with tempfile.TemporaryDirectory(prefix="netlist-dag-") as directory:
        root = Path(directory)
        write_interfaces(cells, root / "library.v")
        commands = ["read_verilog -lib library.v"]
        for index, path in enumerate(paths):
            # Controlled names keep paths out of the Yosys command language.
            name = f"input_{index}.v"
            text = Path(path).read_text()
            if re.search(r"`\s*include\b", text):
                raise BuildError("UNSUPPORTED_INCLUDE", "Provide self-contained Verilog files; include directives are unsupported", path=str(path))
            (root / name).write_text(text)
            commands.append(f"read_verilog -noautowire {name}")

        def run(extra):
            (root / "build.ys").write_text("\n".join(commands + extra) + "\n")
            try:
                process = subprocess.run([binary, "-Q", "-T", "-s", "build.ys"], cwd=root,
                                         text=True, capture_output=True, timeout=timeout)
            except subprocess.TimeoutExpired as error:
                raise BuildError("FRONTEND_TIMEOUT", f"Yosys exceeded {timeout} seconds") from error
            log = process.stdout + process.stderr
            if process.returncode:
                code = "UNSUPPORTED_BEHAVIORAL" if "processes" in log else "VERILOG_PARSE"
                if "does not have a port named" in log or "has no port named" in log:
                    code = "UNKNOWN_PIN"
                raise BuildError(code, "Yosys could not elaborate the structural netlist", details=log[-16000:])
            return log

        first_log = run(["write_json initial.json"])
        modules = json.loads((root / "initial.json").read_text())["modules"]
        designs = {name: module for name, module in modules.items() if name not in cells}
        for name in cells.keys() & modules.keys():
            attributes = modules[name].get("attributes", {})
            if not int(attributes.get("blackbox", "0"), 2):
                raise BuildError("LIBRARY_COLLISION", f"Design redefines library cell {name}")
        used = {cell["type"] for mod in designs.values() for cell in mod.get("cells", {}).values()}
        if top is None:
            candidates = sorted(set(designs) - used)
            if len(candidates) != 1:
                raise BuildError("AMBIGUOUS_TOP", "Specify --top; a unique root module could not be determined", candidates=candidates)
            top = candidates[0]
        if top not in designs:
            raise BuildError("UNKNOWN_TOP", f"Top module {top!r} does not exist", candidates=sorted(designs))
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", top):
            raise BuildError("UNSUPPORTED_IDENTIFIER", "Top module must use a simple Verilog identifier")
        reachable = set()
        todo = [top]
        while todo:
            module_name = todo.pop()
            if module_name in reachable:
                continue
            reachable.add(module_name)
            module = designs[module_name]
            if module.get("memories") or module.get("processes"):
                raise BuildError("UNSUPPORTED_BEHAVIORAL", f"{module_name}: memories/processes are unsupported")
            for instance, cell in module.get("cells", {}).items():
                kind = cell["type"]
                if kind in designs:
                    todo.append(kind)
                elif kind not in cells:
                    code = "UNSUPPORTED_BEHAVIORAL" if kind.startswith("$") else "UNKNOWN_CELL"
                    raise BuildError(code, f"{module_name}/{instance}: unknown or behavioral cell {kind}")
                else:
                    # Fail before hierarchy checking can discard unsupported information.
                    cells[kind].semantics()
        second_log = run([f"hierarchy -check -keep_portwidths -top {top}", "write_json linked.json",
                          "flatten -noscopeinfo", "write_json design.json"])
        linked = json.loads((root / "linked.json").read_text())["modules"]
        for module_name, module in linked.items():
            for instance, raw in module.get("cells", {}).items():
                target = linked.get(raw["type"])
                if target is None:
                    raise BuildError("UNKNOWN_CELL", f"{module_name}/{instance}: unknown cell {raw['type']}")
                if raw["type"] not in cells:
                    for pin, port in target["ports"].items():
                        if port["direction"] == "input" and not raw["connections"].get(pin):
                            raise BuildError("UNCONNECTED_INPUT", f"{module_name}/{instance}/{pin}: hierarchical input is unconnected")
                for pin, bits in raw["connections"].items():
                    if pin not in target["ports"]:
                        raise BuildError("UNKNOWN_PIN", f"{module_name}/{instance}: unknown pin {pin}")
                    width = len(target["ports"][pin]["bits"])
                    if bits and len(bits) != width:
                        raise BuildError("PIN_WIDTH", f"{module_name}/{instance}/{pin}: expected {width} bits, found {len(bits)}")
        design = json.loads((root / "design.json").read_text())
        return design["modules"][top], top, version, first_log + second_log
