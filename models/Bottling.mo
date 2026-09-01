model bottlingModule
  replaceable package Medium = Modelica.Media.Water.StandardWater;
  parameter Real tankMinVol = 0.1;
  parameter Real tankMaxVol = 0.9;
  parameter Real pump_P401_V_flow_at_max_head = 0.000122;
  parameter Real pump_P401_V_flow_at_middle_head = 0.0002;
  parameter Real pump_P401_V_flow_at_min_head = 0.00025;
  parameter Real pump_P401_head_max = 2.045;
  parameter Real pump_P401_head_middle = 1.534;
  parameter Real pump_P401_head_min = 1.022;
  parameter Real closedValveOpening(min = 0, max = 1) = 1e-4;
  parameter Integer noiseSeed = 1;
  // anomalies 
  parameter Real anom_start = 2500;
  parameter Boolean anom_leaking = false annotation(Evaluate = false);
  parameter Boolean anom_valve_in0 = false annotation(Evaluate = false);
  parameter Boolean anom_pump50 = false annotation(Evaluate = false);
  parameter Boolean anom_pump75 = false annotation(Evaluate = false);
  Real var_valve_in(start=0.0); 
  Real var_pump_n(start=1.0);
  Real pump_n_in;
  Boolean fault_window_active;
  // ports
  Modelica.Fluid.Interfaces.FluidPort_a port_in0(redeclare package Medium = Medium) annotation(
    Placement(transformation(origin = {-90, 110}, extent = {{10, -10}, {-10, 10}}), iconTransformation(origin = {200, 0}, extent = {{10, -10}, {-10, 10}})));
  Modelica.Fluid.Interfaces.FluidPort_b port_out0(redeclare package Medium = Medium) annotation(
    Placement(transformation(origin = {90, -110}, extent = {{10, -10}, {-10, 10}}), iconTransformation(origin = {-200, 0}, extent = {{10, -10}, {-10, 10}})));
  Modelica.Fluid.Sources.FixedBoundary anom_sink(redeclare package Medium = Medium, nPorts = 1, p = 1.0e5) annotation(
    Placement(transformation(origin = {50, -110}, extent = {{10, -10}, {-10, 10}})));
  // tanks
  Modelica.Fluid.Examples.AST_BatchPlant.BaseClasses.TankWithTopPorts tank_B401(redeclare package Medium = Medium, V0 = 0.0001, crossArea = 0.01431355, height = 0.22, level_start = 0.01, nPorts = 1, nTopPorts = 1, portsData = {Modelica.Fluid.Vessels.BaseClasses.VesselPortsData(diameter = 0.011, height = 0.001, zeta_out = 0, zeta_in = 1)}, stiffCharacteristicForEmptyPort = false, energyDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, massDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, p_ambient(displayUnit = "Pa") = 1e5) annotation(
    Placement(transformation(origin = {-90, 20}, extent = {{-20, -20}, {20, 20}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B401_low(threshold = 0.1*tank_B401.height) annotation(
    Placement(transformation(origin = {-127, 3}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B401_medium(threshold = 0.5*tank_B401.height) annotation(
    Placement(transformation(origin = {-127, 17}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B401_high(threshold = 0.9*tank_B401.height) annotation(
    Placement(transformation(origin = {-127, 31}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Sources.RealExpression tank_B401_level(y = tank_B401.level) annotation(
    Placement(transformation(origin = {-122, 44}, extent = {{10, -10}, {-10, 10}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B401_low annotation(
    Placement(transformation(origin = {-107, 3}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B401_medium annotation(
    Placement(transformation(origin = {-107, 17}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B401_high annotation(
    Placement(transformation(origin = {-107, 31}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Fluid.Examples.AST_BatchPlant.BaseClasses.TankWithTopPorts tank_B402(redeclare package Medium = Medium, V0 = 0.0001, crossArea = 0.01431355, height = 0.22, level_start = 0.01, nPorts = 1, nTopPorts = 1, portsData = {Modelica.Fluid.Vessels.BaseClasses.VesselPortsData(diameter = 0.011, height = 0.001, zeta_out = 0, zeta_in = 1)}, stiffCharacteristicForEmptyPort = false, energyDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, massDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, p_ambient(displayUnit = "Pa") = 1e5) annotation(
    Placement(transformation(origin = {90, 20}, extent = {{-20, -20}, {20, 20}})));
  Modelica.Blocks.Sources.RealExpression tank_B402_level(y = tank_B402.level) annotation(
    Placement(transformation(origin = {58, 44}, extent = {{10, -10}, {-10, 10}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B402_high(threshold = 0.9*tank_B402.height) annotation(
    Placement(transformation(origin = {53, 31}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B402_medium(threshold = 0.5*tank_B402.height) annotation(
    Placement(transformation(origin = {53, 17}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B402_low(threshold = 0.1*tank_B402.height) annotation(
    Placement(transformation(origin = {53, 3}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B402_high annotation(
    Placement(transformation(origin = {73, 31}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B402_medium annotation(
    Placement(transformation(origin = {73, 17}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B402_low annotation(
    Placement(transformation(origin = {73, 3}, extent = {{-5, -5}, {5, 5}})));
  // pipes
  Modelica.Fluid.Pipes.StaticPipe pipe0(redeclare package Medium = Medium, length = 1, diameter(displayUnit = "mm") = 0.01) annotation(
    Placement(transformation(origin = {-90, -50}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Pipes.StaticPipe pipe1(redeclare package Medium = Medium, diameter(displayUnit = "mm") = 0.01, length = 1) annotation(
    Placement(transformation(origin = {-10, -30}, extent = {{-10, 10}, {10, -10}}, rotation = 90)));
  Modelica.Fluid.Pipes.StaticPipe pipe2(redeclare package Medium = Medium, diameter(displayUnit = "mm") = 0.01, length = 1) annotation(
    Placement(transformation(origin = {90, -30}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  // valves
  Modelica.Fluid.Valves.ValveLinear valve_in(redeclare package Medium = Medium, dp(start = 1), m_flow(start = 1e-5), dp_nominal = 1, m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {-90, 70}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Valves.ValveLinear valve_out(redeclare package Medium = Medium, dp(start = 1e5), dp_nominal = 1, m_flow(start = 0.0001), m_flow_nominal = 1) annotation(
    Placement(transformation(origin = {90, -70}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Valves.ValveLinear valve_pump_P401(redeclare package Medium = Medium, dp(start = 1), dp_nominal = 1, m_flow(start = 1e-5), m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {-90, -90}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Valves.ValveLinear leaking_valve(redeclare package Medium = Medium, dp(start = 1), dp_nominal = 1, m_flow(start = 1e-5), m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {10, -110}, extent = {{10, 10}, {-10, -10}}, rotation = 180)));
  Modelica.Fluid.Valves.ValveLinear clogging_valve(redeclare package Medium = Medium, dp(start = 1), dp_nominal = 1, m_flow(start = 1e-5), m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {-10, -70}, extent = {{10, 10}, {-10, -10}}, rotation = 270)));
  // machines
  Modelica.Fluid.Machines.PrescribedPump pump_P401(redeclare package Medium = Medium, N_nominal = 166.43, m_flow_start = 0.000001, T_start = 300, V(displayUnit = "m3") = 0.00004398128, checkValve = false, energyDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, redeclare function flowCharacteristic = Modelica.Fluid.Machines.BaseClasses.PumpCharacteristics.quadraticFlow(V_flow_nominal = {pump_P401_V_flow_at_max_head, pump_P401_V_flow_at_middle_head, pump_P401_V_flow_at_min_head}, head_nominal = {pump_P401_head_max, pump_P401_head_middle, pump_P401_head_min}), massDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, nParallel = 1, p_a_start = 100000, p_b_start = 100000, use_N_in = true, allowFlowReversal = true) annotation(
    Placement(transformation(origin = {-50, -110}, extent = {{-10, 10}, {10, -10}})));
  Modelica.Blocks.Continuous.FirstOrder firstOrder(T = 1) annotation(
    Placement(transformation(origin = {-70, -150}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Blocks.Sources.RealExpression n_in(y = pump_n_in) annotation(
    Placement(transformation(origin = {-150, -124}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Blocks.Noise.UniformNoise uniformNoise(samplePeriod = 1, y_min = 0.8, y_max = 1.2, useAutomaticLocalSeed = false, fixedLocalSeed = noiseSeed) annotation(
    Placement(transformation(origin = {-150, -150}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Blocks.Math.Product product1 annotation(
    Placement(transformation(origin = {-110, -150}, extent = {{-10, -10}, {10, 10}})));
  // sensors
  Modelica.Fluid.Sensors.VolumeFlowRate sensor_continuous_volumeFlowRate(redeclare package Medium = Medium) annotation(
    Placement(transformation(origin = {-10, 10}, extent = {{-10, -10}, {10, 10}}, rotation = 90)));
  Modelica.Fluid.Sensors.Pressure sensor_continuous_pressure_tank_B401(redeclare package Medium = Medium) annotation(
    Placement(transformation(origin = {-130, -50}, extent = {{-10, -10}, {10, 10}}, rotation = 90)));
  Modelica.Fluid.Sensors.Pressure sensor_continuous_pressure_tank_B402(redeclare package Medium = Medium) annotation(
    Placement(transformation(origin = {50, -30}, extent = {{-10, -10}, {10, 10}}, rotation = 90)));
  Modelica.Fluid.Sensors.Pressure sensor_continuous_pressure_pump_P401(redeclare package Medium = Medium) annotation(
    Placement(transformation(origin = {-40, -70}, extent = {{-10, -10}, {10, 10}})));
  // stategraph
  inner Modelica.StateGraph.StateGraphRoot stateGraphRoot annotation(
    Placement(transformation(origin = {-170, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.Step state_filling_tank_B401(nIn = 2, nOut = 1) annotation(
    Placement(transformation(origin = {-50, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.Step state_emptying_tank_B401(nIn = 1, nOut = 1) annotation(
    Placement(transformation(origin = {30, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.InitialStep state_init(nOut = 1, nIn = 1) annotation(
    Placement(transformation(origin = {-110, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.Transition condition_init_step annotation(
    Placement(transformation(origin = {-80, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.TransitionWithSignal condition_is_full_tank_B401 annotation(
    Placement(transformation(origin = {-10, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.TransitionWithSignal condition_is_empty_tank_B401 annotation(
    Placement(transformation(origin = {72, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.Step state_bottling(nIn = 1, nOut = 1) annotation(
    Placement(transformation(origin = {112, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.TransitionWithSignal condition_is_empty_tank_B402 annotation(
    Placement(transformation(origin = {152, 170}, extent = {{-10, -10}, {10, 10}})));
equation
  assert(not (anom_pump50 and anom_pump75), "Bottling pump50 and pump75 faults are mutually exclusive");
  fault_window_active = time >= anom_start;
// stategraph conditions
  condition_is_full_tank_B401.condition = tank_B401.level >= tank_B401.height*tankMaxVol;
  condition_is_empty_tank_B401.condition = tank_B401.level <= tank_B401.height*tankMinVol;
  condition_is_empty_tank_B402.condition = tank_B402.level <= tank_B402.height*tankMinVol;
// stategraph actions
  valve_in.opening = if state_filling_tank_B401.active then 1.0 else max(closedValveOpening, var_valve_in);
  valve_pump_P401.opening = if state_emptying_tank_B401.active then 1.0 else closedValveOpening;
  pump_n_in = if state_emptying_tank_B401.active then 150.0 * var_pump_n else 0.0;
  valve_out.opening = if state_bottling.active and mod(time, 4) < 2 then 1.0 else closedValveOpening;
// anomalies
  leaking_valve.opening = if (fault_window_active and anom_leaking) then 0.25 else 0.0;
  clogging_valve.opening = 1.0;
  var_valve_in = if (fault_window_active and anom_valve_in0) then 0.2 else 0.0;
  var_pump_n = if (fault_window_active and anom_pump50) then 0.5 else if (fault_window_active and anom_pump75) then 0.75 else 1.0;
// connections
  connect(tank_B401.ports[1], pipe0.port_a) annotation(
    Line(points = {{-90, -1}, {-90, -40}}, color = {0, 127, 255}));
  connect(valve_in.port_a, port_in0) annotation(
    Line(points = {{-90, 80}, {-90, 110}}, color = {0, 127, 255}));
  connect(valve_in.port_b, tank_B401.topPorts[1]) annotation(
    Line(points = {{-90, 60}, {-90, 42}}, color = {0, 127, 255}));
  connect(valve_out.port_b, port_out0) annotation(
    Line(points = {{90, -80}, {90, -110}}, color = {0, 127, 255}));
  connect(state_init.outPort[1], condition_init_step.inPort) annotation(
    Line(points = {{-99.5, 170}, {-83.5, 170}}));
  connect(condition_init_step.outPort, state_filling_tank_B401.inPort[1]) annotation(
    Line(points = {{-78.5, 170}, {-60.5, 170}}));
  connect(state_filling_tank_B401.outPort[1], condition_is_full_tank_B401.inPort) annotation(
    Line(points = {{-39.5, 170}, {-13.5, 170}}));
  connect(condition_is_full_tank_B401.outPort, state_emptying_tank_B401.inPort[1]) annotation(
    Line(points = {{-8.5, 170}, {19, 170}}));
  connect(state_emptying_tank_B401.outPort[1], condition_is_empty_tank_B401.inPort) annotation(
    Line(points = {{40.5, 170}, {68, 170}}));
  connect(pipe0.port_b, valve_pump_P401.port_a) annotation(
    Line(points = {{-90, -60}, {-90, -80}}, color = {0, 127, 255}));
  connect(valve_pump_P401.port_b, pump_P401.port_a) annotation(
    Line(points = {{-90, -100}, {-90, -110}, {-60, -110}}, color = {0, 127, 255}));
  connect(condition_is_empty_tank_B401.outPort, state_bottling.inPort[1]) annotation(
    Line(points = {{73.5, 170}, {101.5, 170}}));
  connect(state_bottling.outPort[1], condition_is_empty_tank_B402.inPort) annotation(
    Line(points = {{122.5, 170}, {148.5, 170}}));
  connect(condition_is_empty_tank_B402.outPort, state_init.inPort[1]) annotation(
    Line(points = {{153.5, 170}, {179.5, 170}, {179.5, 140}, {-140.5, 140}, {-140.5, 170}, {-120.5, 170}}));
  connect(pipe2.port_b, valve_out.port_a) annotation(
    Line(points = {{90, -40}, {90, -60}}, color = {0, 127, 255}));
  connect(tank_B402.ports[1], pipe2.port_a) annotation(
    Line(points = {{90, 0}, {90, -20}}, color = {0, 127, 255}));
  connect(tank_B401_level.y, level_to_boolean_tank_B401_high.u) annotation(
    Line(points = {{-133, 44}, {-141, 44}, {-141, 32}, {-133, 32}}, color = {0, 0, 127}));
  connect(tank_B401_level.y, level_to_boolean_tank_B401_medium.u) annotation(
    Line(points = {{-133, 44}, {-141, 44}, {-141, 18}, {-133, 18}}, color = {0, 0, 127}));
  connect(tank_B401_level.y, level_to_boolean_tank_B401_low.u) annotation(
    Line(points = {{-133, 44}, {-141, 44}, {-141, 4}, {-133, 4}}, color = {0, 0, 127}));
  connect(level_to_boolean_tank_B401_high.y, sensor_discrete_tank_B401_high.activePort) annotation(
    Line(points = {{-121.5, 31}, {-111.5, 31}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B401_medium.y, sensor_discrete_tank_B401_medium.activePort) annotation(
    Line(points = {{-121.5, 17}, {-111.5, 17}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B401_low.y, sensor_discrete_tank_B401_low.activePort) annotation(
    Line(points = {{-121.5, 3}, {-111.5, 3}}, color = {255, 0, 255}));
  connect(tank_B402_level.y, level_to_boolean_tank_B402_high.u) annotation(
    Line(points = {{47, 44}, {39, 44}, {39, 32}, {47, 32}}, color = {0, 0, 127}));
  connect(tank_B402_level.y, level_to_boolean_tank_B402_medium.u) annotation(
    Line(points = {{47, 44}, {39, 44}, {39, 18}, {47, 18}}, color = {0, 0, 127}));
  connect(tank_B402_level.y, level_to_boolean_tank_B402_low.u) annotation(
    Line(points = {{47, 44}, {39, 44}, {39, 4}, {47, 4}}, color = {0, 0, 127}));
  connect(level_to_boolean_tank_B402_high.y, sensor_discrete_tank_B402_high.activePort) annotation(
    Line(points = {{58.5, 31}, {68.5, 31}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B402_medium.y, sensor_discrete_tank_B402_medium.activePort) annotation(
    Line(points = {{58.5, 17}, {68.5, 17}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B402_low.y, sensor_discrete_tank_B402_low.activePort) annotation(
    Line(points = {{58.5, 3}, {68.5, 3}}, color = {255, 0, 255}));
  connect(n_in.y, product1.u1) annotation(
    Line(points = {{-139, -124}, {-131, -124}, {-131, -144}, {-123, -144}}, color = {0, 0, 127}));
  connect(uniformNoise.y, product1.u2) annotation(
    Line(points = {{-139, -150}, {-133, -150}, {-133, -156}, {-123, -156}}, color = {0, 0, 127}));
  connect(product1.y, firstOrder.u) annotation(
    Line(points = {{-99, -150}, {-83, -150}}, color = {0, 0, 127}));
  connect(pump_P401.port_b, leaking_valve.port_a) annotation(
    Line(points = {{-40, -110}, {0, -110}}, color = {0, 127, 255}));
  connect(leaking_valve.port_b, anom_sink.ports[1]) annotation(
    Line(points = {{20, -110}, {40, -110}}, color = {0, 127, 255}));
  connect(clogging_valve.port_b, pipe1.port_a) annotation(
    Line(points = {{-10, -60}, {-10, -40}}, color = {0, 127, 255}));
  connect(sensor_continuous_pressure_pump_P401.port, pump_P401.port_b) annotation(
    Line(points = {{-40, -80}, {-40, -110}}, color = {0, 127, 255}));
  connect(pipe0.port_a, sensor_continuous_pressure_tank_B401.port) annotation(
    Line(points = {{-90, -40}, {-108, -40}, {-108, -50}, {-120, -50}}, color = {0, 127, 255}));
  connect(pipe2.port_a, sensor_continuous_pressure_tank_B402.port) annotation(
    Line(points = {{90, -20}, {60, -20}, {60, -30}}, color = {0, 127, 255}));
  connect(pipe1.port_b, sensor_continuous_volumeFlowRate.port_a) annotation(
    Line(points = {{-10, -20}, {-10, 0}}, color = {0, 127, 255}));
  connect(sensor_continuous_volumeFlowRate.port_b, tank_B402.topPorts[1]) annotation(
    Line(points = {{-10, 20}, {-10, 60}, {90, 60}, {90, 42}}, color = {0, 127, 255}));
  connect(firstOrder.y, pump_P401.N_in) annotation(
    Line(points = {{-58, -150}, {-50, -150}, {-50, -120}}, color = {0, 0, 127}));
  connect(pump_P401.port_b, clogging_valve.port_a) annotation(
    Line(points = {{-40, -110}, {-10, -110}, {-10, -80}}, color = {0, 127, 255}));
  annotation(
    uses(Modelica(version = "4.0.0")),
    Diagram(coordinateSystem(extent = {{-200, -200}, {200, 200}})),
    Icon(coordinateSystem(extent = {{-200, -200}, {200, 200}})),
    version = "");
end bottlingModule;
