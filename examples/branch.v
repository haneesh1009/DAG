// A flat combinational netlist with reconvergent branches.
module branch(input a, b, select, output y);
  wire both, inverted;
  AND2 gate_and(.A(a), .B(b), .Y(both));
  INV gate_inv(.A(b), .Y(inverted));
  MUX2 gate_mux(.A(both), .B(inverted), .S(select), .Y(y));
endmodule
