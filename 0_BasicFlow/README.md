# An Open Source FPGA Compilation Flow using RapidWright

## Aim
In this project, our aim is to use RapidWright to build a basic open source compilation flow for the 7 series Xilinx FPGAs. The flow is not meant to be complete and comprehensive. Rather, it provides insights into the hardware generation process using RapidWright, and how RapidWright can be integrated with existing open source tools.

## Status
- Synthesis (complete)
- Place and Route (complete)
- Bitstream Generation (fixing bugs in FASM generator for clocking and bi-direction PIPs - currently using Vivado for bitstream generation)
- Bitstream Programming (complete)

##  What is RapidWright?
RapidWright is a free tool from Xilinx that contains APIs, Data Structures and device databases needed to implement custom Place & Route algorithms for almost all chips in the vendor family. It is possible to customize the overall flow as well, with developers able to focus on specific parts of P&R and leverage Vivado for the rest. While RapidWright is written in Javascript, it has a built in Python interpreter (Jython) which enables us to use Jupyter Notebook for this project.


## Limitations
RapidWright has four major limitations that we have encountered thus far:

1. RapidWright is not fully open source. There are certain Classes for which only APIs are exposed, and actual implementation details are not available. 

2. RapidWright cannot generate bitstreams. Doing so requires either using Vivado, or a third party tool such as [Project Xray](https://github.com/SymbiFlow/prjxray).  

3. Native file support is limited to Vivado compatible files, namely EDIF (logical netlist) and DCP (design checkpoint). 

4. There is very little documentation for Classes and APIs beyond a [list](http://www.rapidwright.io/javadoc/index.html) of them on the RapidWright website. 



## Circuit
Our target circuit is shown below. We initially tested the flow using a simple 2 bit adder w/ carry and registered outputs since this design had both combinational and sequential components. 

While working on the FASM generator, we added in a "short circuit" i.e. a wire that connects an input port directly to an output port. This was useful for debugging the process of mapping designs to the FPGA's configuration memory space. 


![Target circuit that we will implement on an FPGA](https://github.com/asanaullah/images/blob/master/pnr/0/target_circuit.PNG)



## Yosys (Synthesis)
For synthesis, we will be using [Yosys](http://www.clifford.at/yosys/about.html). 


### Setting Up The Environment

This is the script we use to build Yosys. Since we are reusing the script from [here](https://github.com/asanaullah/ZipVersa-SSDP), there might be more dependencies installed than needed (will be fixed in a future commit). 

```bash
sudo dnf -y groupinstall "Development Tools" "Development Libraries"
audo dnf -y install cmake clang bison flex mercurial gperf tcl-devel libftdi-devel python-xdot graphviz
git clone https://github.com/YosysHQ/yosys.git
cd yosys
make -j$(nproc)
export PATH="$PATH:$PWD/yosys"
```
or on a Fedora machine:

```bash
sudo dnf install yosys
```

Once Yosys is set up, the `synth_xilinx` command can be used to synthesize the design for Xilinx 7-series FPGAs. Details of what each option does is given [here](http://www.clifford.at/yosys/cmd_synth_xilinx.html). The full Yosys call is given below. 

```bash
yosys -p "synth_xilinx -flatten -abc9 -nobram -arch xc7 -top top; write_json top.json" 
```

### EDIF vs JSON 
In the command above, we used the option `write_json` to generate the synthesized logical circuit as a JSON file, as opposed to the more common EDIF file (in the context of EDA) which is generated using the `write_edif` option. While EDIF is natively supported by RapidWright, it is a fairly restrictive format which limits the design information that can be stored. This typically include only the target technology library, used circuit components and component connectivity. Any additional information will have to be rediscovered by post-synthesis tools, which may not be possible if it requires context that could not be included in the EDIF file. Moreover, this also means that we would need yet another interchange format to store the physical design. By contrast, JSON can store virtually any information due to its permissive format, making it a "universal" interchange format for all stages in the compilation flow. We will have to build a custom JSON reader though, but it is relatively simple to do due to the simplicity of the format. 

It is also important to mention here that the Yosys and RapidWright EDIF formats are currently incompatible. Fixing this requires either manually modifying the Yosys EDIF output, or using Vivado to import and rewrite the EDIF file in a RapidWright compatible format. 
 
### HDL Code
The Verilog code for our design is given below. While Yosys will automatically infer IO and global clock buffers, it only inserts the generic `BUFG` cell for the global clock buffer. The assumption here is that the Place & Route tools will replace  `BUFG` with the actual primitive, `BUFGCTRL` in this case. While it is possible to do this using RapidWright, the simpler solution is to manually instantiate a `BUFGCTRL` since Yosys does have support for this. This is also done by other open source Place and Route tools, such as in this [example](https://github.com/daveshah1/nextpnr-xilinx/blob/xilinx-upstream/xilinx/examples/arty-a35/blinky.v) from Nextpnr. 


(Note 1: For clocks, both an IO and a global clock buffer is generated)

(Note 2: If the Yosys EDIF file with `BUFG` is imported into Vivado, Vivado will show `BUFG` in the logical netlist. When the Vivado placer is run, the `BUFG` cell will be placed at a `BUFGCTRL` location, but the schematic will continue to show `BUFG`)

```verilog
module top(
    input i_clk,
    input [1:0] in0,
    input [1:0] in1,
    output [3:0] out);
    
    wire clk;
    reg [2:0] result;
   
    BUFGCTRL clk_buf(
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
        result <= in0+in1;
        
    assign out[2:0] = result;
    assign out[3] = in1[1];
    
endmodule
```

The following logical circuit showing the adder only) was generated by Yosys after synthesizing the above code. As could be seen by the circuit connectivity, and confirmed by generating the bitstream using Vivado, the circuit was not correct. This may be because Yosys was unable to translate the behavioral `+` operator w/ carry support. 

![Circuit generated when compiling the behavioral adder using Yosys](https://github.com/asanaullah/images/blob/master/pnr/0/schematic_auto_adder.PNG)

To address this, we replaced the `+` operator with Boolean logic for each output bit as show below. 

```verilog
result <= {(in1[1]&in0[1])|((in1[0]&in0[0])&(in1[1]^in0[1])),(in1[1]^in0[1])^(in1[0]&in0[0]),in1[0]^in0[0]};
```

And this does give us the correct adder circuit. We verified it by compiling the above HDL code (w/ `+` operator) using Vivado. 


![Circuit generated by Yosys when using boolean logic to specify the adder](https://github.com/asanaullah/images/blob/master/pnr/0/schematic_manual_adder.PNG)

The final Verilog code is thus:

```verilog
module top(
    input i_clk,
    input [1:0] in0,
    input [1:0] in1,
    output [3:0] out);
    
    wire clk;
    reg [2:0] result;
   
    BUFGCTRL clk_buf(
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
        
    assign out[2:0] = result;
    assign out[3] = in1[1];
    
endmodule
```


## Setting Up The RapidWright Environment
A guide for setting up the Jython kernel can be found [here](https://www.rapidwright.io/docs/RapidWright_Jupyter_Setup.html)

## Quick Object Reference
One last thing before diving into the code. There are a lot of well defined objects in RapidWright that we will be using to implement the P&R flow. While the specific role of each object is described in the [RapidWright documentation](https://www.rapidwright.io/docs/index.html) (in particular [here](https://www.rapidwright.io/docs/RapidWright_Overview.html)) and [API guide](http://www.rapidwright.io/javadoc/index.html), we will list some important ones and provide a brief description for each. 


### Common Objects

1. **Design** : Responsible for storing all information regarding the logical and physical representations of the design that we are working on. All code we write either updates **Design** directly, or another object that is created within **Design**. 

### Objects That Deal With The Logical Netlist

2. **EDIFNetlist** : Contains information about the different components in a logical netlist and their connectivity. A **EDIFNetlist** object is automatically created inside a **Design** object. 

3. **EDIFCell** : This is used to store a logical netlist component. In RapidWright, the overall netlist is also considered a netlist component, and the **EDIFCell** for this is automatically created inside the **EDIFNetlist** object (when the **Design** object is created).  

4. **EDIFPort** : This is a logical port of the netlist component represented by an **EDIFCell** object.

5. **EDIFLibrary** : This is a collection of unique **EDIFCell** objects that are used to build the logical netlist. The specific library we will be building is ``hdi_primitives``, which (once built) will contain components available in the target technology. This library is automatically created within the **EDIFNetlist** object (and is initially empty). 

6. **EDIFCellInst** : This is an instance of an **EDIFCell** within another **EDIFCell** object. In a flattened design, only one parent  **EDIFCell** object is created, i.e. the overall logical netlist, and all other **EDIFCell** objects in the ``hdi_primitives`` **EDIFLibrary** are manually instantiated as child **EDIFCellInst** objects in this **EDIFCell**

7. **EDIFPortInst** : This is a logical port instance of the netlist component represented by an **EDIFCellInst** object.

8. **EDIFNet** : An **EDIFNet** object contains all **EDIFPortInst** objects that are connected together in the design. To include an **EDIFPort** in **EDIFNet**, we must first create an **EDIFPortInst** object for it. 

### Objects That Deal With The Physical Netlist

9. **Device** : Contains all information regarding the chip architecture. Each **Design** object must contain a fully defined **Device** object in order to use APIs that require a chip context, such as finding compatable locations for a given component. An empty **Device** object is automatically created inside a **Design** object. 

10. **Cell** : Contains the physical netlist component for a given **EDIFCellInst** object. 

11. **BEL** : Represents a Basic Element of Logic (*BEL*) within the target FPGA. *BELs* form the lowest level in the device fabric hierarchy, and each **Cell** object maps to a unqiue *BEL* within the design. Examples of *BELs* are Look Up Tables (LUTs), D Flip-Flops with Clock Enable and Synchronous Reset (FDREs) and Carry blocks. 

12. **BELPin** : This represents a pin of a **BEL** object.

13. **Site** : Represents a *Site* within the target FPGA. A *Site* is effectively a collection of *BELs* that are hardwired together. 


14. **SiteWire** : This is not technically a class, but rather a special type of **Wire**. **SiteWire**s represent a wire in a **Site** object that connects two or more **BELPin** objects. 


15. **SitePIP** : While the wires between *BEL* pins in a *Site* are fixed, we can use a special type of *BEL*, i.e. a Routing *BEL* (*RBEL*), to control connectivity between regular *BELs*; *RBELs* are essentially MUXs. A **SitePIP** object represents a Input-Ouput pairing of *RBEL* pins. By "turning on" a **SitePIP**, we can specify which input should an *RBEL* select, and thus control the flow of data within a *Site*.  


16. **SitePin** : This represents a pin of a **Site** object. A *Site* can have less pins than the total number of pins for all *BELs* within the *Site*. This is why efficient Packing is important for large design i.e. so that a number of *BEL* connections can be made on an intra-Site level (and therefore would not require access to *Site* pins. 


17. **Net** : A **Net** object is a collection of *Site* pins that are connected together, as well the routing resources being used to connect them. Since these routing resources are only connecting *Site* pins, they do not use *Site* wires or *BELs* of *Sites* that are part of the **Net** object. An exception to this is a "route through", where (in order to create a shorter path) the routing resources used by a **Net** object can include *Site* wires and *BELs* within a *Site* which is not part of the **Net** object. 

18. **Wire** : A **Wire** object represents a physical *wire* on the chip. 

19. **PIP** :  Programmable Interconnect Points (PIPs) are switches/junctions that can be turn on to connect *wires* together. **Net** objects contain a list of **PIP** objects to store their routed paths. It is important to note that some *PIPs* can be bidirectional as well, in which case turning them on is not sufficient - the correct direction of signal transmission must also be specified. 

20. **RouteNode** : A **RouteNode** object can be created from the RapidWright [Router](https://www.rapidwright.io/javadoc/com/xilinx/rapidwright/router/package-summary.html) package. It is useful for keeping track of *PIPs* visited when traversing a chip's routing resources.


<ins>To simplify our discussion in the rest of this document, we will refer to RapidWright objects as "**<Object_Name>**" instead of "**<Object_Name>** object". </ins> 

![Simplified hierarchy of objects in RapidWright](https://github.com/asanaullah/images/blob/master/pnr/0/hierarchy.PNG)


## Common Packages
Let's start by importing some Classes from commonly used Packages. A brief overview of each Class is given in the [documentation](http://www.rapidwright.io/javadoc/index.html), as well as our quick object reference section above. For simplicity's sake, we have grouped almost all imported Classes at the beginning, even though they were added as needed during code development. 


```python
from com.xilinx.rapidwright.design import Design
from com.xilinx.rapidwright.design import DesignTools
from com.xilinx.rapidwright.design import NetType
from com.xilinx.rapidwright.design import Unisim
from com.xilinx.rapidwright.design import Module
from com.xilinx.rapidwright.design import SitePinInst
from com.xilinx.rapidwright.design import PinType 
from com.xilinx.rapidwright.design import Net 
from com.xilinx.rapidwright.design import NetType
from com.xilinx.rapidwright.design.tools import LUTTools
from com.xilinx.rapidwright.device import Device
from com.xilinx.rapidwright.device import Site
from com.xilinx.rapidwright.device import BEL
from com.xilinx.rapidwright.device import SitePIP
from com.xilinx.rapidwright.device import SiteTypeEnum
from com.xilinx.rapidwright.edif import EDIFCell
from com.xilinx.rapidwright.edif import EDIFCellInst
from com.xilinx.rapidwright.edif import EDIFDirection
from com.xilinx.rapidwright.edif import EDIFNet
from com.xilinx.rapidwright.edif import EDIFNetlist
from com.xilinx.rapidwright.edif import EDIFPort
from com.xilinx.rapidwright.edif import EDIFPortInst
from com.xilinx.rapidwright.edif import EDIFTools
from com.xilinx.rapidwright.edif import EDIFParser
from com.xilinx.rapidwright.edif import EDIFLibrary
from com.xilinx.rapidwright.edif import EDIFPropertyObject
from com.xilinx.rapidwright.edif import EDIFValueType
from com.xilinx.rapidwright.router import RouteNode
from com.xilinx.rapidwright.router import Router
from com.xilinx.rapidwright.util import FileTools
from com.xilinx.rapidwright.util import MessageGenerator
```

## Step 0: User Configuration Data
Next, we manually specify some user configuration data that will guide the hardware generation process. This data includes:

1. Name of the **EDIFCell** that represents the full logical netlist. To simplify the code, we use the same name as the top module in our Verilog file i.e. *top*.
2. The device we will be using. In our case, this is the Arty A7-35t board.
3. Name of the synthesized JSON file output by Yosys.
4. Location constraints and other parameters for external IO pins in our design. 

```python
topModule = "top"
device = "xc7a35tcsg324-1"
filename = "top.json"

constraints = {
               'i_clk' : {'LOC' : 'E3', 'IOSTANDARD' : 'LVCMOS33' , 'SLEW' : 'FAST', 'IN_TERM' : 'NONE' , 'PULL_TYPE' : 'NONE'},
               'in0[1]' : {'LOC' : 'C11', 'IOSTANDARD' : 'LVCMOS33' , 'SLEW' : 'FAST', 'IN_TERM' : 'NONE' , 'PULL_TYPE' : 'NONE'},
               'in0[0]' : {'LOC' : 'A8', 'IOSTANDARD' : 'LVCMOS33' , 'SLEW' : 'FAST', 'IN_TERM' : 'NONE' , 'PULL_TYPE' : 'NONE'},
               'in1[1]' : {'LOC' : 'A10', 'IOSTANDARD' : 'LVCMOS33' , 'SLEW' : 'FAST', 'IN_TERM' : 'NONE' , 'PULL_TYPE' : 'NONE'},
               'in1[0]' : {'LOC' : 'C10', 'IOSTANDARD' : 'LVCMOS33' , 'SLEW' : 'FAST', 'IN_TERM' : 'NONE' , 'PULL_TYPE' : 'NONE'},
               'out[3]' : {'LOC' : 'K1', 'IOSTANDARD' : 'LVCMOS33' , 'SLEW' : 'FAST', 'IN_TERM' : 'NONE' , 'PULL_TYPE' : 'NONE'},
               'out[2]' : {'LOC' : 'J3', 'IOSTANDARD' : 'LVCMOS33' , 'SLEW' : 'FAST', 'IN_TERM' : 'NONE' , 'PULL_TYPE' : 'NONE'},
               'out[1]' : {'LOC' : 'G3', 'IOSTANDARD' : 'LVCMOS33' , 'SLEW' : 'FAST', 'IN_TERM' : 'NONE' , 'PULL_TYPE' : 'NONE'},
               'out[0]' : {'LOC' : 'G6', 'IOSTANDARD' : 'LVCMOS33' , 'SLEW' : 'FAST', 'IN_TERM' : 'NONE' , 'PULL_TYPE' : 'NONE'}
             }
```
## Step 1: Importing A Post-Synthesis JSON File
The next step is to import the JSON file generated by Yosys and create a logic netlist. Since RapidWright does not have native support for JSON, we have to write our own routines for populating the **EDIF** objects. While it is not necessary to create the logical netlist (and instead go straight to building a physical netlist from the JSON file), doing so makes it easier (and faster) to write, visualize and debug code/circuits.  

### Read Yosys JSON File
The first routine reads in a user specified JSON file into a local dictionary called `jnet`. 

``` python
import json
def read_file(filename):
    with open(filename, 'r') as file:
        jnet = json.load(file)
    return jnet
```

### Build "hdi_primitives" Technology Library
At the highest level of its hierarchy, the Yosys JSON file is composed of "modules". Each module represents a unique technology specific building block that can be used to construct a logical netlist (our design is also a module). All possible modules supported by the target are provided, even if they are not being used in the actual design. We will use these modules to build our **EDIFLibrary**. The code for this, as well as its breakdown, is given below. Note that not all information provided for each module in the JSON file will be needed. 


``` python
def buildLibrary(jnet, library):
    topModule = library.getNetlist().getTopCell().getName()
    for cell in jnet['modules']:
        if cell == topModule: continue
        if library.containsCell(cell): continue
        ret = EDIFCell(library,cell)
        for port in jnet['modules'][cell]['ports'].keys():
            if jnet['modules'][cell]['ports'][port]['direction'] == "input":
                direction = EDIFDirection.INPUT
            elif jnet['modules'][cell]['ports'][port]['direction'] == "output":
                direction = EDIFDirection.OUTPUT
            else:
                direction = EDIFDirection.INOUT
            ret.createPort(port,direction,1)
        library.addCell(ret)
```


Our routine takes the imported JSON file `jnet` and the **EDIFLibrary** `library` as inputs. It modifies `library` directly instead of returning a new **EDIFLibrary**. 

``` python
def buildLibrary(jnet, library):
```

We begin by getting the name of the top module in our Verilog code, which we set as the name of the **EDIFCell** that represents our overall design. Note that, as discussed earlier, this will be the only **EDIFCell** in our **EDIFNetlist**, and is automatically created when we create our **Design**. Also note that, complimentary to **EDIFNetlist**, the **EDIFLibrary** will have an **EDIFCell** for all modules except our design - and we will convert an **EDIFCell** in the **EDIFLibrary** to an **EDIFCellInst** when instantiating it. 

```python
    topModule = library.getNetlist().getTopCell().getName()
```

Next, we loop over all modules in `jnet`.

```python
    for cell in jnet['modules']:
```

If a module is our custom design or has already been added to **EDIFLibrary**, we will skip it. 

```python
        if cell == topModule: continue
        if library.containsCell(cell): continue
```

Next we create an **EDIFCell** for that module.

```python
       ret = EDIFCell(library,cell)
```
Next we will create an **EDIFPort** for each port of the module. Doing so requires calling the `createPort` routine, which has three inputs: i) name of the port, ii)  an **EDIFDirection**, and iii) the bus width (almost always 1 for target technology modules). All the required information is available in `jnet`. 

```python
       for port in jnet['modules'][cell]['ports'].keys():
            if jnet['modules'][cell]['ports'][port]['direction'] == "input":
                direction = EDIFDirection.INPUT
            elif jnet['modules'][cell]['ports'][port]['direction'] == "output":
                direction = EDIFDirection.OUTPUT
            else:
                direction = EDIFDirection.INOUT
            ret.createPort(port,direction,1)
```

Finally, we add the **EDIFCell** to the `library`. Note that this may not be necessary if the **EDIFCell** constructor automatically adds the **EDIFCell** to the **EDIFLibrary**. It will be removed in a future commit if so. 

```python
        library.addCell(ret)
```

Once we have built our **EDIFLibrary**, we can now start building **EDIFCell**s for our **EDIFNetlist**. As mentioned previously, there will be only one **EDIFCell** in our **EDIFNetlist** which represents our design i.e. the module that we skipped when building our **EDIFLibrary**. This **EDIFCell** is automatically created along with **Design** , and can be accessed by calling the routine `getTopCell()` from **EDIFNetlist** (which in turn is accessed by calling the `getNetlist()` routine in **Design**).


### Define External IO Ports
The first step to building the **EDIFCell** in **EDIFNetlist** is creating **EDIFPort**s for it, which will also be the external I/O ports. The code for this, as well as its breakdown, is given below. 

``` python
def defineExternalPorts(jnet, topCell):
    topModule = topCell.getName()
    for port in jnet['modules'][topModule]["ports"]:
        port_data = jnet['modules'][topModule]["ports"].get(port)
        port_name = str(port)
        num_pins = len(port_data.get("bits"))
        for i in range(num_pins):
            name = port_name + ("" if num_pins == 1 else ("[" + str(i)  + "]"))
            connectionID = port_data.get("bits")[i]
            direction = port_data.get("direction")
            if direction == "input":
                ret = topCell.createPort(name,EDIFDirection.INPUT, 1)
            elif direction == "output":
                ret = topCell.createPort(name,EDIFDirection.OUTPUT, 1)
            else:
                ret = topCell.createPort(name,EDIFDirection.INOUT, 1)
```


Our routine takes the imported JSON file `jnet` and the **EDIFCell** `topCell`  as input, and adds **EDIFPort**s to `topCell`.  

``` python
def defineExternalPorts(jnet, topCell):
```

We begin by getting the name of the top module in our Verilog code i.e. the name of the **EDIFCell**

``` python
    topModule = topCell.getName()
```
Using this name, we loop over all ports for the module and access each port's name (`port_name`) and parameters (`port_data`).  

``` python
    for port in jnet['modules'][topModule]["ports"]:
        port_data = jnet['modules'][topModule]["ports"].get(port)
        port_name = str(port)
```

Since we are working with a custom module, instead of FPGA technology primitives (in **EDIFLibrary**), ports are not necessarily of size 1 and can instead be buses as well. To ensure consistency amount how we deal with all **EDIFCell** s, we will (where applicable) loop over each pin in the bus, append a suffix to the name, and create an **EDIFPort** (of size 1) for it.  For example, in our design, the "out" signal is a bus of width 4, but we will create four separate **EDIFPort**s for it named *out[0]*, *out[1]*, *out[2]* and *out[3]*. In the code fragment below, we find the number of pins from `port_data` and assign a suffix to the `port_name` string.

``` python
        num_pins = len(port_data.get("bits"))
        for i in range(num_pins):
            name = port_name + ("" if num_pins == 1 else ("[" + str(i)  + "]"))
```
Next, we determine the **EDIFDirection** value and create the **EDIFPort** for this pin. 
``` python
            direction = port_data.get("direction")
            if direction == "input":
                ret = topCell.createPort(name,EDIFDirection.INPUT, 1)
            elif direction == "output":
                ret = topCell.createPort(name,EDIFDirection.OUTPUT, 1)
            else:
                ret = topCell.createPort(name,EDIFDirection.INOUT, 1)
```



### Create Logical CellInst Objects
Now that we have set the external I/O ports for our logical netlist (being built within the **EDIFCell** `topCell`), we will now add in components of the netlist from the **EDIFLibrary** i.e. LUTs, FDRE, Buffers etc. The code for this, as well as its breakdown, is given below. 


``` python
def createEDIFCellInsts(jnet, topCell, library):
    topModule = topCell.getName()
    for cell in jnet['modules'][topModule]["cells"]:
        cell_data = jnet['modules']['top']['cells'].get(cell)
        cell_name = cell
        cell_type = cell_data['type']
        cell_properties = cell_data.get('parameters')
        ret = EDIFCellInst(cell_name, library.getCell(cell_type),topCell)
        for proprty in cell_properties.keys():
            value = cell_properties.get(proprty)
            if value == 'x': continue
            ret.addProperty(proprty,str(int(value,2)), EDIFValueType.INTEGER )
```

The inputs to our routine are the imported JSON file `jnet`,  the **EDIFCell** `topCell` that we are building, and the **EDIFLibrary** that we built earlier. Based on the composition of our logical netlist, as specified in `jnet`, we will take **EDIFCell**s from `library`,  create **EDIFCellInst**s for them in`topCell`, and copy over component properties e.g. LUT values.

``` python
def createEDIFCellInsts(jnet, topCell, library):
```

We begin by getting the name of the top module in our Verilog code.

``` python
    topModule = topCell.getName()
```

Using `topModule`, we loop over all its "cells" in `jnet` and get the name, type and properties of each cell. In this context, a cell is an instantiation of one of the modules we used to build `library`. Note that a cell's `type` here is also referred to as its *Unisim* in RapidWright, and the **Unisim** class enumerates the different *Unisim* primitives supported by Xilinx devices. 

``` python
    for cell in jnet['modules'][topModule]["cells"]:
        cell_data = jnet['modules']['top']['cells'].get(cell)
        cell_name = cell
        cell_type = cell_data['type']
        cell_properties = cell_data.get('parameters')
```

Continuing the loop, we create a **EDIFCellInst** for each cell by getting the corresponding **EDIFCell** from `library`.  This **EDIFCellInst** is added to `topCell`.

``` python
        ret = EDIFCellInst(cell_name, library.getCell(cell_type),topCell)
```

Finally, for each property of each **EDIFCellInst** that we create, we will add properties. While this is not a strict requirement, we express property values as integers; from what we have observed thus far, the default choice for Yosys is binary.  If a property is undefined or is not applicable, it is denoted by "x" in `jnet` and will be skipped. 

``` python
        for proprty in cell_properties.keys():
            value = cell_properties.get(proprty)
            if value == 'x': continue
            ret.addProperty(proprty,str(int(value,2)), EDIFValueType.INTEGER )
```

### Create Logical Nets
At this point, we have a logic netlist with components and external I/O.  The only thing left at this point is to build the nets/wires that connect everything together i.e. the **EDIFNet**s. We will do this in three passes. In the first pass we will create signal **EDIFNet**s. In the second pass, we will remove any empty **EDIFNet**s (caused by redundancy in the Yosys output). Finally, the third pass will add in the power **EDIFNet**s i.e. VCC and GND (used to supply hard 1 or 0 logic inputs respectively). 


Let's begin with our first pass: creating  and building **EDIFNet**s for signals. The code for this, as well as its breakdown, is given below. 

``` python
def createEDIFPorts(jnet, topCell):
    topModule = topCell.getName()
    ports = []
    for net in jnet['modules'][topModule]["netnames"]:
        connectionIDs = jnet['modules'][topModule]["netnames"][net]['bits']
        for i in range(len(connectionIDs)):
            ret = topCell.createNet(str(net) + ("" if (len(connectionIDs)) == 1 else ("[" + str(i)  + "]")))
            for cell in jnet['modules'][topModule]["cells"]:
                for port in jnet['modules'][topModule]["cells"][cell]['connections']:
                    value = jnet['modules'][topModule]["cells"][cell]['connections'].get(port)
                    if value[0] == connectionIDs[i]:
                        if ((port,cell) in ports): continue
                        else:
                            ret.createPortInst(port,topCell.getCellInst(cell))
                            ports.append((port,cell))
            for port in jnet['modules'][topModule]['ports']:
                topConnectionIDs = jnet['modules'][topModule]['ports'][port]['bits']
                for j in range(len(topConnectionIDs)):
                    if topConnectionIDs[j] == connectionIDs[i]:
                        name = str(port) + ("" if (len(topConnectionIDs)) == 1 else ("[" + str(j)  + "]"))
                        if ((name,topModule) in ports): continue
                        else:
                            ret.createPortInst(topCell.getPort(name))
                            ports.append((name,topModule))
```

The inputs to our routine are the imported JSON file `jnet` and the **EDIFCell** `topCell` that we are building. Based on the data in `jnet`, we will: i) create and add each  **EDIFNet** to `topCell` and , ii) create and add **EDIFPortInst**s to each **EDIFNet** (where applicable). 

``` python
def createEDIFPorts(jnet, topCell):
```
We begin by getting the name of the top module in our Verilog code.

``` python
    topModule = topCell.getName()
```

Next we initialize an empty list called `ports`. Every time an **EDIFPortInst** is created, we will add it to `ports` so that we can keep track and avoid re-creating it for a different **EDIFNet**. 

``` python
    ports = []
```

Yosys stores most of net data under "netnames" in each module. We will loop over all the fields in "netnames" in order to create **EDIFNet**s.

``` python
    for net in jnet['modules'][topModule]["netnames"]:
```

Next, we create an **EDIFNet** for each net using the net name given in `jnet`. While all nets have unique IDs, stored in the "bits" field of the net in `jnet`, Yosys will sometimes group a number of nets under one name. In such cases, we will use the unique ID to create a unique name for it. Note that we do not append the unique ID to the group name; rather, we run a counter based on the length of the "bits" field (`connectionIDs`) and use its value. 

``` python
        connectionIDs = jnet['modules'][topModule]["netnames"][net]['bits']
        for i in range(len(connectionIDs)):
            ret = topCell.createNet(str(net) + ("" if (len(connectionIDs)) == 1 else ("[" + str(i)  + "]")))
```

For each **EDIFNet** that we create, we loop over every port of every cell for `topModule` in `jnet`, and get the unique net IDs that the port is connected to. These IDs are stored in `value`.

``` python
            for cell in jnet['modules'][topModule]["cells"]:
                for port in jnet['modules'][topModule]["cells"][cell]['connections']:
                    value = jnet['modules'][topModule]["cells"][cell]['connections'].get(port)
```

Next, we compare the net ID from cell connection data to the net ID of the current **EDIFNet**.  If there is a match, and we have not already added this unique "port,cell" tuple to `ports`, we'll create an **EDIFPortInst** for it in the current **EDIFNet** and add the corresponding tuple to `ports`.  Otherwise, we skip this port. 

In some cases, a port may be connected to multiple nets. By default, we select the first net it `value`. We might need an extra step here where we merge nets in `jnet` to ensure a port is only connected to a single net. Since it wasn't needed for the current design, it was skipped for now. However, a routine for this will be added in a future commit if such a situation is encountered when we look at more complex designs. 

``` python
                    if value[0] == connectionIDs[i]:
                        if ((port,cell) in ports): continue
                        else:
                            ret.createPortInst(port,topCell.getCellInst(cell))
                            ports.append((port,cell))
```

So far, for the **EDIFNet** that we  are currently building,  we only created **EDIFPortInst**s for **EDIFCellInst**s in `topCell` (since we looped over "cells"). The **EDIFNet** may also connect to external I/O ports i.e. ports of `topModule`. To check for this and create **EDIFPortInst**s where applicable for external I/O ports, we repeat the above process by looping over ports in `topModule`.  

``` python
            for port in jnet['modules'][topModule]['ports']:
                topConnectionIDs = jnet['modules'][topModule]['ports'][port]['bits']
                for j in range(len(topConnectionIDs)):
                    if topConnectionIDs[j] == connectionIDs[i]:
                        name = str(port) + ("" if (len(topConnectionIDs)) == 1 else ("[" + str(j)  + "]"))
                        if ((name,topModule) in ports): continue
                        else:
                            ret.createPortInst(topCell.getPort(name))
                            ports.append((name,topModule))
```

### Clean Empty Nets

In  the second pass, we remove any **EDIFNet** in `topCell` that does not have any **EDIFPortInst**s i.e. is an empty **EDIFNet**. The code for this is given below. 

```python
def cleanEmptyNets(topCell):
    nets = []
    for net in topCell.getNets():
        if not (net.getPortInsts()):
            nets.append(str(net))
    for i in nets:
        topCell.removeNet(i)
```

 
### Create Logical Power Nets

In the final pass, we create nets for hard '1' and '0's by connecting appropriate ports to power (VCC) or ground (GND). This represents assigning a fixed boolean value to a port . The code for this, as well as its breakdown, is given below. 

``` python
def createStaticSourceNets(jnet, topCell, netlist):
    topModule = topCell.getName()
    gnd = EDIFTools.getStaticNet(NetType.GND, topCell, netlist);
    vcc = EDIFTools.getStaticNet(NetType.VCC, topCell, netlist);
    for cell in jnet['modules'][topModule]["cells"]:
        for port in jnet['modules'][topModule]["cells"][cell]['connections']:
            value = jnet['modules'][topModule]["cells"][cell]['connections'].get(port)
            if value[0] == "0":
                gnd.createPortInst(port , topCell.getCellInst(cell))
            elif value[0] == "1":
                vcc.createPortInst(port , topCell.getCellInst(cell))
```

The inputs to our routine are the imported JSON file `jnet`, the **EDIFCell** `topCell` that we are building, and the **EDIFNetlist** `netlist`. We will use `netlist` and `topCell` to create the VCC and GND **EDIFNet**s, and then create and add **EDIFPortInst**s to them  (where applicable).  Note that we did not need to pass both `topCell` and `netlist` since they can reference each other using inbuilt routines; this will be optimized in a future commit. 

``` python
def createStaticSourceNets(jnet, topCell, netlist):
```

We begin by getting the name of the top module in our Verilog code.

``` python
    topModule = topCell.getName()
```

Next we use the `getStaticNet` routine in the **EDIFTools** class to create two separate **EDIFNet**s for "GND" and "VCC".

``` python
    gnd = EDIFTools.getStaticNet(NetType.GND, topCell, netlist);
    vcc = EDIFTools.getStaticNet(NetType.VCC, topCell, netlist);
```

Similar to how we created **EDIFPortInst**s in the first pass, we will loop over all ports of all cells in `topModule`. We do not need to keep track of the "port,cell" tuple since we will go over each port only once, and a port cannot be part of both the VCC and GND nets (since this will lead to a short circuit).

``` python
    for cell in jnet['modules'][topModule]["cells"]:
        for port in jnet['modules'][topModule]["cells"][cell]['connections']:
            value = jnet['modules'][topModule]["cells"][cell]['connections'].get(port)
```

"GND" and "VCC" nets have a default unique ID of "0" and "1" respectively. We will compare these IDs with the ID stored for the port, and create an **EDIFPortInst** in the appropriate **EDIFNet** if the IDs match. 

``` python
            if value[0] == "0":
                gnd.createPortInst(port , topCell.getCellInst(cell))
            elif value[0] == "1":
                vcc.createPortInst(port , topCell.getCellInst(cell))
```

Note that we wrote this routine with the assumption that none of the external I/O ports are not tied to a fixed logic value. This will not always be true, and therefore support for connecting external output ports to VCC and GND nets will be added in a  future commit. 

### Putting It All Together 

Finally, we put all the routines developed in this Step into a single `read_json` routine that takes the JSON file name (`filename`), Verilog top module name (`topModule`), and device name (`device`) as inputs. The `read_json` routine: i) creates our  **Design** (`design`) by calling the **Design** constructor, ii) builds the logical netlist for `design` by using the routines developed in this Step, and iii) returns `design` which now has the complete logical netlist. 

``` python
def read_json (filename, topModule, device):
    jnet = read_file(filename)
    design = Design(topModule,device)
    netlist = design.getNetlist()
    topCell = netlist.getTopCell()
    library = netlist.getLibrary("hdi_primitives")
    buildLibrary(jnet, library)
    defineExternalPorts(jnet, topCell)    
    createEDIFCellInsts(jnet, topCell, library)
    createEDIFPorts(jnet, topCell)
    cleanEmptyNets(topCell)
    createStaticSourceNets(jnet, topCell,netlist)
    return design
```

At this point, we can use Vivado to verify that the netlist was created correctly by writing out an EDIF or Design Check Point file from RapidWright. From Step 2 onwards, we will be building the physical netlist.

## Step 2: Placing IO Buffers

We begin the process of building the physical netlist by placing the IO buffers for external ports. Unlike other components in the netlist, I/O Buffers must be placed at very specific location, given by the chip pins to which their corresponding ports are connected. The code for placing I/O buffers, as well as its breakdown, is given below. 


``` python

def placeIOBuffers(design , constraints):
    for pin in constraints.keys():
        for topnets in design.getNetlist().getTopCell().getNets().toArray().tolist():
            if pin == str(topnets):
                for cellName in design.getNetlist().getTopCell().getCellInsts().toArray().tolist():
                    if ("IBUF" in str(cellName.getCellType())) or ("OBUF" in str(cellName.getCellType())):
                        for entry in topnets.getPortInstMap():
                            if str(cellName) in str(entry):
                                ret = design.placeIOB(cellName, constraints.get(pin).get('LOC'), constraints.get(pin).get('IOSTANDARD'))
                                ret.addProperty("IOSTANDARD",constraints.get(pin).get("IOSTANDARD"))
                                ret.addProperty("SLEW",constraints.get(pin).get("SLEW"))
                                ret.addProperty("IN_TERM",constraints.get(pin).get("IN_TERM"))
                                ret.addProperty("PULL_TYPE",constraints.get(pin).get("PULL_TYPE"))
```


The `placeIOB` routine in design requires three inputs to place a I/O buffer component: i) the **EDIFCellInst** for the buffer, ii) the chip package pin it corresponds to, and iii) the IO Standard. Information for (ii) and (iii) is provided by the user in the `constraints` object from Step 0. We only need to get the **EDIFCellInst**. 

Doing so requires knowledge of how the I/O *Sites* in Xilinx 7-Series FPGAs are structured (shown in the image below). The specific **EDIFCellInst** we are interested in connects to the chip pin's *PAD* using a single **SiteWire**. If we can find the **EDIFNet** corresponding to this connection, we can find the two **EDIFPortInst**s in this **EDIFNet**. And once we know the **EDIFPortInst**s, we can get the **EDIFCellInst**s they belong to. Note that since the chip pin's *PAD* is not connected to an **EDIFCellInst**, there will be only one result in our search. Let's look at how this will be done using RapidWright APIs.  


![Xilinx 7-Series IO PAD](https://github.com/asanaullah/images/blob/master/pnr/0/iopad.PNG)



``` python

def placeIOBuffers(design , constraints):
```

The first challenge is to find the name of the **EDIFNet**s. To do this, we leverage the observation that Yosys uses the name of the chip pin's *PAD* as the name for the corresponding **EDIFNet**. This is also the name of the pin in the `constraints` object. Therefore, if a name exists in both as a `key` in the `constraints` and as an **EDIFNet** in the **EDIFCell**, then we will process the **EDIFNet**. 

``` python
    for pin in constraints.keys():
        for topnets in design.getNetlist().getTopCell().getNets().toArray().tolist():
            if pin == str(topnets):
```

For the **EDIFNet** selected, we run a nested loop which loops over all **EDIFPortInst**s and all *I/O Buffer* **EDIFCellInst**s. To find if an **EDIFCellInst** is an *I/O Buffer*, we look for `IBUF` and `OBUF` **EDIFCell** types. Note that this `if` condition is not necessary since we will be matching names, but it helps reduce the number of **EDIFCellInst**s we have to check - the total number of **EDIFCellInst**s can be many orders of magnitude higher than just the *I/O Buffer* ones.  

``` python            
                for cellName in design.getNetlist().getTopCell().getCellInsts().toArray().tolist():
                    if ("IBUF" in str(cellName.getCellType())) or ("OBUF" in str(cellName.getCellType())):
                        for entry in topnets.getPortInstMap():
```
For each **EDIFCellInst** and **EDIFPortInst** pair we pick up, we leverage the observation that converting the **EDIFPortInst** to a string will give us the name of its **EDIFCellInst**.  Note that we could also do this in more steps (and more efficiently) by using appropriate APIs to get the **EDIFCellInst** itself from the **EDIFPortInst**, followed by `getName()` calls. 

``` python        
                            if str(cellName) in str(entry):                  
```
If all conditions are met, we have the **EDIFCellInst**. We can then go ahead and place the **EDICellInst** at the location given in `constraints`. The `placeIOB` routine both creates a new **Cell** for this placed buffer in **Design** and returns it. The returned **Cell** is placed in `ret`. 

``` python
                                ret = design.placeIOB(cellName, constraints.get(pin).get('LOC'), constraints.get(pin).get('IOSTANDARD'))
```

Finally, we call the `addProperty` routines in the **Cell** to add the remaining properties in the `constraints` object. 

``` python
                                ret.addProperty("IOSTANDARD",constraints.get(pin).get("IOSTANDARD"))
                                ret.addProperty("SLEW",constraints.get(pin).get("SLEW"))
                                ret.addProperty("IN_TERM",constraints.get(pin).get("IN_TERM"))
                                ret.addProperty("PULL_TYPE",constraints.get(pin).get("PULL_TYPE"))
```

## Step 3: Place - Using A Random Placer Algorithm
The next step is placing the remaining **EDIFCellInst**s on the chip. An exception to this is **EDIFCellInst**s of types *VCC* and *GND*. This is because there is no one specific location for them; there are **BEL**s throughput the chip which have *HARD 1* (VCC) and *HARD 0* (GND) pins. Thus, to provide VCC and GND connections, a placement operation is not necessary and we only need to ensure that their corresponding **Net**s are routed properly. 

We will be using the simplest placement algorithm for this part i.e. a random placer. Moreover, also for simplicity, we will not be doing any packing for this design. The code and its breakdown is given below. Note that we have currently hardcoded support for the different technologies used in our design i.e. IBUF, OBUF, BUFGCTRL, LUT and FDRE. In a future commit, this will be replaced (if possible) with a combination of RapidWright APIs that can automatically derive the **SiteTypeEnum** for a given technology e.g. SLICEL or SLICEM for FDRE.  Also note that we have hardcoded the placement of BUFGCTRL. This is because the design is sufficiently constrained by the clock pin for us to know which of the vertical clock buffers we should be using. 

```python
def placeCells(design):
    cell_Names = design.getNetlist().getTopCell().getCellInsts().toArray().tolist()
    placement_list = []
    for cn in cell_Names:
        if ("GND" in str(cn.getCellType())) or ("VCC" in str(cn.getCellType())):
             continue

        elif ("IBUF" in str(cn.getCellType())) or ("OBUF" in str(cn.getCellType())):
            continue

        elif ("BUFGCTRL" in str(cn.getCellType())):
            cell = design.createCell(str(cn),cn)
            site = design.getDevice().getSite("BUFGCTRL_X0Y16")
            bel = site.getBEL("BUFGCTRL")
            design.placeCell(cell,site,bel)

        elif ("LUT" in str(cn.getCellType()) or "FDRE" in str(cn.getCellType())):
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
```

Since we will be creating and placing **Cell**s in **Design**, we pass **Design** as the input to the `placeCells` routine.  

```python
def placeCells(design):
```

As discussed above, we are going to loop over all **EDIFCellInst**s. To track locations which have been used, we also initialize `placement_list`; this list will contain **Site**/**BEL** tuples which are not available to an **EDIFCellInst**.  

```python
    cell_Names = design.getNetlist().getTopCell().getCellInsts().toArray().tolist()
    placement_list = []
    for cn in cell_Names:
```

Within the loop, we start by skipping **EDIFCellInst**s of type *GND*, *VCC*, *IBUF* and *OBUF*. 


```python
        if ("GND" in str(cn.getCellType())) or ("VCC" in str(cn.getCellType())):
             continue

        elif ("IBUF" in str(cn.getCellType())) or ("OBUF" in str(cn.getCellType())):
            continue
```

Next, we place the `BUFGCTRL` in our design. Note that since we have single clock source, there will only be one such **EDIFCellInst** (although it is possible for us to manually instantiate more - in which case we would apply the algorithm for `LUT` and `FDRE` (given below) here as well. 

We do the placement with a four step approach. First, we create a **Cell** in the design using the **EDIFCellInst**. Doing so ensures that the **Cell** inherits all properties of the **EDIFCellInst**, and greatly simplifies the complexity of **Cell** creation. Next, we create a **Site** where this **Cell** can be placed - in this case, we create a **Site** for `BUFGCTRL_X0Y16`.  Next, we select a **BEL** within the **Site** which can implement this **Cell** - in Xilinx 7-Series, this will always be the `BUFGCTRL` **BEL**. Finally, we call `placeCell` in **Design** to placed the **Cell** `cell` and the **Site** `site` and **BEL** `bel`.


```python
        elif ("BUFGCTRL" in str(cn.getCellType())):
            cell = design.createCell(str(cn),cn)
            site = design.getDevice().getSite("BUFGCTRL_X0Y16")
            bel = site.getBEL("BUFGCTRL")
            design.placeCell(cell,site,bel)
```


Doing placement for `LUT` and `FDRE` **EDIFCellInst**s is essentially the same steps as we saw for `BUFGCTRL` above. However, in this case, we will not hardcode the **Site** and **BEL** locations. To be able to leverage certain RapidWright APIs to find compatible location, it is critical that a valid **Device** has been added to **Design** - otherwise, these routines will fail. 

The first step is again to create a **Cell** using the **EDIFCellInst**. 

```python
        elif ("LUT" in str(cn.getCellType()) or "FDRE" in str(cn.getCellType())):
            cell = design.createCell(str(cn),cn)
```

Next, we get a list of possible **BEL**s where this **Cell** can be placed. This can be done by first calling the `getCompatiblePlacements()` routine in **Cell**, and then filtering the results based on the target **Site** type. For now, we have hardcoded the **SiteTypeEnum** to be `SLICEL` since this type of **Site** can implement look up tables, flip flops and carry chains. Note that a **BEL** does not store location data. This means that `bels` will not contain every compatible **BEL** in every `SLICEL` on the chip - rather, it will only be a list of unique **BEL**s that will exist in any `SLICEL` **Site**.   

```python
            bels = cell.getCompatiblePlacements().get(SiteTypeEnum.SLICEL)
```

Next, get a list of possible **Site**s where this **Cell** can be placed. We again using `SLICEL` as the type, but now call the `getAllCompatibleSites()` routine in **Design**. 


```python
            sites = design.getDevice().getAllCompatibleSites(SiteTypeEnum.SLICEL) 
```

Now that we have list of potential **BEL**s and **Site**s, let's randomly pick a **Site**/**Bell** tuple. We do this inside a `while` loop so that we can keep picking tuples till we find an unassigned one. 

```python   
            running = 1
            while running:
                bel_name = list(bels)[random.randint(0,len(bels)-1)]
                site = sites[random.randint(0,len(sites)-1)]
                bel = site.getBEL(bel_name)
```

If the tuple is not already in `placement_list`, we can use it to place the **Cell** `cell`. We also append it to `placement_list` to indicate that it has now been assigned. 

```python
                if (str(site)+"/"+str(bel)) not in placement_list:
                    placement_list.append((str(site)+"/"+str(bel))) 
                    running = 0
                    design.placeCell(cell,site,bel)
```

## Step 4: Create Physical (Un-Routed) Nets from Logical Netlist
Now that we have created and placed our **Cell**s, lets create the physical **Net**s that will connect them together using information provided by the **EDIFNet**s in our **EDIFCell** `topCell`. We will use three routines for this. 

### External Port Check
The first routine checks if a **Net** corresponds to the *PAD* - *I/O Buffer* connection we discussed in Step 2. 
```python
def checkIfTopPort(topCell,i):
    for key in topCell.getPortMap().keys():
        if str(i) == key: return 1
    return 0
```

### Create Net Objects
The next routine is used to create **Net**s using the remaining **EDIFNet**s. Note that doing so will only initialize some basic variables within the **Net**, such as its name. Other information, such as the physical pins corresponding to **EDIFPortInst**s in an **EDIFNet** cannot be automatically derived - they require a separate routine as we will implement later. The code for this is given below. 

The routine takes as input the **Design**. For each **EDIFNet** in the **EDIFCell** `topCell`, we first remove the corresponding **Net** if it already exists, and then we call `createNet()` to create a **Net** if the **EDIFNet** is not a *PAD* - *I/O Buffer* connection and if it does not correspond to a *VCC* or *GND* connection. 

```python
def createNets(design):
    netlist = design.getNetlist()
    topCell = netlist.getTopCell()
    for i in design.getNets().toArray():
        design.removeNet(i)
    for i in topCell.getNets().toArray():
        if checkIfTopPort(topCell,i): continue
        if i == EDIFTools.getStaticNet(NetType.VCC, topCell, netlist): continue
        if i == EDIFTools.getStaticNet(NetType.GND, topCell, netlist): continue 
        design.createNet(i)
```

### Create Pin Objects For Each Net Object
The last routine adds **SitePinInst**s to each **Net**. Note that a **Net** connects pins of *Site*s, not *BEL*s - as discussed above, **Cell**s are implemented as **BEL**s, and there are be multiple **BEL**s in a single **Site**. Therefore, as we can see from the diagram below of a basic logic block in the Xilinx 7-Series architecture, not all *BEL* pins are directly connected to *Site* pins. The total number of *Site* pins is less than the total number of *BEL* pins, making it impossible to connect all *BEL* pins to *Site* pins simultaneously. This is why packing is a critical process: it increases the number of intra-*Site* connections so that fewer *BEL* pins that need access to *Site* pins, and thus results in higher utilization of a logic block. 



![Xilinx 7-Series Logic Block](https://github.com/asanaullah/images/blob/master/pnr/0/logic_block_xilinx_7_series.PNG)


To multiplex the limited *Site* pins, a large number of MUXs (also known as *Routing BELs*) are implemented in a logic block. By setting the appropriate **SitePIP** (discussed earlier) for a *Routing BEL*, we can connect a *BEL* pin to a *Site* pin, and then add the corresponding **SitePinInst** for this *Site* pin to the **Net**. The code and its breakdown is given below. 

```python
def createNetPins(design):
    netlist = design.getNetlist()
    topCell = netlist.getTopCell()
    for physNet in design.getNets().toArray():
        if checkIfTopPort(topCell,physNet): continue
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
```

The routine `createNetPins` takes the **Design** as input and updates the **Net**s in it.  

```python
def createNetPins(design):
```

We use the `getNetlist()` and `getTopCell()` calls to get the **EDIFCell** for a design. Then, we loop over all **Net**s created in the previous routine. 

```python
    netlist = design.getNetlist()
    topCell = netlist.getTopCell()
    for physNet in design.getNets().toArray():
```

Next, we use our custom `checkIfTopPort()` routine from earlier in this Step to determine if we should skip the **Net**. If the **Net** corresponds to *PAD*-*I/O Buffer* connectivity, then there is no inter-*Site* wiring required, and hence the **Net** will not have any **SitePinInst**s. 

```python
        if checkIfTopPort(topCell,physNet): continue
```
If the above condition is not met, we can start adding **SitePinInst**s to this **Net**. To do this, we first get the **EDIFNet** for this **Net**, and then loop over all **EDIFPortInst**s in the **EDIFNet**. 

```python
        edifNet = physNet.getLogicalNet()
        portInsts = edifNet.getPortInsts().toArray().tolist()
        for portInst in portInsts:
```

If the **EDIFPortInst** is static source, i.e. `VCC` or `GND`, we will skip it. 

```python
            if portInst.isPrimitiveStaticSource(): continue
```

For each non-static source based **EDIFPortInst**, we get the **EDIFCellInst** `portCell` to which it is attached, and then from the **EDIFCellInst** we get the corresponding **Cell** `physCell`. 

```python
            portCell = portInst.getCellInst()
            physCell = design.getCell(str(portCell))
```

To create a **SitePinInst**, we need to know the name of the corresponding *Site* pin. To get this, we call the `getSitePinFromPortInst()` routine from `physCell`. If an empty list is passed to the routine, `siteWires` in our case, then the routine will add to it an ordered list of wires between the *BEL* pin, and the *Site* pin it can connect to. The name of the *Site* pin will be the last entry in this ordered list. 

```python
            siteWires = []
            ret = physCell.getSitePinFromPortInst(portInst,siteWires)    
```
From `physCell`, we get the **SiteInst**. The formal difference between **SiteInst** and **Site**, according to the RapidWright documentation, is "this class represents the instance of a site as configured by the user design...It differs from the Site class in that it carries configuration data from the user design whereas Site is static and only represents available constructs in the silicon". Basically, **SiteInst** will have more information based on our design, and this information can be modified (unlike the information in **Site**). We will see this in more detail in the next Step. 

```python
            siteInst = physCell.getSiteInst()
```
Finally, we call the `createPin()` routine in the **Net** using the **EDIFPortInst** direction, the *Site* pin name, and the **SiteInst**. 

```python        
            physNet.createPin(portInst.isOutput(),siteWires[len(siteWires)-1],siteInst)
```

One observation to make here is that we have assumed all **EDIFNet**s are inter-Site. This will not be the case if we do packing, in which case the use of `getSitePinFromPortInst()` would be incorrect. Therefore, if packing is done, we need to have a further check which skips any intra-*Site* **EDIFNet**s. 


## Step 5: Routing Site Wires

Once we've set up our **Net**s to represent inter-*Site* connectivity, we need to route the *Site* wires to implement the require intra-*Site* connectivity. As discussed earlier, this effectively means turning on appropriate **SitePIP**s in our **Design**'s **SiteInst**s. The code and its breakdown is given below. Note that we have hardcoded support for *BUFGCTRL*, *FDRE* and *LUT* here - while we initially did this using a generic technology-independent algorithm, the complexity of the process made it far too non-intuitive for the purposes of this demo. Also note that while **Design** has a routine `routeSites()` that should do all the processes below automatically, we found that this routine alone was not sufficient in routing the *Site* wires - hence, the `routeSitePIPs()` routine is needed. 


```python
def routeSitePIPs(design):
    netlist = design.getNetlist()
    topCell = netlist.getTopCell()
    for edifNet in topCell.getNets().toArray():
        if checkIfTopPort(topCell,edifNet): continue 
        if edifNet == EDIFTools.getStaticNet(NetType.GND, topCell, netlist): continue 
        for portInst in edifNet.getPortInsts().toArray():
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
```

The `routeSitePIPs()` routine takes the **Design** as its input and modifies it directly. 

```python
def routeSitePIPs(design):
```

We begin by looping over all **EDIFNet**s in the design, as long as they do not correspond to the *PAD*-*I/O Buffer* connectivity and the *GND* connections - we still have to handle *VCC* connections since, unlike *GND*, *VCC* connections are not routed internally in a *Site*. 

```python
    netlist = design.getNetlist()
    topCell = netlist.getTopCell()
    for edifNet in topCell.getNets().toArray():
        if checkIfTopPort(topCell,edifNet): continue 
        if edifNet == EDIFTools.getStaticNet(NetType.GND, topCell, netlist): continue 
```
For each **EDIFNet** in `topCell`, we loop over every **EDIFPortInst** as long as it is not a source for *VCC*. 

```python
        for portInst in edifNet.getPortInsts().toArray():
            if portInst.isPrimitiveStaticSource(): continue
```

Next, we use an **EDIFPortInst** to get the corresponding **EDIFCellInst**, **Cell** and **SiteInst**. 

```python
            portCell = portInst.getCellInst()
            physCell = design.getCell(str(portCell))
            siteInst = physCell.getSiteInst()
```

For `BUFGCTRL`, we need to set the **SitePIP**s for the `CE0` and `S0` pins so that these *BEL* pins can be connected *Site* pins, which in turn can then be connected to a *VCC* source external to the *Site*. To turn on a **SitePIP**, we need to first select it from its **SiteInst**, then call the `addSitePIP()` routine from **SiteInst**, and finally call the `routeSite()` routine again from **SiteInst**. To find the **SitePIP** of interest, we use the earlier trick of working with wires within the *Site* i.e. the `getSitePinFromPortInst()` routine in **Cell**. In the previous Step, we took the last value of `siteWires` since it corresponded to the **SitePin**'s name. This time, we will use both the first and last values. We beging by using the first value since it is the output wire of the *Routing BEL* that drives that **BELPin**. This wire is formatted as "<*Routing BEL Name*>\_OUT". By splitting the string at "\_", we can find the name of this *Routing BEL*. Next, we take the last value of `siteWires` - since the size of `siteWires` will always be 2 for `BUFGCTRLs`, we simply do `siteWires[1]`. We then call `getBELPins()` from **Site** using this wire name (which is also the **SitePin** name) and get a list of all **BELPin**s connected to it. We are now one step away from getting the **SitePIP** of interest. If we can find the correct **BELPin**, we can call the `getSitePIP()` routine from the **SiteInst** (i.e. which input of the MUX do we want to select?). Knowing the name of the *Routing BEL* allows us to determine which pins in the list are its inputs. Since we are dealing with `BUFGCTRL`, there we be only two such pins. From these, we select the non-inverting input by leveraging the "\_B" suffix of the inverting input. Once we have the **BELPin** name, we get the corresponding **SitePIP** through a `getSitePIP()` call, followed by a `addSitePIP()` call on this **SitePIP**, and then finally a `routeSite()` call for the **SiteInst**. 

```python
            if "BUFGCTRL" in str(physCell.getType()):
                if (not("CE0" in str(portInst.getName()))) and (not("S0" in str(portInst.getName()))): continue
                siteWires = []
                ret = physCell.getSitePinFromPortInst(portInst,siteWires)
                bel = siteWires[0].split("_")[0] 
                belpin = ""
                for bp in siteInst.getSite().getBELPins(siteWires[1]).tolist():
                    if (str(bel) in str(bp)) and (not("_B" in str(bp))):
                        belpin = bp
                        break
                sitepip = siteInst.getSitePIP(belpin)
                siteInst.addSitePIP(sitepip)
                siteInst.routeSite()
```

`FDRE` (i.e. D Flip Flops) are substantially more complicated than `BUFGCTRL`s since we not only need to deal with both data and control pins, but we also have to deal with both input and output pins (`BUGCTRL` only required dealing with input pins), and we also have to deal with the different types of `FDRE` connectivity in a logic block (4 of the 8 `FDRE`s in a logic block have a *Routing BEL* on their data input, and the remaining 4 have it on their data output). As a result, we will have a separate algorithm for each **BELPin** in the `FDRE` **BEL**. 
```python
            elif "FDRE" in str(physCell.getType()):
```
Let's start with the `CE` (chip enable) pin. All `FDRE` chip enable pins are connected together, which means enabling one `FDRE` will enable all of them. The *Routing BEL* named `CEUSEDMUX` is used to select the state of `CE` pins. `CEUSEDMUX` has two inputs - one for hardwiring the connection to logic 1 and the other for providing an external (to the *Site*) signal to dynamically modify the `CE` value. In our case, since our `FDREs` are always on, we will select the hardwired logic 1. This would correspond to the **BELPin** name `1` in the **BEL** `CEUSEDMUX`. Once we have the **BELPin**, we can then call `addSitePIP()` and `routeSite()` to turn the **SitePIP** on.  

```python
                if ("CE" == str(portInst.getName())):
                    belpin = siteInst.getSite().getBEL("CEUSEDMUX").getPin("1")
                    sitepip = siteInst.getSitePIP(belpin)
                    siteInst.addSitePIP(sitepip)
                    siteInst.routeSite()  
```

`R`, i.e. the reset pin, follows the same approach as `CE`, except that we will tie it to *GND*, i.e. logic 0. The **BEL** here is `SRUSEDMUX` and the **BELPin** is `0`.

```python
                elif ("R" == str(portInst.getName())):
                    belpin = siteInst.getSite().getBEL("SRUSEDMUX").getPin("0")
                    sitepip = siteInst.getSitePIP(belpin)
                    siteInst.addSitePIP(sitepip)
                    siteInst.routeSite()  
```

The (routing) **BEL** on the clock input selects between providing the clock as is, or inverting it. Since all the clocks in our design are positive edge triggered, we can hardcode this as well. The **BEL** here is called `CLKINV`, and the **BELPin** for the non-inverting input is `CLK`. Note that all `FDREs` share the same clock line. 

```python
                elif ("C" == str(portInst.getName())):
                    belpin = siteInst.getSite().getBEL("CLKINV").getPin("CLK")
                    sitepip = siteInst.getSitePIP(belpin)
                    siteInst.addSitePIP(sitepip)
                    siteInst.routeSite()
```
Now we get to the data pins. Let's start with `Q` i.e. the data output pin. This is similar to the control input pins for `BUFGCTRL`, except that now the pin may be connected to the input of a  *Routing BEL* instead of its output. If there is no *Routing BEL* on the `Q` pin, we don't need to do anything. This is relatively simply check to make, leveraging yet again the highly useful `getSitePinFromPortInst()` routing. If no *Routing BEL* is present on the `Q` pin, the length of the `siteWires` list will be 1 and we can move on to the next loop iteration.  

If the size of `siteWires` is greater than 1, we need to find the input pin of the *Routing BEL* to which `Q` is connected. Note that the size of `siteWires` will be a maximum of 2 since there can only be a maximum of 1 *Routing BEL* on the output path. The algorithm here is similar to `BUFGCTRL` - we used `siteWires[1]` to get the name of the *Routing BEL*, and then scan all **BELPin**s connected to `Q` (using `getBELPins(siteWires[0])`) to find the **BELPin** belong to this *Routing BEL*. Note that a string split here is not necessary to get the *Routing BEL*'s name - it is also possible to get the *Routing BEL*'s name by get the **BELPin** on the wire name stored in `siteWires[1]`, and then using a series of routines to get the name of the corresponding **BEL**. 

```python
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
```
The last pin for `FDRE` is the data input pin `D`. If there is a *Routing BEL* present at the `FDRE` data input (determined by looking at the `siteWires` list size), we reuse the `BUFGCTRL` algorithm to turn on the appropriate **SitePIP**. The only difference here is that there will only be one input pin of the *Routing BEL* with the same name as the **SitePin** since the option for inverting the data input is not available. 

As discussed earlier, the assumption here is that there is no intra-*Site* **EDIFNet**s. If such a connectivity did exist, we likely would not be able to use `getSitePinFromPortInst()` in the exact way that we are doing currently. Additional code would be required to find the one or more **SitePIP**s that will route the intra-*Site* **EDIFNet**. 

```python                
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
```
Finally, we get to the last type of technology i.e. `LUT` (Look Up Table). The algorithm here is similar to `Q` for `FDRE`. Note that the `LUT` inputs are always directly connected to *Site* pins, while the output is always connected to a *Routing BEL*. 

```python
            elif "LUT" in str(physCell.getType()):
                siteWires = []
                ret = physCell.getSitePinFromPortInst(portInst,siteWires)
                if len(siteWires)>1 and portInst.isOutput():
                    belpin = ""
                    for bp in siteInst.getSite().getBELPins(siteWires[0]).tolist():
                        if str(siteInst.getSite().getBELPins(siteWires[1]).tolist()[0]).split(".")[0] in str(bp):
                            belpin = bp
                            break
                    sitepip = siteInst.getSitePIP(belpin)
                    siteInst.addSitePIP(sitepip)
                    siteInst.routeSite()
```


## Step 6: Route Clocks
After finishing the intra-*Site* routing, we will now look at routing the **Net**s. As mentioned previously, routing a **Net** is effectively adding to it a list of **PIP**s that must be set. Routing algorithms are quite complex and it is difficult to write a trivial implementation. Even if we ignore timing requirements, the sheer size of the chip's routing fabric (and Arty is supposed to be a low end board) means doing naive breadth-first or depth-first traversals can take a very long time to complete. Moreover, as we will see later on, there are a number of constraints to take into account as well. For example, clock based **Net**s are constrained to pass through horizontal clock buffers before they can drive logic, even though there is not **Cell** for a horizontal clock buffer in our design. 

Luckily, RapidWright does provide a **Router** class for doing the routing. The source code for the routing algorithm is given [here](https://github.com/Xilinx/RapidWright/blob/master/src/com/xilinx/rapidwright/router/Router.java). 

Unluckily, the routing algorithm is for UltraScale+ FPGAs. 

Luckily, the algorithm is still applicable to 7-series FPGAs. 

Unluckily, it will not handle clocking and only works for if the design is placed in a specific way (i.e. for certain seed values used for our random placer).

Luckily, we can split the routing process. 

Since it is too complex to port the native RapidWright one, we will build a partial router that will route the clocks in our design, lock this routing, and then call the native RapidWright router for the remaining **Net**s. With regards to the seed value, we will put the RapidWright router call in a "try-catch" block and try different seed values still be find one that works. 

Our algorithm for routing clocks will be based on the "Basic Routing" example given [here](https://www.rapidwright.io/docs/FCCM19_Workshop.html).


### Some More Imports
Let's start by importing in some non-RapidWright Classes. 

```python
from java.util import HashSet
from java.util import List
import Queue
from Queue import PriorityQueue
```

### Get Nets Driven By Vertical Global Clock Buffers (BUFGCTRL For 7-Series FPGAs)
Next, we want to identify all the clock **Net**s in our design. To do this, we use a `get_main_clock_nets()` routine which finds all **Net**s who are being driven by a `BUFGCTRL`. Note that we can call `getSiteTypeEnum()` even though `BUFGCTRL` is technically a *BEL* - this is because the *Site* will also have `BUFGCTRL` in its name.  

``` python
def get_main_clock_nets(design):
    nets = []
    for net in design.getNets():
        pins = net.getPins()
        for pin in pins:
            bel_type = pin.getSite().getSiteTypeEnum().toString()
            if "BUFGCTRL" in bel_type and pin.isOutPin():
                if not net in nets:
                    nets.append(net)
    return nets
```


### Create Horizontal Clock Buffers (BUFHCE For 7-Series FPGAs)
The **Net**s we got in the previous step connect `BUFGCTRL` output pins to the clock input pins of logic blocks. Note that a `BUFGCTRL` is a vertical clock buffer, meaning that it can only drive wires that run vertically through the center of the FPGA chip. So how is it able to drive clock pins in a 2-D plane? The answer here is horizontal clock buffers - `BUFHCE` specifically for Xilinx 7-Series FPGAs. There are banks of multiple `BUFHCE`s located at different points of the vertical clock spline running through the middle of the 7-Series FPGA chip. Depending on which region of the chip our logic is located, we need to use an appropriate `BUFHCE` to ensure the clock signal can be routed to it. Note that use of `BUFHCE` is not reflected in the logical netlist. The is likely because, unlike `BUFGCTRL`, we do not know how many individual `BUFHCE` we will need and what logic will be driven by a given `BUFHCE`. Moreover, Vivado does not list `BUFHCE` as a component in the physical netlist - likely because `BUFHCE` are treated as "route-through" instead of actual netlist components. 

To get a better understanding of the clock routing process, we will treat `BUFHCEs` as **Cell**s in our design and manually instantiate them. To create the required `BUFHCEs`, we need routines for: i) creating a cost function to find the appropriate `BUFHCE` *Site* for a given clock sink, ii) selecting a `BUFHCE` from the closest bank, iii) creating a `BUFHCE` **Cell** and updating **Net**s. 


Let's start with the cost function. In our case, we are going for the simple [Manhattan distance](https://xlinux.nist.gov/dads/HTML/manhattanDistance.html) between two **Site**s. We use "Rpm" routines for this since they return the physical coordinates of a **Site** (as opposed to logical). 
```python
def cost (s1, s2):
    return abs(s1.getRpmX() - s2.getRpmX()) + abs(s1.getRpmY() - s2.getRpmY())
```

Next, we write a `closestSite` routine which returns the nearest *Site* to the **Site** `s1` from a list of possible **Site**s `possible_sites`. We simply evaluate the cost for each pair, and built a Priority Queue for the resulting tuple. Once we've iterated over all possibilities in `possible_sites`, we return the **Site** with the tuple with the lowest cost. 

```python
def closestSite (s1, possible_sites):
    p = PriorityQueue()
    for s2 in possible_sites:
        p.put((cost(s1,s2),s2))
    return p.get()
```

Finally, we get to our big routine `createBUFH`. This will be responsible for creating `BUFHCE` **Cell**s, updating existing **Net**s, and creating new **Net**s. The code and its breakdown is given below. 


```python
def createBUFHs(design):
    topCell = design.getNetlist().getTopCell()
    bufhce_sites =  design.getDevice().getAllCompatibleSites(SiteTypeEnum.BUFHCE).tolist()
    for clk_net in get_main_clock_nets(design):
        pins = clk_net.getSinkPins()
        for i in range(len(pins)):
            pin = pins[i]
            pin_site = pin.getSite()
            bufhce_site = closestSite(pin_site,bufhce_sites)[1]

            exists = -1
            for j in range(i):
                if design.getCell(clk_net.getName() + "_bufhce_"+str(j)):
                    if str(design.getCell(clk_net.getName() + "_bufhce_"+str(j)).getSite()) == str(bufhce_site):
                        exists = j

            if exists == -1:
                loc = str(bufhce_site) +"/BUFHCE"
                ret = design.createAndPlaceCell(clk_net.getName() + "_bufhce_"+str(i),Unisim.BUFHCE,loc) 
                ret.connectStaticSourceToPin(NetType.VCC ,"CE")
                ret.getSiteInst().addSitePIP(ret.getSiteInst().getSitePIP(ret.getSiteInst().getBEL("CEINV").getPin("CE")))
                ret.getSiteInst().routeSite()
                net = design.createNet(clk_net.getName() + str(i))
                clk_net.removePin(pin)
                clk_net.addPin(SitePinInst("I",ret.getSiteInst()))
                net.addPin(SitePinInst("O",ret.getSiteInst()))
                net.addPin(pin)
                topCell.getNet(clk_net.getName()+str(i)).createPortInst("O",ret)
                topCell.getNet(clk_net.getName()+str(i)).addPortInst(topCell.getNet(clk_net.getName()).getPortInsts().toArray().tolist()[0])
                topCell.getNet(clk_net.getName()).createPortInst("I",ret)
                topCell.getNet(clk_net.getName()).removePortInst(topCell.getNet(clk_net.getName()).getPortInsts().toArray().tolist()[0])
            else:
                net = design.getNet(clk_net.getName() + str(exists))
                clk_net.removePin(pin)
                net.addPin(pin)
                topCell.getNet(clk_net.getName()+str(exists)).addPortInst(topCell.getNet(clk_net.getName()).getPortInsts().toArray().tolist()[0])
                topCell.getNet(clk_net.getName()).removePortInst(topCell.getNet(clk_net.getName()).getPortInsts().toArray().tolist()[0])                              
```

The routine takes the **Design** as its input, updates it directly and does not return anything. 

```python
def createBUFHs(design):                     
```

Given the **Design**, we get its **EDIFCell** `topCell` and a list of **Site**s that contain the `BUFHCE` **BEL**.  

```python
    topCell = design.getNetlist().getTopCell()
    bufhce_sites =  design.getDevice().getAllCompatibleSites(SiteTypeEnum.BUFHCE).tolist()                 
```

We then set up a nested loop which iterates over each `BUFGCTRL` driven **Net**, and then each sink **SitePin** in that **Net**. If a design has more than one clock inputs, we would need to keep track of and remove any used `BUFHCE` from `bufhce_sites` after each outer loop iteration. Here, we've skipped it since our design only has one clock input. 

```python
    for clk_net in get_main_clock_nets(design):
        pins = clk_net.getSinkPins()
        for i in range(len(pins)):         
```

For each `pin`, we get its **Site** and then call the `closestSite` routine. From the returned tuple, we can get the target `BUFHCE` **Site**. 

```python
            pin = pins[i]
            pin_site = pin.getSite()
            bufhce_site = closestSite(pin_site,bufhce_sites)[1]                    
```

Before we create a new **Cell**, we need to check if it already exists for the `BUFHCE` at `bufhce_site`. The naming convention we are using for our `BUGHCE` **Cell**s is "< **Net**-name >\_bufhce\_< sink-pin-loop-index >". We initially set `exists` to be `-1`. For each pin that we have looped over thus far in the **Net**, we check to see if the `BUFHCE` **Cell** for it has been created. If true, then we check if the **Site** for this **Cell** matches our target **Site** `bufhce_site`. If there is a match, we overwrite `exists` with the matched index. 

```python
            exists = -1
            for j in range(i):
                if design.getCell(clk_net.getName() + "_bufhce_"+str(j)):
                    if str(design.getCell(clk_net.getName() + "_bufhce_"+str(j)).getSite()) == str(bufhce_site):
                        exists = j                 
```

If no match was found, `exists` remains `-1` and we need to do the following:

1. Create a location string `loc` using the **Site** and **BEL** name. In this case, **Site** is `bufhce_site` and it will only have a single `BUFHCE` **BEL**.
2. Create and place a new **Cell** at this location using the naming convention shown earlier. 
3. Connect (but not route) the chip enable pin `CE` for this **Cell** to `VCC`. 
4. Add **SitePIP**.
5. Route **SiteInst**.
6. Create a new **Net** using the inner loop index.
7. Remove the current `pin` from the `BUFGCTRL` **Net**. 
8. Add the input pin `I` of the `BUFHCE` **Cell** to the `BUFGCTRL` **Net**. 
9. Add the output pin `O` of the `BUFHCE` **Cell** to the new `BUFHCE` **Net**. 
10. Add `pin` to the new `BUFHCE` **Net**. 

At this point, we've made changes to the physical netlist. Let's reflect these changes in the logical netlist as well. 

11. Create a new **EDIFPortInst** for the output pin of `BUFHCE` and add it to the **EDIFNet** corresponding to the new `BUFHCE` **Net**. Note that we did not need to create the **EDIFNet** as this was done automatically when we created the **Net**. 
12. Add the **EDIFPortInst** for the `pin` to this **EDIFNet**. How do we find this **EDIFPortInst**? Since we created the physical **Net**s directly from **EDIFNet**s, the ordering of `pins` and **EDIFPortInst**s should be the same. Moreover, we know that the `getPortInsts()` routine will list input **EDIFPortInst**s first. Finally, we also know that once we have added an **EDIFPortInst** to the new **EDIFNet**, we will be removing it later. Using these three pieces of information, we get a list of **EDIFPortInst**s in the `BUFGCTRL` **EDIFNet** and then get the first element in this list. 
13. Create a new **EDIFPortInst** for the input pin of `BUFHCE` and add it to the **EDIFNet** corresponding to the `BUFGCTRL` **Net**. 
14. Remove the first element in the list returned by `getPortInsts()` for the `BUFGCTRL` **EDIFNet**. 


```python
            if exists == -1:
                loc = str(bufhce_site) +"/BUFHCE"
                ret = design.createAndPlaceCell(clk_net.getName() + "_bufhce_"+str(i),Unisim.BUFHCE,loc) 
                ret.connectStaticSourceToPin(NetType.VCC ,"CE")
                ret.getSiteInst().addSitePIP(ret.getSiteInst().getSitePIP(ret.getSiteInst().getBEL("CEINV").getPin("CE")))
                ret.getSiteInst().routeSite()
                net = design.createNet(clk_net.getName() + str(i))
                clk_net.removePin(pin)
                clk_net.addPin(SitePinInst("I",ret.getSiteInst()))
                net.addPin(SitePinInst("O",ret.getSiteInst()))
                net.addPin(pin)
                topCell.getNet(clk_net.getName()+str(i)).createPortInst("O",ret)
                topCell.getNet(clk_net.getName()+str(i)).addPortInst(topCell.getNet(clk_net.getName()).getPortInsts().toArray().tolist()[0])
                topCell.getNet(clk_net.getName()).createPortInst("I",ret)
                topCell.getNet(clk_net.getName()).removePortInst(topCell.getNet(clk_net.getName()).getPortInsts().toArray().tolist()[0])                 
```

If `exists` was updated, the `BUFHCE` **Cell**, its **Net** and its input/output **EDIFPortInst**s already exist. The only thing we need to do is add/remove pins and ports.

```python
            else:
                net = design.getNet(clk_net.getName() + str(exists))
                clk_net.removePin(pin)
                net.addPin(pin)
                topCell.getNet(clk_net.getName()+str(exists)).addPortInst(topCell.getNet(clk_net.getName()).getPortInsts().toArray().tolist()[0])
                topCell.getNet(clk_net.getName()).removePortInst(topCell.getNet(clk_net.getName()).getPortInsts().toArray().tolist()[0])                              
```

### Get Nets Driven By Horizontal Clock Buffers (BUFHCE For 7-Series FPGAs)

Now that we have two types of clock networks, let's write the routine `get_secondary_clock_nets()` for returning all `BUFHCE` driven **Net**s.  

```python
def get_secondary_clock_nets(design):
    nets = []
    for net in design.getNets():
        pins = net.getPins()
        for pin in pins:
            bel_type = pin.getSite().getSiteTypeEnum().toString()
            if "BUFHCE" in bel_type and pin.isOutPin():
                if not net in nets:
                    nets.append(net)
    return nets
```


### Routing Cost Function

Once we have finished setting up our **Net**s, we can now start working on routing them. The first step here is a cost function which operates on two **RouteNode**s. As we outlined eariler, **RouteNode**s keep track of the *Wires* and *PIPs* traversed. While both of our inputs are **RouteNode**s, only one is moving through the chip. The `snk` **RouteNode** is static: it represents the destination/sink of the connection. The `curr` **RouteNode**starts from the connection source and is the one that is moving. Note that we could also flip this in our routing and trace a path from sink to source. 

The `BUFHCE` cost function earlier dealt with placement and hence a simple Manhattan distance computation was sufficient. Since we are now dealing with routing, something more complex is needed. In this case, we follow the RapidWright tutorial and factor in the number of "hops" done thus far by the **RouteNode** - given by the `getLevel()' routine. More "hops" can mean a longer route and high routing fabric resource usage, both of which we want to minimize. We do scale the `getLevel()` output so that it does not dominate the cost function too quickly. 

```python
def costFunction(curr, snk):
    return curr.getManhattanDistance(snk) + curr.getLevel()/8  
```


### Find Route Between Two RouteNode Objects In A Clock Net Object

Next we write the routine `findRoute` which takes a sink **RouteNode** `snk` and a Priority Queue `q` of **RouteNode**s as input, and returns all **PIP**s traversed in a successful route. When the routine is called, `q` only has a single entry i.e. the source **RouteNode**. Before we start routing, we also instantiate a HashSet `visited` to keep track of already traversed fabric. Note that there typically would be third input to this routine: a list of all **PIP**s used by **Net**s that have already been routed. This list would ensure that **Net**s don't cross each other. However, since we are effectively only routing a single signal, this can be skipped for now. 

The overall goal here, while the Priority Queue is not empty, is to take the lowest cost entry in the Priority Queue and check if it matches with the sink **RouteNode**. If there is a match, we have successfully routed the signal and we call the `getPIPsBackToSource()` from the `curr` **RouteNode** to get the required **PIP**s. If there is no match, we create a new set of **RouteNode**s using the `curr` **RouteNode** and every **Wire** branching out from it. We then evalue the costs for these new **RouteNode**s and add them to the Priority Queue. Since these **RouteNode**s were created from `curr`, they will  automatically copy over all path encountered by `curr` and add it to their own local information. 

If the Priority Queue empties out, the routing is deemed to have failed. Note that it is also possible to implement (and has been implemented in the RapidWright tutorial) a watchdog timer to support timeout functionality if routing is taking much longer than it should. 

```python
def findRoute(q, snk):
    visited = HashSet()
    while(not q.isEmpty()):
        curr = q.poll()
        if(curr.equals(snk)):
            return curr.getPIPsBackToSource()
        visited.add(curr)
        for wire in curr.getConnections():
            nextNode = RouteNode(wire,curr)
            if visited.contains(nextNode): continue
            curr_cost = costFunction(nextNode,snk)
            nextNode.setCost(curr_cost)
            q.add(nextNode)
    # Unroutable situation
    print "Route failed!"
    return []
```

### Route Individual Sinks And Add Unique PIPs For Each Clock Net Object

To drive the `findRoute()` routine, we write the `routeClockNet()` routine. `routeClockNet()`  takes as input a target **Net**, finds the list of **PIPs** in a successfully routed connection, and adds them to the **Net**. For each sink in this **Net**, we create a new Priority Queue and add the **Net** source's **RouteNode** to it. This is followed by a call to `findRoute()`. The results of all `findRoute()` calls for this **Net** are stored in a list called `path`. Once we have processed all sinks, we then remove duplicate **PIP** entries in `path` and add it to the **Net** using the `setPIPs()` routine.   

```python 
def routeClockNet(net):
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
```


### Putting It All Together
Now that we have all our routines, let's put it all together in the `routeClocks()` routine. 

```python
def routeClocks(design):
    createBUFHs(design)
    for net in get_main_clock_nets(design):
        routeClockNet(net,usedPIPs)        
    for net in get_secondary_clock_nets(design):
        routeClockNet(net,usedPIPs)
```



## Step 7: Route Remaining Design Using The Native RapidWright Design Router
To route the rest of the design, we need to call `routeDesign()` from the **Router** class. However, before we do that, we need to lock the clock routing to prevent it from getting overwritten. And once the remaining signals are routed, we will unlock the clock routing. 

```python
def designRouter(design):
    for net in get_main_clock_nets(design):
        net.lockRouting()   
    for net in get_secondary_clock_nets(design):
        net.lockRouting()               
    Router(design).routeDesign()
    for net in get_main_clock_nets(design):
        net.unlockRouting()
    for net in get_secondary_clock_nets(design):
        net.unlockRouting()
```


## Step 8: FASM Generator
At this point, we have a placed and routed design. The final piece is generating the bitstream using an open source tool such as [Project Xray](https://github.com/SymbiFlow/prjxray). Doing so requires writing out a `.fasm` file which maps the physical netlist we just created to the specific FPGA configuration memory bits that must be set.  

Currently, this is still a work in process. We have provided an algorithm for it in the accompanying Jupyter Notebook file that can successfully map *LUTs* (including route-through *LUTs*), *FDREs*, *IO BUFs* and most signals. It is, however, unable to reliably map clock nets and bi-directional **PIPs**. As a result, for now we will use Vivado for bitstream generation. 


## Step 9: The Overall RapidWright Flow
In this Step, we will put together the overall RapidWright flow using everything we have built thus far. 

### Some More Imports
We begin by importing some more Classes. 

```python
import random
import os
```

### Putting Our RapidWright Routines Together 
The `run_rapidwright` requires a seed for random number generation (`seed`), the name of our **EDIFCell** (`topModule`), the device name (`device`), the JSON Yosys output (`filename`) and our design constraints (`constraints`). `run_rapidwright` does the following operations: 

1. Set the random number generation seed. 
2. Read the Yosys JSON file and build a logical netlsit. 
3. Get the **EDIFNetlist** and **EDIFCell** for the design. 
4. Place I/O buffers using user defined constraints. 
5. Place **Cell**s.
6. Create **Net**s and **SitePinInst**s in these **Net**s. 
7. Add and route **SitePIPs**. 
8. Run `routeSites()` again, but this time for the overall design instead of for a particular **SiteInst** - this was able to route the **SitePIP**s in the IO Buffers. 
9. Route clocks in the design. 

Since the routing can fail for certain seed values, we do the rest in a try block. 

10. Run the native RapidWright design router.
11. Map the physical netlist to FPGA configuration memory and write out the `.fasm` file. 
12. Write out a `.dcp` design checkpoint file that is used by Vivado to import the placed and routed design. 
13. If everything was successful, return `1`. Else, return `0`. 

```python
def run_rapidwright(seed, topModule,device,filename,constraints):
    random.seed(seed)
    design = read_json(filename,topModule,device)
    net = design.getNetlist()
    net.setDevice(design.getDevice())
    topCell = net.getCell("top")
    placeIOBuffers(design , constraints)
    placeCells(design)
    createNets(design)
    createNetPins(design)
    routeSitePIPs(design)
    design.routeSites() 
    routeClocks(design)
    try:
        designRouter(design)
        write_fasm(design)
        design.writeCheckpoint(topModule+".dcp")
        return 1
    except:
        return 0
```


### Running RapidWright
And finally, call `run_rapidwright` with incrementing seed values till the routine returns `1`.  

```python
for i in range(1000):
    if (run_rapidwright(i, topModule,device,filename,constraints)):
        print "Seed Value: " + str(i)
        break
```


## Step 10: The Overall Synthesis + P&R + Bitstream Generation Flow
In the last step, let's combine all the separate flows into one routine.  

### Run Yosys
We run Yosys from within the Jupyter Notebook using the command discussed earlier. 
```python
def run_yosys(topModule):
    yosys_cmd = """yosys -p "synth_xilinx -flatten -abc9 -nobram -arch xc7 -top """+topModule+"""; write_json """+topModule+""".json" """+topModule+""".v"""
    ret = os.system(yosys_cmd)
```    
    
    
    
### Generate Bitstream Using Project XRAY
If we are using Project XRAY for bitstream generation, we would need to call the following functions to generate the bitstream for our target Arty FPGA. 

```bash
${XRAY_UTILS_DIR}/fasm2frames.py --part xc7a35tcsg324-1 --db-root ${XRAY_UTILS_DIR}/../database/artix7 top.fasm > top.frames

${XRAY_TOOLS_DIR}/xc7frames2bit --part_file ${XRAY_UTILS_DIR}/../database/artix7/xc7a35tcsg324-1/part.yaml --part_name xc7a35tcsg324-1  --frm_file top.frames --output_file top.bit
```


### Generate Bitstream Using Vivado
If we are using Vivado for bitstream generation, we need to call the `write_bitstream` tcl command. We do not need to make a Vivado project for this. Instead, we first create a tcl script that will open the design checkpoint and write the bitstream, and then call Vivado without opening its GUI (assuming it has been added to `PATH`). 

```python
def generate_vivado_bistream(topModule):
    tcl_code="""
    open_checkpoint """+topModule+""".dcp
    write_bitstream -force """+topModule+"""
    """
    tcl_file = open(topModule+".tcl","w")
    ret = tcl_file.write(tcl_code)
    tcl_file.close()
    vivado_cmd = """vivado vivado_files/"""+topModule+""".xpr -nolog -nojournal -notrace -mode batch -source """+topModule+""".tcl"""
    ret = os.system(vivado_cmd)
```

### Putting It All Together

The final `main()` routine looks like this:

```python
run_yosys(topModule)

for i in range(1000):
    if (run_rapidwright(i, topModule,device,filename,constraints)):
        print "Seed Value: " + str(i)
        break

generate_vivado_bistream(topModule)
print "Done"
```


## Step 11: Programming The Bitstream Using OpenOCD
In the spirit of maximizing the use of open source tools, let's limit the use of Vivado to just bitstream generation and use another tool for programming. OpenOCD is one such tool that provides the JTAG capabilities needed to program the FPGA. It can be installed using:

```bash
sudo dnf install openocd
```

or built from source using:

```bash
tar -xf openocd-0.10.0.tar.bz2
cd openocd-0.10.0
./configure  --enable-ft2232_libftdi --enable-libusb0 --disable-werror
make
sudo make install
```

OpenOCD requires a device configuration file before it can program the device. The following is the configuration file `top.cfg` for Digilent Arty A7-35t. 

```bash
interface ftdi
ftdi_device_desc "Digilent USB Device"
ftdi_vid_pid 0x0403 0x6010
ftdi_channel 0
ftdi_layout_init 0x0088 0x008b
reset_config none
adapter_khz 10000
source [find cpld/xilinx-xc7.cfg]
```

And with that set up, we can go ahead and program the device with our bitstream. 

```bash
sudo openocd -f top.cfg  -c "init; pld load 0 top.bit; exit"
```

