interface link_if;
  logic valid, ready;
  logic [3:0] data; logic direct;
  modport master(output valid, data, input ready);
  modport slave(input valid, data, output ready);
endinterface

module sender(input logic clk, input logic en, input logic [3:0] value,
              link_if.master port);
  always_ff @(posedge clk) port.valid <= en;
  assign port.data = value;
  wire stalled = !port.ready;
endmodule

module receiver(link_if.slave rx, output wire seen);
  assign rx.ready = 1'b1;
  assign seen = rx.valid & rx.data[1];
endmodule

module tap(link_if sigs, output wire observed);
  assign observed = sigs.valid;
endmodule

module relay(link_if conn, output wire observed);
  tap u_tap(.sigs(conn), .observed(observed));
endmodule

module npi_demo(input logic clk, input logic [3:0] value, input logic en,
                output wire [1:0] seen, output wire [1:0] taps);
  for (genvar i = 0; i < 2; i++) begin : lane
    link_if bus();
    sender u_tx(.clk(clk), .en(en), .value(value), .port(bus));
    receiver u_rx(.rx(bus), .seen(seen[i]));
    relay u_relay(.conn(bus), .observed(taps[i]));
  end
  wire spare;
  wire multi;
  assign multi = en;
  assign multi = value[0];
  wire consume = multi;
  assign lane[0].bus.direct = en;
  wire direct_tap = lane[0].bus.direct;
  link_if watched();
  conditional u_cond(.p(watched), .clk(clk), .seen());
  link_if banks[2]();
  array_tx u_array(.p(banks[1]));
endmodule

module conditional(link_if p, input wire clk, output logic seen);
  always_ff @(posedge clk) begin
    if (p.direct) seen <= 1'b1;
    else seen <= 1'b0;
  end
endmodule

module array_tx(link_if.master p);
  assign p.valid = 1'b1;
  renamed_if aliased();
  renamed_tx u_writer(.p(aliased));
endmodule

interface renamed_if;
  logic value, enable;
  modport writer(output .push(value), input .gate(enable));
endinterface

module renamed_tx(renamed_if.writer p);
  assign p.push = p.gate;
endmodule

