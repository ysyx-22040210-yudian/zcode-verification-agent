`include "uvm_macros.svh"

interface fifo_signals;
  bit clk = 0;
  bit rst_n = 0;
  bit wr_req = 0;
  bit rd_req = 0;
  bit [7:0] wr_data = 0;
  wire [7:0] rd_data;
  wire full, empty;
  wire [2:0] count;
  always #5 clk = ~clk;
endinterface

package fifo_uvm_pkg;
  import uvm_pkg::*;

  class fifo_scoreboard extends uvm_scoreboard;
    `uvm_component_utils(fifo_scoreboard)
    bit [7:0] expected[$];
    int checked;
    covergroup accepted_operations with function sample(bit pushed, bit popped);
      option.per_instance = 1;
      operation: coverpoint {pushed, popped} {
        bins idle = {2'b00};
        bins read_only = {2'b01};
        bins write_only = {2'b10};
        bins simultaneous = {2'b11};
      }
    endgroup

    function new(string name, uvm_component parent);
      super.new(name, parent);
      accepted_operations = new();
    endfunction

    function void record(bit wr, bit rd, bit [7:0] data, logic [7:0] observed);
      bit pushed, popped;
      bit [7:0] head;
      pushed = wr && expected.size() < 4;
      popped = rd && expected.size() > 0;
      if (popped) begin
        head = expected.pop_front();
        if (head !== observed)
          `uvm_error("FIFO-ORDER", $sformatf("expected head 0x%02h, observed 0x%02h", head, observed))
      end
      if (pushed) expected.push_back(data);
      accepted_operations.sample(pushed, popped);
    endfunction

    function void compare_status(logic [2:0] count, logic full, logic empty);
      int size;
      size = expected.size();
      checked++;
      if (count !== size[2:0] || full !== (size == 4) || empty !== (size == 0))
        `uvm_error("FIFO-STATUS", $sformatf("check=%0d expected occupancy=%0d actual=%0d full=%b empty=%b",
          checked, size, count, full, empty))
    endfunction
  endclass

  class fifo_test extends uvm_test;
    `uvm_component_utils(fifo_test)
    virtual fifo_signals signals;
    fifo_scoreboard scoreboard;

    function new(string name, uvm_component parent);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      if (!uvm_config_db#(virtual fifo_signals)::get(this, "", "signals", signals))
        `uvm_fatal("CONFIG", "FIFO interface missing")
      scoreboard = fifo_scoreboard::type_id::create("scoreboard", this);
    endfunction

    task step(bit wr, bit rd, bit [7:0] data);
      @(negedge signals.clk);
      signals.wr_req = wr;
      signals.rd_req = rd;
      signals.wr_data = data;
      scoreboard.record(wr, rd, data, signals.rd_data);
      @(posedge signals.clk);
      #1;
      scoreboard.compare_status(signals.count, signals.full, signals.empty);
    endtask

    task run_phase(uvm_phase phase);
      phase.raise_objection(this);
      repeat (2) @(negedge signals.clk);
      scoreboard.compare_status(signals.count, signals.full, signals.empty);
      signals.rst_n = 1;
      step(0, 0, 0);
      step(1, 0, 8'h11);
      step(1, 1, 8'h22);
      step(0, 1, 0);
      step(0, 1, 0);
      for (int n = 0; n < 5; n++) step(1, 0, 8'($urandom_range(255, 0)));
      repeat (5) step(0, 1, 0);
      $display("VERIFY_COVERAGE functional=%.2f checked=%0d",
        scoreboard.accepted_operations.get_inst_coverage(), scoreboard.checked);
      $display("VERIFY_RESULT COMPLETE checked=%0d", scoreboard.checked);
      phase.drop_objection(this);
    endtask
  endclass
endpackage

module fifo_uvm;
  import uvm_pkg::*;
  import fifo_uvm_pkg::*;
  fifo_signals signals();
  string wave_path;
  fifo #(.BUGGY_SIMULTANEOUS(
    `ifdef VERIFY_MUTANT
      1
    `else
      0
    `endif
  )) dut (
    .clk(signals.clk), .rst_n(signals.rst_n),
    .wr_req(signals.wr_req), .rd_req(signals.rd_req), .wr_data(signals.wr_data),
    .rd_data(signals.rd_data), .full(signals.full), .empty(signals.empty), .count(signals.count)
  );

  initial begin
    if ($value$plusargs("VERIFY_WAVE=%s", wave_path)) begin
      $dumpfile(wave_path);
      $dumpvars(0, fifo_uvm);
    end
    uvm_config_db#(virtual fifo_signals)::set(null, "*", "signals", signals);
    run_test();
  end
endmodule
