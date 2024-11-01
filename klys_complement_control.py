import os
import sys
import time
import numpy as np
import yaml
import logging
from datetime import datetime
from functools import partial

from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QHeaderView
from PyQt5.QtCore import Qt, QTimer
import pyqtgraph as pg

from p4p.client.thread import Context
from p4p.nt import NTNDArray
from epics import get_pv
import pydm
from pydm import Display

# sys.path.append('/usr/local/facet/tools/python/')
# sys.path.append('/usr/local/facet/tools/python/F2_live_model')
# from F2_live_model.bmad import BmadLiveModel
SELF_PATH = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(*os.path.split(SELF_PATH)[:-1])
# sys.path.append(REPO_ROOT)
sys.path.append('/home/fphysics/zack/workspace/')
from F2_pytools import slc_klys as slck
from F2_pytools import widgets as f2widgets

# L2: S11-S14, L3: S15-S19, 8x klys per sector
L2 = [str(i) for i in range(11,15)]
L3 = [str(i) for i in range(15,20)]
SECTORS = L2 + L3
KLYSTRONS = [str(i) for i in range(1,9)]

# stations that don't exist
NONEXISTANT_RFS = ['11-1', '11-2', '11-3', '14-7','14-8', '15-2', '19-7', '19-8']

UPDATE_INTERVAL_MSEC = 5000

class F2LEMApp(Display):
    def __init__(self, parent=None, args=None):
        super(F2LEMApp, self).__init__(parent=parent, args=args)

        self.buttons = {}

        self.l2_containers = [
            self.ui.cont_LI11,
            self.ui.cont_LI12,
            self.ui.cont_LI13,
            self.ui.cont_LI14,
            ]

        self.l3_containers = [
            self.ui.cont_LI15,
            self.ui.cont_LI16,
            self.ui.cont_LI17,
            self.ui.cont_LI18,
            self.ui.cont_LI19,
            ]


        self.setup(L2, self.l2_containers)
        self.setup(L3, self.l3_containers)

        self.stat_update()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.start()
        self.refresh_timer.setInterval(UPDATE_INTERVAL_MSEC)
        self.refresh_timer.timeout.connect(self.stat_update)

    def setup(self, linac, containers):
        for s, container in zip(linac, containers):
            for k in KLYSTRONS:
                if f'{s}-{k}' in NONEXISTANT_RFS:
                    container.layout().addWidget(QWidget())
                    continue
                klys_name = f'KLYS:LI{int(s)}:{int(k)}1'
                btn = f2widgets.F2KlysToggleButton(klys_name)
                btn.setMaximumWidth(55)
                self.buttons[klys_name] = btn
                container.layout().addWidget(btn)

    def stat_update(self):
        self.kstats = slck.get_all_klys_stat()
        for klys_name, btn in self.buttons.items():
            btn.set_button_enable_states(
                onbeam=self.kstats[klys_name]['accel'],
                maint=(self.kstats[klys_name]['status']==28),
                )

    def ui_filename(self): return os.path.join(SELF_PATH, 'klys_complement_control.ui')