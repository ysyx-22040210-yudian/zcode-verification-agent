module fifo_open(input clk, input rst_n, input wr_req, input rd_req, input [7:0] wr_data);
  wire [7:0] rd_data;
  wire full, empty;
  wire [2:0] count;
  wire both = wr_req && rd_req && !full && !empty;

`ifdef VERIFY_MUTANT
  localparam MUTANT = 1'b1;
`else
  localparam MUTANT = 1'b0;
`endif
  fifo #(.BUGGY_SIMULTANEOUS(MUTANT)) dut(.*);

  reg past_valid = 0;
  always @(posedge clk) begin
    past_valid <= 1;
    // Apply reset for the initial sample, then release it as in the IFV harness.
    assume(rst_n == past_valid);
    if (rst_n) begin
      p_count_range: assert(count <= 4);
      c_simultaneous: cover(both);
    end
    if (past_valid && rst_n && $past(rst_n && both)) begin
      p_simultaneous_hold: assert(count == $past(count));
    end
  end
endmodule

