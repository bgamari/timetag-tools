PREFIX=/usr
CXXFLAGS=-std=c++0x -ggdb -I/usr/include/libusb-1.0
CC=g++

PROGS=timetag_acquire bin_photons photon_generator dump_records dump_photons

all : ${PROGS}

timetag_acquire : timetag_acquire.o timetagger.o
	g++ -lusb-1.0 -lboost_thread -o$@ $+

install :
	cp timetag_acquire ${PREFIX}/bin/timetag_acquire
	chmod ug+s ${PREFIX}/bin/timetag_acquire
	cp bin_photons dump_photons photon_generator timetag_acquire timetag_ui.py ${PREFIX}/bin
	cp capture_pipeline.py timetag_interface.py ${PREFIX}/lib/pymodules/python2.6
	mkdir -p ${PREFIX}/share/timetag
	cp timetag_ui.glade output_channel.glade ${PREFIX}/share/timetag

clean :
	rm -f ${PROGS} *.o

