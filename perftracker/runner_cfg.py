#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

description = """Replays web pages under simulated network conditions.

Must be run as administrator (sudo).

To record web pages:
  1. Start the program in record mode.
     $ sudo ./replay.py --record archive.wpr
  2. Load the web pages you want to record in a web browser. It is important to
     clear browser caches before this so that all subresources are requested
     from the network.
  3. Kill the process to stop recording.

To replay web pages:
  1. Start the program in replay mode with a previously recorded archive.
     $ sudo ./replay.py archive.wpr
  2. Load recorded pages in a web browser. A 404 will be served for any pages or
     resources not in the recorded archive.

Network simulation examples:
  # 128KByte/s uplink bandwidth, 4Mbps/s downlink bandwidth with 100ms RTT time
  $ sudo ./replay.py --up 128KByte/s --down 4Mbit/s --delay_ms=100 archive.wpr

  # 1% packet loss rate
  $ sudo ./replay.py --packet_loss_rate=0.01 archive.wpr"""

import dnsproxy
import httpproxy
import logging
import optparse
import socket
import sys
import threading
import time
import traceback
import trafficshaper


if sys.version < '2.6':
  print 'Need Python 2.6 or greater.'
  sys.exit(1)


def main(options, replay_file):
  if options.record:
    replay_server_class = httpproxy.RecordHttpProxyServer
  elif options.spdy:
    # TODO(lzheng): move this import to the front of the file once
    # nbhttp moves its logging config in server.py into main.
    import replayspdyserver
    replay_server_class = replayspdyserver.ReplaySpdyServer
  else:
    replay_server_class = httpproxy.ReplayHttpProxyServer

  try:
    with dnsproxy.DnsProxyServer(options.dns_forwarding,
                                 options.dns_private_passthrough) as dns_server:
      with replay_server_class(replay_file,
                               options.deterministic_script,
                               dns_server.real_dns_lookup):
        with trafficshaper.TrafficShaper(options.dns_forwarding,
                                         options.up,
                                         options.down,
                                         options.delay_ms,
                                         options.packet_loss_rate):
          start = time.time()
          while (not options.time_limit or
                 time.time() - start < options.time_limit):
            time.sleep(1)
  except KeyboardInterrupt:
    logging.info('Shutting down.')
  except dnsproxy.DnsProxyException, e:
    logging.critical(e)
  except trafficshaper.TrafficShaperException, e:
    logging.critical(e)
  except:
    print traceback.format_exc()


if __name__ == '__main__':
  class PlainHelpFormatter(optparse.IndentedHelpFormatter):
    def format_description(self, description):
      if description:
        return description + '\n'
      else:
        return ''

  option_parser = optparse.OptionParser(
      usage='%prog [options] replay_file',
      formatter=PlainHelpFormatter(),
      description=description,
      epilog='http://code.google.com/p/web-page-replay/')

  option_parser.add_option('-s', '--spdy', default=False,
      action='store_true',
      help='Use spdy to replay relay_file.')
  option_parser.add_option('-r', '--record', default=False,
      action='store_true',
      help='Download real responses and record them to replay_file')
  option_parser.add_option('-l', '--log_level', default='debug',
      action='store',
      type='choice',
      choices=('debug', 'info', 'warning', 'error', 'critical'),
      help='Minimum verbosity level to log')
  option_parser.add_option('-f', '--log_file', default=None,
      action='store',
      type='string',
      help='Log file to use in addition to writting logs to stderr.')
  option_parser.add_option('-t', '--time_limit', default=None,
      action='store',
      type='int',
      help='Maximum number of seconds to run before quiting.')

  network_group = optparse.OptionGroup(option_parser,
      'Network Simulation Options',
      'These options configure the network simulation in replay mode')
  network_group.add_option('-u', '--up', default='0',
      action='store',
      type='string',
      help='Upload Bandwidth in [K|M]{bit/s|Byte/s}. Zero means unlimited.')
  network_group.add_option('-d', '--down', default='0',
      action='store',
      type='string',
      help='Download Bandwidth in [K|M]{bit/s|Byte/s}. Zero means unlimited.')
  network_group.add_option('-m', '--delay_ms', default='0',
      action='store',
      type='string',
      help='Propagation delay (latency) in milliseconds. Zero means no delay.')
  network_group.add_option('-p', '--packet_loss_rate', default='0',
      action='store',
      type='string',
      help='Packet loss rate in range [0..1]. Zero means no loss.')
  option_parser.add_option_group(network_group)

  harness_group = optparse.OptionGroup(option_parser,
      'Replay Harness Options',
      'These advanced options configure various aspects of the replay harness')
  harness_group.add_option('-n', '--no-deterministic_script', default=True,
      action='store_false',
      dest='deterministic_script',
      help=('Don\'t inject JavaScript which makes sources of entropy such as '
            'Date() and Math.random() deterministic. CAUTION: With this option '
            'many web pages will not replay properly.'))
  harness_group.add_option('-P', '--no-dns_private_passthrough', default=True,
      action='store_false',
      dest='dns_private_passthrough',
      help='Don\'t forward DNS requests that resolve to private network '
           'addresses. CAUTION: With this option important services like '
           'Kerberos will resolve to the HTTP proxy address.')
  harness_group.add_option('-x', '--no-dns_forwarding', default=True,
      action='store_false',
      dest='dns_forwarding',
      help='Don\'t forward DNS requests to the local replay server.'
           'CAUTION: With this option an external mechanism must be used to '
           'forward traffic to the replay server.')
  option_parser.add_option_group(harness_group)

# The location of Chrome to test
chrome_path = "<path to chrome>"

# The location of the recorded replay data
replay_data_archive = "<path to recorded data archive from web-page-replay>"

# The URL of the PerfTracker web application to post results to
benchmark_server = "<url of server, such as 'localhost:8080' or 'foo.com'>"
benchmark_server_url = "http://" + benchmark_server + "/"


#
# The set of configurations to run
#

# The configuration to use in the runner
configurations = {}
configurations["iterations"] = 15;
configurations["networks"] = [
    {   # Fast Network
        "download_bandwidth_kbps": 0,
        "upload_bandwidth_kbps"  : 0,
    },
    {   # 10Mbps Network
        "download_bandwidth_kbps": 10000,
        "upload_bandwidth_kbps"  : 10000,
    },
    {   # Cable Network
        "download_bandwidth_kbps": 5000,
        "upload_bandwidth_kbps"  : 1000,
    },
    {   # DSL Network
        "download_bandwidth_kbps": 2000,
        "upload_bandwidth_kbps"  : 400,
    }
]
configurations["round_trip_times"] = [
    0, 40, 80, 100, 120, 160, 200
]
configurations["packet_loss_rates"] = [
    0, 1
]

# The list of URLs to test
configurations["urls"] = [
    "http://www.google.com/",
    "<add your list of urls here>
]
