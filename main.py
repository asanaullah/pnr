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



######################################################################################
#                       
######################################################################################


topModule = "top";

parser = EDIFParser(topModule+"_2.edif")
netlist = parser.parseEDIFNetlist()
design = Design(topModule,"xc7a35tcsg324-1")
design.setAutoIOBuffers(False) 
design.setNetlist(netlist)

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
                
                
                
outputFileName = topModule+".dcp"
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

design.routeSites()  # not necessary, but helps route input site wire for OBUFS



outputFileName = topModule+"4.dcp"
design.writeCheckpoint(outputFileName)
print "Wrote DCP '" + os.path.join(os.getcwd(), outputFileName) + "' successfully"


######################################################################################
#                       
######################################################################################

ret = Router(design).routeDesign()

outputFileName = topModule+"5.dcp"
design.writeCheckpoint(outputFileName)
print "Wrote DCP '" + os.path.join(os.getcwd(), outputFileName) + "' successfully"
