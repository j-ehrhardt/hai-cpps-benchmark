model filterModule
  replaceable package Medium = Modelica.Media.Water.StandardWater;
  // parameters and variables
  parameter Real tankMinVol = 0.05;
  parameter Real tankMaxVol = 0.95;
  parameter Real pump_P101_V_flow_at_max_head = 0.000122;
  parameter Real pump_P101_V_flow_at_middle_head = 0.0002;
  parameter Real pump_P101_V_flow_at_min_head = 0.00025;
  parameter Real pump_P101_head_max = 2.045;
  parameter Real pump_P101_head_middle = 1.534;
  parameter Real pump_P101_head_min = 1.022;
  parameter Real closedValveOpening(min = 0, max = 1) = 1e-4;
  parameter Integer noiseSeed = 1;
  
  // anomalies
  parameter Real anom_start = 2500;
  parameter Boolean anom_leaking = false annotation(Evaluate = false);
  parameter Boolean anom_pollution = false annotation(Evaluate = false);
  parameter Boolean anom_valve_in0 = false annotation(Evaluate = false);
  parameter Boolean anom_pump50 = false annotation(Evaluate = false);
  parameter Boolean anom_pump75 = false annotation(Evaluate = false);
  Real pollution_value(start=0.5);
  Real var_valve_in(start=0.0);
  Real var_pump_n(start=1.0);
  Real pump_n_in;
  Boolean fault_window_active;
  
  // ports
  Modelica.Fluid.Interfaces.FluidPort_a port_in0(redeclare package Medium = Medium) annotation(
    Placement(transformation(origin = {-170, 110}, extent = {{10, -10}, {-10, 10}}), iconTransformation(origin = {70, 0}, extent = {{10, -10}, {-10, 10}})));
  Modelica.Fluid.Interfaces.FluidPort_b port_out0(redeclare package Medium = Medium) annotation(
    Placement(transformation(origin = {170, -110}, extent = {{10, -10}, {-10, 10}}), iconTransformation(origin = {70, 0}, extent = {{10, -10}, {-10, 10}})));
  Modelica.Fluid.Sources.FixedBoundary anom_sink(redeclare package Medium = Medium, nPorts = 1, p = 0.999e5)  annotation(
    Placement(transformation(origin = {90, -150}, extent = {{10, -10}, {-10, 10}}, rotation = -0)));
  
  // tanks
  Modelica.Fluid.Examples.AST_BatchPlant.BaseClasses.TankWithTopPorts tank_B101(redeclare package Medium = Medium, V0 = 0.0001, crossArea = 0.01431355, height = 0.22, level_start = 0.01, nPorts = 1, nTopPorts = 1, portsData = {Modelica.Fluid.Vessels.BaseClasses.VesselPortsData(diameter = 0.011, height = 0.001, zeta_out = 0, zeta_in = 1)}, stiffCharacteristicForEmptyPort = false, energyDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, massDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, p_ambient(displayUnit = "Pa") = 1e5) annotation(
    Placement(transformation(origin = {-170, 18}, extent = {{-20, -20}, {20, 20}})));

  Modelica.Fluid.Examples.AST_BatchPlant.BaseClasses.TankWithTopPorts tank_B102(redeclare package Medium = Medium, V0 = 0.0001, crossArea = 0.01431355, height = 0.22, level_start = 0.01, nPorts = 1, nTopPorts = 1, portsData = {Modelica.Fluid.Vessels.BaseClasses.VesselPortsData(diameter = 0.011, height = 0.001, zeta_out = 0, zeta_in = 1)}, stiffCharacteristicForEmptyPort = false, energyDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, massDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, p_ambient(displayUnit = "Pa") = 1e5) annotation(
    Placement(transformation(origin = {170, 20}, extent = {{-20, -20}, {20, 20}})));
  
  // pipes
  Modelica.Fluid.Pipes.StaticPipe pipe0(redeclare package Medium = Medium, length = 1, diameter(displayUnit = "mm") = 0.01) annotation(
    Placement(transformation(origin = {-170, -30}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Pipes.StaticPipe pipe1(redeclare package Medium = Medium, diameter(displayUnit = "mm") = 0.01, length = 1) annotation(
    Placement(transformation(origin = {-50, -150}, extent = {{-10, 10}, {10, -10}})));
  Modelica.Fluid.Pipes.StaticPipe pipe2(redeclare package Medium = Medium, diameter(displayUnit = "mm") = 0.01, length = 1) annotation(
    Placement(transformation(origin = {170, -30}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Pipes.StaticPipe pipe3(redeclare package Medium = Medium, diameter(displayUnit = "mm") = 0.01, length = 1) annotation(
    Placement(transformation(origin = {30, -90}, extent = {{-10, 10}, {10, -10}}, rotation = 90)));
  Modelica.Fluid.Pipes.StaticPipe pipe4(redeclare package Medium = Medium, diameter(displayUnit = "mm") = 0.01, length = 1) annotation(
    Placement(transformation(origin = {170, 70}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));

  // valves
  Modelica.Fluid.Valves.ValveLinear valve_in(redeclare package Medium = Medium, dp(start = 1), m_flow(start = 1e-5), dp_nominal = 1, m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {-170, 70}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Valves.ValveLinear valve_out(redeclare package Medium = Medium, dp(start = 1e5), dp_nominal = 1, m_flow(start = 0.0001), m_flow_nominal = 1) annotation(
    Placement(transformation(origin = {170, -70}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Valves.ValveLinear valve_pump_P101(redeclare package Medium = Medium, dp(start = 1), dp_nominal = 1, m_flow(start = 1e-5), m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {-170, -70}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  
  Modelica.Fluid.Valves.ValveLinear leaking_valve(redeclare package Medium = Medium, dp(start = 1), dp_nominal = 1, m_flow(start = 1e-5), m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {50, -150}, extent = {{10, 10}, {-10, -10}}, rotation = 180)));
  Modelica.Fluid.Valves.ValveLinear clogging_valve(redeclare package Medium = Medium, dp(start = 1), dp_nominal = 1, m_flow(start = 1e-5), m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {-10, -150}, extent = {{10, 10}, {-10, -10}}, rotation = 180)));

  // machines
  Modelica.Fluid.Machines.PrescribedPump pump_P101(redeclare package Medium = Medium, N_nominal = 166.43, m_flow_start = 0.000001, T_start = 300, V(displayUnit = "m3") = 0.00004398128, checkValve = false, energyDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, redeclare function flowCharacteristic = Modelica.Fluid.Machines.BaseClasses.PumpCharacteristics.quadraticFlow(V_flow_nominal = {pump_P101_V_flow_at_max_head, pump_P101_V_flow_at_middle_head, pump_P101_V_flow_at_min_head}, head_nominal = {pump_P101_head_max, pump_P101_head_middle, pump_P101_head_min}), massDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, nParallel = 1, p_a_start = 100000, p_b_start = 100000, use_N_in = true, allowFlowReversal = true) annotation(Placement(transformation(origin = {-90, -150}, extent = {{-10, 10}, {10, -10}})));
  Modelica.Blocks.Continuous.FirstOrder firstOrder(T = 1)  annotation(
    Placement(transformation(origin = {-110, -190}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Blocks.Sources.RealExpression n_in(y = pump_n_in) annotation(
    Placement(transformation(origin = {-190, -164}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Blocks.Noise.UniformNoise uniformNoise(samplePeriod = 1, y_min = 0.8, y_max = 1.2, useAutomaticLocalSeed = false, fixedLocalSeed = noiseSeed)  annotation(
    Placement(transformation(origin = {-190, -190}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Blocks.Math.Product product1 annotation(
    Placement(transformation(origin = {-150, -190}, extent = {{-10, -10}, {10, 10}})));

  //filter
  Modelica.Fluid.Valves.ValveLinear filter_F101(redeclare package Medium = Medium, dp(start = 1), dp_nominal = 1, m_flow(start = 1e-5), m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {30, -48}, extent = {{10, 10}, {-10, -10}}, rotation = -90)));
  Modelica.Blocks.Math.Division division annotation(
    Placement(transformation(origin = {0, 100}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Blocks.Math.Product product annotation(
    Placement(transformation(origin = {-60, 60}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Blocks.Math.Add add annotation(
    Placement(transformation(origin = {-28, 80}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Blocks.Continuous.Integrator integrator annotation(
    Placement(transformation(origin = {-90, 50}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Blocks.Sources.RealExpression const1(y = 1.0)  annotation(
    Placement(transformation(origin = {-120, 110}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Blocks.Sources.RealExpression const2(y = 1.0)  annotation(
    Placement(transformation(origin = {-120, 90}, extent = {{-10, -10}, {10, 10}})));  
  Modelica.Blocks.Sources.RealExpression pollution(y = pollution_value)  annotation(
    Placement(transformation(origin = {-120, 70}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Blocks.Sources.RealExpression mflow_filter(y = filter_F101.port_a.m_flow)  annotation(
    Placement(transformation(origin = {-120, 50}, extent = {{-10, -10}, {10, 10}})));

  // sensors
  Modelica.Fluid.Sensors.VolumeFlowRate sensor_continuous_volumeFlowRate(redeclare package Medium=Medium) annotation(
    Placement(transformation(origin = {30, -10}, extent = {{-10, -10}, {10, 10}}, rotation = 90)));
  Modelica.Fluid.Sensors.Pressure sensor_continuous_pressure_tank_B101(redeclare package Medium=Medium) annotation(
    Placement(transformation(origin = {-210, -30}, extent = {{-10, -10}, {10, 10}}, rotation = 90)));
  Modelica.Fluid.Sensors.Pressure sensor_continuous_pressure_tank_B102(redeclare package Medium=Medium) annotation(
    Placement(transformation(origin = {130, -30}, extent = {{-10, -10}, {10, 10}}, rotation = 90)));
  Modelica.Fluid.Sensors.Pressure sensor_continuous_pressure_pump_P101(redeclare package Medium=Medium) annotation(
    Placement(transformation(origin = {-80, -110}, extent = {{-10, -10}, {10, 10}})));
  //// tank B101
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B101_low(threshold = 0.1 * tank_B101.height)  annotation(
    Placement(transformation(origin = {-207, 1}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B101_medium(threshold = 0.5 * tank_B101.height)  annotation(
    Placement(transformation(origin = {-207, 15}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B101_high(threshold = 0.9 * tank_B101.height)  annotation(
    Placement(transformation(origin = {-207, 29}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Sources.RealExpression tank_B101_level(y = tank_B101.level) annotation(
    Placement(transformation(origin = {-202, 42}, extent = {{10, -10}, {-10, 10}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B101_low annotation(
    Placement(transformation(origin = {-187, 1}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B101_medium annotation(
    Placement(transformation(origin = {-187, 15}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B101_high annotation(
    Placement(transformation(origin = {-187, 29}, extent = {{-5, -5}, {5, 5}})));
  //// tank B102
  Modelica.Blocks.Sources.RealExpression tank_B102_level(y = tank_B102.level) annotation(
    Placement(transformation(origin = {138, 44}, extent = {{10, -10}, {-10, 10}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B102_high(threshold = 0.9 * tank_B102.height) annotation(
    Placement(transformation(origin = {133, 31}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B102_medium(threshold = 0.5 * tank_B102.height) annotation(
    Placement(transformation(origin = {133, 17}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B102_low(threshold = 0.1 * tank_B102.height) annotation(
    Placement(transformation(origin = {133, 3}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B102_high annotation(
    Placement(transformation(origin = {153, 31}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B102_medium annotation(
    Placement(transformation(origin = {153, 17}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B102_low annotation(
    Placement(transformation(origin = {153, 3}, extent = {{-5, -5}, {5, 5}})));


  // stategraph
  inner Modelica.StateGraph.StateGraphRoot stateGraphRoot annotation(
    Placement(transformation(origin = {-170, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.Step state_filling_tank_B101(nIn = 2, nOut = 1)  annotation(
    Placement(transformation(origin = {-50, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.Step state_emptying_tank_B101(nIn = 1, nOut = 1)  annotation(
    Placement(transformation(origin = {30, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.InitialStep state_initialStep(nOut = 1, nIn = 1) annotation(
    Placement(transformation(origin = {-110, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.Transition condition_init_step annotation(
    Placement(transformation(origin = {-80, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.TransitionWithSignal condition_is_full_tank_B101 annotation(
    Placement(transformation(origin = {-10, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.TransitionWithSignal condition_is_empty_tank_B101 annotation(
    Placement(transformation(origin = {72, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.Step state_emptying_tank_B102(nIn = 1, nOut = 1) annotation(
    Placement(transformation(origin = {112, 170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.TransitionWithSignal state_is_empty_tank_B102 annotation(
    Placement(transformation(origin = {152, 170}, extent = {{-10, -10}, {10, 10}})));
equation
  assert(not (anom_pump50 and anom_pump75), "Filter pump50 and pump75 faults are mutually exclusive");
  fault_window_active = time >= anom_start;
  // state graph equations
  condition_is_full_tank_B101.condition = tank_B101.level >= tank_B101.height*tankMaxVol;
  condition_is_empty_tank_B101.condition = tank_B101.level <= tank_B101.height*tankMinVol;
  state_is_empty_tank_B102.condition = tank_B102.level <= tank_B102.height*tankMinVol;
  valve_in.opening = if state_filling_tank_B101.active then 1.0 else max(closedValveOpening, var_valve_in);
  valve_pump_P101.opening = if state_emptying_tank_B101.active then 1.0 else closedValveOpening;
  pump_n_in = if state_emptying_tank_B101.active then 150.0 * var_pump_n else 0.0;
  valve_out.opening = if state_emptying_tank_B102.active then 1.0 else closedValveOpening;

  // anomalies
  leaking_valve.opening = if (fault_window_active and anom_leaking) then 0.25 else 0.0;
  clogging_valve.opening = 1.0;
  pollution_value = if (fault_window_active and anom_pollution) then 1.0 else 0.5;
  var_valve_in = if (fault_window_active and anom_valve_in0) then 0.2 else 0.0;
  var_pump_n = if (fault_window_active and anom_pump50) then 0.5 else if (fault_window_active and anom_pump75) then 0.75 else 1.0;
  
  // connections
  connect(tank_B101.ports[1], pipe0.port_a) annotation(
    Line(points = {{-170, -3}, {-170, -20}}, color = {0, 127, 255}));
  connect(valve_in.port_a, port_in0) annotation(
    Line(points = {{-170, 80}, {-170, 110}}, color = {0, 127, 255}));
  connect(valve_in.port_b, tank_B101.topPorts[1]) annotation(
    Line(points = {{-170, 60}, {-170, 39}}, color = {0, 127, 255}));
  connect(valve_out.port_b, port_out0) annotation(
    Line(points = {{170, -80}, {170, -110}}, color = {0, 127, 255}));
  connect(state_initialStep.outPort[1], condition_init_step.inPort) annotation(
    Line(points = {{-99.5, 170}, {-83.5, 170}}));
  connect(condition_init_step.outPort, state_filling_tank_B101.inPort[1]) annotation(
    Line(points = {{-78.5, 170}, {-60.5, 170}}));
  connect(state_filling_tank_B101.outPort[1], condition_is_full_tank_B101.inPort) annotation(
    Line(points = {{-39.5, 170}, {-13.5, 170}}));
  connect(condition_is_full_tank_B101.outPort, state_emptying_tank_B101.inPort[1]) annotation(
    Line(points = {{-8.5, 170}, {19, 170}}));
  connect(state_emptying_tank_B101.outPort[1], condition_is_empty_tank_B101.inPort) annotation(
    Line(points = {{40.5, 170}, {68, 170}}));
  connect(pipe0.port_b, valve_pump_P101.port_a) annotation(
    Line(points = {{-170, -40}, {-170, -60}}, color = {0, 127, 255}));
  connect(valve_pump_P101.port_b, pump_P101.port_a) annotation(
    Line(points = {{-170, -80}, {-170, -150}, {-100, -150}}, color = {0, 127, 255}));
  connect(condition_is_empty_tank_B101.outPort, state_emptying_tank_B102.inPort[1]) annotation(
    Line(points = {{73.5, 170}, {101.5, 170}}));
  connect(state_emptying_tank_B102.outPort[1], state_is_empty_tank_B102.inPort) annotation(
    Line(points = {{122.5, 170}, {148.5, 170}}));
  connect(state_is_empty_tank_B102.outPort, state_initialStep.inPort[1]) annotation(
    Line(points = {{153.5, 170}, {179.5, 170}, {179.5, 140}, {-140.5, 140}, {-140.5, 170}, {-120.5, 170}}));
  connect(tank_B102.ports[1], pipe2.port_a) annotation(
    Line(points = {{170, -1}, {170, -21}}, color = {0, 127, 255}));
  connect(pipe2.port_b, valve_out.port_a) annotation(
    Line(points = {{170, -40}, {170, -60}}, color = {0, 127, 255}));
  connect(pump_P101.port_b, pipe1.port_a) annotation(
    Line(points = {{-80, -150}, {-60, -150}}, color = {0, 127, 255}));
  connect(pipe4.port_b, tank_B102.topPorts[1]) annotation(
    Line(points = {{170, 60}, {170, 42}}, color = {0, 127, 255}));
  connect(pipe3.port_b, filter_F101.port_a) annotation(
    Line(points = {{30, -80}, {30, -58}}, color = {0, 127, 255}));
  connect(mflow_filter.y, integrator.u) annotation(
    Line(points = {{-109, 50}, {-102, 50}}, color = {0, 0, 127}));
  connect(pollution.y, product.u1) annotation(
    Line(points = {{-109, 70}, {-73, 70}, {-73, 66}, {-72, 66}}, color = {0, 0, 127}));
  connect(integrator.y, product.u2) annotation(
    Line(points = {{-78, 50}, {-72, 50}, {-72, 54}}, color = {0, 0, 127}));
  connect(product.y, add.u2) annotation(
    Line(points = {{-49, 60}, {-40, 60}, {-40, 74}}, color = {0, 0, 127}));
  connect(const2.y, add.u1) annotation(
    Line(points = {{-109, 90}, {-41, 90}, {-41, 88}, {-40.5, 88}, {-40.5, 86}, {-40, 86}}, color = {0, 0, 127}));
  connect(add.y, division.u2) annotation(
    Line(points = {{-17, 80}, {-12, 80}, {-12, 94}}, color = {0, 0, 127}));
  connect(const1.y, division.u1) annotation(
    Line(points = {{-109, 110}, {-13, 110}, {-13, 108}, {-13.5, 108}, {-13.5, 106}, {-12, 106}}, color = {0, 0, 127}));
  connect(division.y, filter_F101.opening) annotation(
    Line(points = {{11, 100}, {20, 100}, {20, -48}, {22, -48}}, color = {0, 0, 127}));
  connect(firstOrder.y, pump_P101.N_in) annotation(
    Line(points = {{-99, -190}, {-90, -190}, {-90, -160}}, color = {0, 0, 127}));
  connect(pipe1.port_b, clogging_valve.port_a) annotation(
    Line(points = {{-40, -150}, {-20, -150}}, color = {0, 127, 255}));
  connect(clogging_valve.port_b, pipe3.port_a) annotation(
    Line(points = {{0, -150}, {30, -150}, {30, -100}}, color = {0, 127, 255}));
  connect(clogging_valve.port_b, leaking_valve.port_a) annotation(
    Line(points = {{0, -150}, {40, -150}}, color = {0, 127, 255}));
  connect(leaking_valve.port_b, anom_sink.ports[1]) annotation(
    Line(points = {{60, -150}, {80, -150}}, color = {0, 127, 255}));
  connect(product1.y, firstOrder.u) annotation(
    Line(points = {{-138, -190}, {-122, -190}}, color = {0, 0, 127}));
  connect(uniformNoise.y, product1.u2) annotation(
    Line(points = {{-178, -190}, {-172, -190}, {-172, -196}, {-162, -196}}, color = {0, 0, 127}));
  connect(n_in.y, product1.u1) annotation(
    Line(points = {{-178, -164}, {-170, -164}, {-170, -184}, {-162, -184}}, color = {0, 0, 127}));
  connect(tank_B101_level.y, level_to_boolean_tank_B101_high.u) annotation(
    Line(points = {{-213, 42}, {-221, 42}, {-221, 30}, {-213, 30}}, color = {0, 0, 127}));
  connect(tank_B101_level.y, level_to_boolean_tank_B101_medium.u) annotation(
    Line(points = {{-213, 42}, {-221, 42}, {-221, 16}, {-213, 16}}, color = {0, 0, 127}));
  connect(tank_B101_level.y, level_to_boolean_tank_B101_low.u) annotation(
    Line(points = {{-213, 42}, {-221, 42}, {-221, 2}, {-213, 2}}, color = {0, 0, 127}));
  connect(level_to_boolean_tank_B101_high.y, sensor_discrete_tank_B101_high.activePort) annotation(
    Line(points = {{-201.5, 29}, {-191.5, 29}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B101_medium.y, sensor_discrete_tank_B101_medium.activePort) annotation(
    Line(points = {{-201.5, 15}, {-191.5, 15}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B101_low.y, sensor_discrete_tank_B101_low.activePort) annotation(
    Line(points = {{-201.5, 1}, {-191.5, 1}}, color = {255, 0, 255}));
  connect(tank_B102_level.y, level_to_boolean_tank_B102_high.u) annotation(
    Line(points = {{128, 44}, {120, 44}, {120, 32}, {128, 32}}, color = {0, 0, 127}));
  connect(tank_B102_level.y, level_to_boolean_tank_B102_medium.u) annotation(
    Line(points = {{128, 44}, {120, 44}, {120, 18}, {128, 18}}, color = {0, 0, 127}));
  connect(tank_B102_level.y, level_to_boolean_tank_B102_low.u) annotation(
    Line(points = {{128, 44}, {120, 44}, {120, 4}, {128, 4}}, color = {0, 0, 127}));
  connect(level_to_boolean_tank_B102_high.y, sensor_discrete_tank_B102_high.activePort) annotation(
    Line(points = {{138, 32}, {148, 32}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B102_medium.y, sensor_discrete_tank_B102_medium.activePort) annotation(
    Line(points = {{138, 18}, {148, 18}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B102_low.y, sensor_discrete_tank_B102_low.activePort) annotation(
    Line(points = {{138, 4}, {148, 4}}, color = {255, 0, 255}));
  connect(pump_P101.port_b, sensor_continuous_pressure_pump_P101.port) annotation(
    Line(points = {{-80, -150}, {-80, -120}}, color = {0, 127, 255}));
  connect(pipe0.port_a, sensor_continuous_pressure_tank_B101.port) annotation(
    Line(points = {{-170, -20}, {-200, -20}, {-200, -30}}, color = {0, 127, 255}));
  connect(pipe2.port_a, sensor_continuous_pressure_tank_B102.port) annotation(
    Line(points = {{170, -20}, {140, -20}, {140, -30}}, color = {0, 127, 255}));
  connect(filter_F101.port_b, sensor_continuous_volumeFlowRate.port_a) annotation(
    Line(points = {{30, -38}, {30, -20}}, color = {0, 127, 255}));
  connect(sensor_continuous_volumeFlowRate.port_b, pipe4.port_a) annotation(
    Line(points = {{30, 0}, {30, 100}, {170, 100}, {170, 80}}, color = {0, 127, 255}));
  annotation(
    uses(Modelica(version = "4.0.0")),
  Diagram(coordinateSystem(extent = {{-200, -200}, {200, 200}})),
  Icon(coordinateSystem(extent = {{-200, -200}, {200, 200}})),
  version = "");
end filterModule;
