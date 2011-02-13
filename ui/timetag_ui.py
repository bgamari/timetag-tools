#!/usr/bin/python
# vim: set fileencoding=utf-8

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


import logging
from collections import defaultdict
import time
from datetime import datetime
import os

import gobject, gtk
import matplotlib
from matplotlib.figure import Figure
from matplotlib.backends.backend_gtk import FigureCanvasGTK as FigureCanvas
#from matplotlib.backends.backend_gtkagg import FigureCanvasGTKAgg as FigureCanvas

from capture_pipeline import CapturePipeline, TestPipeline

PULSESEQ_FREQ = 30e6
TAGGER_FREQ = 30e6

use_test_pipeline = False
resource_prefix = '/usr/share/timetag'
default_configs = [ os.path.expanduser('~/.timetag.cfg'),
		    os.path.join(resource_prefix, 'default.cfg') ]

with open(os.path.join(resource_prefix, 'timetag-tools-ver'), 'r') as f:
        ui_version = f.readline().strip()

class NumericalIndicators(object):
        def __init__(self, n_inputs, main_win):
                self.main_win = main_win
                self.rate_mode = True
                self.last_stats = defaultdict(lambda: (0, 0, 0))

		self.inputs = []
		table = gtk.Table(n_inputs, 3)
		for c in range(n_inputs):
			label, photons, lost = gtk.Label(), gtk.Label(), gtk.Label()
			label.set_markup('<span size="large">Channel %d</span>' % c)
			table.attach(label, 0,1, c,c+1)
			table.attach(photons, 1,2, c,c+1)
			table.attach(lost, 2,3, c,c+1)
			self.inputs.append((photons, lost))

                self.widget = table

        def update(self):
                if self.rate_mode:
                        self._update_rate_indicators()
                else:
                        self._update_total_indicators()

        def _update_rate_indicators(self):
                for n, photon_count, lost_count, timestamp in self.main_win.pipeline.stats():
                        last_photon_count, last_lost_count, last_timestamp = self.last_stats[n]
                        if last_timestamp != timestamp:
                                photon_rate = (photon_count - last_photon_count) / (timestamp - last_timestamp)
                                loss_rate = (lost_count - last_lost_count) / (timestamp - last_timestamp)

				markup = "<span color='darkgreen' size='xx-large'>%d</span> <span size='large'>photons/second</span>" % photon_rate
				self.inputs[n][0].set_markup(markup)
				markup = "<span color='darkred' size='xx-large'>%d</span> <span size='large'>loss events/second</span>" % loss_rate
				self.inputs[n][1].set_markup(markup)
                        self.last_stats[n] = (photon_count, lost_count, timestamp)


        def _update_total_indicators(self):
                for n, photon_count, lost_count, timestamp in self.main_win.pipeline.stats():
			markup = "<span color='darkgreen' size='xx-large'>%1.3e</span> <span size='large'>photons</span>" % photon_count
			self.inputs[n][0].set_markup(markup)
			markup = "<span color='darkred' size='xx-large'>%d</span> <span size='large'>loss events</span>" % lost_count
			self.inputs[n][1].set_markup(markup)


class Plot(object):
        def __init__(self, main_win):
                self.scroll = False
                self.width = 1
                self.y_bounds = None

                self.main_win = main_win
                self.sync_timestamp = 0
                self.sync_walltime = 0
                self.figure = Figure()
                self.axes = self.figure.add_subplot(111)
                self.axes.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter(useOffset=False))
                self.lines = {}
                self.canvas = FigureCanvas(self.figure)

		self.fps_interval = 5 # seconds
		self.frame_cnt = 0
		def display_fps():
			if not self.frame_cnt > 0: return True
			fps = self.frame_cnt / self.fps_interval
			self.frame_cnt = 0
			logging.debug("Plot: %2.1f FPS" % fps)
			return True
		gobject.timeout_add_seconds(self.fps_interval, display_fps)
			

        @property
        def pipeline(self):
                return self.main_win.pipeline

        def update(self):
                if not self.pipeline:
                        return False

                for n,times,counts in self.pipeline.bins():
                        if not self.lines.has_key(n):
                                self.lines[n], = self.axes.plot(times, counts)#, animated=True)
                        else:
                                self.lines[n].set_data(times, counts)

                self.axes.relim()

		# Scale X axis:
                def calc_x_bounds():
                        xmax = self.sync_timestamp
                        if self.scroll:
                                xmax += time.time() - self.sync_walltime
                        xmin = xmax - self.width
                        return xmin, xmax

                xmin, xmax = calc_x_bounds()
                if not xmin < self.pipeline.latest_timestamp < xmax:
                        self.sync_walltime = time.time()
                        self.sync_timestamp = self.pipeline.latest_timestamp
                        xmin, xmax = calc_x_bounds()
                        
		self.axes.set_xlim(xmin, xmax)

		# Scale Y axis:
		ymin,ymax = None,None
		if self.y_bounds:
                        ymin, ymax = self.y_bounds
                else:
			self.axes.autoscale_view(scalex=False, scaley=True, tight=False)
			_,ymax = self.axes.get_ylim()
			ymax *= 1.1
			ymin = 0
                self.axes.set_ylim(ymin, ymax)

                self.figure.canvas.draw()
		self.frame_cnt += 1


class MainWindow(object):
        def __init__(self, n_inputs=4):
                self.plot_update_rate = 20 # in Hertz
                self.indicators_update_rate = 5 # in Hertz
                self.pipeline = None

                self.builder = gtk.Builder()
                self.builder.add_from_file(os.path.join(resource_prefix, 'timetag_ui.glade'))
                self.builder.connect_signals(self)

                def quit(unused):
                        if self.pipeline:
                                self.pipeline.stop()
                        gtk.main_quit()
                self.win = self.builder.get_object('main_window')
                self.win.connect('destroy', quit)

		self.set_default_output_file()
                self.indicators = NumericalIndicators(n_inputs, self)
                self.builder.get_object('channel_stats').pack_start(self.indicators.widget)

                self.plot = Plot(self)
                self.builder.get_object('plot_container').pack_start(self.plot.canvas)
		for f in default_configs:
			if os.path.isfile(f):
				self.load_config(f)
				break

                self.win.show_all()
	
	def usb_latency_changed_cb(self, combobox):
		iter = combobox.get_active_iter()
		latency = combobox.get_model().get_value(iter, 0)
		self.pipeline.tagger.set_send_window(latency)

	def set_default_output_file(self):
		file_n = 0
		def get_name(file_n):
			now = datetime.today()
			return "%04u-%02u-%02u-run_%03u.timetag" % (now.year, now.month, now.day, file_n)
		while os.path.exists(get_name(file_n)):
			file_n += 1
		self.builder.get_object('output_file').props.text = get_name(file_n)

        def select_output_file_activate_cb(self, action):
		filter = gtk.FileFilter()
		filter.set_name('Timetag data file')
		filter.add_pattern('*.timetag')

                fc = gtk.FileChooserDialog('Select output file', self.win, gtk.FILE_CHOOSER_ACTION_SAVE,
                        (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,  gtk.STOCK_OK, gtk.RESPONSE_OK))
		fc.add_filter(filter)
                fc.props.do_overwrite_confirmation = True
                res = fc.run()
                fc.hide()
                if res == gtk.RESPONSE_OK:
                        self.builder.get_object('output_file').props.text = fc.get_filename()

        def start_pipeline(self):
                if self.pipeline:
                        raise "Tried to start a capture pipeline while one is already running"

                file = None
                if self.builder.get_object('file_output_enabled').props.active:
			metadata = {
				'start': datetime.now(),
				'ui version': ui_version,
				'clockrate': TAGGER_FREQ,
                                'instrument': 'FPGA time tagger',
                                'sample': '',
                                'channels': {
                                        'strobe0': '',
                                },
			}
                        file = self.builder.get_object('output_file').props.text
			meta_file = file + ".meta"
                        json.dump(metadata, open(meta_file, 'w'))

                if use_test_pipeline:
                        self.pipeline = TestPipeline(100)
                else:
                        self.pipeline = CapturePipeline(output_file=file, bin_time=self.bin_time, capture_clock=TAGGER_FREQ, npts=self.n_points)

                self.pipeline.start()
                self.pipeline.tagger.reset_counter()

                # Start update loop for plot
                def update_plot():
			if not self.pipeline: return False
                        try:
                                self.plot.update()
                        except AttributeError as e:
                                # Ignore exceptions if pipeline is shut down
                                raise e
                        return True

                def update_indicators():
			if not self.pipeline: return False
                        try:
                                self.indicators.update()
                        except AttributeError as e:
                                # Ignore exceptions if pipeline is shut down
                                raise e
                        return True

                gobject.timeout_add(int(1000.0/self.indicators_update_rate), update_indicators)
                gobject.timeout_add(int(1000.0/self.plot_update_rate), update_plot)

        @property
        def bin_time(self):
                return self.builder.get_object('bin_time').props.value / 1000.0

        @property
        def plot_width(self):
		return self.builder.get_object('x_width').props.value
        
        @property
        def n_points(self):
                """ The required number of points to fill the entire
                width of the plot at the given bin_time """
                return self.plot_width / self.bin_time

	def x_width_value_changed_cb(self, *args):
		if not self.pipeline: return
		self.pipeline.resize_buffer(self.n_points)
                self.plot.width = self.plot_width

        def stop_pipeline(self):
                self.stop_readout()
                self.pipeline.stop()
                self.pipeline = None
                # As a precaution to prevent accidental overwriting of acquired data
                self.builder.get_object('file_output_enabled').props.active = False

        def pipeline_running_toggled_cb(self, action):
		get_object = self.builder.get_object
                state = action.props.active
                for o in [ 'file_output_enabled', 'output_file', 'select_output_file', 'bin_time_spin' ]:
                        get_object(o).props.sensitive = not state
                for o in [ 'readout_running', 'stop_outputs', 'start_outputs', 'usb_latency' ]:
                        get_object(o).props.sensitive = state

                if state:
                        self.start_pipeline()
                else:
			get_object('readout_running').set_active(False)
                        self.stop_pipeline()

        def start_readout(self):
                self.pipeline.tagger.reset()
                self.pipeline.tagger.start_capture()
                self.plot.scroll = True

        def stop_readout(self):
                self.pipeline.tagger.stop_capture()
                self.plot.scroll = False

        def readout_running_toggled_cb(self, action):
                if action.props.active:
                        self.start_readout()
                        action.props.label = "Running"       
                else:
                        self.stop_readout()
                        action.props.label = "Stopped"

        def indicator_mode_changed_cb(self, widget):
                self.indicators.rate_mode = bool(self.builder.get_object('show_rates').props.active)

        def y_bounds_changed_cb(self, *args):
                get_object = self.builder.get_object

                auto = get_object('y_auto').props.active
                for o in [ 'y_upper_spin', 'y_lower_spin' ]:
                        get_object(o).props.sensitive = not auto

                if auto:
                        self.plot.y_bounds = None
                else:
                        self.plot.y_bounds = (get_object('y_lower').props.value, get_object('y_upper').props.value)

	def load_config_activate_cb(self, action):
		filter = gtk.FileFilter()
		filter.set_name("Configuration file")
		filter.add_pattern("*.cfg")

                fc = gtk.FileChooserDialog('Select configuration file', self.win, gtk.FILE_CHOOSER_ACTION_OPEN,
                        (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,  gtk.STOCK_OK, gtk.RESPONSE_OK))
		fc.add_filter(filter)
                res = fc.run()
                fc.hide()
                if res == gtk.RESPONSE_OK:
                        self.load_config(fc.get_filename())

	def save_config_activate_cb(self, action):
		filter = gtk.FileFilter()
		filter.set_name("Configuration file")
		filter.add_pattern("*.cfg")

                fc = gtk.FileChooserDialog('Select configuration file', self.win, gtk.FILE_CHOOSER_ACTION_SAVE,
                        (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,  gtk.STOCK_OK, gtk.RESPONSE_OK))
                fc.props.do_overwrite_confirmation = True
		fc.add_filter(filter)
                res = fc.run()
                fc.hide()
                if res == gtk.RESPONSE_OK:
                        self.save_config(fc.get_filename())
		
	def load_config(self, file):
		from ConfigParser import ConfigParser
		get_object = self.builder.get_object
		config = ConfigParser()
		config.read(file)

		get_object('bin_time').props.value = config.getfloat('acquire', 'bin_time')
		get_object('x_width').props.value = config.getfloat('acquire', 'plot_width')

	def save_config(self, file):
		from ConfigParser import ConfigParser
		get_object = self.builder.get_object
		config = ConfigParser()

		config.add_section('acquire')
		config.set('acquire', 'bin_time', get_object('bin_time').props.value)
		config.set('acquire', 'plot_width', get_object('x_width').props.value)
		config.write(open(file,'w'))

if __name__ == '__main__':
        from optparse import OptionParser
        
        parser = OptionParser()
        parser.add_option('-d', '--debug', dest='debug',
                          help='Enable debugging output')
        parser.add_option('-t', '--test', dest='test',
                          help="Use test input pipeline instead of actual hardware")
        opts, args = parser.parse_args()
        use_test_pipeline = opts.test
        if opts.debug:
                logging.basicConfig(level=logging.DEBUG)

        gtk.gdk.threads_init()
        win = MainWindow()
        gtk.main()
