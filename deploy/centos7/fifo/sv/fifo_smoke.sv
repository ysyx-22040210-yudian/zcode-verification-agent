module fifo_smoke;
  bit clk = 0;
  bit rst_n = 0;
  bit wr_req = 0;
  bit rd_req = 0;
  bit [7:0] wr_data = 0;
  wire [7:0] rd_data;
  wire full, empty;
  wire [2:0] count;
  string wave_path;
  always #5 clk = ~clk;
  fifo dut(.*);

  initial begin
    if ($value$plusargs("VERIFY_WAVE=%s", wave_path)) begin
      $dumpfile(wave_path);
      $dumpvars(0, fifo_smoke);
    end
    repeat (2) @(negedge clk);
    rst_n = 1;
    wr_req = 1;
    wr_data = 8'h2a;
    @(posedge clk);
    #1;
    if (empty || full || count !== 3'd1 || rd_data !== 8'h2a)
      $fatal(1, "PUSH: expected one word 0x2a, count=%0d read=0x%0h", count, rd_data);
    @(negedge clk);
    wr_req = 0;
    rd_req = 1;
    @(posedge clk);
    #1;
    if (!empty || count !== 3'd0) $fatal(1, "POP: expected empty, count=%0d", count);
    $display("VERIFY_RESULT PASS checked=2");
    $finish;
  end
endmodule
