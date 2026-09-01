model distillModule
  replaceable package Medium = Modelica.Media.Water.StandardWater;
  parameter Real tankMinVol = 0.1;
  parameter Real tankMaxVol = 0.9;
  parameter Real pump_P101_V_flow_at_max_head = 0.000122;
  parameter Real pump_P101_V_flow_at_middle_head = 0.0002;
  parameter Real pump_P101_V_flow_at_min_head = 0.00025;
  parameter Real pump_P101_head_max = 2.045;
  parameter Real pump_P101_head_middle = 1.534;
  parameter Real pump_P101_head_min = 1.022;
  parameter Real p_ambient = 1e5;
  parameter Real Tmin = 275;
  parameter Real closedValveOpening(min = 0, max = 1) = 1e-4;
  parameter Integer noiseSeed = 1;
  
  // anomalies
  parameter Real anom_start = 2500;
  parameter Boolean anom_leaking = false annotation(Evaluate = false);
  parameter Boolean anom_valve_in0 = false annotation(Evaluate = false);
  parameter Boolean anom_pump50 = false annotation(Evaluate = false);
  parameter Boolean anom_pump75 = false annotation(Evaluate = false);
  parameter Boolean anom_heat75 = false annotation(Evaluate = false);
  parameter Boolean anom_heat50 = false annotation(Evaluate = false);
  Real var_valve_in0(start=0.0);
  Real var_pump_n(start=1.0);
  Real var_heat(start=1.0);
  Real pump_n_in;
  Boolean fault_window_active;


  // ports
  Modelica.Fluid.Interfaces.FluidPort_a port_in0(redeclare package Medium = Medium) annotation(
    Placement(transformation(origin = {-110, 90}, extent = {{10, -10}, {-10, 10}}), iconTransformation(origin = {70, 0}, extent = {{10, -10}, {-10, 10}})));
  Modelica.Fluid.Interfaces.FluidPort_b port_out0(redeclare package Medium = Medium) annotation(
    Placement(transformation(origin = {70, -130}, extent = {{10, 10}, {-10, -10}}), iconTransformation(origin = {70, 0}, extent = {{10, -10}, {-10, 10}})));
  Modelica.Fluid.Interfaces.FluidPort_b port_out1(redeclare package Medium = Medium) annotation(
    Placement(transformation(origin = {148, -130}, extent = {{10, 10}, {-10, -10}}), iconTransformation(origin = {80, 10}, extent = {{10, -10}, {-10, 10}})));
  // system
  Modelica.Fluid.Sources.FixedBoundary anom_sink(redeclare package Medium = Medium, nPorts = 1, p = 0.999e5) annotation(
    Placement(transformation(origin = {-30, -180}, extent = {{-10, -10}, {10, 10}}, rotation = 90)));

  
  // tanks
  Modelica.Fluid.Examples.AST_BatchPlant.BaseClasses.TankWithTopPorts tank_B101(redeclare package Medium = Medium, V0 = 0.0001, crossArea = 0.01431355, height = 0.22, level_start = 0.01, nPorts = 1, nTopPorts = 1, portsData = {Modelica.Fluid.Vessels.BaseClasses.VesselPortsData(diameter = 0.011, height = 0.001, zeta_out = 0, zeta_in = 1)}, stiffCharacteristicForEmptyPort = false, energyDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, massDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, p_ambient(displayUnit = "Pa") = 1e5) annotation(
    Placement(transformation(origin = {-110, 0}, extent = {{-20, -20}, {20, 20}})));
  Modelica.Fluid.Examples.AST_BatchPlant.BaseClasses.TankWith3InletOutletArraysWithEvaporatorCondensor distill(redeclare package Medium = Medium, height = 1.22, n_SidePorts = 1, V0 = 0.001, n_BottomPorts = 1, bottom_pipeArea = {0.0001}, top_pipeArea = {0.0001}, n_TopPorts = 1, min_level_for_heating = 0.0001, level_start = 0.0009, crossArea = 0.01431355, initType = Modelica.Fluid.Examples.AST_BatchPlant.BaseClasses.Init.InitialValues, side_pipeArea = {0.0001}, redeclare model HeatTransfer = Modelica.Fluid.Vessels.BaseClasses.HeatTransfer.IdealHeatTransfer(k = 4.9)) annotation(
    Placement(transformation(origin = {160, 100}, extent = {{-110, -60}, {-30, -20}})));
  Modelica.Fluid.Examples.AST_BatchPlant.BaseClasses.TankWithTopPorts tank_B102(redeclare package Medium = Medium, V0 = 0.0001, nTopPorts = 1, height = 0.22, crossArea = 0.01431355, level_start = 0.01, nPorts = 1, portsData = {Modelica.Fluid.Vessels.BaseClasses.VesselPortsData(diameter = 0.011, height = 0)}, stiffCharacteristicForEmptyPort = false, use_HeatTransfer = true, T_start = 298, redeclare model HeatTransfer = Modelica.Fluid.Vessels.BaseClasses.HeatTransfer.IdealHeatTransfer(k = 4.9)) annotation(
    Placement(transformation(origin = {130, 20}, extent = {{-80, -80}, {-40, -40}})));
  Modelica.Fluid.Examples.AST_BatchPlant.BaseClasses.TankWithTopPorts tank_B103(redeclare package Medium = Medium, V0 = 0.0001, nTopPorts = 1, height = 0.22, crossArea = 0.01431355, level_start = 0.01, nPorts = 1, portsData = {Modelica.Fluid.Vessels.BaseClasses.VesselPortsData(diameter = 0.011, height = 0)}, stiffCharacteristicForEmptyPort = false, use_HeatTransfer = true, T_start = 298, redeclare model HeatTransfer = Modelica.Fluid.Vessels.BaseClasses.HeatTransfer.IdealHeatTransfer(k = 4.9)) annotation(
    Placement(transformation(origin = {208, 20}, extent = {{-80, -80}, {-40, -40}}, rotation = -0)));
  // pipes
  Modelica.Fluid.Pipes.StaticPipe pipe0(redeclare package Medium = Medium, length = 1, diameter(displayUnit = "mm") = 0.01) annotation(
    Placement(transformation(origin = {-110, -50}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Pipes.StaticPipe pipe1(redeclare package Medium = Medium, diameter(displayUnit = "mm") = 0.01, length = 1) annotation(
    Placement(transformation(origin = {-30, -50}, extent = {{-10, 10}, {10, -10}}, rotation = 90)));
  // valves
  Modelica.Fluid.Valves.ValveLinear valve_in(redeclare package Medium = Medium, dp(start = 1), m_flow(start = 1e-5), dp_nominal = 1, m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {-110, 50}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Valves.ValveLinear valve_pump_P101(redeclare package Medium = Medium, dp(start = 1), dp_nominal = 1, m_flow(start = 1e-5), m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {-110, -90}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Valves.ValveLinear valve_distill1(redeclare package Medium = Medium, dp(start = 1), dp_nominal = 1, m_flow(start = 1e-5), m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {-30, -90}, extent = {{-10, 10}, {10, -10}}, rotation = 90)));
  Modelica.Fluid.Valves.ValveLinear valve_distill2(redeclare package Medium = Medium, dp(start = 1), dp_nominal = 1, m_flow(start = 1e-5), m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {148, 10}, extent = {{-10, 10}, {10, -10}}, rotation = -90)));
  Modelica.Fluid.Valves.ValveLinear valve_distill3(redeclare package Medium = Medium, dp(start = 1), dp_nominal = 1, m_flow(start = 1e-5), m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {70, 10}, extent = {{-10, 10}, {10, -10}}, rotation = -90)));
  Modelica.Fluid.Valves.ValveLinear valve_out0(redeclare package Medium = Medium, dp(start = 1e5), dp_nominal = 1, m_flow(start = 0.0001), m_flow_nominal = 1) annotation(
    Placement(transformation(origin = {70, -90}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Valves.ValveLinear valve_out1(redeclare package Medium = Medium, dp(start = 1e5), dp_nominal = 1, m_flow(start = 0.0001), m_flow_nominal = 1) annotation(
    Placement(transformation(origin = {148, -90}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Valves.ValveLinear leaking_valve(redeclare package Medium = Medium, dp(start = 1), dp_nominal = 1, m_flow(start = 1e-5), m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {-30, -150}, extent = {{10, 10}, {-10, -10}}, rotation = 90)));
  Modelica.Fluid.Valves.ValveLinear clogging_valve(redeclare package Medium = Medium, dp(start = 1), dp_nominal = 1, m_flow(start = 1e-5), m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {-30, 30}, extent = {{10, -10}, {-10, 10}}, rotation = 270)));

  // machines
  Modelica.Fluid.Machines.PrescribedPump pump_P101(redeclare package Medium = Medium, N_nominal = 166.43, m_flow_start = 0.000001, T_start = 300, V(displayUnit = "m3") = 0.00004398128, checkValve = false, energyDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, redeclare function flowCharacteristic = Modelica.Fluid.Machines.BaseClasses.PumpCharacteristics.quadraticFlow(V_flow_nominal = {pump_P101_V_flow_at_max_head, pump_P101_V_flow_at_middle_head, pump_P101_V_flow_at_min_head}, head_nominal = {pump_P101_head_max, pump_P101_head_middle, pump_P101_head_min}), massDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, nParallel = 1, p_a_start = 100000, p_b_start = 100000, use_N_in = true, allowFlowReversal = true) annotation(
    Placement(transformation(origin = {-70, -130}, extent = {{-10, 10}, {10, -10}})));
  Modelica.Blocks.Continuous.FirstOrder firstOrder(T = 1) annotation(
    Placement(transformation(origin = {-90, -170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Blocks.Sources.RealExpression n_in(y = pump_n_in) annotation(
    Placement(transformation(origin = {-170, -150}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Blocks.Noise.UniformNoise uniformNoise(samplePeriod = 1, y_max = 1.2, y_min = 0.8, useAutomaticLocalSeed = false, fixedLocalSeed = noiseSeed) annotation(
    Placement(transformation(origin = {-170, -170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Blocks.Math.Product product1 annotation(
    Placement(transformation(origin = {-130, -170}, extent = {{-10, -10}, {10, 10}})));
    
  // heat transfer
  Modelica.Thermal.HeatTransfer.Sources.PrescribedHeatFlow heater_distill annotation(
    Placement(transformation(origin = {170, 100}, extent = {{-150, -50}, {-130, -30}})));
  Modelica.Thermal.HeatTransfer.Sources.PrescribedHeatFlow cooler_B102 annotation(
    Placement(transformation(origin = {-90, 50}, extent = {{-150, -130}, {-130, -110}}, rotation = 90)));
  Modelica.Thermal.HeatTransfer.Sources.PrescribedHeatFlow cooler_B103 annotation(
    Placement(transformation(origin = {110, -90}, extent = {{-10, -10}, {10, 10}}, rotation = 90)));
  
  
  // sensors
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B101_low(threshold = 0.1*tank_B101.height) annotation(
    Placement(transformation(origin = {-147, -15}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B101_medium(threshold = 0.5*tank_B101.height) annotation(
    Placement(transformation(origin = {-147, -1}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B101_high(threshold = 0.9*tank_B101.height) annotation(
    Placement(transformation(origin = {-147, 13}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Sources.RealExpression tank_B101_level(y = tank_B101.level) annotation(
    Placement(transformation(origin = {-142, 26}, extent = {{10, -10}, {-10, 10}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B101_low annotation(
    Placement(transformation(origin = {-127, -15}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B101_medium annotation(
    Placement(transformation(origin = {-127, -1}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B101_high annotation(
    Placement(transformation(origin = {-127, 13}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Sources.RealExpression tank_B102_level(y = tank_B102.level) annotation(
    Placement(transformation(origin = {38, -16}, extent = {{10, -10}, {-10, 10}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B102_high(threshold = 0.9*tank_B102.height) annotation(
    Placement(transformation(origin = {33, -29}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B102_medium(threshold = 0.5*tank_B102.height) annotation(
    Placement(transformation(origin = {33, -43}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B102_low(threshold = 0.1*tank_B102.height) annotation(
    Placement(transformation(origin = {33, -57}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B102_high annotation(
    Placement(transformation(origin = {53, -29}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B102_medium annotation(
    Placement(transformation(origin = {53, -43}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B102_low annotation(
    Placement(transformation(origin = {53, -57}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B103_high(threshold = 0.9*tank_B103.height) annotation(
    Placement(transformation(origin = {111, -29}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Sources.RealExpression tank_B103_level(y = tank_B103.level) annotation(
    Placement(transformation(origin = {116, -16}, extent = {{10, -10}, {-10, 10}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B103_low annotation(
    Placement(transformation(origin = {131, -57}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B103_medium annotation(
    Placement(transformation(origin = {131, -43}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B103_high annotation(
    Placement(transformation(origin = {131, -29}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B103_low(threshold = 0.1*tank_B103.height) annotation(
    Placement(transformation(origin = {111, -57}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B103_medium(threshold = 0.5*tank_B103.height) annotation(
    Placement(transformation(origin = {111, -43}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Fluid.Sensors.Pressure sensor_continuous_pressure_tank_B101(replaceable package Medium = Medium) annotation(
    Placement(transformation(origin = {-88, -50}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Fluid.Sensors.VolumeFlowRate sensor_continuous_volumeFlowRate(replaceable package Medium = Medium) annotation(
    Placement(transformation(origin = {-30, -10}, extent = {{10, -10}, {-10, 10}}, rotation = -90)));
  Modelica.Fluid.Sensors.Pressure sensor_continuous_pressure_tank_B102(replaceable package Medium = Medium) annotation(
    Placement(transformation(origin = {90, -70}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Fluid.Sensors.Pressure sensor_continuous_pressure_tank_B103(replaceable package Medium = Medium) annotation(
    Placement(transformation(origin = {170, -70}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Fluid.Sensors.Pressure sensor_continuous_pressure_distill_out0(replaceable package Medium = Medium) annotation(
    Placement(transformation(origin = {90, 30}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Fluid.Sensors.Pressure sensor_continuous_pressure_distill_out1(replaceable package Medium = Medium) annotation(
    Placement(transformation(origin = {170, 30}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Fluid.Sensors.Pressure sensor_continuous_pressure_pump_P101(replaceable package Medium = Medium) annotation(
    Placement(transformation(origin = {-10, -120}, extent = {{-10, -10}, {10, 10}})));
  
  
  // stategraph
  inner Modelica.StateGraph.StateGraphRoot stateGraphRoot annotation(
    Placement(transformation(origin = {-170, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.Step state_filling_tank_B101(nIn = 2, nOut = 1) annotation(
    Placement(transformation(origin = {-70, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.Step state_emptying_tank_B101(nIn = 1, nOut = 1) annotation(
    Placement(transformation(origin = {10, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.Step state_destillation(nIn = 1, nOut = 1) annotation(
    Placement(transformation(origin = {90, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.Step state_emptying_distill(nIn = 1, nOut = 1) annotation(
    Placement(transformation(origin = {-70, 130}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.InitialStep state_initialStep(nOut = 1, nIn = 1) annotation(
    Placement(transformation(origin = {-130, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.Step state_emptying_output_tanks(nIn = 1, nOut = 1) annotation(
    Placement(transformation(origin = {10, 130}, extent = {{-10, -10}, {10, 10}})));

  Modelica.StateGraph.Transition condition_init_step annotation(
    Placement(transformation(origin = {-100, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.TransitionWithSignal condition_is_full_tank_B101 annotation(
    Placement(transformation(origin = {-30, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.TransitionWithSignal condition_is_empty_tank_B101 annotation(
    Placement(transformation(origin = {52, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.TransitionWithSignal condition_destillation_done annotation(
    Placement(transformation(origin = {130, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.TransitionWithSignal condition_is_empty_distill(enableTimer = true, waitTime = 10)  annotation(
    Placement(transformation(origin = {-30, 130}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.TransitionWithSignal condition_is_empty_output_tanks annotation(
    Placement(transformation(origin = {50, 130}, extent = {{-10, -10}, {10, 10}})));


equation
  assert(not (anom_pump50 and anom_pump75), "Distillation pump50 and pump75 faults are mutually exclusive");
  assert(not (anom_heat50 and anom_heat75), "Distillation heat50 and heat75 faults are mutually exclusive");
  fault_window_active = time >= anom_start;
  condition_is_full_tank_B101.condition = tank_B101.level >= tank_B101.height*tankMaxVol;
  condition_is_empty_tank_B101.condition = tank_B101.level <= tank_B101.height*tankMinVol;
  condition_destillation_done.condition = distill.level <= 0.1*distill.height;
  condition_is_empty_distill.condition = distill.level <= distill.height*tankMinVol;
  condition_is_empty_output_tanks.condition = tank_B102.level <= tank_B102.height*tankMinVol and tank_B103.level <= tank_B103.height*tankMinVol;
  valve_in.opening = if state_filling_tank_B101.active then 1.0 else max(closedValveOpening, var_valve_in0);
  pump_n_in = if state_emptying_tank_B101.active then 150.0 * var_pump_n else 0.0;
  valve_pump_P101.opening = if state_emptying_tank_B101.active then 1.0 else closedValveOpening;
  valve_distill1.opening = if state_emptying_tank_B101.active then 1.0 else closedValveOpening;
  heater_distill.Q_flow = if state_destillation.active then 20000 * var_heat else 0;
  cooler_B102.Q_flow = if state_destillation.active then 0 else 0;
// -2000
  cooler_B103.Q_flow = if state_destillation.active then 0 else 0;
// -2000
  valve_distill2.opening = if state_emptying_distill.active then 1.0 else 1.0;
  valve_distill3.opening = if state_emptying_distill.active then 1.0 else closedValveOpening;
  valve_out0.opening = if state_emptying_output_tanks.active then 1.0 else closedValveOpening;
  valve_out1.opening = if state_emptying_output_tanks.active then 1.0 else closedValveOpening;
// anomalies
  leaking_valve.opening = if (fault_window_active and anom_leaking) then 0.25 else 0.0;
  clogging_valve.opening = 1.0;
  var_valve_in0 = if (fault_window_active and anom_valve_in0) then 0.2 else 0.0;
  var_pump_n = if (fault_window_active and anom_pump50) then 0.5 else if (fault_window_active and anom_pump75) then 0.75 else 1.0;
  var_heat = if (fault_window_active and anom_heat50) then 0.5 else if (fault_window_active and anom_heat75) then 0.75 else 1.0;
  
// connections 
  connect(tank_B101.ports[1], pipe0.port_a) annotation(
    Line(points = {{-110, -21}, {-110, -40}}, color = {0, 127, 255}));
  connect(valve_in.port_a, port_in0) annotation(
    Line(points = {{-110, 60}, {-110, 90}}, color = {0, 127, 255}));
  connect(valve_in.port_b, tank_B101.topPorts[1]) annotation(
    Line(points = {{-110, 40}, {-110, 22}}, color = {0, 127, 255}));
  connect(state_initialStep.outPort[1], condition_init_step.inPort) annotation(
    Line(points = {{-119.5, 170}, {-103.5, 170}}));
  connect(condition_init_step.outPort, state_filling_tank_B101.inPort[1]) annotation(
    Line(points = {{-98.5, 170}, {-81, 170}}));
  connect(state_filling_tank_B101.outPort[1], condition_is_full_tank_B101.inPort) annotation(
    Line(points = {{-59.5, 170}, {-34, 170}}));
  connect(condition_is_full_tank_B101.outPort, state_emptying_tank_B101.inPort[1]) annotation(
    Line(points = {{-28.5, 170}, {-1, 170}}));
  connect(state_emptying_tank_B101.outPort[1], condition_is_empty_tank_B101.inPort) annotation(
    Line(points = {{20.5, 170}, {48, 170}}));
  connect(pipe0.port_b, valve_pump_P101.port_a) annotation(
    Line(points = {{-110, -60}, {-110, -80}}, color = {0, 127, 255}));
  connect(valve_pump_P101.port_b, pump_P101.port_a) annotation(
    Line(points = {{-110, -100}, {-110, -130}, {-80, -130}}, color = {0, 127, 255}));
  connect(pump_P101.port_b, valve_distill1.port_a) annotation(
    Line(points = {{-60, -130}, {-30, -130}, {-30, -100}}, color = {0, 127, 255}));
  connect(valve_distill1.port_b, pipe1.port_a) annotation(
    Line(points = {{-30, -80}, {-30, -60}}, color = {0, 127, 255}));
  connect(valve_out0.port_b, port_out0) annotation(
    Line(points = {{70, -100}, {70, -130}}, color = {0, 127, 255}));
  connect(valve_out1.port_b, port_out1) annotation(
    Line(points = {{148, -100}, {148, -130}}, color = {0, 127, 255}));
  connect(heater_distill.port, distill.heatPort) annotation(
    Line(points = {{40, 60}, {50, 60}}, color = {191, 0, 0}));
  connect(cooler_B102.port, tank_B102.heatPort) annotation(
    Line(points = {{30, -80}, {29.5, -80}, {29.5, -70}, {49, -70}, {49, -40}, {50, -40}}, color = {191, 0, 0}));
  connect(valve_distill3.port_b, tank_B102.topPorts[1]) annotation(
    Line(points = {{70, 0}, {70, -18}}, color = {0, 127, 255}));
  connect(tank_B102.ports[1], valve_out0.port_a) annotation(
    Line(points = {{70, -61}, {70, -81}}, color = {0, 127, 255}));
  connect(valve_distill2.port_b, tank_B103.topPorts[1]) annotation(
    Line(points = {{148, 0}, {148, -19}}, color = {0, 127, 255}));
  connect(tank_B103.ports[1], valve_out1.port_a) annotation(
    Line(points = {{148, -61}, {148, -81}}, color = {0, 127, 255}));
  connect(cooler_B103.port, tank_B103.heatPort) annotation(
    Line(points = {{110, -80}, {109.5, -80}, {109.5, -70}, {129, -70}, {129, -40}, {128, -40}}, color = {191, 0, 0}));
  connect(distill.BottomFluidPort[1], valve_distill3.port_a) annotation(
    Line(points = {{70, 39.6}, {70, 19.6}}, color = {0, 127, 255}));
  connect(distill.Condensed, valve_distill2.port_a) annotation(
    Line(points = {{130.4, 72}, {148, 72}, {148, 20}}, color = {0, 127, 255}));
  connect(condition_is_empty_tank_B101.outPort, state_destillation.inPort[1]) annotation(
    Line(points = {{53.5, 170}, {79, 170}}));
  connect(state_destillation.outPort[1], condition_destillation_done.inPort) annotation(
    Line(points = {{100.5, 170}, {126, 170}}));
  connect(condition_destillation_done.outPort, state_emptying_distill.inPort[1]) annotation(
    Line(points = {{131.5, 170}, {145.25, 170}, {145.25, 150}, {-85.875, 150}, {-85.875, 130}, {-81, 130}}));
  connect(state_emptying_distill.outPort[1], condition_is_empty_distill.inPort) annotation(
    Line(points = {{-59.5, 130}, {-34, 130}}));
  connect(condition_is_empty_distill.outPort, state_emptying_output_tanks.inPort[1]) annotation(
    Line(points = {{-28.5, 130}, {-1.5, 130}}));
  connect(state_emptying_output_tanks.outPort[1], condition_is_empty_output_tanks.inPort) annotation(
    Line(points = {{20.5, 130}, {46, 130}}));
  connect(uniformNoise.y, product1.u2) annotation(
    Line(points = {{-159, -170}, {-153, -170}, {-153, -176}, {-143, -176}}, color = {0, 0, 127}));
  connect(n_in.y, product1.u1) annotation(
    Line(points = {{-159, -150}, {-153, -150}, {-153, -164}, {-143, -164}}, color = {0, 0, 127}));
  connect(product1.y, firstOrder.u) annotation(
    Line(points = {{-119, -170}, {-102, -170}}, color = {0, 0, 127}));
  connect(firstOrder.y, pump_P101.N_in) annotation(
    Line(points = {{-79, -170}, {-71, -170}, {-71, -140}}, color = {0, 0, 127}));
  connect(condition_is_empty_output_tanks.outPort, state_filling_tank_B101.inPort[2]) annotation(
    Line(points = {{52, 130}, {60, 130}, {60, 110}, {-92, 110}, {-92, 170}, {-80, 170}}));
  connect(leaking_valve.port_b, anom_sink.ports[1]) annotation(
    Line(points = {{-30, -160}, {-30, -170}}, color = {0, 127, 255}));
  connect(clogging_valve.port_b, distill.TopFluidPort[1]) annotation(
    Line(points = {{-30, 40}, {-30, 100}, {70, 100}, {70, 80}}, color = {0, 127, 255}));
  connect(pump_P101.port_b, leaking_valve.port_a) annotation(
    Line(points = {{-60, -130}, {-30, -130}, {-30, -140}}, color = {0, 127, 255}));
  connect(tank_B101_level.y, level_to_boolean_tank_B101_high.u) annotation(
    Line(points = {{-153, 26}, {-161, 26}, {-161, 13}, {-153, 13}}, color = {0, 0, 127}));
  connect(tank_B101_level.y, level_to_boolean_tank_B101_medium.u) annotation(
    Line(points = {{-153, 26}, {-161, 26}, {-161, -1}, {-153, -1}}, color = {0, 0, 127}));
  connect(tank_B101_level.y, level_to_boolean_tank_B101_low.u) annotation(
    Line(points = {{-153, 26}, {-161, 26}, {-161, -15}, {-153, -15}}, color = {0, 0, 127}));
  connect(level_to_boolean_tank_B101_high.y, sensor_discrete_tank_B101_high.activePort) annotation(
    Line(points = {{-141.5, 13}, {-133, 13}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B101_medium.y, sensor_discrete_tank_B101_medium.activePort) annotation(
    Line(points = {{-141.5, -1}, {-133, -1}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B101_low.y, sensor_discrete_tank_B101_low.activePort) annotation(
    Line(points = {{-141.5, -15}, {-133, -15}}, color = {255, 0, 255}));
  connect(tank_B102_level.y, level_to_boolean_tank_B102_high.u) annotation(
    Line(points = {{27, -16}, {19, -16}, {19, -28}, {27, -28}}, color = {0, 0, 127}));
  connect(tank_B102_level.y, level_to_boolean_tank_B102_medium.u) annotation(
    Line(points = {{27, -16}, {19, -16}, {19, -42}, {27, -42}}, color = {0, 0, 127}));
  connect(tank_B102_level.y, level_to_boolean_tank_B102_low.u) annotation(
    Line(points = {{27, -16}, {19, -16}, {19, -56}, {27, -56}}, color = {0, 0, 127}));
  connect(level_to_boolean_tank_B102_high.y, sensor_discrete_tank_B102_high.activePort) annotation(
    Line(points = {{38.5, -29}, {48.5, -29}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B102_medium.y, sensor_discrete_tank_B102_medium.activePort) annotation(
    Line(points = {{38.5, -43}, {48.5, -43}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B102_low.y, sensor_discrete_tank_B102_low.activePort) annotation(
    Line(points = {{38.5, -57}, {48.5, -57}}, color = {255, 0, 255}));
  connect(tank_B103_level.y, level_to_boolean_tank_B103_high.u) annotation(
    Line(points = {{105, -16}, {97, -16}, {97, -28}, {105, -28}}, color = {0, 0, 127}));
  connect(tank_B103_level.y, level_to_boolean_tank_B103_medium.u) annotation(
    Line(points = {{105, -16}, {97, -16}, {97, -42}, {105, -42}}, color = {0, 0, 127}));
  connect(tank_B103_level.y, level_to_boolean_tank_B103_low.u) annotation(
    Line(points = {{105, -16}, {97, -16}, {97, -56}, {105, -56}}, color = {0, 0, 127}));
  connect(level_to_boolean_tank_B103_high.y, sensor_discrete_tank_B103_high.activePort) annotation(
    Line(points = {{116.5, -29}, {126.5, -29}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B103_medium.y, sensor_discrete_tank_B103_medium.activePort) annotation(
    Line(points = {{116.5, -43}, {126.5, -43}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B103_low.y, sensor_discrete_tank_B103_low.activePort) annotation(
    Line(points = {{116.5, -57}, {126.5, -57}}, color = {255, 0, 255}));
  connect(pipe1.port_b, sensor_continuous_volumeFlowRate.port_a) annotation(
    Line(points = {{-30, -40}, {-30, -20}}, color = {0, 127, 255}));
  connect(sensor_continuous_volumeFlowRate.port_b, clogging_valve.port_a) annotation(
    Line(points = {{-30, 0}, {-30, 20}}, color = {0, 127, 255}));
  connect(sensor_continuous_pressure_tank_B101.port, valve_pump_P101.port_a) annotation(
    Line(points = {{-88, -60}, {-88, -80}, {-110, -80}}, color = {0, 127, 255}));
  connect(sensor_continuous_pressure_tank_B102.port, valve_out0.port_a) annotation(
    Line(points = {{90, -80}, {70, -80}}, color = {0, 127, 255}));
  connect(sensor_continuous_pressure_tank_B103.port, valve_out1.port_a) annotation(
    Line(points = {{170, -80}, {148, -80}}, color = {0, 127, 255}));
  connect(sensor_continuous_pressure_distill_out1.port, valve_distill2.port_a) annotation(
    Line(points = {{170, 20}, {148, 20}}, color = {0, 127, 255}));
  connect(sensor_continuous_pressure_distill_out0.port, valve_distill3.port_a) annotation(
    Line(points = {{90, 20}, {70, 20}}, color = {0, 127, 255}));
  connect(pump_P101.port_b, sensor_continuous_pressure_pump_P101.port) annotation(
    Line(points = {{-60, -130}, {-10, -130}}, color = {0, 127, 255}));
  annotation(
    uses(Modelica(version = "4.0.0")),
    Diagram(coordinateSystem(extent = {{-200, -200}, {200, 200}})),
    Icon(coordinateSystem(extent = {{-200, -200}, {200, 200}})),
    version = "");
end distillModule;
