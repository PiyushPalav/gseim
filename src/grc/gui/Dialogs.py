# Copyright 2008, 2009, 2016 Free Software Foundation, Inc.
# This file is part of GNU Radio
#
# GNU Radio Companion is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# GNU Radio Companion is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA

from __future__ import absolute_import

import sys
import textwrap
from distutils.spawn import find_executable

from gi.repository import Gtk, GLib

from . import Utils, Actions, Constants
from ..core import Messages

class SimpleTextDisplay(Gtk.TextView):
    """
    A non user-editable gtk text view.
    """

    def __init__(self, text=''):
        """
        TextDisplay constructor.

        Args:
            text: the text to display (string)
        """
        Gtk.TextView.__init__(self)
        self.set_text = self.get_buffer().set_text
        self.set_text(text)
        self.set_editable(False)
        self.set_cursor_visible(False)
        self.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)

class TextDisplay(SimpleTextDisplay):
    """
    A non user-editable scrollable text view with popup menu.
    """

    def __init__(self, text=''):
        """
        TextDisplay constructor.

        Args:
            text: the text to display (string)
        """
        SimpleTextDisplay.__init__(self, text)
        self.scroll_lock = True
        self.connect("populate-popup", self.populate_popup)

    def insert(self, line):
        """
        Append text after handling backspaces and auto-scroll.

        Args:
            line: the text to append (string)
        """
        line = self._consume_backspaces(line)
        self.get_buffer().insert(self.get_buffer().get_end_iter(), line)
        self.scroll_to_end()

    def _consume_backspaces(self, line):
        """
        Removes text from the buffer if line starts with '\b'

        Args:
            line: a string which may contain backspaces

        Returns:
            The string that remains from 'line' with leading '\b's removed.
        """
        if not line:
            return

        # for each \b delete one char from the buffer
        back_count = 0
        start_iter = self.get_buffer().get_end_iter()
        while len(line) > back_count and line[back_count] == '\b':
            # stop at the beginning of a line
            if not start_iter.starts_line():
                start_iter.backward_char()
            back_count += 1
        # remove chars from buffer
        self.get_buffer().delete(start_iter, self.get_buffer().get_end_iter())
        return line[back_count:]

    def scroll_to_end(self):
        """ Update view's scroll position. """
        if self.scroll_lock:
            buf = self.get_buffer()
            mark = buf.get_insert()
            buf.move_mark(mark, buf.get_end_iter())
            self.scroll_mark_onscreen(mark)

    def clear(self):
        """ Clear all text from buffer. """
        buf = self.get_buffer()
        buf.delete(buf.get_start_iter(), buf.get_end_iter())

    def save(self, file_path):
        """
        Save context of buffer to the given file.

        Args:
            file_path: location to save buffer contents
        """
        with open(os.path.expanduser(file_path), 'w') as logfile:
            buf = self.get_buffer()
            logfile.write(buf.get_text(buf.get_start_iter(),
                                       buf.get_end_iter(), True))

    # Action functions are set by the Application's init function
    def clear_cb(self, menu_item, web_view):
        """ Callback function to clear the text buffer """
        Actions.CLEAR_CONSOLE()

    def scroll_back_cb(self, menu_item, web_view):
        """ Callback function to toggle scroll lock """
        Actions.TOGGLE_SCROLL_LOCK()

    def save_cb(self, menu_item, web_view):
        """ Callback function to save the buffer """
        Actions.SAVE_CONSOLE()

    def populate_popup(self, view, menu):
        """Create a popup menu for the scroll lock and clear functions"""
        menu.append(Gtk.SeparatorMenuItem())

        lock = Gtk.CheckMenuItem(label = "Scroll Lock")
        menu.append(lock)
        lock.set_active(self.scroll_lock)
        lock.connect('activate', self.scroll_back_cb, view)

        save = Gtk.ImageMenuItem(label = Gtk.STOCK_SAVE)
        menu.append(save)
        save.connect('activate', self.save_cb, view)

        clear = Gtk.ImageMenuItem(label = Gtk.STOCK_CLEAR)
        menu.append(clear)
        clear.connect('activate', self.clear_cb, view)
        menu.show_all()
        return False

class MessageDialogWrapper(Gtk.MessageDialog):
    """ Run a message dialog. """

    def __init__(self, parent, message_type, buttons, title=None, markup=None,
                 default_response=None, extra_buttons=None):
        """
        Create a modal message dialog.

        Args:
            message_type: the type of message may be one of:
                            Gtk.MessageType.INFO
                            Gtk.MessageType.WARNING
                            Gtk.MessageType.QUESTION or Gtk.MessageType.ERROR
            buttons: the predefined set of buttons to use:
                            Gtk.ButtonsType.NONE
                            Gtk.ButtonsType.OK
                            Gtk.ButtonsType.CLOSE
                            Gtk.ButtonsType.CANCEL
                            Gtk.ButtonsType.YES_NO
                            Gtk.ButtonsType.OK_CANCEL
            title: the title of the window (string)
            markup: the message text with pango markup
            default_response: if set, determines which button is highlighted by default
            extra_buttons: a tuple containing pairs of values:
                            each value is the button's text and the button's return value

        """
        Gtk.MessageDialog.__init__(
            self, transient_for=parent, modal=True, destroy_with_parent=True,
            message_type=message_type, buttons=buttons
        )
        if title:
            self.set_title(title)
        if markup:
            self.set_markup(markup)
        if extra_buttons:
            self.add_buttons(*extra_buttons)
        if default_response:
            self.set_default_response(default_response)

    def run_and_destroy(self):
        response = self.run()
        self.hide()
        return response

class ErrorsDialog(Gtk.Dialog):
    """ Display flowgraph errors. """

    def __init__(self, parent, flowgraph):
        """Create a listview of errors"""
        Gtk.Dialog.__init__(
            self,
            title='Errors and Warnings',
            transient_for=parent,
            modal=True,
            destroy_with_parent=True,
        )
        self.add_buttons(Gtk.STOCK_OK, Gtk.ResponseType.ACCEPT)
        self.set_size_request(750, Constants.MIN_DIALOG_HEIGHT)
        self.set_border_width(10)

        self.store = Gtk.ListStore(str, str, str)
        self.update(flowgraph)

        self.treeview = Gtk.TreeView(model=self.store)
        for i, column_title in enumerate(["Block", "Aspect", "Message"]):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(column_title, renderer, text=i)
            column.set_sort_column_id(i)  # liststore id matches treeview id
            column.set_resizable(True)
            self.treeview.append_column(column)

        self.scrollable = Gtk.ScrolledWindow()
        self.scrollable.set_vexpand(True)
        self.scrollable.add(self.treeview)

        self.vbox.pack_start(self.scrollable, True, True, 0)
        self.show_all()

    def update(self, flowgraph):
        self.store.clear()
        for element, message in flowgraph.iter_error_messages():
            if element.is_block:
                src, aspect = element.name, ''
            elif element.is_connection:
                src = element.source_block.name
                aspect = "Connection to '{}'".format(element.sink_block.name)
            elif element.is_port:
                src = element.parent_block.name
                aspect = "{} '{}'".format('Sink' if element.is_sink else 'Source', element.name)
            elif element.is_param:
                src = element.parent_block.name
                aspect = "Param '{}'".format(element.name)
            else:
                src = aspect = ''
            self.store.append([src, aspect, message])

    def run_and_destroy(self):
        response = self.run()
        self.hide()
        return response

def show_about(parent, config):
    ad = Gtk.AboutDialog(transient_for=parent)
    ad.set_program_name(config.name)
    ad.set_name('')
    ad.set_license(config.license)

    #ad.set_comments("")
    ad.set_copyright(config.license.splitlines()[0])
    ad.set_website(config.website)

    ad.connect("response", lambda action, param: action.hide())
    ad.show()

def show_help(parent):
    """ Display basic usage tips. """

    markup = textwrap.dedent("""\
        <b>Usage Tips</b>
        \n\
        <u>Add block</u>: drag and drop or double click a block in the block 
       selection window.
        <u>Rotate block</u>: Select a block, press left/right on the keyboard.
        <u>Edit parameters</u>: double click on a block in the flow graph.
        <u>Make connection</u>: click on the source port of one block, then 
       click on the sink port of another block.
        <u>Remove connection</u>: select the connection and press delete, or 
       drag the connection.
        \n\
        *Press CTRL+K or see menu for Keyboard - Shortcuts
        \
    """)

    MessageDialogWrapper(
        parent, Gtk.MessageType.INFO, Gtk.ButtonsType.CLOSE, title='Help', markup=markup
    ).run_and_destroy()

def show_keyboard_shortcuts(parent):
    """ Display keyboard shortcut-keys. """

    markup = textwrap.dedent("""\
    <b>Keyboard Shortcuts</b>
    \n\
    <u>Ctrl+N</u>: Create a new flowgraph. 
    <u>Ctrl+O</u>: Open an existing flowgraph.
    <u>Ctrl+S</u>: Save the current flowgraph or save as for new. 
    <u>Ctrl+W</u>: Close the current flowgraph.
    <u>Ctrl+Z</u>: Undo a change to the flowgraph.         
    <u>Ctrl+Y</u>: Redo a change to the flowgraph.
    <u>Ctrl+A</u>: Selects all blocks and connections.
    <u>Ctrl+P</u>: Screen Capture of the Flowgraph.
    <u>Ctrl+F</u>: Search for a block by name.       
    <u>Ctrl+Q</u>: Quit. 
    <u>F1</u>    : Help menu.            
    <u>F5</u>    : Generate the Flowgraph. 
    <u>F6</u>    : Execute the Flowgraph.     
    <u>F7</u>    : Kill the Flowgraph.
    <u>Ctrl+Shift+S</u>: Save as the current flowgraph.
    <u>Ctrl+Shift+D</u>: Create a duplicate of current flow graph.   
    
    <u>Ctrl+X/C/V</u>: Edit-cut/copy/paste.
    <u>Shift+T/M/B/L/C/R</u>: Vertical Align Top/Middle/Bottom and
            Horizontal Align Left/Center/Right respectively of the 
            selected block.
    \
    """)
    
    MessageDialogWrapper(
        parent, Gtk.MessageType.INFO, Gtk.ButtonsType.CLOSE, title='Keyboard - Shortcuts', markup=markup
    ).run_and_destroy()

