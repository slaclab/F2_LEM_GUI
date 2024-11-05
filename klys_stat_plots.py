import os
import sys
import time
import numpy as np
from functools import partial
import pyqtgraph as pg
from epics import get_pv
import pydm
from pydm import Display

SELF_PATH = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(*os.path.split(SELF_PATH)[:-1])
sys.path.append(REPO_ROOT)


# stations that don't exist
NONEXISTANT_RFS = ['11-1', '11-2', '11-3', '14-7','14-8', '15-2', '19-7', '19-8']

ALL_KLYS = []
BAD_KLYS = []
for s in range(11,20):
    for k in range(1,9):
        if f'{s}-{k}' in NONEXISTANT_RFS:
            BAD_KLYS.append(f'LI{s}:KLYS:{k}1')
        ALL_KLYS.append(f'LI{s}:KLYS:{k}1')

class F2KlysStatBarPlots(Display):
    def __init__(self, extant=True, parent=None, args=None):
        super(F2KlysStatBarPlots, self).__init__(parent=parent, args=args)

        self.ENLD_PVs = {}
        self.SBST_PVs = {}
        self.PDES_PVs = {}
        self.pw_ENLD = pg.PlotWidget()
        self.pw_PDES = pg.PlotWidget()
        self.ui.layout().addWidget(self.pw_PDES)
        self.ui.layout().addWidget(self.pw_ENLD)
        self.bars_ENLD = {}
        self.bars_PDES = {}
        self.bars_SBST = {}

        emptyarr = [1]

        for idx, klys_channel in enumerate(ALL_KLYS):
            if klys_channel in BAD_KLYS: continue

            s = int(klys_channel[2:4])
            k = int(klys_channel[-2:-1])
            x_idx = 10*s + k

            self.ENLD_PVs[klys_channel] = get_pv(f'{klys_channel}:ENLD')
            self.PDES_PVs[klys_channel] = get_pv(f'{klys_channel}:PDES')
            self.SBST_PVs[klys_channel] = get_pv(f'LI{s}:SBST:1:PDES')

            # bar item for ENLD
            self.bars_ENLD[klys_channel] = InteractiveBarItem(
                channel=klys_channel,
                x=x_idx,
                height=self.ENLD_PVs[klys_channel].get(),
                width=0.6, brush='g', pen='g'
                )
            self.pw_ENLD.addItem(self.bars_ENLD[klys_channel])
            self.ENLD_PVs[klys_channel].clear_callbacks()
            self.ENLD_PVs[klys_channel].add_callback(partial(self._update_ENLD, klys_channel, x_idx))
            self.ENLD_PVs[klys_channel].run_callbacks()

            # bar item for SB pdes
            sb_pdes = self.SBST_PVs[klys_channel].get()
            self.bars_SBST[klys_channel] = pg.BarGraphItem(
                x=x_idx,
                height=sb_pdes,
                width=0.6, brush='darkCyan', pen='darkCyan'
                )
            # bar item for klys phase
            self.bars_PDES[klys_channel] = InteractiveBarItem(
                channel=klys_channel,
                x=10*s + k,
                y0=sb_pdes,
                height=self.PDES_PVs[klys_channel].get(),
                width=0.6, brush='c', pen='c',
                )
            self.pw_PDES.addItem(self.bars_SBST[klys_channel])
            self.pw_PDES.addItem(self.bars_PDES[klys_channel])
            self.SBST_PVs[klys_channel].clear_callbacks()
            self.PDES_PVs[klys_channel].clear_callbacks()
            self.SBST_PVs[klys_channel].add_callback(partial(self._update_PDES, klys_channel, x_idx))
            self.PDES_PVs[klys_channel].add_callback(partial(self._update_PDES, klys_channel, x_idx))
            
            self.ENLD_PVs[klys_channel].run_callbacks()
            self.SBST_PVs[klys_channel].run_callbacks()
            self.PDES_PVs[klys_channel].run_callbacks()



        self.pw_ENLD.getAxis('left').setLabel('ENLD (MeV)')
        self.pw_ENLD.showGrid(x=True, y=True, alpha=0.5)
        self.pw_ENLD.setXRange(110, 200)

        self.pw_PDES.getAxis('left').setLabel('target phase (degS)')
        self.pw_PDES.showGrid(x=True, y=True, alpha=0.5)
        self.pw_PDES.setXRange(110, 200)
        self.pw_PDES.setYRange(-190, 190)

    def ui_filename(self): return os.path.join(SELF_PATH, 'klys_enld_plot.ui')

    def _update_ENLD(self, klys_channel, idx, value, **kw):
        self.bars_ENLD[klys_channel].setOpts(x=idx, height=value)
        self.bars_ENLD[klys_channel].setToolTip(f"{klys_channel}\nENLD = {value:.1f} MeV")

    def _update_PDES(self, klys_channel, idx, value, **kw):
        sb_pdes = self.SBST_PVs[klys_channel].get()
        self.bars_SBST[klys_channel].setOpts(x=idx, height=sb_pdes)
        self.bars_PDES[klys_channel].setOpts(x=idx, y0=sb_pdes, height=value)
        self.bars_PDES[klys_channel].setToolTip(
            f"{klys_channel}\nSBST_PDES = {sb_pdes:.1f} degS\nPDES = {value:.1f} degS\nPACT ~ {sb_pdes+value:.1f}degS"
            )

# class for bargraph item + hover function
class InteractiveBarItem(pg.BarGraphItem):
    def __init__(self, channel, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setToolTip(f"{channel}\nENLD = {self.opts['height']:.1f} MeV")
        # required in order to receive hoverEnter/Move/Leave events
        self.setAcceptHoverEvents(True)
        self.prev_brush, self.prev_pen = None, None

    # highlight/unhighlight on hover enter/leave
    def hoverEnterEvent(self, event):
        self.prev_brush, self.prev_pen = self.opts['brush'], self.opts['pen']
        self.setOpts(brush='b', pen='b')
    
    def hoverLeaveEvent(self, event):
        self.setOpts(brush=self.prev_brush, pen=self.prev_pen)
        self.prev_brush, self.prev_pen = None, None