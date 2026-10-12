from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from liberty.parser import parse_liberty
from liberty.types import EscapedString

from .boolean import literal, parse, support
from .errors import BuildError


def value(item):
    return str(item.value) if isinstance(item, EscapedString) else str(item)


@dataclass
class Pin:
    name: str
    direction: str
    function: Optional[str]
    three_state: bool = False
    timing: List[dict] = field(default_factory=list)


@dataclass
class Cell:
    name: str
    pins: Dict[str, Pin]
    source: str
    ff: Optional[dict] = None
    unsupported: Optional[str] = None

    def semantics(self):
        if self.unsupported:
            raise BuildError("UNSUPPORTED_CELL", f"{self.name}: {self.unsupported}", cell_type=self.name)
        for pin in self.pins.values():
            if pin.direction not in ("input", "output") or pin.three_state:
                raise BuildError("UNSUPPORTED_CELL", f"{self.name}/{pin.name}: bidirectional or tri-state pins are unsupported")
        inputs = {p.name for p in self.pins.values() if p.direction == "input"}
        roles = {name: "data" for name in inputs}
        dependencies = {}
        if self.ff:
            ff = self.ff
            if set(ff["attributes"]) - {"clocked_on", "next_state"}:
                raise BuildError("UNSUPPORTED_SEQUENTIAL", f"{self.name}: only simple edge-triggered flip-flops are supported")
            try:
                clock = literal(parse(ff["attributes"]["clocked_on"]))
                data = literal(parse(ff["attributes"]["next_state"]))
            except KeyError as error:
                raise BuildError("UNSUPPORTED_SEQUENTIAL", f"{self.name}: missing clocked_on or next_state") from error
            if not clock or not data or clock == data or inputs != {clock, data}:
                raise BuildError("UNSUPPORTED_SEQUENTIAL", f"{self.name}: complex clock/data, scan, or enable semantics are unsupported")
            roles[clock] = "clock"
            roles[data] = "register_input"
        for pin in self.pins.values():
            if pin.direction != "output":
                continue
            if pin.function is None:
                raise BuildError("MISSING_FUNCTION", f"{self.name}/{pin.name}: missing output function")
            tree = parse(pin.function)
            refs = support(tree)
            if self.ff:
                if literal(tree) not in self.ff["state"]:
                    raise BuildError("UNSUPPORTED_SEQUENTIAL", f"{self.name}/{pin.name}: output is not a state literal")
                dependencies[pin.name] = []
                roles[pin.name] = "register_output"
            else:
                if not refs <= inputs:
                    raise BuildError("INVALID_FUNCTION", f"{self.name}/{pin.name}: references non-input pins {sorted(refs - inputs)}")
                dependencies[pin.name] = sorted(refs)
                roles[pin.name] = "combinational_output"
        return roles, dependencies


def read_libraries(paths):
    cells = {}
    for path in paths:
        try:
            library = parse_liberty(Path(path).read_text())
            if library.group_name != "library":
                raise ValueError("expected library group")
            for group in library.get_groups("cell"):
                name = value(group.args[0])
                if name in cells:
                    raise BuildError("DUPLICATE_CELL", f"Cell {name} is defined more than once", path=str(path))
                pins = {}
                for p in group.get_groups("pin"):
                    for argument in p.args:
                        pin_name = value(argument)
                        if pin_name in pins:
                            raise BuildError("DUPLICATE_PIN", f"Duplicate pin {name}/{pin_name}")
                        function = p.get_attribute("function")
                        timing = []
                        for arc in p.get_groups("timing"):
                            timing.append({a.name: value(a.value) for a in arc.attributes
                                           if a.name in ("related_pin", "timing_type", "timing_sense", "when")})
                        pins[pin_name] = Pin(pin_name, value(p.get_attribute("direction")),
                                             value(function) if function is not None else None,
                                             p.get_attribute("three_state") is not None, timing)
                reason = None
                if any(group.get_groups(kind) for kind in ("latch", "latch_bank", "ff_bank", "statetable", "memory", "bus", "bundle", "test_cell")):
                    reason = "latches, banks, state tables, memories, library buses/bundles, and test cells are unsupported"
                ffs = group.get_groups("ff")
                ff = None
                if len(ffs) > 1:
                    reason = "multiple state elements per cell are unsupported"
                elif ffs:
                    ff = {"state": [value(a) for a in ffs[0].args],
                          "attributes": {a.name: value(a.value) for a in ffs[0].attributes}}
                cells[name] = Cell(name, pins, str(path), ff, reason)
        except BuildError:
            raise
        except Exception as error:
            raise BuildError("LIBERTY_PARSE", f"Cannot parse {path}: {error}", path=str(path)) from error
    if not cells:
        raise BuildError("EMPTY_LIBRARY", "No library cells were found")
    return cells


def verilog_identifier(name):
    if not name or any(c.isspace() for c in name) or "\\" in name:
        raise BuildError("UNSUPPORTED_IDENTIFIER", f"Unsupported library identifier: {name!r}")
    return "\\" + name + " "


def write_interfaces(cells, path):
    """Generate black boxes from the same parsed pin table used for analysis.

    This keeps library instances intact and avoids Yosys interpreting sequential
    behavior differently. Pin declaration order is preserved for positional ports.
    """
    lines = []
    for cell in cells.values():
        names = [verilog_identifier(name) for name in cell.pins]
        lines.append(f"(* blackbox *) module {verilog_identifier(cell.name)}({', '.join(names)});")
        for pin in cell.pins.values():
            direction = pin.direction if pin.direction in ("input", "output", "inout") else "inout"
            lines.append(f"  {direction} {verilog_identifier(pin.name)};")
        lines.append("endmodule")
    Path(path).write_text("\n".join(lines) + "\n")
