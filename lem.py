import os
import sys
import time
import numpy as np
import yaml
import logging
from datetime import datetime
from functools import partial

from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import QTableWidgetItem, QHeaderView
from PyQt5.QtCore import Qt, QTimer
import pyqtgraph as pg

from p4p.client.thread import Context
from p4p.nt import NTNDArray
from epics import get_pv
import pydm
from pydm import Display

sys.path.append('/usr/local/facet/tools/python/')
sys.path.append('/usr/local/facet/tools/python/F2_live_model')
from F2_live_model.bmad import BmadLiveModel
from F2_pytools import slc_mags as slcmag

SELF_PATH = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(*os.path.split(SELF_PATH)[:-1])
sys.path.append(REPO_ROOT)

DIR_CONFIG = os.path.join('/usr/local/facet/tools/python/', 'F2_live_model', 'config')
with open(os.path.join(DIR_CONFIG, 'facet2e.yaml'), 'r') as f:
    CONFIG = yaml.safe_load(f)

DIR_LEM_DATA = '/home/fphysics/zack/scratchdata/'

ctx = Context('pva')
LEM_BASE = 'BMAD:SYS0:1:FACET2E:LEM'

UPDATE_INTERVAL_MSEC = 1000


class F2LEMApp(Display):
    def __init__(self, parent=None, args=None):
        super(F2LEMApp, self).__init__(parent=parent, args=args)
        self._status('Initializing ...')

        self.regions = ['L0', 'L1', 'L2', 'L3']
        self.LEM_ref_profile = None
        self.backup_profile = None
        self.backup_BDES = None
        self.last_LEM_file = None

        hdr = self.ui.LEM_table.horizontalHeader()
        for i in range(11):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)

        self.enable_buttons = {
            'L0': self.ui.enable_L0,
            'L1': self.ui.enable_L1,
            'L2': self.ui.enable_L2,
            'L3': self.ui.enable_L3,
            }
        self.ui.ctrl_trim.clicked.connect(self._trim)
        self.ui.ctrl_undo.clicked.connect(self._undo)
        self.ui.ctrl_undo.setEnabled(False)

        self.ui.pub_prof_design.clicked.connect(
            partial(self._publish_momentum_profile, live=False, design=True)
            )
        self.ui.pub_prof_live.clicked.connect(
            partial(self._publish_momentum_profile, live=True)
            )
        
        self.refresh_timer = QTimer(self)
        self.refresh_timer.start()
        self.refresh_timer.setInterval(UPDATE_INTERVAL_MSEC)
        self.refresh_timer.timeout.connect(self._refresh)
        self._status('Done')

    def ui_filename(self): return os.path.join(SELF_PATH, 'lem.ui')

    def _status(self, msg):
        self.ui.logdisplay.write(f"{datetime.now().strftime('%H:%M:%S')} {msg}")
        self.ui.logdisplay.repaint()

    def _refresh(self):
        try:
            self._update_data()
            self._update_LEM_table()
        except Exception as E:
            self._status('ERROR: LEM data update failed')
            self._status(repr(E))

    def _update_data(self):
        # fetches new LEM data, live twiss data (for live p(z)) and magnet BDESes
        self.LEM_data = ctx.get(f'{LEM_BASE}:DATA').value
        if self.LEM_ref_profile is None:
            self.LEM_ref_profile = self.LEM_data.EREF
        else:
            self.LEM_ref_profile = self._get_LEM_ref_profile()
        twiss_data = ctx.get('BMAD:SYS0:1:FACET2E:LIVE:TWISS').value
        self.pz_live = twiss_data.p0c

        self.BDES = np.ndarray(len(self.LEM_data.device_name))
        for i, dname in enumerate(self.LEM_data.device_name):
            self.BDES[i] = get_pv(f"{dname}:BDES").value

    def _update_LEM_table(self):
        # get LEM data from PVA service & other values from EPICS
        # make some calculations & pack data into relevant arrays
        tbl = self.ui.LEM_table
        tbl.clearContents()
        tbl.setRowCount(0)
        for reg in self.regions:
            qms = CONFIG['linac'][reg]['matching_quads']
            for i, elem in enumerate(self.LEM_data.element):
                if (self.LEM_data.region[i] != reg): continue
                dname = self.LEM_data.device_name[i]

                self.BDES[i] = get_pv(f"{dname}:BDES").value
                
                tbl.insertRow(i)
                tbl.setItem(i, 0,  QTableWidgetItem(f'{reg}'))
                tbl.setItem(i, 1,  QTableWidgetItem(f'{elem}'))
                tbl.setItem(i, 2,  QTableWidgetItem(f'{dname}'))
                tbl.setItem(i, 3,  QTableWidgetItem(f'{self.LEM_data.EREF[i]:.3f}'))
                tbl.setItem(i, 4,  QTableWidgetItem(f'{self.LEM_ref_profile[i]:.3f}'))
                tbl.setItem(i, 5,  QTableWidgetItem(f'{self.LEM_data.EACT[i]:.3f}'))
                tbl.setItem(i, 6,  QTableWidgetItem(f'{self.LEM_data.EERR[i]:.3f}'))
                tbl.setItem(i, 7,  QTableWidgetItem(f'{self.LEM_data.BLEM_DESIGN[i]:.3f}'))
                tbl.setItem(i, 8,  QTableWidgetItem(f'{self.LEM_data.BLEM_EXTANT[i]:.3f}'))
                tbl.setItem(i, 9,  QTableWidgetItem(f'{self.BDES[i]:.3f}'))
                tbl.setItem(i, 10,  QTableWidgetItem(f'{self.LEM_data.s[i]:.3f}'))
                tbl.setItem(i, 11, QTableWidgetItem(f'{self.LEM_data.z[i]:.3f}'))
                tbl.setItem(i, 12, QTableWidgetItem(f'{self.LEM_data.length[i]:.3f}'))

    def _trim(self):
        # trim magnets based on the current live momentum profile
        # if self.backup_BDES == self.BDES:
        if np.array_equal(self.BDES, self.backup_BDES):
            self._status('Magnets are already set.')
            return

        # save current magnet settings for undo button
        # also write to a csv file for later recovery if needed
        # then set magnets & update the reference momentum profile
        self.last_LEM_file = self._write_LEM_data()
        self.backup_BDES = self.BDES
        self.backup_profile = ctx.get(f'{LEM_BASE}:PROFILE')
        self._status(f'Saved previous settings to {self.last_LEM_file}')

        SLC_dev, SLC_bdes, EPICS_dev, EPICS_bdes = self._get_trim_request()
        self._magnet_set(EPICS_dev, EPICS_bdes, magtype='EPICS')
        self._magnet_set(SLC_dev, SLC_bdes, magtype='SLC')

        self._publish_momentum_profile(live=True)
        self.ui.ctrl_undo.setEnabled(True)
        self._status('Done')

    def _undo(self):
        # restores backup momentum profile & magnet settings
        self._status('Undoing trim operation ...')

        SLC_dev, SLC_bdes, EPICS_dev, EPICS_bdes = self._get_trim_request(undo=True)
        self._magnet_set(EPICS_dev, EPICS_bdes, magtype='EPICS')
        self._magnet_set(SLC_dev, SLC_bdes, magtype='SLC')

        self._publish_momentum_profile(live=False)
        self.ui.ctrl_undo.setEnabled(False)
        self.backup_BDES = None
        self._status('Done')

    def _get_trim_request(self, undo=False):
        # get a list of magnets and BDESes to send to AIDA
        SLC_dev, SLC_bdes = [], []
        EPICS_dev, EPICS_bdes = [], []
        for reg in self.regions:
            if not self.enable_buttons[reg].isChecked(): continue
            for i, device in enumerate(self.LEM_data.device_name):
                if (self.LEM_data.region[i] != reg): continue
                if device[:4] == 'QUAD':
                    bdes_list = EPICS_bdes
                    EPICS_dev.append(device)
                else:
                    bdes_list = SLC_bdes
                    SLC_dev.append(device)
                if undo:
                    bdes_list.append(self.backup_BDES[i])
                elif self.ui.setScaleDesign.isChecked():
                    bdes_list.append(self.LEM_data.BLEM_DESIGN[i])
                elif self.ui.setScaleExtant.isChecked():
                    bdes_list.append(self.LEM_data.BLEM_EXTANT[i])
        return SLC_dev, SLC_bdes, EPICS_dev, EPICS_bdes

    def _magnet_set(self, device_list, bdes_list, magtype='EPICS'):
        # trim magnets to BLEM or to the backup_BDES
        try:
            self._status(f'Trimming {type} magnets ...')
            print('magnet settings to input:')
            for d,b in zip(device_list, bdes_list): print(f'  {d}: {b:.4f}')
            if magtype == 'EPICS':
                for dev, bdes in zip(device_list, bdes_list):
                    get_pv(f'{dev}BDES').put(bdes)
            elif magtype == 'SLC':
                slcmag.set_magnets(device_list, bdes_list)
            self._status('Done.')

        except Exception as E:
            self._status('ERROR: Trim operation failed.')
            self._status(repr(E))


    def _publish_momentum_profile(self, live=True, design=False):
        if live and design: raise ValueError('Invalid args')
        if live:
            msg = 'Publishing reference momentum ...'
            prof = self.LEM_ref_profile
        elif design:
            msg = 'Setting reference momentum to design ...'
            prof = self.LEM_data.EREF
        else:
            msg = 'Resetting reference momentum ...'
            prof = self.backup_profile

        self._status(msg)
        r = ctx.put(f'{LEM_BASE}:PROFILE', NTNDArray().wrap(prof))

    def _get_LEM_ref_profile(self):
        # get the energy profile at time of trim request
        # to be written to BMAD:SYS0:1:FACET2E:LEM:PROFILE
        prof = np.ndarray(len(self.LEM_data.device_name))
        for i, device in enumerate(self.LEM_data.device_name):
            if not self.enable_buttons[self.LEM_data.region[i]].isChecked():
                prof[i] =  self.LEM_ref_profile[i]
            else:
                prof[i] = self.LEM_data.EACT[i]
        return prof

    def _write_LEM_data(self):
        # write LEM info to a .csv for retrieval as needed
        txt_lines = []
        for reg in self.regions:
            qms = CONFIG['linac'][reg]['matching_quads']
            for i, elem in enumerate(self.LEM_data.element):
                if (self.LEM_data.region[i] != reg): continue
                dname = self.LEM_data.device_name[i]
                eref = self.LEM_data.EREF[i]
                elem = self.LEM_ref_profile[i]
                eact = self.LEM_data.EACT[i]
                eerr = self.LEM_data.EERR[i]
                blem_des = self.LEM_data.BLEM_DESIGN[i]
                blem_ext = self.LEM_data.BLEM_EXTANT[i]
                # bdes = get_pv(f"{dname}:BDES").value
                bdes = self.BDES[i]
                s, z, l = self.LEM_data.s[i], self.LEM_data.z[i], self.LEM_data.length[i]
                row = f'{dname},{eref},{elem},{eact},{eerr},{blem_des},{blem_ext},{bdes},{s},{z},{l}\n'
                txt_lines.append(row)

        fname = os.path.join(DIR_LEM_DATA, f"LEMdata_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv")
        with open(fname, 'w') as f: f.write(''.join([l for l in txt_lines]))
        return fname

    def _read_LEM_data(self, fname=None):
        # load LEM trim info from a .csv file
        # if fname is not provided, get the most recent available trim
        with open(fname, 'r') as f: txt_lines = f.readlines()

        print(txt_lines)

        return
