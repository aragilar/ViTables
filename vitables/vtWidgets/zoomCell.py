# -*- coding: utf-8 -*-
#!/usr/bin/env python


########################################################################
#
#       Copyright (C) 2005, 2006, 2007 Carabos Coop. V. All rights reserved
#       Copyright (C) 2008 Vicent Mas. All rights reserved
#
#       This program is free software: you can redistribute it and/or modify
#       it under the terms of the GNU General Public License as published by
#       the Free Software Foundation, either version 3 of the License, or
#       (at your option) any later version.
#
#       This program is distributed in the hope that it will be useful,
#       but WITHOUT ANY WARRANTY; without even the implied warranty of
#       MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#       GNU General Public License for more details.
#
#       You should have received a copy of the GNU General Public License
#       along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#       Author:  Vicent Mas - vmas@vitables.org
#
#       $Source$
#       $Id: zoomCell.py 1083 2008-11-04 16:41:02Z vmas $
#
########################################################################

"""Here is defined the ZoomCell class.

Classes:

* ZoomCell(qttable.QTable)

Methods:

* __init__(self, cell, caption, workspace, name=None)
* hasShape(self)
* getGridDimensions(self)
* getPyObjectDimensions(self)
* getArrayDimensions(self, shape)
* getTableDimensions(self, dtype)
* zoomTable(self)
* zoomArray(self)
* slotZoomView(self, row, col, button, position)

Misc variables:

* __docformat__

"""

__docformat__ = 'restructuredtext'

import numpy

import tables.utilsExtension

import PyQt4.QtCore as QtCore
import PyQt4.QtGui as QtGui

import vitables.utils

class ZoomCell(QtGui.QMdiSubWindow):
    """
    Display an array/table cell on its own view (table widget).

    When a leaf is displayed in a view, is quite usual that the content
    of some cells is not fully visible because it doesn't fit into
    the cell. To alleviate this problem this class provides a way to,
    recursively, display the content of any cell on its own view.
    The cell content depends on the kind of leaf and the shape of its
    atom. Cells of `Table` views and `E/C/Array` views can be:

    - a `numpy` scalar. `Atom` shape is ()
    - a `numpy` array. `Atom` shape is not ()

    In addition, cells of `VLArray` views can be:

    - a serialized `Python` object. `Atom` kind is ``object``, shape is ()
    - a `Python` string. `Atom` kind is ``vlstring``, shape is ()

    Finally, cells of `Table` views also can be:

    - a `numpy.void` object when the cell corresponds to nested field of the record
    """
    def __init__(self, data, title, workspace, leaf):
        """
        Creates a zoom view for a given cell.

        The passed cell is an element of a given dataset. It is always
        a (potentially nested) `numpy` array. See cell accessor methods
        in the `Buffer` class for details.

        :Parameters:

            - `data`: the value stored in the cell being zoomed
            - `title`: the base string for the zoomed view title
            - `workspace`: the parent of the zoomed view
            - `leaf`: a LeafNode instance
        """

        self.data = data
        self.title = title
        self.workspace = workspace
        self.data_shape = self.hasShape()
        self.field_names = []

        # Create and customise the widget that will display the zoomed cell
        # The pindex attribute is required to keep working the code for
        # synchronising workspace and tree of databases view.
        # The leaf attribute is required to keep working the code for
        # cleaning the workspace when a file is closed.
        # The WA_DeleteOnClose flag makes that when the widget is
        # closed either programatically (see VTAPP.slotWindowsClose)
        # or by the user (clicking the close button in the titlebar)
        # the widget is hiden AND destroyed --> the workspace
        # updates automatically its list of open windows --> the
        # Windows menu content is automatically updated
        QtGui.QMdiSubWindow.__init__(self, workspace)
        self.pindex = None
        self.leaf = leaf
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        # The internal widget
        self.grid = QtGui.QTableWidget()
        self.setWidget(self.grid)
        # Configure the titlebar
        self.setWindowTitle(self.title)
        iconsDictionary = vitables.utils.getIcons()
        self.setWindowIcon(iconsDictionary['zoom'])

        # Decide how the cell content will be formatted. Content can be:
        # - a numpy array
        # - either a string or a unicode string
        # - other Python object
        if self.data_shape:
            self.formatContent = vitables.utils.formatArrayContent
        elif isinstance(cell, str) or isinstance(cell, unicode):
            self.formatContent = vitables.utils.formatStringContent
        else:
            self.formatContent = vitables.utils.formatObjectContent

        # Setup grid dimensions
        (nrows, ncols) = self.getGridDimensions()
        self.grid.setColumnCount(ncols)
        self.grid.setRowCount(nrows)

        # Setup grid editing
        self.grid.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)

        # Setup grid horizontal header
        if self.field_names:
            for section in range(0, ncols):
                item = QtGui.QTableWidgetItem()
                item.setText(self.field_names[section])
                self.grid.setHorizontalHeaderItem(section, item)
        else:
            for section in range(0, ncols):
                item = QtGui.QTableWidgetItem()
                item.setText(str(section + 1))
                self.grid.setHorizontalHeaderItem(section, item)

        # Fill the grid
        if self.field_names:
            self.zoomTable()
        else:
            self.zoomArray()

        self.show()

        rmode = QtGui.QHeaderView.Stretch
        if self.grid.columnCount() == 1:
            self.grid.horizontalHeader().setResizeMode(rmode)
        if self.grid.rowCount() == 1:
            self.grid.verticalHeader().setResizeMode(rmode)

        # Connect signals to slots
        QtCore.QObject.connect(self.grid,
            QtCore.SIGNAL('cellDoubleClicked(int, int)'), 
            self.slotZoomView)


    def hasShape(self):
        """Find out if the zoomed cell has a shape attribute."""

        if hasattr(self.data, 'shape'):
            return True
        else:
            return False


    def getGridDimensions(self):
        """
        Get the dimensions of the grid where the zoomed cell will be displayed.

        :Returns: a tuple (rows, columns)
        """

        if self.data_shape:
            # The cell contains a numpy object
            shape = self.data.shape
            dtype = self.data.dtype
            if dtype.fields:
                # Table nested fields come here
                return self.getNestedFieldDimensions(dtype)
            else:
                # Any other case come here
                return self.getArrayDimensions(shape)
        else:
            # The cell contains a Python object
            return self.getPyObjectDimensions()


    def getPyObjectDimensions(self):
        """
        Get the dimensions of the grid where the cell will be zoomed.

        The zoomed cell contains a `Python` object.

        :Returns: a tuple (rows, columns)
        """

        if isinstance(self.data, list) or isinstance(self.data, tuple):
            return (len(self.data), 1)
        else:
            return (1, 1)


    def getArrayDimensions(self, shape):
        """
        Get the dimensions of the grid where the cell will be zoomed.

        The zoomed cell contains a `numpy` array and will be displayed
        in a table with the same shape than it.

        :Parameter shape: the cell shape

        :Returns: a tuple (rows, columns)
        """

        # Numpy scalars are special a case
        if shape == ():
            nrows = ncols = 1
        # 1-D arrays are displayed as a 1-column vector with nrows
        elif len(shape) == 1:
            nrows = shape[0]
            ncols = 1
        # N-D arrays are displayed as a matrix (nrowsXncols) which
        # elements are (N-2)-D arrays
        else:
            nrows = shape[0]
            ncols = shape[1]

        return (nrows, ncols)


    def getNestedFieldDimensions(self, dtype):
        """
        Get the dimensions of the grid where the cell will be zoomed.

        The zoomed cell contains a nested field and will be displayed
        in a table with only one row and one column per (top - 1)
        level field. Note that fields have `shape`=().

        :Parameter dtype: the cell data type

        :Returns: a tuple (rows, columns)
        """

        self.field_names = [name for (name, format) in self.data.dtype.descr]
        ncols = len(self.field_names)
        nrows = 1

        return (nrows, ncols)


    def zoomTable(self):
        """Fill the zoom view with the content of the clicked nested field."""

        for column in range(0, self.grid.columnCount()):
            content = self.data[self.field_names[column]]
            text = self.formatContent(content)
            item = QtGui.QTableWidgetItem(text)
            self.grid.setItem(0, column, item)


    def zoomArray(self):
        """Fill the zoom view with the content of the clicked cell."""

        numRows = self.grid.rowCount()
        numCols = self.grid.columnCount()
        # Numpy scalars are displayed in a 1x1 grid
        if numRows == numCols == 1:
            content = self.data
            text = self.formatContent(content)
            item = QtGui.QTableWidgetItem(text)
            self.grid.setItem(0, 0, item)
        # 1-D arrays
        elif numCols == 1:
            for row in range(0, numRows):
                content = self.data[row]
                text = self.formatContent(content)
                item = QtGui.QTableWidgetItem(text)
                self.grid.setItem(row, 0, item)
        # N-D arrays
        else:
            for row in range(0, numRows):
                for column in range(0, numCols):
                    content = self.data[row][column]
                    text = self.formatContent(content)
                    item = QtGui.QTableWidgetItem(text)
                    self.grid.setItem(row, column, item)


    def slotZoomView(self, row, col):
        """Makes the content of the clicked cell fully visible.

        :Parameters:

            - `row`: the row of the clicked cell
            - `col`: the column of the clicked cell
        """

        # Check if the zoom has to be done
        if self.data_shape:
            if not (self.data.shape !=() or self.field_names):
                return
        elif not (isinstance(self.data, list) or isinstance(self.data, tuple)):
                return

        # Get data
        if self.data_shape:
            # Arrays and table nested fields
            if self.field_names:
                cell = self.data[self.field_names[col]]
            elif len(self.data.shape) > 1:
                cell = self.data[row][ col]
            elif len(self.data.shape) == 1:
                cell = self.data[row]
        else:
            # Python lists and tuples
            cell = self.data[row]

        # Get caption
        if self.field_names:
            caption = '%s: %s[%s]' % (self.title,
                self.field_names[col], row + 1)
        else:
            caption = '%s: (%s, %s)' % (self.title, row + 1, col + 1)
        ZoomCell(cell, caption, self.workspace, self.leaf)





