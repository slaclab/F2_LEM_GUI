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

class F2ENLDPlots(Display):
    def __init__(self, extant=True, parent=None, args=None):
        super(F2ENLDPlots, self).__init__(parent=parent, args=args)

        self.PVs = {}
        self.pw = pg.PlotWidget()
        self.ui.layout().addWidget(self.pw)
        self.bg_items = {}

        emptyarr = [1]

        for idx, klys_channel in enumerate(ALL_KLYS):
            if klys_channel in BAD_KLYS: continue

            x_idx = idx
            s = int(klys_channel[2:4])
            k = int(klys_channel[-2:-1])

            x_idx = 10*s + k

            self.PVs[klys_channel] = get_pv(f'{klys_channel}:ENLD')

            self.bg_items[klys_channel] = InteractiveBarItem(
                channel=klys_channel,
                x=10*s + k,
                height=self.PVs[klys_channel].get(),
                width=0.6, brush='g', pen='g'
                )
            self.pw.addItem(self.bg_items[klys_channel])
            self.PVs[klys_channel].clear_callbacks()
            self.PVs[klys_channel].add_callback(partial(self._update_plot, klys_channel, idx))

        self.pw.getAxis('left').setLabel('ENLD (MeV)')
        self.pw.showGrid(x=True, y=True, alpha=0.5)
        self.pw.setXRange(110, 200)


    def ui_filename(self): return os.path.join(SELF_PATH, 'klys_enld_plot.ui')

    def _update_plot(self, klys_channel, idx, value, **kw):
        self.bg_items[klys_channel].setOpts(x=idx, height=value)
        self.bg_items[klys_channel].setToolTip(f"{channel}\nENLD = {value:.1f} MeV")


# class for bargraph item + hover function
class InteractiveBarItem(pg.BarGraphItem):
    def __init__(self, channel, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setToolTip(f"{channel}\nENLD = {self.opts['height']:.1f} MeV")
        # required in order to receive hoverEnter/Move/Leave events
        self.setAcceptHoverEvents(True)

    # highlight/unhighlight on hover enter/leave
    def hoverEnterEvent(self, event): self.setOpts(brush='b', pen='b')
    def hoverLeaveEvent(self, event): self.setOpts(brush='g', pen='g')