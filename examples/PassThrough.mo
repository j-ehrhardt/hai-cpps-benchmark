model passThroughModule
  replaceable package Medium = Modelica.Media.Water.StandardWater;
  Modelica.Fluid.Interfaces.FluidPort_a port_in0(redeclare package Medium = Medium);
  Modelica.Fluid.Interfaces.FluidPort_b port_out0(redeclare package Medium = Medium);
  Modelica.Fluid.Pipes.StaticPipe pipe(
    redeclare package Medium = Medium,
    length = 1,
    diameter = 0.05);
equation
  connect(port_in0, pipe.port_a);
  connect(pipe.port_b, port_out0);
end passThroughModule;
