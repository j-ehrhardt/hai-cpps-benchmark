model mixerModule
  replaceable package Medium = Modelica.Media.Water.StandardWater;
  parameter Real tankMinVol = 0.1;
  parameter Real tankMaxVol = 0.45;
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
  parameter Boolean anom_valve_in0 = false annotation(Evaluate = false);
  parameter Boolean anom_valve_in1 = false annotation(Evaluate = false);
  parameter Boolean anom_valve_in2 = false annotation(Evaluate = false);
  parameter Boolean anom_pump50 = false annotation(Evaluate = false);
  parameter Boolean anom_pump75 = false annotation(Evaluate = false);
  Real var_valve_in0(start = 0.0);
  Real var_valve_in1(start = 0.0);
  Real var_valve_in2(start = 0.0);
  Real var_pump_n(start = 1.0);
  Real pump_n_in;
  Boolean fault_window_active;
  // ports
  Modelica.Fluid.Interfaces.FluidPort_a port_in0(redeclare package Medium = Medium) annotation(
    Placement(transformation(origin = {-150, 110}, extent = {{10, -10}, {-10, 10}}), iconTransformation(origin = {-210, 0}, extent = {{10, -10}, {-10, 10}})));
  Modelica.Fluid.Interfaces.FluidPort_a port_in1(redeclare package Medium = Medium) annotation(
    Placement(transformation(origin = {-50, 110}, extent = {{10, -10}, {-10, 10}}), iconTransformation(origin = {-210, 128}, extent = {{10, -10}, {-10, 10}})));
  Modelica.Fluid.Interfaces.FluidPort_a port_in2(redeclare package Medium = Medium) annotation(
    Placement(transformation(origin = {50, 110}, extent = {{10, -10}, {-10, 10}}), iconTransformation(origin = {-210, -110}, extent = {{10, -10}, {-10, 10}})));
  Modelica.Fluid.Interfaces.FluidPort_b port_out0(redeclare package Medium = Medium) annotation(
    Placement(transformation(origin = {180, -110}, extent = {{10, -10}, {-10, 10}}), iconTransformation(origin = {210, 0}, extent = {{10, -10}, {-10, 10}})));
  Modelica.Fluid.Sources.FixedBoundary anom_sink(redeclare package Medium = Medium, nPorts = 1, p = 1e5) annotation(
    Placement(transformation(origin = {70, -170}, extent = {{-10, -10}, {10, 10}})));
  // tanks
  Modelica.Fluid.Examples.AST_BatchPlant.BaseClasses.TankWithTopPorts tank_B201(redeclare package Medium = Medium, V0 = 0.0001, crossArea = 0.01431355, height = 0.14, level_start = 0.01, nPorts = 1, nTopPorts = 1, portsData = {Modelica.Fluid.Vessels.BaseClasses.VesselPortsData(diameter = 0.011, height = 0.001, zeta_out = 0, zeta_in = 1)}, stiffCharacteristicForEmptyPort = false, energyDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, massDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, p_ambient(displayUnit = "Pa") = 1e5) annotation(
    Placement(transformation(origin = {-150, 10}, extent = {{-20, -20}, {20, 20}})));
  Modelica.Fluid.Examples.AST_BatchPlant.BaseClasses.TankWithTopPorts tank_B202(redeclare package Medium = Medium, V0 = 0.0001, crossArea = 0.01431355, energyDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, height = 0.14, level_start = 0.01, massDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, nPorts = 1, nTopPorts = 1, p_ambient(displayUnit = "Pa") = 1e5, portsData = {Modelica.Fluid.Vessels.BaseClasses.VesselPortsData(diameter = 0.011, height = 0.001, zeta_out = 0, zeta_in = 1)}, stiffCharacteristicForEmptyPort = false) annotation(
    Placement(transformation(origin = {-50, 10}, extent = {{-20, -20}, {20, 20}})));
  Modelica.Fluid.Examples.AST_BatchPlant.BaseClasses.TankWithTopPorts tank_B203(redeclare package Medium = Medium, V0 = 0.0001, crossArea = 0.01431355, energyDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, height = 0.14, level_start = 0.01, massDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, nPorts = 1, nTopPorts = 1, p_ambient(displayUnit = "Pa") = 1e5, portsData = {Modelica.Fluid.Vessels.BaseClasses.VesselPortsData(diameter = 0.011, height = 0.001, zeta_out = 0, zeta_in = 1)}, stiffCharacteristicForEmptyPort = false) annotation(
    Placement(transformation(origin = {50, 10}, extent = {{-20, -20}, {20, 20}})));
  Modelica.Fluid.Examples.AST_BatchPlant.BaseClasses.TankWithTopPorts tank_B204(redeclare package Medium = Medium, V0 = 0.0001, crossArea = 0.01431355, height = 0.22, level_start = 0.01, nPorts = 1, nTopPorts = 1, portsData = {Modelica.Fluid.Vessels.BaseClasses.VesselPortsData(diameter = 0.011, height = 0.001, zeta_out = 0, zeta_in = 1)}, stiffCharacteristicForEmptyPort = false, energyDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, massDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, p_ambient(displayUnit = "Pa") = 1e5) annotation(
    Placement(transformation(origin = {180, 10}, extent = {{-20, -20}, {20, 20}})));
  // pipes
  Modelica.Fluid.Pipes.StaticPipe pipe0(redeclare package Medium = Medium, length = 1, diameter(displayUnit = "mm") = 0.01) annotation(
    Placement(transformation(origin = {-150, -30}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Pipes.StaticPipe pipe2(redeclare package Medium = Medium, diameter(displayUnit = "mm") = 0.01, length = 1) annotation(
    Placement(transformation(origin = {-50, -30}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Pipes.StaticPipe pipe4(redeclare package Medium = Medium, diameter(displayUnit = "mm") = 0.01, length = 1) annotation(
    Placement(transformation(origin = {50, -30}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Pipes.StaticPipe pipe5(redeclare package Medium = Medium, diameter(displayUnit = "mm") = 0.01, length = 1, m_flow_start = 0.0005) annotation(
    Placement(transformation(origin = {110, -90}, extent = {{-10, 10}, {10, -10}}, rotation = 90)));
  Modelica.Fluid.Pipes.StaticPipe pipe6(redeclare package Medium = Medium, diameter(displayUnit = "mm") = 0.01, length = 1, m_flow_start = 0.0005) annotation(
    Placement(transformation(origin = {-10, -130}, extent = {{-10, 10}, {10, -10}})));
  Modelica.Fluid.Fittings.TeeJunctionVolume tee0(redeclare package Medium = Medium, V = 0.001) annotation(
    Placement(transformation(origin = {-130, -110}, extent = {{-10, 10}, {10, -10}})));
  Modelica.Fluid.Fittings.TeeJunctionVolume tee1(redeclare package Medium = Medium, V = 0.001) annotation(
    Placement(transformation(origin = {-50, -110}, extent = {{-10, -10}, {10, 10}})));
  // valves
  Modelica.Fluid.Valves.ValveLinear valve_in0(redeclare package Medium = Medium, dp(start = 1), m_flow(start = 1e-5), dp_nominal = 1, m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {-150, 70}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Valves.ValveLinear valve_in1(redeclare package Medium = Medium, dp(start = 1), dp_nominal = 1, m_flow(start = 1e-5), m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {-50, 70}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Valves.ValveLinear valve_in2(redeclare package Medium = Medium, dp(start = 1), dp_nominal = 1, m_flow(start = 1e-5), m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {50, 70}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Valves.ValveLinear valve_out(redeclare package Medium = Medium, dp(start = 1e5), dp_nominal = 1, m_flow(start = 0.0001), m_flow_nominal = 1) annotation(
    Placement(transformation(origin = {180, -70}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Valves.ValveLinear valve_pump_tank_B201(redeclare package Medium = Medium, dp(start = 1), dp_nominal = 1, m_flow(start = 1e-5), m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {-150, -70}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Valves.ValveLinear valve_pump_tank_B202(redeclare package Medium = Medium, dp(start = 1), dp_nominal = 1, m_flow(start = 1e-5), m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {-50, -70}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Valves.ValveLinear valve_pump_tank_B203(redeclare package Medium = Medium, dp(start = 1), dp_nominal = 1, m_flow(start = 1e-5), m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {50, -70}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
  Modelica.Fluid.Valves.ValveLinear valve_pump_tank_B204(redeclare package Medium = Medium, dp(start = 1), dp_nominal = 1, m_flow(start = 1e-5), m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {110, -50}, extent = {{-10, 10}, {10, -10}}, rotation = 90)));
  Modelica.Fluid.Valves.ValveLinear leaking_valve(redeclare package Medium = Medium, dp(start = 1), dp_nominal = 1, m_flow(start = 1e-5), m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {110, -150}, extent = {{10, 10}, {-10, -10}}, rotation = 90)));
  Modelica.Fluid.Valves.ValveLinear clogging_valve(redeclare package Medium = Medium, dp(start = 1), dp_nominal = 1, m_flow(start = 1e-5), m_flow_nominal = 1e-3) annotation(
    Placement(transformation(origin = {50, -130}, extent = {{10, -10}, {-10, 10}}, rotation = -180)));
  // machines
  Modelica.Fluid.Machines.PrescribedPump pump_P101(redeclare package Medium = Medium, N_nominal = 166.43, m_flow_start = 0.000001, T_start = 300, V(displayUnit = "m3") = 0.00004398128, checkValve = false, energyDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, redeclare function flowCharacteristic = Modelica.Fluid.Machines.BaseClasses.PumpCharacteristics.quadraticFlow(V_flow_nominal = {pump_P101_V_flow_at_max_head, pump_P101_V_flow_at_middle_head, pump_P101_V_flow_at_min_head}, head_nominal = {pump_P101_head_max, pump_P101_head_middle, pump_P101_head_min}), massDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial, nParallel = 1, p_a_start = 100000, p_b_start = 100000, use_N_in = true, allowFlowReversal = true) annotation(
    Placement(transformation(origin = {-70, -130}, extent = {{-10, 10}, {10, -10}})));
  Modelica.Blocks.Continuous.FirstOrder firstOrder(T = 1) annotation(
    Placement(transformation(origin = {-110, -170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Blocks.Sources.RealExpression n_in(y = pump_n_in) annotation(
    Placement(transformation(origin = {-190, -150}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Blocks.Noise.UniformNoise uniformNoise(samplePeriod = 1, y_max = 1.2, y_min = 0.8, useAutomaticLocalSeed = false, fixedLocalSeed = noiseSeed) annotation(
    Placement(transformation(origin = {-190, -170}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Blocks.Math.Product product1 annotation(
    Placement(transformation(origin = {-150, -170}, extent = {{-10, -10}, {10, 10}})));
  // sensors
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B201_low(threshold = 0.1*tank_B201.height) annotation(
    Placement(transformation(origin = {-187, -5}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B201_medium(threshold = 0.5*tank_B201.height) annotation(
    Placement(transformation(origin = {-187, 9}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B201_high(threshold = 0.9*tank_B201.height) annotation(
    Placement(transformation(origin = {-187, 23}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Sources.RealExpression tank_B201_level(y = tank_B201.level) annotation(
    Placement(transformation(origin = {-182, 36}, extent = {{10, -10}, {-10, 10}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B201_low annotation(
    Placement(transformation(origin = {-167, -5}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B201_medium annotation(
    Placement(transformation(origin = {-167, 9}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B201_high annotation(
    Placement(transformation(origin = {-167, 23}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B202_low(threshold = 0.1*tank_B202.height) annotation(
    Placement(transformation(origin = {-87, -5}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B202_medium(threshold = 0.5*tank_B202.height) annotation(
    Placement(transformation(origin = {-87, 9}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B202_high(threshold = 0.9*tank_B202.height) annotation(
    Placement(transformation(origin = {-87, 23}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Sources.RealExpression tank_B202_level(y = tank_B202.level) annotation(
    Placement(transformation(origin = {-82, 36}, extent = {{10, -10}, {-10, 10}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B202_low annotation(
    Placement(transformation(origin = {-67, -5}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B202_medium annotation(
    Placement(transformation(origin = {-67, 9}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B202_high annotation(
    Placement(transformation(origin = {-67, 23}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B203_low(threshold = 0.1*tank_B203.height) annotation(
    Placement(transformation(origin = {13, -5}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B203_medium(threshold = 0.5*tank_B203.height) annotation(
    Placement(transformation(origin = {13, 9}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B203_high(threshold = 0.9*tank_B203.height) annotation(
    Placement(transformation(origin = {13, 23}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Sources.RealExpression tank_B203_level(y = tank_B203.level) annotation(
    Placement(transformation(origin = {18, 36}, extent = {{10, -10}, {-10, 10}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B203_low annotation(
    Placement(transformation(origin = {33, -5}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B203_medium annotation(
    Placement(transformation(origin = {33, 9}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B203_high annotation(
    Placement(transformation(origin = {33, 23}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B204_low(threshold = 0.1*tank_B204.height) annotation(
    Placement(transformation(origin = {145, -5}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B204_medium(threshold = 0.5*tank_B204.height) annotation(
    Placement(transformation(origin = {145, 9}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Math.RealToBoolean level_to_boolean_tank_B204_high(threshold = 0.9*tank_B204.height) annotation(
    Placement(transformation(origin = {145, 23}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Sources.RealExpression tank_B204_level(y = tank_B204.level) annotation(
    Placement(transformation(origin = {150, 36}, extent = {{10, -10}, {-10, 10}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B204_low annotation(
    Placement(transformation(origin = {165, -5}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B204_medium annotation(
    Placement(transformation(origin = {165, 9}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Blocks.Interaction.Show.BooleanValue sensor_discrete_tank_B204_high annotation(
    Placement(transformation(origin = {165, 23}, extent = {{-5, -5}, {5, 5}})));
  Modelica.Fluid.Sensors.Pressure sensor_continuous_pressure_tank_B201(replaceable package Medium = Medium) annotation(
    Placement(transformation(origin = {-190, -30}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Fluid.Sensors.Pressure sensor_continuous_pressure_tank_B202(replaceable package Medium = Medium) annotation(
    Placement(transformation(origin = {-90, -30}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Fluid.Sensors.Pressure sensor_continuous_pressure_tank_B203(replaceable package Medium = Medium) annotation(
    Placement(transformation(origin = {10, -30}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Fluid.Sensors.Pressure sensor_continuous_pressure_tank_B204(replaceable package Medium = Medium) annotation(
    Placement(transformation(origin = {150, -30}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Fluid.Sensors.Pressure pressure_pump_P101(replaceable package Medium = Medium) annotation(
    Placement(transformation(origin = {130, -130}, extent = {{-10, 10}, {10, -10}}, rotation = 90)));
  Modelica.Fluid.Sensors.VolumeFlowRate sensor_continuous_volumeFlowRate(replaceable package Medium = Medium) annotation(
    Placement(transformation(origin = {110, 10}, extent = {{10, -10}, {-10, 10}}, rotation = -90)));
  // stategraph
  inner Modelica.StateGraph.StateGraphRoot stateGraphRoot annotation(
    Placement(transformation(origin = {-180, 150}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.Step state_filling_tank_B201(nIn = 2, nOut = 1) annotation(
    Placement(transformation(origin = {-110, 190}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.Step state_emptying_tank_B201(nIn = 1, nOut = 1) annotation(
    Placement(transformation(origin = {-110, 150}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.InitialStep state_initialStep(nOut = 1, nIn = 1) annotation(
    Placement(transformation(origin = {-180, 190}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.Transition condition_init_step(enableTimer = true, waitTime = 0) annotation(
    Placement(transformation(origin = {-150, 190}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.TransitionWithSignal condition_is_full_tank_B201(enableTimer = true, waitTime = 0) annotation(
    Placement(transformation(origin = {-70, 190}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.TransitionWithSignal condition_is_empty_tank_B201(enableTimer = true, waitTime = 0) annotation(
    Placement(transformation(origin = {-70, 150}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.Step state_filling_tank_B202(nIn = 1, nOut = 1) annotation(
    Placement(transformation(origin = {-30, 190}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.TransitionWithSignal condition_is_full_tank_B202(enableTimer = true, waitTime = 0) annotation(
    Placement(transformation(origin = {10, 190}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.Step state_emptying_tank_B202(nIn = 1, nOut = 1) annotation(
    Placement(transformation(origin = {-30, 150}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.TransitionWithSignal condition_is_empty_tank_B202(enableTimer = true, waitTime = 0) annotation(
    Placement(transformation(origin = {10, 150}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.TransitionWithSignal condition_is_full_tank_B203(enableTimer = true, waitTime = 0) annotation(
    Placement(transformation(origin = {90, 190}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.Step state_filling_tank_B203(nIn = 1, nOut = 1) annotation(
    Placement(transformation(origin = {50, 190}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.TransitionWithSignal condition_is_empty_tank_B203(enableTimer = true, waitTime = 0) annotation(
    Placement(transformation(origin = {90, 150}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.Step state_emptying_tank_B203(nIn = 1, nOut = 1) annotation(
    Placement(transformation(origin = {50, 150}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.Step state_emptying_tank_B204(nIn = 1, nOut = 1) annotation(
    Placement(transformation(origin = {130, 150}, extent = {{-10, -10}, {10, 10}})));
  Modelica.StateGraph.TransitionWithSignal condition_is_empty_tank_B204(enableTimer = true, waitTime = 0) annotation(
    Placement(transformation(origin = {170, 150}, extent = {{-10, -10}, {10, 10}})));
  Modelica.Fluid.Pipes.StaticPipe pipe7(redeclare package Medium = Medium, diameter(displayUnit = "mm") = 0.01, length = 1, m_flow_start = 0.0005) annotation(
    Placement(transformation(origin = {-110, -130}, extent = {{-10, 10}, {10, -10}})));
equation
  assert(not (anom_pump50 and anom_pump75), "Mixer pump50 and pump75 faults are mutually exclusive");
  fault_window_active = time >= anom_start;
  condition_is_full_tank_B201.condition = tank_B201.level >= tank_B201.height*tankMaxVol;
  condition_is_full_tank_B202.condition = tank_B202.level >= tank_B202.height*tankMaxVol;
  condition_is_full_tank_B203.condition = tank_B203.level >= tank_B203.height*tankMaxVol;
  condition_is_empty_tank_B201.condition = tank_B201.level <= tank_B201.height*tankMinVol;
  condition_is_empty_tank_B202.condition = tank_B202.level <= tank_B202.height*tankMinVol;
  condition_is_empty_tank_B203.condition = tank_B203.level <= tank_B203.height*tankMinVol;
  condition_is_empty_tank_B204.condition = tank_B204.level <= tank_B204.height*tankMinVol;
  valve_in0.opening = smooth(1, if state_filling_tank_B201.active then 1.0 else max(closedValveOpening, var_valve_in0));
  valve_in1.opening = smooth(1, if state_filling_tank_B202.active then 1.0 else max(closedValveOpening, var_valve_in1));
  valve_in2.opening = smooth(1, if state_filling_tank_B203.active then 1.0 else max(closedValveOpening, var_valve_in2));
  valve_pump_tank_B201.opening = smooth(1, if state_emptying_tank_B201.active then 1.0 else closedValveOpening);
  valve_pump_tank_B202.opening = smooth(1, if state_emptying_tank_B202.active then 1.0 else closedValveOpening);
  valve_pump_tank_B203.opening = smooth(1, if state_emptying_tank_B203.active then 1.0 else closedValveOpening);
  valve_pump_tank_B204.opening = smooth(1, if state_emptying_tank_B201.active then 1.0 elseif state_emptying_tank_B202.active then 1.0 elseif state_emptying_tank_B203.active then 1.0 else closedValveOpening);
  pump_n_in = if state_emptying_tank_B201.active then 150.0*var_pump_n elseif state_emptying_tank_B202.active then 150.0*var_pump_n
   elseif state_emptying_tank_B203.active then 150.0*var_pump_n else 0.0;
  valve_out.opening = if state_emptying_tank_B204.active then 1.0 else closedValveOpening;
// anomalies
  leaking_valve.opening = if (fault_window_active and anom_leaking) then 0.25 else 0.0;
  clogging_valve.opening = 1.0;
  var_valve_in0 = if (fault_window_active and anom_valve_in0) then 0.2 else 0.0;
  var_valve_in1 = if (fault_window_active and anom_valve_in1) then 0.2 else 0.0;
  var_valve_in2 = if (fault_window_active and anom_valve_in2) then 0.2 else 0.0;
  var_pump_n = if (fault_window_active and anom_pump50) then 0.5 else if (fault_window_active and anom_pump75) then 0.75 else 1.0;
// connections
  connect(tank_B201.ports[1], pipe0.port_a) annotation(
    Line(points = {{-150, -11}, {-150, -20}}, color = {0, 127, 255}));
  connect(valve_in0.port_a, port_in0) annotation(
    Line(points = {{-150, 80}, {-150, 110}}, color = {0, 127, 255}));
  connect(valve_in0.port_b, tank_B201.topPorts[1]) annotation(
    Line(points = {{-150, 60}, {-150, 32}}, color = {0, 127, 255}));
  connect(valve_out.port_b, port_out0) annotation(
    Line(points = {{180, -80}, {180, -110}}, color = {0, 127, 255}));
  connect(state_initialStep.outPort[1], condition_init_step.inPort) annotation(
    Line(points = {{-169.5, 190}, {-153.5, 190}}));
  connect(condition_init_step.outPort, state_filling_tank_B201.inPort[1]) annotation(
    Line(points = {{-148.5, 190}, {-120.5, 190}}));
  connect(state_filling_tank_B201.outPort[1], condition_is_full_tank_B201.inPort) annotation(
    Line(points = {{-99.5, 190}, {-73.5, 190}}));
  connect(state_emptying_tank_B201.outPort[1], condition_is_empty_tank_B201.inPort) annotation(
    Line(points = {{-99.5, 150}, {-74, 150}}));
  connect(tank_B204.ports[1], valve_out.port_a) annotation(
    Line(points = {{180, -11}, {180, -60}}, color = {0, 127, 255}));
  connect(pipe0.port_b, valve_pump_tank_B201.port_a) annotation(
    Line(points = {{-150, -40}, {-150, -60}}, color = {0, 127, 255}));
  connect(state_emptying_tank_B204.outPort[1], condition_is_empty_tank_B204.inPort) annotation(
    Line(points = {{140.5, 150}, {166.5, 150}}));
  connect(valve_in1.port_a, port_in1) annotation(
    Line(points = {{-50, 80}, {-50, 110}}, color = {0, 127, 255}));
  connect(valve_in1.port_b, tank_B202.topPorts[1]) annotation(
    Line(points = {{-50, 60}, {-50, 32}}, color = {0, 127, 255}));
  connect(tank_B202.ports[1], pipe2.port_a) annotation(
    Line(points = {{-50, -11}, {-50, -21}}, color = {0, 127, 255}));
  connect(pipe2.port_b, valve_pump_tank_B202.port_a) annotation(
    Line(points = {{-50, -40}, {-50, -60}}, color = {0, 127, 255}));
  connect(condition_is_full_tank_B201.outPort, state_filling_tank_B202.inPort[1]) annotation(
    Line(points = {{-68.5, 190}, {-40.5, 190}}));
  connect(state_filling_tank_B202.outPort[1], condition_is_full_tank_B202.inPort) annotation(
    Line(points = {{-19.5, 190}, {6.5, 190}}));
  connect(condition_is_empty_tank_B201.outPort, state_emptying_tank_B202.inPort[1]) annotation(
    Line(points = {{-68.5, 150}, {-40.5, 150}}));
  connect(state_emptying_tank_B202.outPort[1], condition_is_empty_tank_B202.inPort) annotation(
    Line(points = {{-19.5, 150}, {6.5, 150}}));
  connect(firstOrder.y, pump_P101.N_in) annotation(
    Line(points = {{-99, -170}, {-71, -170}, {-71, -140}}, color = {0, 0, 127}));
  connect(valve_pump_tank_B201.port_b, tee0.port_1) annotation(
    Line(points = {{-150, -80}, {-150, -110}, {-140, -110}}, color = {0, 127, 255}));
  connect(condition_is_full_tank_B202.outPort, state_filling_tank_B203.inPort[1]) annotation(
    Line(points = {{12, 190}, {40, 190}}));
  connect(state_filling_tank_B203.outPort[1], condition_is_full_tank_B203.inPort) annotation(
    Line(points = {{60, 190}, {86, 190}}));
  connect(condition_is_empty_tank_B202.outPort, state_emptying_tank_B203.inPort[1]) annotation(
    Line(points = {{12, 150}, {40, 150}}));
  connect(state_emptying_tank_B203.outPort[1], condition_is_empty_tank_B203.inPort) annotation(
    Line(points = {{60, 150}, {86, 150}}));
  connect(condition_is_full_tank_B203.outPort, state_emptying_tank_B201.inPort[1]) annotation(
    Line(points = {{92, 190}, {120, 190}, {120, 170}, {-130, 170}, {-130, 150}, {-120, 150}}));
  connect(condition_is_empty_tank_B203.outPort, state_emptying_tank_B204.inPort[1]) annotation(
    Line(points = {{92, 150}, {120, 150}}));
  connect(valve_in2.port_a, port_in2) annotation(
    Line(points = {{50, 80}, {50, 110}}, color = {0, 127, 255}));
  connect(valve_in2.port_b, tank_B203.topPorts[1]) annotation(
    Line(points = {{50, 60}, {50, 32}}, color = {0, 127, 255}));
  connect(tank_B203.ports[1], pipe4.port_a) annotation(
    Line(points = {{50, -11}, {50, -21}}, color = {0, 127, 255}));
  connect(pipe4.port_b, valve_pump_tank_B203.port_a) annotation(
    Line(points = {{50, -40}, {50, -60}}, color = {0, 127, 255}));
  connect(valve_pump_tank_B203.port_b, tee1.port_2) annotation(
    Line(points = {{50, -80}, {50, -110}, {-40, -110}}, color = {0, 127, 255}));
  connect(valve_pump_tank_B202.port_b, tee1.port_3) annotation(
    Line(points = {{-50, -80}, {-50, -100}}, color = {0, 127, 255}));
  connect(tee1.port_1, tee0.port_2) annotation(
    Line(points = {{-60, -110}, {-120, -110}}, color = {0, 127, 255}));
  connect(condition_is_empty_tank_B204.outPort, state_initialStep.inPort[1]) annotation(
    Line(points = {{172, 150}, {200, 150}, {200, 130}, {-200, 130}, {-200, 190}, {-191, 190}}));
  connect(tank_B201_level.y, level_to_boolean_tank_B201_high.u) annotation(
    Line(points = {{-193, 36}, {-201, 36}, {-201, 23}, {-193, 23}}, color = {0, 0, 127}));
  connect(tank_B201_level.y, level_to_boolean_tank_B201_medium.u) annotation(
    Line(points = {{-193, 36}, {-201, 36}, {-201, 9}, {-193, 9}}, color = {0, 0, 127}));
  connect(tank_B201_level.y, level_to_boolean_tank_B201_low.u) annotation(
    Line(points = {{-193, 36}, {-201, 36}, {-201, -5}, {-193, -5}}, color = {0, 0, 127}));
  connect(level_to_boolean_tank_B201_high.y, sensor_discrete_tank_B201_high.activePort) annotation(
    Line(points = {{-181.5, 23}, {-173, 23}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B201_medium.y, sensor_discrete_tank_B201_medium.activePort) annotation(
    Line(points = {{-181.5, 9}, {-173, 9}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B201_low.y, sensor_discrete_tank_B201_low.activePort) annotation(
    Line(points = {{-181.5, -5}, {-173, -5}}, color = {255, 0, 255}));
  connect(tank_B202_level.y, level_to_boolean_tank_B202_high.u) annotation(
    Line(points = {{-93, 36}, {-101, 36}, {-101, 24}, {-93, 24}}, color = {0, 0, 127}));
  connect(tank_B202_level.y, level_to_boolean_tank_B202_medium.u) annotation(
    Line(points = {{-93, 36}, {-101, 36}, {-101, 10}, {-93, 10}}, color = {0, 0, 127}));
  connect(tank_B202_level.y, level_to_boolean_tank_B202_low.u) annotation(
    Line(points = {{-93, 36}, {-101, 36}, {-101, -4}, {-93, -4}}, color = {0, 0, 127}));
  connect(level_to_boolean_tank_B202_high.y, sensor_discrete_tank_B202_high.activePort) annotation(
    Line(points = {{-81.5, 23}, {-71.5, 23}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B202_medium.y, sensor_discrete_tank_B202_medium.activePort) annotation(
    Line(points = {{-81.5, 9}, {-71.5, 9}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B202_low.y, sensor_discrete_tank_B202_low.activePort) annotation(
    Line(points = {{-81.5, -5}, {-71.5, -5}}, color = {255, 0, 255}));
  connect(tank_B203_level.y, level_to_boolean_tank_B203_high.u) annotation(
    Line(points = {{7, 36}, {-1, 36}, {-1, 24}, {7, 24}}, color = {0, 0, 127}));
  connect(tank_B203_level.y, level_to_boolean_tank_B203_medium.u) annotation(
    Line(points = {{7, 36}, {-1, 36}, {-1, 10}, {7, 10}}, color = {0, 0, 127}));
  connect(tank_B203_level.y, level_to_boolean_tank_B203_low.u) annotation(
    Line(points = {{7, 36}, {-1, 36}, {-1, -4}, {7, -4}}, color = {0, 0, 127}));
  connect(level_to_boolean_tank_B203_high.y, sensor_discrete_tank_B203_high.activePort) annotation(
    Line(points = {{18.5, 23}, {28.5, 23}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B203_medium.y, sensor_discrete_tank_B203_medium.activePort) annotation(
    Line(points = {{18.5, 9}, {28.5, 9}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B203_low.y, sensor_discrete_tank_B203_low.activePort) annotation(
    Line(points = {{18.5, -5}, {28.5, -5}}, color = {255, 0, 255}));
  connect(tank_B204_level.y, level_to_boolean_tank_B204_high.u) annotation(
    Line(points = {{139, 36}, {131, 36}, {131, 24}, {139, 24}}, color = {0, 0, 127}));
  connect(tank_B204_level.y, level_to_boolean_tank_B204_medium.u) annotation(
    Line(points = {{139, 36}, {131, 36}, {131, 10}, {139, 10}}, color = {0, 0, 127}));
  connect(tank_B204_level.y, level_to_boolean_tank_B204_low.u) annotation(
    Line(points = {{139, 36}, {131, 36}, {131, -4}, {139, -4}}, color = {0, 0, 127}));
  connect(level_to_boolean_tank_B204_high.y, sensor_discrete_tank_B204_high.activePort) annotation(
    Line(points = {{150.5, 23}, {160.5, 23}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B204_medium.y, sensor_discrete_tank_B204_medium.activePort) annotation(
    Line(points = {{150.5, 9}, {160.5, 9}}, color = {255, 0, 255}));
  connect(level_to_boolean_tank_B204_low.y, sensor_discrete_tank_B204_low.activePort) annotation(
    Line(points = {{150.5, -5}, {160.5, -5}}, color = {255, 0, 255}));
  connect(sensor_continuous_volumeFlowRate.port_b, tank_B204.topPorts[1]) annotation(
    Line(points = {{110, 20}, {110, 80}, {180, 80}, {180, 31}}, color = {0, 127, 255}));
  connect(sensor_continuous_pressure_tank_B201.port, valve_pump_tank_B201.port_a) annotation(
    Line(points = {{-190, -40}, {-190, -60}, {-150, -60}}, color = {0, 127, 255}));
  connect(sensor_continuous_pressure_tank_B202.port, valve_pump_tank_B202.port_a) annotation(
    Line(points = {{-90, -40}, {-90, -60}, {-50, -60}}, color = {0, 127, 255}));
  connect(sensor_continuous_pressure_tank_B203.port, valve_pump_tank_B203.port_a) annotation(
    Line(points = {{10, -40}, {10, -60}, {50, -60}}, color = {0, 127, 255}));
  connect(sensor_continuous_pressure_tank_B204.port, valve_out.port_a) annotation(
    Line(points = {{150, -40}, {150, -60}, {180, -60}}, color = {0, 127, 255}));
  connect(uniformNoise.y, product1.u2) annotation(
    Line(points = {{-179, -170}, {-173, -170}, {-173, -176}, {-163, -176}}, color = {0, 0, 127}));
  connect(n_in.y, product1.u1) annotation(
    Line(points = {{-179, -150}, {-173, -150}, {-173, -164}, {-163, -164}}, color = {0, 0, 127}));
  connect(product1.y, firstOrder.u) annotation(
    Line(points = {{-139, -170}, {-122, -170}}, color = {0, 0, 127}));
  connect(leaking_valve.port_b, anom_sink.ports[1]) annotation(
    Line(points = {{110, -160}, {110, -170}, {80, -170}}, color = {0, 127, 255}));
  connect(tee0.port_3, pipe7.port_a) annotation(
    Line(points = {{-130, -120}, {-130, -130}, {-120, -130}}, color = {0, 127, 255}));
  connect(pipe7.port_b, pump_P101.port_a) annotation(
    Line(points = {{-100, -130}, {-80, -130}}, color = {0, 127, 255}));
  connect(pump_P101.port_b, pipe6.port_a) annotation(
    Line(points = {{-60, -130}, {-20, -130}}, color = {0, 127, 255}));
  connect(pipe6.port_b, clogging_valve.port_a) annotation(
    Line(points = {{0, -130}, {40, -130}}, color = {0, 127, 255}));
  connect(clogging_valve.port_b, pressure_pump_P101.port) annotation(
    Line(points = {{60, -130}, {120, -130}}, color = {0, 127, 255}));
  connect(clogging_valve.port_b, leaking_valve.port_a) annotation(
    Line(points = {{60, -130}, {110, -130}, {110, -140}}, color = {0, 127, 255}));
  connect(clogging_valve.port_b, pipe5.port_a) annotation(
    Line(points = {{60, -130}, {110, -130}, {110, -100}}, color = {0, 127, 255}));
  connect(pipe5.port_b, valve_pump_tank_B204.port_a) annotation(
    Line(points = {{110, -80}, {110, -60}}, color = {0, 127, 255}));
  connect(valve_pump_tank_B204.port_b, sensor_continuous_volumeFlowRate.port_a) annotation(
    Line(points = {{110, -40}, {110, 0}}, color = {0, 127, 255}));
  annotation(
    uses(Modelica(version = "4.0.0")),
    Diagram(coordinateSystem(extent = {{-210, -200}, {210, 210}})),
    Icon(coordinateSystem(extent = {{-210, -200}, {210, 210}})),
    version = "");
end mixerModule;
