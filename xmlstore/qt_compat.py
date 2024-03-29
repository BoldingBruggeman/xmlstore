from __future__ import print_function

import os

def importPyQt4():
    import sip
    sip.setapi('QString',  2)
    sip.setapi('QVariant', 2)
    import PyQt4.QtCore as _QtCore
    return _QtCore

def importPyQt5():
    import PyQt5.QtCore as _QtCore
    return _QtCore

def importPySide():
    import PySide.QtCore as _QtCore
    return _QtCore

preference = ('PyQt4', importPyQt4), ('PySide', importPySide), ('PyQt5', importPyQt5)

if 'QT_API' in os.environ:
    preference = list(preference)
    for i, (name, fn) in enumerate(preference):
        if name.lower() == os.environ['QT_API'].lower():
            preference.insert(0, preference.pop(i))
            break
    else:
        print('Qt backend "%s" set in environment variable "QT_API" not found. Auto-detecting...' % (os.environ['QT_API'],))

qt4_backend = None
for name, importFunction in preference:
    try:
        QtCore = importFunction()
    except ImportError:
        continue
    except AttributeError:
        continue
    qt4_backend = name
    break
else:
    raise Exception('Unable to import PyQt4 or PySide. Please install one of these packages first.')

def importModule(moduleName):
    qt4 = __import__(qt4_backend, globals(), locals(), [moduleName])
    return getattr(qt4, moduleName)

# Store properties describing backend.
# Create additional methods in QtCore module where needed.
if qt4_backend == 'PySide':
    import PySide
    mpl_qt4_backend = 'PySide'
    qt4_backend_version = PySide.__version__
else:
    mpl_qt4_backend = qt4_backend
    qt4_backend_version = QtCore.PYQT_VERSION_STR

    QtCore.Signal = QtCore.pyqtSignal
    QtCore.Slot = QtCore.pyqtSlot
    QtCore.Property = QtCore.pyqtProperty

# Import QtGui module and create additional methods where needed.
QtGui = importModule('QtGui')
if qt4_backend == 'PyQt5':
    QtWidgets = importModule('QtWidgets')
    QtPrintSupport = importModule('QtPrintSupport')
else:
    QtWidgets = QtGui
    QtPrintSupport = QtGui
if qt4_backend in ('PySide', 'PyQt5'):
    QtWidgets.QFileDialog.getOpenFileNamesAndFilter = QtWidgets.QFileDialog.getOpenFileNames
    QtWidgets.QFileDialog.getOpenFileNameAndFilter = QtWidgets.QFileDialog.getOpenFileName
    QtWidgets.QFileDialog.getSaveFileNameAndFilter = QtWidgets.QFileDialog.getSaveFileName
