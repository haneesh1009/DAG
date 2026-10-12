// Deliberately invalid: two inverters form a combinational loop.
module loop(output y);
  wire feedback;
  INV first(.A(feedback), .Y(y));
  INV second(.A(y), .Y(feedback));
endmodule
