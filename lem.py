import os
import sys
import time
import numpy as np
import yaml

from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import QTableWidgetItem, QWidget, QFrame, QHeaderView
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


class F2LEMApp(Display):
    def __init__(self, parent=None, args=None):
        super(F2LEMApp, self).__init__(parent=parent, args=args)
        self.regions = ['L0', 'L1', 'L2', 'L3']
        self._startup_timer = QTimer.singleShot(10, self._refresh)

    def ui_filename(self): return os.path.join(SELF_PATH, 'lem.ui')

    def _refresh(self):
        self._update_data()
        self._update_LEM_table()

    def _update_data(self):
        self.LEM_data = ctx.get(f'{LEM_BASE}:DATA').value
        # self.twiss_data = ctx.get('BMAD:SYS0:1:FACET2E:LIVE:TWISS').value

    def _update_LEM_table(self):
        # get LEM data from PVA service & other values from EPICS
        # make some calculations & pack data into relevant arrays
        tbl = self.ui.LEM_table
        hdr = tbl.horizontalHeader()
        for i in range(11):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for reg in self.regions:
            qms = CONFIG['linac'][reg]['matching_quads']
            for i, elem in enumerate(self.LEM_data.element):
                if (self.LEM_data.region[i] != reg): continue
                dname = self.LEM_data.device_name[i]
                tbl.insertRow(i)
                tbl.setItem(i, 0,  QTableWidgetItem(f'{reg}'))
                tbl.setItem(i, 1,  QTableWidgetItem(f'{elem}'))
                tbl.setItem(i, 2,  QTableWidgetItem(f'{dname}'))
                tbl.setItem(i, 3,  QTableWidgetItem(f'{self.LEM_data.EREF[i]:.3f}'))
                tbl.setItem(i, 4,  QTableWidgetItem(f'{self.LEM_data.EREF[i]:.3f}'))
                tbl.setItem(i, 5,  QTableWidgetItem(f'{self.LEM_data.EACT[i]:.3f}'))
                tbl.setItem(i, 6,  QTableWidgetItem(f'{self.LEM_data.EERR[i]:.3f}'))
                tbl.setItem(i, 7,  QTableWidgetItem(f'{self.LEM_data.BLEM[i]:.3f}'))
                tbl.setItem(i, 8,  QTableWidgetItem(f'{get_pv(f"{dname}:BDES").value:.3f}'))
                tbl.setItem(i, 9,  QTableWidgetItem(f'{self.LEM_data.s[i]:.3f}'))
                tbl.setItem(i, 10, QTableWidgetItem(f'{self.LEM_data.z[i]:.3f}'))
                tbl.setItem(i, 11, QTableWidgetItem(f'{self.LEM_data.length[i]:.3f}'))
