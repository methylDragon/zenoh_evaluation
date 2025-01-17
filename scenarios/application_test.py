#!/usr/bin/python3

from mininet.net import Mininet
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.util import dumpNodeConnections, waitListening, decode, pmonitor
from signal import SIGINT
import importlib
import os
import selectors
import subprocess
import sys
import time
import utils


def start_processes(host, executables):
    processes = {}
    for executable in executables:
        process = host.popen(
            ['../mont_blanc/zenoh/target/debug/' + executable,
             '1'])
        processes[executable] = process
    return processes


def terminate_processes(processes):
    for k in processes:
        processes[k].send_signal(SIGINT)


def process_line(node_names, line):
    ignore_line = False
    line_is_expected = False
    started = False

    splits = line.split(':', maxsplit=1)
    if len(splits) == 2:
        source_process, output = splits
        source_process = source_process.lower().strip()
        output = output.strip()

        if output == 'Starting loop':
            started = True
            ignore_line = True
        elif output in ['Data generation started', 'Data generation done']:
            ignore_line = True
        else:
            if source_process in node_names:
                line_is_expected = True
            else:
                line_is_expected = False
    else:
        print(line)

    return ignore_line, line_is_expected, started


def application_test(net, scenario_module):
    robot, workstation = utils.get_source_and_sink(net, scenario_module)

    robot_executables = ['cordoba',
        'lyon',
        'freeport',
        'medellin',
        'portsmouth',
        'delhi',
        'hamburg',
        'taipei',
        'osaka',
        'hebron',
        'kingston',
        'tripoli',
        'mandalay',
        'ponce']
    workstation_executables = ['geneva',
        'monaco',
        'rotterdam',
        'barcelona',
        'arequipa',
        'georgetown']

    robot_processes = start_processes(robot, robot_executables)
    workstation_processes = start_processes(
        workstation,
        workstation_executables)
    all_processes = {**robot_processes, **workstation_processes}

    not_started_processes = robot_executables + workstation_executables
    started_processes = []
    received_data_processes = []
    robot_expected_lines = {}
    workstation_expected_lines = {}
    unexpected_lines = {}

    start_time = time.time()
    started = False

    for executable, line in pmonitor(all_processes, timeoutms=2000):
        if executable:
            line = line.strip()

            ignore, is_expected, has_started = process_line(
                robot_executables + workstation_executables,
                line)
            if not ignore:
                if is_expected:
                    if executable in robot_executables:
                        if line in robot_expected_lines:
                            robot_expected_lines[line] = robot_expected_lines[line] + 1
                        else:
                            robot_expected_lines[line] = 1
                    else:
                        if line in workstation_expected_lines:
                            workstation_expected_lines[line] = workstation_expected_lines[line] + 1
                        else:
                            workstation_expected_lines[line] = 1
                else:
                    if line in unexpected_lines:
                        unexpected_lines[line] = unexpected_lines[line] + 1
                    else:
                        unexpected_lines[line] = 1

            if has_started:
                not_started_processes.remove(executable)
                started_processes.append(executable)
                print('Started processes ({}): {}'.format(len(started_processes), started_processes))
                print('Waiting for processes ({}): {}'.format(len(not_started_processes), not_started_processes))

            if len(not_started_processes) == 0 and not started:
                print('All nodes started')
                started = True
                start_time = time.time()
        if started and (time.time() - start_time) > 10:
            break
    print('Run time exceeded; terminating')
    terminate_processes(all_processes)
    print("Received {} lines from robot processes:".format(len(robot_expected_lines)))
    for l in robot_expected_lines:
        print("{}\t{}".format(robot_expected_lines[l], l))
    print("Received {} lines from workstation processes:".format(len(workstation_expected_lines)))
    for l in workstation_expected_lines:
        print("{}\t{}".format(workstation_expected_lines[l], l))
    print("Received {} lines from unknown processes:".format(len(unexpected_lines)))
    for l in unexpected_lines:
        print("{}\t{}".format(unexpected_lines[l], l))


def main():
    if len(sys.argv) != 2:
        print('Please supply a scenario name')
        return 1
    scenario_name = sys.argv[1]
    scenario_module = importlib.import_module('.' + scenario_name, 'scenarios')
    topo = scenario_module.ScenarioTopo()
    net = Mininet(topo, host=CPULimitedHost, link=TCLink)
    net.start()
    scenario_module.configure_network(net)
    load = scenario_module.start_network_load(net)
    print('Connections:')
    dumpNodeConnections(net.hosts)

    tshark_robot = utils.start_tshark_on_source(net, scenario_module, '/tmp/robot_capture.pcap')
    tshark_ws = utils.start_tshark_on_sink(net, scenario_module, '/tmp/ws_capture.pcap')
    time.sleep(2)
    application_test(net, scenario_module)
    time.sleep(2)
    utils.stop_tshark(tshark_robot)
    utils.stop_tshark(tshark_ws)

    scenario_module.stop_network_load(load)
    net.stop()

    utils.process_zenoh_packet_capture('/tmp/robot_capture.pcap', 1)
    utils.process_zenoh_packet_capture('/tmp/ws_capture.pcap', 1)

    return 0


if __name__ == '__main__':
    sys.exit(main())
