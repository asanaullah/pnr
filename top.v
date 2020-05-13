module top(
input [1:0] in0,
input [1:0] in1,
output [3:0] out);
           
         
assign out [2:0] = {(in1[1]&in0[1])|((in1[0]&in0[0])&(in1[1]^in0[1])),(in1[1]^in0[1])^(in1[0]&in0[0]),in1[0]^in0[0]};
assign out[3] = in1[1];
         
           
endmodule
