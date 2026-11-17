module fifo #(
  parameter BUGGY_SIMULTANEOUS = 1'b0
) (
  input          clk,
  input          rst_n,
  input          wr_req,
  input          rd_req,
  input  [7:0]   wr_data,
  output [7:0]   rd_data,
  output         full,
  output         empty,
  output reg [2:0] count
);
  reg [7:0] storage [0:3];
  reg [1:0] write_pointer;
  reg [1:0] read_pointer;
  wire push = wr_req && !full;
  wire pop = rd_req && !empty;

  assign full = count == 3'd4;
  assign empty = count == 3'd0;
  assign rd_data = storage[read_pointer];

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      count <= 3'd0;
      write_pointer <= 2'd0;
      read_pointer <= 2'd0;
    end else begin
      if (push) begin
        storage[write_pointer] <= wr_data;
        write_pointer <= write_pointer + 2'd1;
      end
      if (pop)
        read_pointer <= read_pointer + 2'd1;
      case ({push, pop})
        2'b10: count <= count + 3'd1;
        2'b01: count <= count - 3'd1;
        2'b11: if (BUGGY_SIMULTANEOUS) count <= count + 3'd1;
        default: ;
      endcase
    end
  end
endmodule
