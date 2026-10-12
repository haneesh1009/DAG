module lane(input a, output y);
  INV inverter(.A(a), .Y(y));
endmodule
module hierarchy(input [1:0] a, output [1:0] y);
  lane low(.a(a[0]), .y(y[0]));
  lane high(.a(a[1]), .y(y[1]));
endmodule
