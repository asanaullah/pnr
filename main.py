######################################################################################
#                       
######################################################################################

import os
import random
from com.xilinx.rapidwright.design import Design
from com.xilinx.rapidwright.design import DesignTools
from com.xilinx.rapidwright.design import NetType
from com.xilinx.rapidwright.design import Unisim
from com.xilinx.rapidwright.design import Module
from com.xilinx.rapidwright.design import SitePinInst
from com.xilinx.rapidwright.device import Device
from com.xilinx.rapidwright.device import Site
from com.xilinx.rapidwright.device import BEL
from com.xilinx.rapidwright.device import SitePIP
from com.xilinx.rapidwright.device import SiteTypeEnum
from com.xilinx.rapidwright.design import PinType 
from com.xilinx.rapidwright.design import Net 
from com.xilinx.rapidwright.design import NetType 
from com.xilinx.rapidwright.placer.blockplacer import BlockPlacer2
from com.xilinx.rapidwright.edif import EDIFCell
from com.xilinx.rapidwright.edif import EDIFCellInst
from com.xilinx.rapidwright.edif import EDIFDirection
from com.xilinx.rapidwright.edif import EDIFNet
from com.xilinx.rapidwright.edif import EDIFNetlist
from com.xilinx.rapidwright.edif import EDIFPort
from com.xilinx.rapidwright.edif import EDIFPortInst
from com.xilinx.rapidwright.edif import EDIFTools
from com.xilinx.rapidwright.edif import EDIFParser
from com.xilinx.rapidwright.util import FileTools
from com.xilinx.rapidwright.router import RouteNode
from com.xilinx.rapidwright.router import Router
from com.xilinx.rapidwright.util   import MessageGenerator
from java.util import HashSet
from java.util import List
from pprint import pprint
import Queue
from Queue import PriorityQueue   

######################################################################################
#                       
######################################################################################

topModule = "top";

######################################################################################
#                       
######################################################################################

verilog_code="""
module top(
input i_clk,
input [1:0] in0,
input [1:0] in1,
output [2:0] out);

wire clk;
reg [2:0] result;

BUFGCTRL 
#(.PRESELECT_I0(1'b1))
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
"""

verilog_file = open(topModule+".v","w")
ret = verilog_file.write(verilog_code)
verilog_file.close()

######################################################################################
#                       
######################################################################################

yosys_cmd = """yosys -p "synth_xilinx -flatten -abc9 -nobram -arch xc7 -top """+topModule+"""; write_edif """+topModule+""".edif" """+topModule+""".v"""
ret = os.system(yosys_cmd)

######################################################################################
#                       
######################################################################################

# still need to link to topModule in some places!
xpr_code="""
<?xml version="1.0" encoding="UTF-8"?>
<!-- Product Version: Vivado v2017.2 (64-bit)              -->
<!--                                                         -->
<!-- Copyright 1986-2017 Xilinx, Inc. All Rights Reserved.   -->

<Project Version="7" Minor="20" Path="./vivado_files/"""+topModule+""".xpr">
  <DefaultLaunch Dir="$PWD"/>
  <Configuration>
    <Option Name="Part" Val="xc7a35tcsg324-1"/>
  </Configuration>
  <FileSets Version="1" Minor="31">
    <FileSet Name="sources_1" Type="DesignSrcs" RelSrcDir="$PSRCDIR/sources_1">
      <Filter Type="Srcs"/>
      <File Path="./top.edif">
      </File>
      <Config>
        <Option Name="DesignMode" Val="GateLvl"/>
        <Option Name="TopModule" Val="top"/>
        <Option Name="TopRTLFile" Val="top.edif"/>
      </Config>
    </FileSet>
  </FileSets>
</Project>
"""

if not os.path.isdir('./vivado_files'):
    os.mkdir(os.getcwd()+"/vivado_files")
xpr_file = open("vivado_files/"+topModule+".xpr","w")
ret = xpr_file.write(xpr_code)
xpr_file.close()

tcl_code="""
link_design
write_edif """+topModule+"""_2.edif
"""
tcl_file = open(topModule+".tcl","w")
ret = tcl_file.write(tcl_code)
tcl_file.close()

vivado_cmd = """vivado vivado_files/"""+topModule+""".xpr -nolog -nojournal -notrace -mode batch -source """+topModule+""".tcl"""
ret = os.system(vivado_cmd)

######################################################################################
#                       
######################################################################################

parser = EDIFParser(topModule+"_2.edif")
netlist = parser.parseEDIFNetlist()
design = Design(topModule,"xc7a35tcsg324-1")
design.setAutoIOBuffers(False) 
design.setNetlist(netlist)

outputFileName = topModule+"0.dcp"
design.writeCheckpoint(outputFileName)
print "Wrote DCP '" + os.path.join(os.getcwd(), outputFileName) + "' successfully"

net = design.getNetlist()
net.setDevice(design.getDevice())
topCell = net.getCell("top")

Pin_Constraints = {'i_clk' : 'E3' , 
                  'in0[1]': 'C11' ,
                  'in0[0]': 'A8',
                  'in1[1]': 'A10',
                  'in1[0]': 'C10',
                  'out[2]': 'T9' ,
                  'out[1]': 'J5' ,
                  'out[0]': 'H5'
                 }

######################################################################################
#                       
######################################################################################

for pin in Pin_Constraints.keys():
    for topnets in topCell.getNets().toArray().tolist():
        if pin == str(topnets):
            for cellName in topCell.getCellInsts().toArray().tolist():
                if ("IBUF" in str(cellName.getCellType())) or ("OBUF" in str(cellName.getCellType())):
                    for entry in topnets.getPortInstMap():
                        if str(cellName) in str(entry):
                            ret = design.placeIOB(cellName, Pin_Constraints.get(pin), "LVCMOS33")

cell_Names = topCell.getCellInsts().toArray().tolist()
placement_list = []
random.seed(6)
for cn in cell_Names:
    if ("GND" in str(cn.getCellType())) or ("VCC" in str(cn.getCellType())):
        continue
    elif ("IBUF" in str(cn.getCellType())) or ("OBUF" in str(cn.getCellType())):
        continue
    elif ("BUFGCTRL" in str(cn.getCellType())):
        topCell.removeCellInst(str(cn))
        loc = "BUFGCTRL_X0Y16/BUFGCTRL"
        ret = design.createAndPlaceCell(str(cn),Unisim.valueOf(str(cn.getCellType())),loc) 
        ret.setProperties(cn.getProperties())
        ret.connectStaticSourceToPin(NetType.VCC ,"CE0")
        ret.connectStaticSourceToPin(NetType.VCC ,"S0")
        ret.connectStaticSourceToPin(NetType.GND ,"CE1")
        ret.connectStaticSourceToPin(NetType.GND ,"S1")
        ret.connectStaticSourceToPin(NetType.GND ,"IGNORE1")
        ret.connectStaticSourceToPin(NetType.GND ,"IGNORE0")
    elif ("FDRE" in str(cn.getCellType())): 
        bels = Design().createCell(str(cn),cn).getCompatiblePlacements().get(SiteTypeEnum.SLICEL)
        sites = design.getDevice().getAllCompatibleSites(SiteTypeEnum.SLICEL)    
        running = 1
        while running:
            bel_name = list(bels)[random.randint(0,len(bels)-1)]
            site = sites[random.randint(0,len(sites)-1)]
            bel = site.getBEL(bel_name)
            if (str(site)+"/"+str(bel)) not in placement_list:
                placement_list.append((str(site)+"/"+str(bel))) 
                running = 0
        loc = str(site)+"/"+str(bel.getName())
        unsm = Unisim.FDRE
        cell = str(cn)
        topCell.removeCellInst(str(cn))
        ret = design.createAndPlaceCell(cell,unsm,loc)        
        ret.connectStaticSourceToPin(NetType.GND ,"R")
        ret.connectStaticSourceToPin(NetType.VCC ,"CE")
    elif ("LUT" in str(cn.getCellType())):
        cell = design.createCell(str(cn),cn)
        bels = cell.getCompatiblePlacements().get(SiteTypeEnum.SLICEL)
        sites = design.getDevice().getAllCompatibleSites(SiteTypeEnum.SLICEL)    
        running = 1
        while running:
            bel_name = list(bels)[random.randint(0,len(bels)-1)]
            site = sites[random.randint(0,len(sites)-1)]
            bel = site.getBEL(bel_name)
            if (str(site)+"/"+str(bel)) not in placement_list:
                placement_list.append((str(site)+"/"+str(bel))) 
                running = 0
                design.placeCell(cell,site,bel)
 
outputFileName = topModule+"1.dcp"
design.writeCheckpoint(outputFileName)
print "Wrote DCP '" + os.path.join(os.getcwd(), outputFileName) + "' successfully"

######################################################################################
#                       
######################################################################################

for i in design.getNets().toArray().tolist():
    design.removeNet(i)

for i in design.getNetlist().getTopCell().getNets().toArray().tolist():
    if str(i) in Pin_Constraints.keys() and not(str(i) == "clk"): continue  
    if str(i) == "VCC_NET": continue     
    if str(i) == "GND_NET": continue   
    design.createNet(i)

for physNet in design.getNets().toArray().tolist():
    if str(physNet) in Pin_Constraints.keys() and not(str(physNet) == "clk"): continue
    edifNet = physNet.getLogicalNet()
    portInsts = edifNet.getPortInsts().toArray().tolist()
    for portInst in portInsts:
        portName = portInst.getName()
        portCell = portInst.getCellInst()
        portDir = portInst.getDirection()
        physCell = design.getCell(str(portCell))
        if portInst.isPrimitiveStaticSource(): continue
        siteInst = physCell.getSiteInst()
        siteWires = []
        ret = physCell.getSitePinFromPortInst(portInst,siteWires)            
        physNet.createPin(portInst.isOutput(),siteWires[len(siteWires)-1],siteInst)
            
outputFileName = topModule+"2.dcp"
design.writeCheckpoint(outputFileName)
print "Wrote DCP '" + os.path.join(os.getcwd(), outputFileName) + "' successfully"

######################################################################################
#                       
######################################################################################
        
for edifNet in topCell.getNets().toArray().tolist():
    if str(edifNet) in Pin_Constraints.keys() and not(str(edifNet) == "clk"): continue
    if  (str(edifNet) == "GND_NET"): continue
    portInsts = edifNet.getPortInsts().toArray().tolist()
    for portInst in portInsts:
        if portInst.isPrimitiveStaticSource(): continue
        portCell = portInst.getCellInst()
        physCell = design.getCell(str(portCell))
        siteInst = physCell.getSiteInst()
        if "BUFGCTRL" in str(physCell.getType()):
            if (not("CE0" in str(portInst.getName()))) and (not("S0" in str(portInst.getName()))): continue
            siteWires = []
            ret = physCell.getSitePinFromPortInst(portInst,siteWires)
            bel = siteWires[0].split("_")[0] 
            belpin = ""
            for bp in siteInst.getSite().getBELPins(siteWires[1]).tolist():
                if str(bel) in str(bp):
                    belpin = bp
                    break
            sitepip = siteInst.getSitePIP(belpin)
            siteInst.addSitePIP(sitepip)
            siteInst.routeSite()        
        elif "FDRE" in str(physCell.getType()):
            if ("CE" == str(portInst.getName())):
                belpin = siteInst.getSite().getBEL("CEUSEDMUX").getPin("1")
                sitepip = siteInst.getSitePIP(belpin)
                siteInst.addSitePIP(sitepip)
                siteInst.routeSite()  
            elif ("R" == str(portInst.getName())):
                belpin = siteInst.getSite().getBEL("SRUSEDMUX").getPin("0")
                sitepip = siteInst.getSitePIP(belpin)
                siteInst.addSitePIP(sitepip)
                siteInst.routeSite()  
            elif ("C" == str(portInst.getName())):
                belpin = siteInst.getSite().getBEL("CLKINV").getPin("CLK")
                sitepip = siteInst.getSitePIP(belpin)
                siteInst.addSitePIP(sitepip)
                siteInst.routeSite()
            elif  ("Q" == str(portInst.getName())):
                siteWires = []
                ret = physCell.getSitePinFromPortInst(portInst,siteWires)
                if len(siteWires)>1:
                    belpin = ""
                    for bp in siteInst.getSite().getBELPins(siteWires[0]).tolist():
                        if str(siteInst.getSite().getBELPins(siteWires[1]).tolist()[0]).split(".")[0] in str(bp):
                            belpin = bp
                            break
                    sitepip = siteInst.getSitePIP(belpin)
                    siteInst.addSitePIP(sitepip)
                    siteInst.routeSite()                
            elif  ("D" == str(portInst.getName())):
                siteWires = []
                ret = physCell.getSitePinFromPortInst(portInst,siteWires)
                if len(siteWires)>1:
                    bel = siteWires[0].split("_")[0] 
                    belpin = ""
                    for bp in siteInst.getSite().getBELPins(siteWires[1]).tolist():
                        if str(bel) in str(bp):
                            belpin = bp
                            break
                    sitepip = siteInst.getSitePIP(belpin)
                    siteInst.addSitePIP(sitepip)
                    siteInst.routeSite()
        elif "LUT" in str(physCell.getType()):
            siteWires = []
            ret = physCell.getSitePinFromPortInst(portInst,siteWires)
            if len(siteWires)>1 and portInst.isOutput():
                if ("IOB" in str(siteInst.getSite().getSiteTypeEnum())): continue
                belpin = ""
                for bp in siteInst.getSite().getBELPins(siteWires[0]).tolist():
                    if str(siteInst.getSite().getBELPins(siteWires[1]).tolist()[0]).split(".")[0] in str(bp):
                        belpin = bp
                        break
                sitepip = siteInst.getSitePIP(belpin)
                siteInst.addSitePIP(sitepip)
                siteInst.routeSite()

outputFileName = topModule+"3.dcp"
design.writeCheckpoint(outputFileName)
print "Wrote DCP '" + os.path.join(os.getcwd(), outputFileName) + "' successfully"

######################################################################################
#                       
######################################################################################

design.routeSites() # not necessary, but helps route input site wire for OBUFS

outputFileName = topModule+"4.dcp"
design.writeCheckpoint(outputFileName)
print "Wrote DCP '" + os.path.join(os.getcwd(), outputFileName) + "' successfully"

######################################################################################
#                       
######################################################################################
#assuming one buffer per FF
def cost (s1, s2):
    return abs(s1.getRpmX() - s2.getRpmX()) + abs(s1.getRpmY() - s2.getRpmY())

def closestSite (s1, possible_sites):
    p = PriorityQueue()
    for s2 in possible_sites:
        p.put((cost(s1,s2),s2))
    return p.get()

sites = []
pins = design.getNet("clk").getSinkPins()
for pin in pins:
    pin_site = pin.getSite()
    bufhce_sites =  design.getDevice().getAllCompatibleSites(SiteTypeEnum.BUFHCE).tolist()
    sites.append(closestSite(pin_site,bufhce_sites)[1])

for i in range(len(pins)):
    loc = str(sites[i]) +"/BUFHCE"
    ret = design.createAndPlaceCell("bufhce_"+str(i),Unisim.BUFHCE,loc) 
    ret.connectStaticSourceToPin(NetType.VCC ,"CE")
    ret.getSiteInst().addSitePIP(ret.getSiteInst().getSitePIP(ret.getSiteInst().getBEL("CEINV").getPin("CE")))
    ret.getSiteInst().routeSite()
    net = design.createNet("clk" + str(i))
    design.getNet("clk").removePin(pins[i])
    design.getNet("clk").addPin(SitePinInst("I",ret.getSiteInst()))
    net.addPin(SitePinInst("O",ret.getSiteInst()))
    net.addPin(pins[i])
    topCell.getNet("clk"+str(i)).createPortInst("O",ret)
    topCell.getNet("clk"+str(i)).addPortInst(topCell.getNet("clk").getPortInsts().toArray().tolist()[0])
    topCell.getNet("clk").createPortInst("I",ret)
    topCell.getNet("clk").removePortInst(topCell.getNet("clk").getPortInsts().toArray().tolist()[0])

######################################################################################
#                       
######################################################################################

def costFunction(curr, snk):
    return curr.getManhattanDistance(snk) + curr.getLevel()/8  

def routeNet(net, usedPIPs):
    path = []
    for sink in net.getPins():
        if sink.equals(net.getSource()): 
            continue
        q = RouteNode.getPriorityQueue()
        q.add(net.getSource().getRouteNode())
        path.extend(findRoute(q,sink.getRouteNode())) 
    path = list(dict.fromkeys(path))
    net.setPIPs(path)
    return

def findRoute(q, snk):
    visited = HashSet()
    while(not q.isEmpty()):
        curr = q.poll()
        if(curr.equals(snk)):
            print "Visited Wire Count: " + str(visited.size())
            return curr.getPIPsBackToSource()
        visited.add(curr)
        for wire in curr.getConnections():
            nextNode = RouteNode(wire,curr)
            if visited.contains(nextNode): continue
            if wire.isRouteThru(): continue
            curr_cost = costFunction(nextNode,snk)
            nextNode.setCost(curr_cost)
            q.add(nextNode)
    print "Route failed!"
    return []

usedPIPs = []           
for net in design.getNets():
    if "clk" in str(net):  
        routeNet(net,usedPIPs)
        net.lockRouting()
  
outputFileName = topModule+"5.dcp"
design.writeCheckpoint(outputFileName)
print "Wrote DCP '" + os.path.join(os.getcwd(), outputFileName) + "' successfully"

######################################################################################
#                       
######################################################################################

Router(design).routeDesign()

for net in design.getNets():
    if "clk" in str(net):
        net.unlockRouting()

outputFileName = topModule+"6.dcp"
design.writeCheckpoint(outputFileName)
print "Wrote DCP '" + os.path.join(os.getcwd(), outputFileName) + "' successfully"
