// Input to the separate fixture-generation synthesis step, not to netlist-dag.
module counter(input clk, input enable, output reg [3:0] count);
  always @(posedge clk)
    if (enable) count <= count + 1'b1;
endmodule
