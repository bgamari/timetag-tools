# vim: set fileencoding=utf-8 et :

# timetag-tools - Tools for UMass FPGA timetagger
# 
# Copyright © 2010 Ben Gamari
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see http://www.gnu.org/licenses/ .
# 
# Author: Ben Gamari <bgamari@physics.umass.edu>
# 

import socket
import passfd
import logging
import sys
from time import sleep

logging.basicConfig(level=logging.DEBUG)

class CapturePipeline(object):
        def __init__(self, control_sock='/tmp/timetag.sock'):
                """ Create a capture pipeline. The bin_time is given in
                    seconds. """
                self.stop_notifiers = []
                self.start_notifiers = []
                self._control_sock_name = control_sock
                self._control_sock = None
                self._connect()

                self.clockrate = int(self._tagger_cmd('clockrate?\n'))
                logging.info('Tagger clockrate: %f MHz' % (self.clockrate / 1e6))
                self.hw_version = self._tagger_cmd('version?\n')
                logging.info('Tagger HW version: %s' % self.hw_version)

        def _connect(self):
                if self._control_sock is not None:
                        self._control_sock.close()
                self._control_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM, 0)
                connected = False
                for i in range(10):
                        sleep(0.05)
                        try: self._control_sock.connect(self._control_sock_name)
                        except: pass
                        else:
				connected = True
				break

                if not connected:
                        raise RuntimeError('Failed to connect to timetag_acquire')

                sleep(0.5)
                self._control = self._control_sock.makefile('rw', 0)
                l = self._control.readline() # Read "ready"
                if l.strip() != "ready":
                        raise RuntimeError('Invalid status message: %s' % l)

        def _tagger_cmd(self, cmd):
                logging.debug("Tagger command: %s" % cmd.strip())
                try:
                        self._control.write(cmd)
                        return self._read_reply(cmd)
                except socket.error as e:
                        self._connect()

        def _read_reply(self, cmd=''):
                result = None
                while True:
                        l = self._control.readline().strip()
                        if l.startswith('= '):
                                result = l[2:]
                                l = self._control.readline().strip()
                        if l == 'ready':
                                break
                        if l.startswith('error'):
                                logging.error('Timetagger error while handling command: %s' % cmd)
                                logging.error('Error: %s' % l)
                                raise RuntimeError
                        else:
                                logging.error('Invalid status message: %s' % l)
                                raise RuntimeError
                return result

        def stop(self):
                logging.info("Capture pipeline shutdown")
                self._control.write('quit\n')
                self._control.close()

        def stop_capture(self):
                self._tagger_cmd('stop_capture\n')
                for n in self.stop_notifiers: n()

        def start_capture(self):
                self._tagger_cmd('reset_counter\n')
                self._tagger_cmd('start_capture\n')
                for n in self.start_notifiers: n()

        def is_capture_running(self):
                return bool(int(self._tagger_cmd('capture?\n')))

        def set_send_window(self, window):
                self._tagger_cmd('set_send_window %d\n' % window)

        def add_output(self, name, file):
                logging.debug("Tagger command: add_output %s" % name)
                self._control.write('add_output_fd %s\n' % name)
                sleep(0.01) # HACK: Otherwise the packet gets lost
                passfd.sendfd(self._control_sock, file)
                oid = self._read_reply()
                logging.debug("output_id = %s" % oid)
                return int(oid)

        def remove_output(self, oid):
                self._tagger_cmd('remove_output %d\n' % oid)
