""" IDA ROP view plugin UI functions and classes """

# IDA libraries
import idaapi
import idc
from idaapi import Form, Choose2

# Python libraries
import os
import csv

from .engine import IdaRopEngine, IdaRopSearch, Gadget

###############################################################################
# ROP/JOP/COP Form

class IdaRopForm(Form):

    def __init__(self, idarop, idaropengine,  select_list = None):

        self.idarop = idarop
        self.engine = idaropengine
        self.select_list = select_list

        self.segments = SegmentView(self.engine, embedded=True)

        Form.__init__(self, 
r"""BUTTON YES* Search
Search ROP gadgets

{FormChangeCb}<Segments:{cEChooser}>

Search Settings:
<Bad Chars        :{strBadChars}>     
Unicode Table    <ANSI:{rUnicodeANSI}><OEM:{rUnicodeOEM}><UTF7:{rUnicodeUTF7}><UTF8:{rUnicodeUTF8}>{radUnicode}>
<Bad Instructions :{strBadMnems}>
<Max gadget size  :{intMaxRopSize}>
<Max gadget offset:{intMaxRopOffset}>
<Max RETN imm16   :{intMaxRetnImm}>
<Max JOP imm8/32  :{intMaxJopImm}>
<Max gadgets      :{intMaxRops}>
Other settings   <Allow conditional jumps:{cRopAllowJcc}>
                <Do not allow bad bytes:{cRopNoBadBytes}>
                <Search for ROP gadgets:{cRopSearch}>
                <Search for JOP gadgets:{cJopSearch}>{ropGroup}>


""", {
                'cEChooser'       : Form.EmbeddedChooserControl(self.segments, swidth=90),
                #'ptrGroup'        : Form.ChkGroupControl(("cPtrNonull", "cPtrAscii", "cPtrAsciiPrint", "cPtrUnicode",'cPtrAlphaNum','cPtrAlpha','cPtrNum')),
                'ropGroup'        : Form.ChkGroupControl(('cRopAllowJcc','cRopNoBadBytes','cRopSearch','cJopSearch')),
                'intMaxRopSize'   : Form.NumericInput(swidth=4,tp=Form.FT_DEC,value=self.engine.rop.maxRopSize),
                'intMaxRopOffset' : Form.NumericInput(swidth=4,tp=Form.FT_DEC,value=self.engine.rop.maxRopOffset),
                'intMaxRops'      : Form.NumericInput(swidth=4,tp=Form.FT_DEC,value=self.engine.rop.maxRops),
                'intMaxRetnImm'   : Form.NumericInput(swidth=4,tp=Form.FT_HEX,value=self.engine.rop.maxRetnImm),
                'intMaxJopImm'    : Form.NumericInput(swidth=4,tp=Form.FT_HEX,value=self.engine.rop.maxJopImm),
                'strBadChars'     : Form.StringInput(swidth=70,tp=Form.FT_ASCII),
                'radUnicode'      : Form.RadGroupControl(("rUnicodeANSI","rUnicodeOEM","rUnicodeUTF7","rUnicodeUTF8")),
                'strBadMnems'     : Form.StringInput(swidth=80,tp=Form.FT_ASCII,value="leave, int, into, enter, syscall, sysenter, sysexit, sysret, in, out, loop, loope, loopne, lock, rep, repe, repz, repne, repnz"),
                'FormChangeCb'    : Form.FormChangeCb(self.OnFormChange),
            })

        self.Compile()

    def OnFormChange(self, fid):

        # Form initialization
        if fid == -1:
            self.SetFocusedField(self.cEChooser)

            # Preselect executable segments on startup if none were already specified:
            if self.select_list == None:

                self.select_list = list()

                for i, seg in enumerate(self.engine.segments):
                    if seg.x:
                        self.select_list.append(i)

            self.SetControlValue(self.cEChooser, self.select_list)

            # Enable both ROP and JOP search by default
            self.SetControlValue(self.cRopSearch, True)
            self.SetControlValue(self.cJopSearch, True)

            # Skip bad instructions by default
            self.SetControlValue(self.cRopNoBadBytes, True)

        # Form OK pressed
        elif fid == -2:
            pass

        return 1

###############################################################################
class SegmentView(Choose2):

    def __init__(self, idarop, embedded = False):
        self.idarop = idarop

        Choose2.__init__(self, "Segments",
                         [ ["Name",     13 | Choose2.CHCOL_PLAIN],
                           ["Start",  13 | Choose2.CHCOL_HEX], 
                           ["End",     10 | Choose2.CHCOL_HEX], 
                           ["Size",     10 | Choose2.CHCOL_HEX],
                           ["R",   1 | Choose2.CHCOL_PLAIN],
                           ["W",      1 | Choose2.CHCOL_PLAIN], 
                           ["X",       1 | Choose2.CHCOL_PLAIN],
                           #["D",    1 | Choose2.CHCOL_PLAIN],
                           ["Class",     8 | Choose2.CHCOL_PLAIN], 
                         ],
                         flags = Choose2.CH_MULTI,  # Select multiple modules
                         embedded=embedded)

        self.icon = 150

        # Items for display
        self.items = list()

        # Initialize/Refresh the view
        self.refreshitems()

        # Selected items
        self.select_list = list()

    def show(self):
        # Attempt to open the view
        if self.Show() < 0: return False

    def refreshitems(self):
        self.items = list()

        for segment in self.idarop.list_segments():
            self.items.append(segment.get_display_list())

    def OnCommand(self, n, cmd_id):

        # Search ROP gadgets
        if cmd_id == self.cmd_search_gadgets:
            
            # Initialize ROP gadget form with empty selection
            self.idarop.process_rop(select_list = self.select_list)

    def OnSelectLine(self, n):
        pass

    def OnGetLine(self, n):
        return self.items[n]

    def OnGetIcon(self, n):

        if not len(self.items) > 0:
            return -1

        segment = self.idarop.list_segments()[n]
        if segment.x : # Exec Seg
            return 61
        else:
            return 59

    def OnClose(self):
        self.cmd_search_gadgets = None

    def OnGetSize(self):
        return len(self.items)

    def OnRefresh(self, n):
        self.refreshitems()
        return n

    def OnActivate(self):
        self.refreshitems()


class IdaRopView(Choose2):
    """
    Chooser class to display security characteristics of loaded modules.
    """
    def __init__(self, idarop):

        self.idarop = idarop

        Choose2.__init__(self,
                         "ROP gadgets",
                         [ ["Address",           13 | Choose2.CHCOL_HEX], 
                           ["Gadget",            30 | Choose2.CHCOL_PLAIN], 
                           #["Opcodes",          10 | Choose2.CHCOL_PLAIN],
                           ["Size",               3 | Choose2.CHCOL_DEC],
                           ["Pivot",              4 | Choose2.CHCOL_DEC],
                         ],
                         flags = Choose2.CH_MULTI)

        self.icon = 182

        # Items for display
        self.items = []

        # Initialize/Refresh the view
        self.refreshitems()

        # export as csv command
        self.cmd_export_csv  = None

        # clear result command
        self.clear_rop_list = None

    def show(self):
        # Attempt to open the view
        if self.Show() < 0: return False

        if self.cmd_export_csv == None:
            self.cmd_export_csv  = self.AddCommand("Export as csv...", flags = idaapi.CHOOSER_POPUP_MENU, icon=40)
        if self.clear_rop_list == None:
            self.clear_rop_list  = self.AddCommand("Clear rop list", flags = idaapi.CHOOSER_POPUP_MENU, icon=32)

        return True

    def refreshitems(self):
        self.items = []

        if self.idarop.rop != None and len(self.idarop.rop.gadgets):
            for g in self.idarop.rop.gadgets:
                self.items.append(g.get_display_list(self.idarop.addr_format))

    def OnCommand(self, n, cmd_id):

        # Export CSV
        if cmd_id == self.cmd_export_csv:

            file_name = idaapi.askfile_c(1, "*.csv", "Please enter CSV file name")
            if file_name:
                print "[idarop] Exporting gadgets to %s" % file_name
                with open(file_name, 'wb') as csvfile:
                    csvwriter = csv.writer(csvfile, delimiter=',',
                                            quotechar='"', quoting=csv.QUOTE_MINIMAL)
                    csvwriter.writerow(["Address","Gadget","Size","Pivot"])
                    for item in self.items:
                        csvwriter.writerow(item)

        elif cmd_id == self.clear_rop_list:
            self.idarop.rop.gadgets = list()
            self.refreshitems()

        return 1

    def OnSelectLine(self, n):
        """ Callback on double click line : should open a custom view with the disas gadget.
            IDA disass view can't show "unaligned" gadgets.
        """
        idaapi.jumpto( self.idarop.rop.gadgets[n].address )

    def OnGetLine(self, n):
        return self.items[n]

    def OnClose(self):
        self.cmd_export_csv  = None
        self.clear_rop_list  = None

    def OnGetSize(self):
        return len(self.items)

    def OnRefresh(self, n):
        self.refreshitems()
        return n

    def OnActivate(self):
        self.refreshitems()



###############################################################################

class IdaRopManager():

    def __init__(self): 
        self.addmenu_item_ctxs = list()
        self.idarop = IdaRopEngine()

        # Initialize ROP gadget search engine
        self.idarop.rop = IdaRopSearch(self.idarop)

        # Defered csv loading for a faster startup
        self.defered_loading = False

    ###########################################################################
    # Menu Items
    def add_menu_item_helper(self, menupath, name, hotkey, flags, pyfunc, args):

        # add menu item and report on errors
        addmenu_item_ctx = idaapi.add_menu_item(menupath, name, hotkey, flags, pyfunc, args)
        if addmenu_item_ctx is None:
            return 1
        else:
            self.addmenu_item_ctxs.append(addmenu_item_ctx)
            return 0

    def add_menu_items(self):
        if self.add_menu_item_helper("Search/all error operands", "list rop gadgets...", "Shift+Ctrl+r", 1, self.proc_rop, None): return 1
        if self.add_menu_item_helper("View/Open subviews/Problems", "View rop gadgets...", "Shift+r", 1, self.show_rop_view, None): return 1
        return 0

    def del_menu_items(self):
        for addmenu_item_ctx in self.addmenu_item_ctxs:
            idaapi.del_menu_item(addmenu_item_ctx)

    ###########################################################################

    # ROP View
    def show_rop_view(self):

        # If the default csv exist but has not been loaded, load here
        if self.defered_loading == True:
            idaapi.show_wait_box("loading gadgets db ...")
            self.load_default_csv(force = True)
            idaapi.hide_wait_box()
            self.defered_loading = False

        # Show the ROP gadgets view
        ropView = IdaRopView(self.idarop)
        ropView.show()

    def proc_rop(self):
        
        # Prompt user for ROP search settings
        f = IdaRopForm(self, self.idarop)
        ok = f.Execute()
        if ok == 1:
            # reset previous results
            self.defered_loading = False

            ret = self.idarop.process_rop(f, f.segments.GetEmbSelection())

            if ret:
                self.show_rop_view()

        f.Free()


    def export_default_csv(self):
        """ Export the found rop gadget in a default csv file """

        ropView = IdaRopView(self.idarop)
        if len(ropView.items) == 0:
            return

        file_name = "%s.gadgets" % idaapi.get_input_file_path()
        with open(file_name, 'wb') as csvfile:
            csvwriter = csv.writer(csvfile, delimiter=',',
                                            quotechar='"', quoting=csv.QUOTE_MINIMAL)
            csvwriter.writerow(["Offset","Instructions", "Size","Pivot"])
            for item in ropView.items:
                address,insn,size,pivot = item
                offset = "0x%x" % (int(address, 16) - idaapi.get_imagebase())
                csvwriter.writerow((offset, insn, size, pivot))


    def load_default_csv(self, force=False):
        """ Load the rop gadgets list from a default csv file """

        file_name = "%s.gadgets" % idaapi.get_input_file_path()
        if not os.path.lexists(file_name) or not os.path.isfile(file_name):
            return

        if os.path.getsize(file_name) > 0x1400000 and force == False:
            print("IDA ROP loading csv : csv file too big to be loaded on startup. It will loaded on first call to 'View Rop gadgets'")
            self.defered_loading = True
            return

        with open(file_name, 'rb') as csvfile:
            csvreader = csv.reader(csvfile, delimiter=',',
                                            quotechar='"', quoting=csv.QUOTE_MINIMAL)
            # ignore header
            header = next(csvreader)

            for row in csvreader:
                offset,instructions, size, pivot = row
                
                # Reconstruct linear address based on binary base address and offset
                address = int(offset, 16) + idaapi.get_imagebase()


                gadget = Gadget(
                    address = address,                    
                    instructions = instructions,
                    size = int(size),
                    pivot = int(pivot))

                self.idarop.rop.gadgets.append(gadget)