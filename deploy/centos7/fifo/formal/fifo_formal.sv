`ifdef VERIFY_MUTANT
`define FIFO_FORMAL_BUG 1
`else
`define FIFO_FORMAL_BUG 0
`endif

module fifo_formal (
  input clk,
  input rst_n,
  input wr_req,
  input rd_req,
  input [7:0] wr_data
);
  wire [7:0] rd_data;
  wire full, empty;
  wire [2:0] count;
  wire both = wr_req && rd_req && !full && !empty;

  fifo #(.BUGGY_SIMULTANEOUS(`FIFO_FORMAL_BUG)) dut(.*);

  p_simultaneous_hold: assert property (@(posedge clk) disable iff (!rst_n)
    both |=> $stable(count));
  p_count_range: assert property (@(posedge clk) disable iff (!rst_n)
    count <= 3'd4);
  c_simultaneous: cover property (@(posedge clk) disable iff (!rst_n) both);
endmodule
