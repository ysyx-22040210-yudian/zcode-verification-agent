`timescale 1ns/1ns
module wave_lane(input logic sample, output wire observed);
  assign observed = sample;
endmodule

module wave_demo;
  logic clk, valid, stable;
  logic [7:0] data;
  wire a, b;
  wave_lane left_lane(.sample(valid), .observed(a));
  wave_lane right_lane(.sample(clk), .observed(b));
  initial begin
    $fsdbDumpfile("demo.fsdb");
    $fsdbDumpvars(0, wave_demo, "+all");
    clk = 0; valid = 0; stable = 1; data = 8'h12;
    #3 data = 8'ha5;
    #2 clk = 1;
    #2 valid = 1;
    #2 data = 8'b10xz0011;
    #1 clk = 0;
    #2 valid = 1'bx;
    #3 clk = 1; valid = 1'bz; data = 8'h3c;
    #3 valid = 0;
    #2 clk = 0;
    #5;
    if ({clk, valid, a, b, stable, data} !== {4'b0000, 1'b1, 8'h3c})
      $fatal(1, "Unexpected final waveform state");
    $display("VERIFY_RESULT PASS checked=1");
    $finish;
  end
endmodule

