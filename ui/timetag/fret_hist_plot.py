import time
import pkgutil

import gobject, gtk
import matplotlib
from matplotlib.figure import Figure
from matplotlib.backends.backend_gtk import FigureCanvasGTK
from matplotlib.backends.backend_gtkagg import FigureCanvasGTKAgg
from matplotlib.backends.backend_gtkcairo import FigureCanvasGTKCairo
from collections import defaultdict

from timetag.binner import FretHistBinner

class FretHistPlot(object):
        FigureCanvas = FigureCanvasGTK

        def __init__(self, pipeline):
                self.bin_time = 1e-2
                self.builder = gtk.Builder()
                src = pkgutil.get_data('timetag', 'fret_hist.glade')
                self.builder.add_from_string(src)
                self.builder.connect_signals(self)
                self.win = self.builder.get_object('hist_window')
                self.win.connect('destroy', self.destroy_cb)
                self.pipeline = pipeline
                self.update_rate = 0.3 # Hz

                self.binner = None
                self._restart_binner()

                self.figure = Figure()
                self.axes = self.figure.add_subplot(111)
                self.axes.get_xaxis().set_major_formatter(
                                matplotlib.ticker.ScalarFormatter(useOffset=False))
                self.axes.set_xlabel('Counts per bin')

                canvas = self.__class__.FigureCanvas(self.figure)
                self.builder.get_object('plot_container').pack_start(canvas)
                self.builder.get_object('bin_width').value = 40
                self.win.show_all()

                def update_plot():
                        try:
                                self.update()
                        except AttributeError as e:
                                # Ignore exceptions in case pipeline is shut down
                                raise e
                        return self.running

                self.running = True
                gobject.timeout_add(int(1000.0 / self.update_rate), update_plot)

        def destroy_cb(self, a):
                self.running = False
                self._stop_binner()

        def _stop_binner(self):
                if self.binner is not None:
                        self.pipeline.remove_output(self.output_id)
                        self.binner.stop()

        def _restart_binner(self):
                self._stop_binner()
                self.binner = FretHistBinner(self.bin_time, self.pipeline.clockrate)
                self.output_id = str(id(self))
                self.pipeline.add_output(self.output_id, self.binner.get_data_fd())

        def update(self):
                print 'hi'
                hist_width = self.binner.hist_width
                hist = self.binner.hist
                if len(hist) == 0: return
                print 'hello'
                self.axes.cla()
                self.axes.bar(hist.keys(), hist.values(), hist_width)
                self.axes.relim()
                self.axes.xlim(0, 1)
                self.figure.canvas.draw()

        def binning_config_changed_cb(self, *args):
                get_obj = self.builder.get_object
                model = get_obj('channel_model')
                self.binner.donor_channel = model[get_obj('donor_combo').get_active_iter()][0]
                self.binner.acceptor_channel = model[get_obj('acceptor_combo').get_active_iter()][0]
                self.binner.threshold = get_obj('threshold').get_value()
                self.binner.hist_width = 1. / get_obj('nbins').get_value()
                self.binner.reset_hist()

