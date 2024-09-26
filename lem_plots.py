import os
import sys
import time
import numpy as np
import yaml
from copy import deepcopy

from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import QHBoxLayout, QWidget, QFrame, QPushButton
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont
import pyqtgraph as pg

from p4p.client.thread import Context
from epics import get_pv
import pydm
from pydm import Display


sys.path.append('/usr/local/facet/tools/python/')
sys.path.append('/usr/local/facet/tools/python/F2_live_model')
from F2_live_model.bmad import BmadLiveModel

SELF_PATH = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(*os.path.split(SELF_PATH)[:-1])
sys.path.append(REPO_ROOT)

DIR_CONFIG = os.path.join('/usr/local/facet/tools/python/', 'F2_live_model', 'config')
with open(os.path.join(DIR_CONFIG, 'facet2e.yaml'), 'r') as f:
    CONFIG = yaml.safe_load(f)

ctx = Context('pva')
LEM_BASE = 'BMAD:SYS0:1:FACET2E:LEM'

# fill background for spectrometer regions
SPECTROMETER_BOUNDARIES = {
    'L0': ('BEGDL10', 'ENDDL10'),
    'L1': ('BEGBC11_1', 'ENDBC11_2'),
    'L2': ('BEGBC14_1', 'ENDBC14_2'),
    'L3': ('BEGBC20', 'ENDBC20'),
    }

UPDATE_INTERVAL_MSEC = 200
LEM_ERROR_TOELRANCE_PCT = 2.0

class F2LEMPlots(Display):
    def __init__(self, parent=None, args=None):
        super(F2LEMPlots, self).__init__(parent=parent, args=args)
        self.regions = ['L0', 'L1', 'L2', 'L3']
        self._startup_timer = QTimer.singleShot(10, self._startup)
        self.show_exc_err = True

    def ui_filename(self): return os.path.join(SELF_PATH, 'lem_plots.ui')

    def _startup(self):
        # delayed startup for responsiveness
        self.f2m = BmadLiveModel(design_only=True)
        self.pz_des =  self.f2m.design.p0c*1e-6
        self._init_LEM_plots()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.start()
        self.refresh_timer.setInterval(UPDATE_INTERVAL_MSEC)
        self.refresh_timer.timeout.connect(self.refresh_plots)

    def refresh_plots(self):
        self._update_LEM_data()
        self._update_LEM_plots()

    def _update_LEM_data(self):
        # get LEM data from PVA service & other values from EPICS
        # make some calculations & pack data into relevant arrays
        LEM_data = ctx.get(f'{LEM_BASE}:DATA').value
        twiss_data = ctx.get('BMAD:SYS0:1:FACET2E:LIVE:TWISS').value

        self.pz_live = twiss_data.p0c
        self.E_err = 100*((self.pz_live - self.pz_des) / self.pz_des)

        self.BDESes = {}
        self.BLEMs = {}
        self.S = {}
        self.BLEM_err = {}
        # also track matching quads/other presently excluded devices
        self.exc_err = {}
        self.exc_S = {}
        for reg in self.regions:
            self.BDESes[reg] = []
            self.BLEMs[reg] = []
            self.S[reg] = []
            self.exc_S[reg] = []
            self.exc_err[reg] = []
            exc_blem = []
            exc_bdes = []
            qms = CONFIG['linac'][reg]['matching_quads']

            for i, elem in enumerate(LEM_data.element):
                if (LEM_data.region[i] != reg): continue
                dname = LEM_data.device_name[i]
                if not dname: continue

                bdes, blem = get_pv(f'{dname}:BDES').value, LEM_data.BLEM[i]
                if elem in qms or reg in ['L0','L1']:
                    self.exc_S[reg].append(LEM_data.s[i])
                    exc_bdes.append(bdes)
                    exc_blem.append(blem)
                else:
                    self.S[reg].append(LEM_data.s[i])
                    self.BDESes[reg].append(bdes)
                    self.BLEMs[reg].append(blem)

            self.BLEMs[reg] =  np.array(self.BLEMs[reg], dtype=np.float64)
            self.BDESes[reg] = np.array(self.BDESes[reg], dtype=np.float64)
            self.S[reg] =      np.array(self.S[reg], dtype=np.float64)
            exc_blem, exc_bdes = np.array(exc_blem), np.array(exc_bdes)
            self.BLEM_err[reg] = 100*(self.BLEMs[reg] - self.BDESes[reg])/self.BDESes[reg]
            self.exc_err[reg] = 100*(exc_blem - exc_bdes)/exc_bdes

        

    def _update_LEM_plots(self):
        self.pzdat1.setData(self.f2m.S, self.pz_live)
        
        i_OK_E = (np.abs(self.E_err) < LEM_ERROR_TOELRANCE_PCT)
        i_bad_E = np.abs(self.E_err) >= LEM_ERROR_TOELRANCE_PCT
        self.bg_E1.setOpts(
            x=self.f2m.S[i_OK_E], height=self.E_err[i_OK_E],
            width=2, brush='g', pen='g')
        self.bg_E2.setOpts(
            x=self.f2m.S[i_bad_E], height=self.E_err[i_bad_E],
            width=2, brush='r', pen='r'
            )
        for reg in self.regions:
            i_OK_B = np.abs(self.BLEM_err[reg]) < LEM_ERROR_TOELRANCE_PCT 
            i_bad_B = np.abs(self.BLEM_err[reg]) >= LEM_ERROR_TOELRANCE_PCT
            self.bg_items[reg][0].setOpts(
                x=self.S[reg][i_OK_B], height=self.BLEM_err[reg][i_OK_B],
                brush='g', pen='g'
                )
            self.bg_items[reg][1].setOpts(
                x=self.S[reg][i_bad_B], height=self.BLEM_err[reg][i_bad_B],
                brush='r', pen='r'
                )
            if self.show_exc_err:
                self.bg_items[reg][2].setOpts(
                    x=self.exc_S[reg], height=self.exc_err[reg],
                    brush=(60,60,60), pen=(60,60,60)
                    )

    def _init_LEM_plots(self):
        self.plot_pz = pg.PlotWidget()
        self.plot_EERR = pg.PlotWidget()
        self.plot_BLEM = pg.PlotWidget()
        self.ui.layout().addWidget(self.plot_pz)
        self.ui.layout().addWidget(self.plot_EERR)
        self.ui.layout().addWidget(self.plot_BLEM)

        pdats = [self.plot_pz, self.plot_EERR, self.plot_BLEM,]

        self.pzdat1 = pg.PlotDataItem(brush='c', pen=pg.mkPen('c',width=2))
        self.pzdat2 = pg.PlotDataItem(brush='w', pen='w')
        self.pzdat2.setData(self.f2m.S, self.pz_des)
        self.plot_pz.addItem(self.pzdat1)
        self.plot_pz.addItem(self.pzdat2)

        emptyarr = [1]
        self.bg_E1 = pg.BarGraphItem(x=emptyarr, height=emptyarr, width=2)
        self.bg_E2 = pg.BarGraphItem(x=emptyarr, height=emptyarr, width=2)
        self.plot_EERR.addItem(self.bg_E1)
        self.plot_EERR.addItem(self.bg_E2)

        self.bg_items = {}
        for reg in self.regions:

            e1,e2 = SPECTROMETER_BOUNDARIES[reg]
            s1 = self.f2m.S[self.f2m.ix[e1]]
            s2 = self.f2m.S[self.f2m.ix[e2]]
            for pdat in pdats:
                highlight = pg.LinearRegionItem(
                    values=(s1,s2), orientation='vertical', brush=(30,30,30), pen=(0,0,0)
                    )
                highlight.setZValue(-1)
                pdat.addItem(highlight)
            self.bg_items[reg] = []
            self.bg_items[reg].append(pg.BarGraphItem(x=emptyarr, height=emptyarr, width=2))
            self.bg_items[reg].append(pg.BarGraphItem(x=emptyarr, height=emptyarr, width=2))
            self.plot_BLEM.addItem(self.bg_items[reg][0])
            self.plot_BLEM.addItem(self.bg_items[reg][1])
            if self.show_exc_err:
                self.bg_items[reg].append(pg.BarGraphItem(x=emptyarr, height=emptyarr, width=2))
                self.plot_BLEM.addItem(self.bg_items[reg][2])

        lab_font = QFont('Helvetica', 12)
        self.plot_EERR.setXLink(self.plot_pz)
        self.plot_BLEM.setXLink(self.plot_pz)
        self.plot_pz.getAxis('left').setLabel('pz(s) (MeV)')
        self.plot_EERR.getAxis('left').setLabel('EERR (rel. %)')
        self.plot_BLEM.getAxis('left').setLabel('BLEM-BDES (rel. %)')
        for pdat in pdats:
            pdat.showGrid(x=True, y=True, alpha=0.5)
            pdat.getAxis('left').setTickFont(lab_font)
            pdat.getAxis('bottom').setTickFont(lab_font)
        self.plot_EERR.setYRange(-12,12)
        self.plot_BLEM.setYRange(-12,12)
        return


