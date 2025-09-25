import os
import importlib

def import_qt(backend):
    if backend == 'PyQt4':
        import sip
        sip.setapi('QString',  2)
        sip.setapi('QVariant', 2)
    return importlib.import_module(backend + ".QtCore")

preference = ('PySide6', 'PyQt6', 'PyQt5', 'PySide2') 

if 'QT_API' in os.environ:
    preference = list(preference)
    for i, name in enumerate(preference):
        if name.lower() == os.environ['QT_API'].lower():
            preference.insert(0, preference.pop(i))
            break
    else:
        print('Qt backend "%s" set in environment variable "QT_API" not found. Auto-detecting...' % (os.environ['QT_API'],))

qt4_backend = None
for name in preference:
    try:
        QtCore = import_qt(name)
    except ImportError:
        continue
    except AttributeError:
        continue
    qt4_backend = name
    break
else:
    raise Exception('Unable to import any of: %s. Please install one of these packages first.' % (", ".join(preference),))

def importModule(moduleName):
    return importlib.import_module(qt4_backend + "." + moduleName)

# Store properties describing backend.
# Create additional methods in QtCore module where needed.
if qt4_backend.startswith('PySide'):
    root_mod = importlib.import_module(qt4_backend)
    qt4_backend_version = root_mod.__version__
    mpl_qt4_backend = qt4_backend
else:
    mpl_qt4_backend = qt4_backend
    qt4_backend_version = QtCore.PYQT_VERSION_STR

    QtCore.Signal = QtCore.pyqtSignal
    QtCore.Slot = QtCore.pyqtSlot
    QtCore.Property = QtCore.pyqtProperty

# Import QtGui module and create additional methods where needed.
QtGui = importModule('QtGui')
QtWidgets = importModule('QtWidgets')
QtPrintSupport = importModule('QtPrintSupport')

if not hasattr(QtWidgets, "QAction"):
    # Qt6 moved QAction from QtWidgets to QtGui
    QtWidgets.QAction = QtGui.QAction

# PySide2 only has exec_, not exec
if not hasattr(QtWidgets.QApplication, "exec"):
    QtWidgets.QApplication.exec = lambda self, *args, **kwargs: self.exec_(*args, **kwargs)
if not hasattr(QtWidgets.QMenu, "exec"):
    QtWidgets.QMenu.exec = lambda self, *args, **kwargs: self.exec_(*args, **kwargs)
if not hasattr(QtWidgets.QDialog, "exec"):
    QtWidgets.QDialog.exec = lambda self, *args, **kwargs: self.exec_(*args, **kwargs)
