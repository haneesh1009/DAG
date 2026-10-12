// Registered feedback: q -> XOR -> MUX -> D. This is a valid data DAG.
module demo(input a, b, select, clk, output y, q);
  wire both, inverted, next_q, feedback;
  AND2 gate_and(.A(a), .B(b), .Y(both));
  INV gate_inv(.A(b), .Y(inverted));
  OR2 gate_or(.A(both), .B(inverted), .Y(y));
  XOR2 gate_xor(.A(q), .B(a), .Y(feedback));
  MUX2 gate_mux(.A(y), .B(feedback), .S(select), .Y(next_q));
  DFF state(.D(next_q), .CLK(clk), .Q(q));
endmodule
