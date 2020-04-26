module top(
input i_clk,
input [1:0] in0,
input [1:0] in1,
output [2:0] out);

wire clk;
reg [2:0] result;

BUFGCTRL 
#(.PRESELECT_I0("TRUE"))
clk_buf(
.I1(1'b0),
.I0(i_clk),
.O(clk),
.S0(1'b1),
.CE0(1'b1),
.IGNORE0(1'b0),
.S1(1'b0),
.CE1(1'b0),
.IGNORE1(1'b0)
);

always @(posedge clk) 
           result <= {(in1[1]&in0[1])|((in1[0]&in0[0])&(in1[1]^in0[1])),(in1[1]^in0[1])^(in1[0]&in0[0]),in1[0]^in0[0]};
//         result <= in0+in1;
        
assign out = result;

endmodule
