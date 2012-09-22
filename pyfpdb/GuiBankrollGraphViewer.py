#!/usr/bin/env python
# -*- coding: utf-8 -*-

#Copyright 2008-2011 Carl Gherardi
#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU Affero General Public License as published by
#the Free Software Foundation, version 3 of the License.
#
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#GNU General Public License for more details.
#
#You should have received a copy of the GNU Affero General Public License
#along with this program. If not, see <http://www.gnu.org/licenses/>.
#In the "official" distribution you can find the license in agpl-3.0.txt.


# Todo list :
#   - hide the «ID» from transfertTab : it's useless for user, it only serves to delete a row from the database if needed …
#   - add "in cents (€/$)" on the sum selection in the transfert window
#   - legend below graph : actual benefit - old transferts, not every ones
#   - reput the legend on the top corner "actual br && benefice"
#   - enable negative transfert of $$ (withdraw)
#   - add currency in table ?
# performance ?
        

import L10n
_ = L10n.get_translation()
import threading
import pygtk
pygtk.require('2.0')
import gtk
import gobject
import os
import sys
import traceback
from time import *
from datetime import datetime
#import pokereval

import Database
import Filters
import Charset

_COL_ALIAS, _COL_SHOW, _COL_HEADING,_COL_XALIGN,_COL_FORMAT,_COL_TYPE = 0,1,2,3,4,5

try:
    calluse = not 'matplotlib' in sys.modules
    import matplotlib
    if calluse:
        matplotlib.use('GTKCairo')
    from matplotlib.figure import Figure
    from matplotlib.dates import YearLocator, MonthLocator, DateFormatter
    import datetime
    from matplotlib.backends.backend_gtk import FigureCanvasGTK as FigureCanvas
    from matplotlib.backends.backend_gtkagg import NavigationToolbar2GTKAgg as NavigationToolbar
    from matplotlib.font_manager import FontProperties
    from numpy import arange, cumsum
    from pylab import *
except ImportError, inst:
    print _("""Failed to load libs for graphing, graphing will not function. Please install numpy and matplotlib if you want to use graphs.""")
    print _("""This is of no consequence for other parts of the program, e.g. import and HUD are NOT affected by this problem.""")
    print "ImportError: %s" % inst.args

class GuiBankrollGraphViewer (threading.Thread):

    def __init__(self, settings, db, querylist, config, parent, debug=True):
        """Constructor for GraphViewer"""
        self.settings = settings
        self.db = db
        self.sql = querylist
        self.conf = config
        self.debug = debug
        self.parent = parent
        #print "start of GraphViewer constructor"
        self.db = Database.Database(self.conf, sql=self.sql)

        view = None
        filters_display = { "Heroes"    : True,
                            "Sites"     : True,
                            "Games"     : False,
                            "Limits"    : False,
                            "LimitSep"  : False,
                            "LimitType" : False,
                            "Type"      : False,
                            "UseType"   : 'tour',
                            "Seats"     : False,
                            "SeatSep"   : False,
                            "Dates"     : True,
                            "Groups"    : False,
                            "Button1"   : True,
                            "Button2"   : True
                          }

        self.filters = Filters.Filters(self.db, self.conf, self.sql, display = filters_display)
        self.filters.registerButton1Name(_("Refresh _Graph"))
        self.filters.registerButton1Callback(self.generateGraph)
        self.filters.registerButton2Name(_("_Export to File"))
        self.filters.registerButton2Callback(self.exportGraph)


        
        self.mainHBox = gtk.HBox(False, 0)
        self.mainHBox.show()

        self.leftPanelBox = self.filters.get_vbox()

        #add a button to modify transferts
        ButtonTransfert=gtk.Button(_("ButtonTransfert"))
        ButtonTransfert.set_label(_("_Modify Transferts"))
        ButtonTransfert.connect("clicked", self.transfertsWindow, "clicked")
        ButtonTransfert.set_sensitive(True)
        
        self.filters.mainVBox.pack_start(ButtonTransfert, False)
        ButtonTransfert.show()

        self.hpane = gtk.HPaned()
        self.hpane.pack1(self.leftPanelBox)
        self.mainHBox.add(self.hpane)
        # hierarchy:  self.mainHBox / self.hpane / self.graphBox / self.canvas / self.fig / self.ax

        self.graphBox = gtk.VBox(False, 0)
        self.graphBox.show()
        self.hpane.pack2(self.graphBox)
        self.hpane.show()

        self.fig = None
        #self.exportButton.set_sensitive(False)
        self.canvas = None

        #update the graph at entry (simulate a «Refresh Graph» click)
        gobject.GObject.emit (self.filters.Button1, "clicked");

        self.db.rollback()
        #endinit
    def get_vbox(self):
        """returns the vbox of this thread"""
        return self.mainHBox
    #end def get_vbox

    def clearGraphData(self):
        try:
            if self.canvas:
                self.graphBox.remove(self.canvas)
        except:
            pass

        if self.fig != None:
            self.fig.clear()
        self.fig = Figure(figsize=(5,4), dpi=100)
        if self.canvas is not None:
            self.canvas.destroy()

        self.canvas = FigureCanvas(self.fig)  # a gtk.DrawingArea

    def generateGraph(self, widget, data):
        self.clearGraphData()

        sitenos = []
        playerids = []

        sites   = self.filters.getSites()
        heroes  = self.filters.getHeroes()
        siteids = self.filters.getSiteIds()

        # Which sites are selected?
        for site in sites:
            if sites[site] == True:
                sitenos.append(siteids[site])
                _hname = Charset.to_utf8(heroes[site])
                result = self.db.get_player_id(self.conf, site, _hname)
                if result is not None:
                    playerids.append(int(result))

        if not sitenos:
            #Should probably pop up here.
            print _("No sites selected - defaulting to PokerStars")
            self.db.rollback()
            return

        if not playerids:
            print _("No player ids found")
            self.db.rollback()
            return

        #Set graph properties
        self.ax = self.fig.add_subplot(111)

        #Get graph data from DB
        starttime = time()
        (green, dates, transfer, transferType) = self.getData(playerids, sitenos)
        print _("Graph generated in: %s") %(time() - starttime)


        #Set axis labels and grid overlay properites
        self.ax.set_ylabel("$", fontsize = 12)
        self.ax.grid(color='g', linestyle=':', linewidth=0.2)
        
        if green == None or green == []:
            self.ax.set_title(_("No Data for Player(s) Found"))
            green = ([    0.,     0.,     0.,     0.,   500.,  1000.,   900.,   800.,
                        700.,   600.,   500.,   400.,   300.,   200.,   100.,     0.,
                        500.,  1000.,  1000.,  1000.,  1000.,  1000.,  1000.,  1000.,
                        1000., 1000.,  1000.,  1000.,  1000.,  1000.,   875.,   750.,
                        625.,   500.,   375.,   250.,   125.,     0.,     0.,     0.,
                        0.,   500.,  1000.,   900.,   800.,   700.,   600.,   500.,
                        400.,   300.,   200.,   100.,     0.,   500.,  1000.,  1000.])
            red   =  ([    0.,     0.,     0.,     0.,   500.,  1000.,   900.,   800.,
                        700.,   600.,   500.,   400.,   300.,   200.,   100.,     0.,
                        0.,   0.,     0.,     0.,     0.,     0.,   125.,   250.,
                        375.,   500.,   500.,   500.,   500.,   500.,   500.,   500.,
                        500.,   500.,   375.,   250.,   125.,     0.,     0.,     0.,
                        0.,   500.,  1000.,   900.,   800.,   700.,   600.,   500.,
                        400.,   300.,   200.,   100.,     0.,   500.,  1000.,  1000.])
            blue =    ([    0.,     0.,     0.,     0.,   500.,  1000.,   900.,   800.,
                          700.,   600.,   500.,   400.,   300.,   200.,   100.,     0.,
                          0.,     0.,     0.,     0.,     0.,     0.,   125.,   250.,
                          375.,   500.,   625.,   750.,   875.,  1000.,   875.,   750.,
                          625.,   500.,   375.,   250.,   125.,     0.,     0.,     0.,
                        0.,   500.,  1000.,   900.,   800.,   700.,   600.,   500.,
                        400.,   300.,   200.,   100.,     0.,   500.,  1000.,  1000.])

            self.ax.plot(green, color='green', label=_('Bankroll') + _('Profit') + ': $%.2f' % green[-1])
            self.graphBox.add(self.canvas)
            self.canvas.show()
            self.canvas.draw()

            #TODO: Do something useful like alert user
        else:
            self.ax.set_title(_("Bankroll Results"))
            useDates = True

            #nothing to draw
            if (len(green) == 0):
                return
            #Get the dates of the action (transfert / cg hand / tourney)
            #if it has no date, get the most ancient date and assume it's its one
            if dates[0] is None:
                i = 1
                while i < len(dates) and type(dates[i]) is None:
                    i = i+1
                if i == len(dates):
                    print "Wow wow wow : no dates in your whole database"
                    useDates = False
                else:
                    dates[0] = dates[i]

            #now, convert date to dateTime format
            if useDates:
                for i in range(0, len(dates)):
                    if dates[i] is None:
                        dates[i] = dates[i-1]
                    #~else:
                        #~dates[i] = datetime.datetime.strptime(dates[i], "%Y-%m-%d %H:%M:%S")

            for i in range(0,  len(green)-1):
                beneficeSinceStart=green[i+1]-self.totalTransfer(dates[i+1], transfer)
                mycolor = self.color(transferType[i+1], beneficeSinceStart)

                self.ax.plot([i,i+1], [green[i],green[i+1]], color=mycolor)
                #show date and gain only 5 times on X axis
                if (i % (len(green)/5) == 1):
                    gain=""
                    if (beneficeSinceStart==0):
                        gain="="
                    else:
                        if (beneficeSinceStart>0):
                            gain="+"
                        gain += str(beneficeSinceStart)
                    
                    #the gain since start at this time
                    self.ax.annotate(gain, xy=(i, 0), color=mycolor, xycoords=('data', 'axes fraction'),
                    xytext=(0, 18), textcoords='offset points', va='top', ha='left')

                    #and show the date too if enabled
                    if useDates:
                        dateMMDD=datetime.datetime.strptime(dates[i], "%Y-%m-%d %H:%M:%S").strftime('%d/%m')
                        self.ax.annotate(dateMMDD, xy=(i, 0), xycoords=('data', 'axes fraction'),
                        xytext=(0, -18), textcoords='offset points', va='top', ha='left')


            #plot the last one and show the top corner legend
            i = len(green)-1
            
            bankroll = float(green[i])
            profit = bankroll
            if len(transfer)>0:
                profit -= transfer[len(transfer)-1][0]
                
            self.ax.plot([i,i+1], [green[i],green[i]], color=self.color(transferType[i], beneficeSinceStart),
                label=_('Bankroll') + ': \$%.2f' % bankroll + '\n' + _('Profit') + ': \$%.2f' % profit)
            
            legend = self.ax.legend(loc='upper left', fancybox=True, shadow=True, prop=FontProperties(size='smaller'))
            legend.draggable(True)

            self.graphBox.add(self.canvas)
            self.canvas.show()
            self.canvas.draw()
    #end of def showClicked
    
    #return total cash from transfer until «date»
    def totalTransfer(self, date, transferts):
        #~print transferts
        if len(transferts) == 0 or (date < transferts[0][1]): 
            return 0
        
        i=0
        while (i < len(transferts)-1 and date > transferts[i][1]):
            i = i + 1
        return transferts[i][0]
    
    def color(self, typ, gain):
        # 0:play, 1:transfert
        if typ == 1:
            return 'black'
        elif gain < 0:
            return 'red'
        else:
            return 'green'
    
    def getData(self, names, sites):
        print "DEBUG: args are :"
        print names
        print sites
        
        tmp = self.rightRequest('getAllPrintIdSite', names, sites)
        tmp2 = self.rightRequest('getAllTransfer', names, sites)

        print "DEBUG: sql query:"
        print tmp
        self.db.cursor.execute(tmp)
        #returns (HandId,Winnings,Costs,Profit)
        winnings = self.db.cursor.fetchall()

        self.db.cursor.execute(tmp2)
        transfers = self.db.cursor.fetchall()
        self.db.rollback()

        if len(winnings) == 0:
            return None

        green = map(lambda x:float(x[0]), winnings)
        dates = map(lambda x:x[1], winnings)
        transferType = map(lambda x:x[2], winnings)
        
        #blue  = map(lambda x: float(x[1]) if x[2] == True  else 0.0, winnings)
        #red   = map(lambda x: float(x[1]) if x[2] == False else 0.0, winnings)
        greenline = cumsum(green)

        #blueline  = cumsum(blue)
        #redline   = cumsum(red)

        #~transfers[0] = cumsum(transfers[0])
        return (greenline/100., dates, transfers, transferType)

    def exportGraph (self, widget, data):
        if self.fig is None:
            return # Might want to disable export button until something has been generated.

        dia_chooser = gtk.FileChooserDialog(title=_("Please choose the directory you wish to export to:"),
                                            action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
                                            buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_OK,gtk.RESPONSE_OK))
        dia_chooser.set_destroy_with_parent(True)
        dia_chooser.set_transient_for(self.parent)
        try:
            dia_chooser.set_filename(self.exportFile) # use previously chosen export path as default
        except:
            pass

        response = dia_chooser.run()

        if response <> gtk.RESPONSE_OK:
            print _('Closed, no graph exported')
            dia_chooser.destroy()
            return

        # generate a unique filename for export
        now = datetime.now()
        now_formatted = now.strftime("%Y%m%d%H%M%S")
        self.exportFile = dia_chooser.get_filename() + "/fpdb" + now_formatted + ".png"
        dia_chooser.destroy()

        #print "DEBUG: self.exportFile = %s" %(self.exportFile)
        self.fig.savefig(self.exportFile, format="png")

        #display info box to confirm graph created
        diainfo = gtk.MessageDialog(parent=self.parent,
                                flags=gtk.DIALOG_DESTROY_WITH_PARENT,
                                type=gtk.MESSAGE_INFO,
                                buttons=gtk.BUTTONS_OK,
                                message_format=_("Graph created"))
        diainfo.format_secondary_text(self.exportFile)
        diainfo.run()
        diainfo.destroy()

    #end of def exportGraph
    def transfertsWindow (self, widget, data) :
        #if the window is already launched, put it in front
        if not self.settings['global_lock'].acquire(wait=False, source="GuiBankrollGraphViewer"):
            return

        #create the window …
        #first, check if there is at least one player on database, else quit
        if (len(self.filters.getHeroes()) == 0):
            print "No site/hero found, abort"
            return

        
        self.transferWindow = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.transferWindow.set_title("Transferts Management")
        self.transferWindow.set_position(gtk.WIN_POS_CENTER)
        self.transferWindow.set_transient_for(self.parent)
        self.transferWindow.connect("destroy", self.release)
        vbox = gtk.VBox(False, 0)
        self.transferWindow.add(vbox)
        
        #####
        #####
        #«new transfert» part
        hboxAdd = gtk.HBox(False, 0)
        vbox.pack_start(hboxAdd)
        
        #calendar
        cal = gtk.Calendar()        
        vboxSelection = gtk.VBox(False, 0)
        
        #hour selection
        hboxHour = gtk.HBox(False, 0)
        vboxSelection.pack_start(hboxHour, 0)
        
        timeHourPicker = gtk.SpinButton(None, 0, 0);   
        timeHourPicker.set_increments(1, 6)
        timeHourPicker.set_range(0, 23)
        timeHourPicker.set_value(datetime.datetime.now().hour) # current hour
            
        timeMinPicker = gtk.SpinButton(None, 0, 0);   
        timeMinPicker.set_increments(1, 10)
        timeMinPicker.set_range(0, 59)
        timeMinPicker.set_value(datetime.datetime.now().minute) # current hour
        
        #site/hero selection
        IDSelection = gtk.combo_box_new_text()
        
        for site, hero in self.filters.getHeroes().items():
            IDSelection.append_text(site + " - " + hero)
        
        IDSelection.set_active(0)
        #amount of virement ? ?
        amountEntry = gtk.Entry()
        amountEntry.set_text('100')
        amountEntry.connect('changed', self.on_changed, 'changed')

        #button add
        buttonAdd = gtk.ToolButton(gtk.STOCK_ADD)
        buttonAdd.connect('clicked', self.newTransfer, 'clicked', cal, timeHourPicker, timeMinPicker, IDSelection, amountEntry)
        buttonAdd.connect('clicked', self.destroyWindow)


        hboxAdd.pack_start(cal, 0)
        hboxAdd.pack_start(vboxSelection, 0)
        hboxHour.pack_start(timeHourPicker, 0)
        hboxHour.pack_start(timeMinPicker, 0)
        vboxSelection.pack_start(IDSelection, 0)
        vboxSelection.pack_start(amountEntry, 0)
        vboxSelection.pack_start(buttonAdd, -1)
                
        #end of "new transfert" part
        #####
        ####
        
        ####
        #start of "delete transfert" part
        
        hboxDelete = gtk.HBox(False, 0)
        vbox.pack_start(hboxDelete)
        
        #tab to create
        vboxTab = gtk.VBox(False, 0)
        self.createTab(vboxTab)
        
        buttonDelete = gtk.ToolButton(gtk.STOCK_DELETE)
        buttonDelete.connect('clicked', self.deleteTransfer, 'clicked')

        
        hboxDelete.pack_start(vboxTab, 1)                
        hboxDelete.pack_start(buttonDelete, 1)                
        #end of "delete transfert" part
        ####


        self.transferWindow.show_all()
        return
    #end of def transfertsWindow
    def release(self, widget, data=None):
        self.settings['global_lock'].release()
        self.transferWindow.destroy()
        return
    def on_changed(self, widget, data):
        text = widget.get_text().strip()
        widget.set_text(''.join([i for i in text if i in '0123456789']))
    def destroyWindow(self, widget):
        self.transferWindow.destroy()
        return
    def newTransfer(self, widget, data, cal, timeHourPicker, timeMinPicker, IDSelection, amountEntry):
        year, month, day = cal.get_date()
        month = month + 1 # because gtk gives it between 0 and 11 ?!
        hour = timeHourPicker.get_value()
        minute = timeMinPicker.get_value()
        (site, separator, hero) = IDSelection.get_active_text().partition(' - ')
        transfer = amountEntry.get_text()
        
        now = datetime.datetime(year, month, day, int(hour), int(minute), 0)

        #get siteID from siteName (table "sites")
        self.db.cursor.execute('SELECT id from sites where name LIKE "' + site + '"')
        siteID = self.db.cursor.fetchall()[0][0]
        self.db.rollback()
        
        #get heroID from heroName and siteID (table "players")
        self.db.cursor.execute('select id from players where name LIKE "' + hero + '" and siteId = ' + str(siteID))
        heroID = self.db.cursor.fetchall()[0][0]
        self.db.rollback()
        
        #insert it in the table now
        query = "INSERT INTO BankrollsManagement(siteId, playerId, transfer, startTime) VALUES (?, ?, ?, ?)"      
        #~print "DEBUG:\n%s" % query
        self.db.cursor.execute(query, (siteID, heroID, transfer, now))
        self.db.commit()
        self.db.rollback()
        
        #update the graph
        gobject.GObject.emit (self.filters.Button1, "clicked");
        
    def deleteTransfer(self, widget, data):
        #get the active line of the array
        selected = self.view.get_cursor()[0]

        #if no row selected, abort
        if selected is None:
            return
        #else, retrieve the line ( /!\ rowNumber != Id from the table ),        
        rowNumber = selected[0]
        line = self.liststore[0][rowNumber]
        
        id = line[0]

        #then delete it from table and refresh graph
        self.db.cursor.execute('DELETE FROM BankrollsManagement WHERE id=' + str(id))
        self.db.commit()
        self.db.rollback()            
        
        #destroy the window
        self.destroyWindow(widget)
        gobject.GObject.emit (self.filters.Button1, "clicked");

    def createTab(self, vbox) :
        cols_to_show =  [ ["id",            False, _("ID"),    0.0, "%s", "str"]
                        , ["siteName",      True,  _("Site"),    0.0, "%s", "str"]   # true not allowed for this line (set in code)
                        , ["playerName",    True,  _("Name"),    0.8, "%s", "str"]   # true not allowed for this line (set in code)
                        , ["amount",        True,  _("Amount"),    0.0, "%1.0f", "str"]
                        , ["date",          True, _("Date"),       0.0, "%s", "str"]]

        self.liststore=[]
        self.liststore.append( gtk.ListStore(*([str] * len(cols_to_show))) )
        self.view = gtk.TreeView(model=self.liststore[0])
        
        self.view.set_grid_lines(gtk.TREE_VIEW_GRID_LINES_BOTH)
        #vbox.pack_start(view, expand=False, padding=3)
        vbox.add(self.view)
        textcell = gtk.CellRendererText()
        textcell50 = gtk.CellRendererText()
        textcell50.set_property('xalign', 0.5)
        numcell = gtk.CellRendererText()
        numcell.set_property('xalign', 1.0)
        
        listcols = []
        listcols.append( [] )
        # Create header row   eg column: ("game",     True, "Game",     0.0, "%s")
        for i, col in enumerate(cols_to_show):
            listcols[0].append(gtk.TreeViewColumn(col[_COL_HEADING]))

            self.view.append_column(listcols[0][i])
            if col[_COL_FORMAT] == '%s':
                if col[_COL_XALIGN] == 0.0:
                    listcols[0][i].pack_start(textcell, expand=True)
                    listcols[0][i].add_attribute(textcell, 'text', i)
                    cellrend = textcell
                else:
                    listcols[0][i].pack_start(textcell50, expand=True)
                    listcols[0][i].add_attribute(textcell50, 'text', i)
                    cellrend = textcell50
                listcols[0][i].set_expand(True)
            else:
                listcols[0][i].pack_start(numcell, expand=True)
                listcols[0][i].add_attribute(numcell, 'text', i)
                listcols[0][i].set_expand(True)
                cellrend = numcell

        query = self.sql.query['getAllTransferInformations']

        #~print "DEBUG:\n%s" % query
        self.db.cursor.execute(query)
        
        result = self.db.cursor.fetchall()
        #~print "result of the big query in addGrid:",result
        colnames = [desc[0] for desc in self.db.cursor.description]



        #~for i in range(0, len(tab))
        rows = len(result) # +1 for title row
        counter = 0
        row = 0
        sqlrow = 0
        while sqlrow < rows:
            treerow = []
            for col,column in enumerate(cols_to_show):
                if column[_COL_ALIAS] in colnames:
                    value = result[sqlrow][colnames.index(column[_COL_ALIAS])]
                else:
                    value = 111

                if value != None and value != -999:
                    treerow.append(column[_COL_FORMAT] % value)
                else:
                    treerow.append(' ')
            #print "addGrid, just before end of big for. grid:",grid,"treerow:",treerow
            iter = self.liststore[0].append(treerow)
            sqlrow += 1
            row += 1
        vbox.show_all()
        
    def rightRequest(self, request, names, sites):
        tmp = self.sql.query[request]
        print "DEBUG: getData. :"
        start_date, end_date = self.filters.getDates()

        #Buggered if I can find a way to do this 'nicely' take a list of integers and longs
        # and turn it into a tuple readale by sql.
        # [5L] into (5) not (5,) and [5L, 2829L] into (5, 2829)
        nametest = str(tuple(names))
        sitetest = str(tuple(sites))

        #Must be a nicer way to deal with tuples of size 1 ie. (2,) - which makes sql barf
        tmp = tmp.replace("<player_test>", nametest)
        tmp = tmp.replace("<site_test>", sitetest)
        tmp = tmp.replace("<startdate_test>", start_date)
        tmp = tmp.replace("<enddate_test>", end_date)
        tmp = tmp.replace(",)", ")")
        
        return tmp
