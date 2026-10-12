# Circuit Atlas: understand it, demonstrate it, defend it

Prepared for your upcoming presentation. Read the explanation first, then rehearse the five-minute script aloud. The examples and implementation claims below were checked against the local code and exported results.

## The sentence to remember

“My project reads a gate-level Verilog netlist and a matching Liberty library, builds a validated graph of pin dependencies, and identifies one longest logic path. It handles simple register boundaries and reports invalid combinational loops. OpenTimer motivated the connection to graph-based analysis; this version measures gate depth, not timing delay.”

You do not need to memorize every implementation detail. You should be able to explain the two inputs, one AND gate, the register boundary, the orange path, and the difference between depth and delay.

## 1. Start with the physical idea

A digital circuit contains gates connected by wires. Gates process binary values, 0 and 1. An AND gate outputs 1 only when both inputs are 1. An inverter flips 0 to 1 or 1 to 0. An OR gate outputs 1 when at least one input is 1. A multiplexer, or MUX, selects one of its data inputs according to a selection input. A flip-flop stores one bit and updates at its specified clock edge.

A **cell type** is a reusable part definition, such as AND2. A **cell instance** is one particular copy in a circuit, such as gate_and. A **pin** is a connection point on that copy, such as gate_and/A. A **net** is the electrical connection joining a driver to one or more loads. A driver provides a value; a load receives it.

The project analyzes connectivity and dependencies. It does not simulate a sequence of 0s and 1s or generate waveforms.

## 2. Why there are two files

**Liberty (.lib): the parts catalog.** It defines cell types, pin directions, output functions, and supported sequential behavior. Real libraries can also contain physical timing information. Our tiny demonstration library has no physical delay tables.

**Verilog netlist (.v): the wiring description.** It names the actual copies and connects their pins to signals.

For example, the Verilog says:

```verilog
AND2 gate_and(.A(a), .B(b), .Y(both));
```

Read it aloud as: “Place one AND2 cell called gate_and. Connect its A input to signal a, its B input to b, and its Y output to both.” The library tells the analyzer that A and B are inputs, Y is an output, and Y depends on A and B.

The names do not determine functionality. A strangely named cell with the same supported Liberty function can still be understood. A familiar-looking name with missing semantics is not automatically accepted.

**Gate-level** describes the circuit using gates or library cells. **Flat** means there are no nested design modules left to expand. These are separate properties. This project's main demo is flat gate-level Verilog; the frontend also flattens supported structural user hierarchy. Behavioral Verilog using processes or operations that require synthesis is outside the analyzer's direct input scope.

## 3. What a DAG actually means

A graph is a collection of nodes and edges. An edge is a connection between nodes.

- Directed: each arrow has a direction.
- Acyclic: following arrows cannot bring you back to your starting point.
- Graph: the nodes and arrows together.

Our nodes are individual cell pins, top-level port bits, and constants. They are not just whole gates, and they are not the wires themselves.

There are two main kinds of edges:

```text
a ──wire──> gate_and/A ──cell dependency──> gate_and/Y
b ──wire──> gate_and/B ──cell dependency──> gate_and/Y
```

A wire edge connects a driver to a load. A cell edge connects an input to an output that references it in its Liberty Boolean function. A MUX output therefore has structural dependencies on both data inputs and the select input, even though a particular select value chooses only one data input.

**Why pin-level detail matters:** a cell may have two independent outputs. If Y depends only on A and Z only on B, we preserve those relationships separately. Treating the whole cell as one node can suggest a dependency or apparent cycle that does not exist at pin level. There is a test for this case in the project.

The dependencies are conservative, based on variables referenced in the function. They do not prove that every drawn path can carry a transition under a consistent set of input values.

## 4. What each software component does

| Component | Responsibility | What you can say |
|---|---|---|
| liberty-parser + our adapter | Read library definitions and interpret the supported semantics | “This tells us what each part means.” |
| Yosys + our frontend | Resolve Verilog names, ports, connections and supported hierarchy | “This resolves the wiring accurately.” |
| Our Python graph logic + NetworkX | Construct edges, validate connections, detect cycles, order nodes, compute depth and reconstruct the path | “This performs the analysis.” |
| Graphviz | Lay out and draw the graph | “This makes the result visible.” |
| Browser viewer | Show exported examples and inspect pins/paths; recheck graph depth | “This makes the result easy to explore.” |

The analyzer generates black-box cell interface definitions from the library for Yosys. These describe cell ports; our library adapter supplies the cell semantics for graph construction. The normal analysis flow does not synthesize or optimize away gate instances.

The offline HTML already contains results produced by the analyzer. Switching examples does not rerun Python or Yosys. Recheck graph independently checks the exported graph in JavaScript. Parsing a new pair of files needs the separate CLI.

## 5. Why a register changes the graph boundary

A flip-flop has a data input D, a clock input CLK, and an output Q. Q holds the stored value; D supplies the value to capture at the next active clock edge.

```text
Q: stored value ──> logic gates ──> D: next value
```

This feedback is normal. The new D value does not immediately pass through the flip-flop and become Q. Our combinational graph starts at Q and stops at D. It has no combinational D-to-Q edge.

The clock connection is retained separately as control information. It is not an ordinary data-path edge. The project does not calculate clock-to-Q delay, setup/hold checks, or clock skew.

Compare a pair of inverters feeding each other with no register. Following their dependency arrows returns to the same input pin. We report that cycle and withhold longest-path results. We do not silently delete an edge to make a successful DAG.

## 6. How the orange path is calculated

**Topological order** means processing every node after all the nodes that directly feed it. Think of completing prerequisite steps before a dependent step.

For each node, the code records the largest number of gate stages encountered on a route to that node:

```text
depth(v) = maximum of [depth(u) + edge_weight(u,v)] over incoming u

wire edge weight = 0
cell dependency edge weight = 1
source depth = 0
```

Zero here means “does not add a gate stage.” It does not claim that a physical wire has zero delay.

At a merge, keep the larger incoming stage count. Remember the predecessor responsible for that result. Once all nodes are processed, select a deepest endpoint and walk those remembered predecessors backward, then reverse that list to display a complete path. Equal-depth choices use stable node IDs, so results are repeatable.

Here is the actual demo route:

| Position | Added stages | Total |
|---|---:|---:|
| Input a | 0 | 0 |
| Wire to gate_and/A | 0 | 0 |
| AND2 input to output | 1 | 1 |
| Wire to gate_or/A | 0 | 1 |
| OR2 input to output | 1 | 2 |
| Wire to gate_mux/A | 0 | 2 |
| MUX2 input to output | 1 | 3 |
| Wire to state/D | 0 | 3 |

That is **8 nodes, 7 edges, but only 3 gate stages**. The register does not add another combinational stage.

One subtle point for technical questions: our reported logic level is a weighted stage count. Wire-connected nodes can have the same level. Therefore equal displayed levels do not guarantee independent tasks that can run in parallel. The topological order still respects those zero-weight wire dependencies.

## 7. Evidence you can show

| Example | Cells | Registers | Nodes | Data edges | Depth | Result |
|---|---:|---:|---:|---:|---:|---|
| Registered feedback | 6 | 1 | 24 | 23 | 3 | Valid |
| Combinational branches | 3 | 0 | 13 | 13 | 2 | Valid |
| Intentional inverter loop | 2 | 0 | 5 | 5 | Undefined | Invalid |

The previous full test run passed **54 tests**. These check expected edges, register boundaries, loops, buses, hierarchy, diagnostics, deterministic exports, and longest-path behavior. Test coverage supports these claims; it does not prove every possible input will work.

A public Nangate45 library was also used with a counter netlist synthesized by us: 11 cells, 4 registers, 47 nodes, 44 data edges, depth 2. The library parsed as 135 cells; that does not mean all 135 cell types are supported by the semantic model. An independently supplied project netlist has not yet been validated.

## 8. The OpenTimer connection, with exact attribution

Use the original reference: **Tsung-Wei Huang and Martin D. F. Wong, “OpenTimer: A High-Performance Timing Analysis Tool,” ICCAD 2015, pp. 895–902.**

The paper discusses pin-based graphs, topological levelization, timing propagation, incremental updates, parallel scheduling, and common path pessimism removal. Section IV-B covers levelization; IV-C3 relates arrival-time propagation to paths in a DAG; II and IV-E discuss updating affected regions. [Original paper](https://tsung-wei-huang.github.io/papers/10A_3.pdf).

Our connection is conceptual: use a valid dependency order to propagate a quantity and trace a route. Our quantity is a count of gate stages. We have not integrated OpenTimer or implemented its timing engine. These graph algorithms are established methods, not new algorithms invented by this project.

Three presentation points you can add:

1. **Already implemented:** “I extended graph construction with weighted logic-depth propagation and a reproducible longest-path explanation.”
2. **Already implemented:** “The result preserves pins and register boundaries, so I can explain why a path exists and why sequential feedback is valid.”
3. **Future extension:** “A bounded fan-in/fan-out view already exists in the CLI. A next step would be tracking changed regions and updating affected results instead of rebuilding the entire graph.” A cone view alone is not incremental analysis. Changed topology, loads and timing constraints would require additional invalidation rules in a real timing engine.

For a question about newer work: **OpenTimer v2** introduced a task-based approach and builder/action/accessor architecture. A task graph schedules computations; our circuit graph represents signal dependencies. They are different graph roles. These details belong to the later v2 work, not a claim about our implementation. [2021 v2 paper](https://tsung-wei-huang.github.io/papers/tcad21-ot2.pdf).

## 9. Understand enough timing to answer questions

Static timing analysis checks timing using circuit structure, delay models, and constraints rather than requiring a time-domain waveform simulation for every input pattern. It does not prove the circuit's full functional correctness.

For a simplified maximum-delay/setup analysis:

```text
arrival(v) = max(arrival(u) + delay(u,v))
setup slack = required arrival time - actual arrival time
```

Arrival time: when data reaches a point. Required time: the deadline at that point. Positive setup slack means margin; negative setup slack means the data is late under that model. Hold checks use earliest arrivals and a different comparison, so do not present this setup formula as universal for all timing checks.

Illustration only, not a tool result: a deadline of 5 ns and arrival of 4 ns gives +1 ns setup slack. Arrival of 6 ns gives -1 ns. Real register timing additionally needs launch/capture clock behavior, clock-to-Q and setup/hold information.

Why depth cannot substitute for timing: suppose route A has 3 gates taking 10 ps each, while route B has 2 gates taking 30 ps each. A has greater depth (3 versus 2), but B is slower (60 ps versus 30 ps). These invented numbers explain the distinction; they are not measurements from our library. Different endpoint deadlines also affect which path has worst slack.

OpenTimer's documented flow includes libraries, netlists, constraints and optional parasitic input, and reports timing paths and slack. Our version has no SDC interpretation, SPEF delay evaluation, arrival/required times, or slack computation. [Official OpenTimer documentation](https://github.com/OpenTimer/OpenTimer).

For paper vocabulary if asked:

- **Incremental:** update affected results after a change instead of recomputing everything.
- **Parallel:** execute independent work concurrently. This project does not implement parallel graph analysis.
- **Block/graph-based timing:** combine timing information at graph points.
- **Path-based timing:** evaluate path-specific timing information. Merely displaying a path is not path-based STA.
- **CPPR:** remove overly pessimistic treatment of shared clock-path segments. Our analyzer does not implement it. See the original paper's discussion of CPPR.
- **Slew:** how quickly a signal changes voltage. **Load:** what an output must drive. Both affect real cell delay; stage counts ignore them.

## 10. A five-minute talk you can rehearse

**0:00–0:40 — Problem.** “A gate-level netlist is difficult to inspect by reading text. I wanted to turn the cell definitions and connections into a graph that can be validated and explained.” Show the homepage.

**0:40–1:20 — Inputs and architecture.** “The Liberty file defines what each cell does. The Verilog file says where those cells are used and how they connect. Yosys resolves structural connectivity, Python builds and checks the graph, and Graphviz produces the diagram.” Click the architecture stages.

**1:20–2:15 — Concrete demo.** Open Registered feedback. “This example contains six cells and one register. Nodes represent pins and ports, so it has 24 nodes rather than six.” Select gate_and/A, then gate_and/Y. Explain the AND function and the two edge types.

**2:15–3:00 — Added analysis.** Click Step through path. “The highlighted path crosses AND, OR and MUX cells before reaching the register's D input. That is three gate stages. Wires add zero to the stage count. This explains a structural bottleneck candidate; it does not measure a timing violation.”

**3:00–3:40 — Show a failure deliberately.** Choose Intentional loop. “A cycle is rejected and no longest path is reported. The tool preserves the offending connections so the issue can be diagnosed.” Return to Registered feedback and explain Q versus D.

**3:40–4:25 — Research connection.** “OpenTimer showed the importance of dependency-ordered propagation on circuit graphs. I applied that idea at a smaller scope: a weighted longest logic path. Physical timing, incremental updates and parallel scheduling are separate extensions.”

**4:25–5:00 — Evidence and scope.** “The current version passed 54 tests, including invalid cases. A public Nangate library and our mapped counter were checked. This is a working structural-analysis prototype; further independent netlist validation is the next practical step.”

Use “I” for decisions and work you can personally explain and stand behind. If asked about AI, say: “AI assisted implementation. The analysis itself is deterministic. I can show the model, code, tests, and boundaries of the results.” Do not claim to have independently authored or verified work you did not.

## 11. Questions to expect

| Question | Answer to practice |
|---|---|
| What did you add beyond a drawing? | Connection validation, explicit register boundaries, cycle diagnostics, logic levels, and a traceable longest path. |
| Why use Yosys instead of writing a Verilog parser? | Structural elaboration involves widths, ports and hierarchy. Reusing a frontend let this project focus on semantic graph construction and analysis. |
| Did you write NetworkX or Graphviz? | No. NetworkX supplies graph primitives; Graphviz draws the result. Our code connects library semantics, netlist connectivity, diagnostics and path reporting. |
| Do you infer gate behavior from its name? | No. We interpret the supported Liberty function and sequential metadata. |
| Why is a wire weight zero? | Because we count gate stages. It is not a statement about electrical delay. |
| Is the orange route the critical timing path? | No. It is one longest logic path. Timing criticality needs delays and constraints. |
| Do you simulate values? | No. We analyze structural dependencies and stage counts. |
| How do you detect a loop? | NetworkX identifies strongly connected components; the tool reports a representative cycle, including a self-loop if present. |
| Why allow feedback at all? | A flip-flop separates the stored value Q from next-state input D. There is no combinational D-to-Q edge. |
| Does a valid DAG mean the design is correct? | It means the supported model passed structural checks. It does not prove intended function or timing. |
| Can you parse any Verilog or Liberty? | No. The target is structural gate-level Verilog and matching supported library cells. Unsupported constructs are rejected. |
| What is unsupported? | Behavioral synthesis, latches, async reset/set, scan/enable or complex sequential cells, memories, tri-state/inout, and library bus/bundle pins. |
| Why does a MUX have edges from both inputs? | Either input can influence the output depending on select. This is conservative structural dependence, not a particular simulated select value. |
| How expensive is longest-path analysis? | Given a topological order, the recurrence visits nodes and edges in O(V+E). The implementation's deterministic lexicographical ordering adds ordering overhead; this is not an end-to-end runtime guarantee. V means nodes, E means edges. |
| Could multiple paths tie? | Yes. We report one, choosing deterministically. We do not claim it is unique. |
| Have you validated against OpenTimer? | No. OpenTimer is a research reference. There is no timing-result comparison because this project does not compute timing. |
| Have you used external inputs? | A public Nangate library, with a counter netlist synthesized by us. An independently supplied project netlist remains unvalidated. |
| Is the browser rerunning the parser? | No. It explores actual saved exports and can recheck graph properties. New parsing runs through the CLI. |
| What would you do next? | Validate an independently supplied flat netlist and matching library. Then consider a clearly labeled timing-model prototype or integrating a real STA engine. |

If you do not know an answer: “That case is outside what I have validated. Here is what the current implementation does, and here is how I would test that extension.”

## 12. Tonight's rehearsal

1. Extract the ZIP and open Circuit-Atlas.html in your regular desktop browser. The in-app browser blocks file URLs, so local launch still needs this manual check.
2. Explain the AND2 line without reading notes.
3. Follow the orange path and explain why 7 edges mean 3 gate stages.
4. Explain Q, D, and the intentionally invalid inverter loop.
5. Practice the OpenTimer connection and the depth-versus-delay example.
6. Rehearse the five-minute script once with a timer, then answer the table's questions aloud.

If time is short, prioritize those steps over adding new untested functionality.
