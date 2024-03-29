from __future__ import print_function

# Import modules from standard Python (>= 2.4) library
import datetime, sys, io
try:
    import cPickle as pickle
except ImportError:
    import pickle

# Import third-party modules
from .qt_compat import QtGui,QtCore,QtWidgets

# Import our own custom modules
from . import xmlstore,util,datatypes
from .datatypes import unicode

def find_global(module,name):
    import sys
    return getattr(sys.modules[module],name)

def dumps(obj):
    stream = io.BytesIO()
    p = pickle.Pickler(stream,-1)
    #setattr(p,'find_global',find_global)
    p.dump(obj)
    return stream.getvalue()

def loads(self,string):
    stream = io.BytesIO(string)
    p = pickle.Unpickler(stream)
    setattr(p,'find_global',find_global)
    return p.load()

def needCloseButton():
    """Whether to add a close button to Qt4 windows.
    On some platforms the window manager does not provide facilities for
    closing windows, so we have to add a close button to the dialogs.
    """
    return sys.platform!='win32'

# =======================================================================
# Functionality for linking data types to editor classes, and adding
# custom data types.
# =======================================================================

# This will hold the dictionary linking data type names to editor classes.
# It is populated lazily, i.e., when the dictionary is first requested.
editors = None

def getEditors():
    """Returns a dictionary linking data type names to editor classes.
    """
    global editors
    if editors is None:
        editors = {'string'  :StringEditor,
                   'int'     :IntEditor,
                   'float'   :ScientificDoubleEditor,
                   'bool'    :BoolEditor,
                   'datetime':DateTimeEditor,
                   'duration':DurationEditor,
                   'color'   :ColorEditor}
    return editors

def getEditor(name):
    edts = getEditors()
    if name not in edts and name.startswith('array(') and name.endswith(')'):
        # This is an array data type. Build a suitable editor class on the spot.
        basename = name[6:-1]
        baseclass = getEditor(basename)
        if baseclass is None: return None
        valueclass = xmlstore.datatypes.get(name)
        
        # Create a new class for this array type and cache it for future use.
        edts[name] = type('Array'+baseclass.__name__,(ArrayEditor,),{'elementeditorclass':baseclass,'elementname':basename,'valueclass':valueclass})
    return edts.get(name,None)
             
def createEditor(node,parent=None,selectwithradio=False,**kwargs):
    """Returns an editor for the specified TypedStore node, as child of the supplied
    parent QWidget.
    """
    assert isinstance(node,xmlstore.Node), 'First argument to createEditor must be of type node.'
    assert parent is None or isinstance(parent,QtWidgets.QWidget), 'If a parent is supplied to createEditor, it must derive from QWidget.'
    if 'editorclass' in kwargs:
        editorclass = kwargs.pop('editorclass')
    else:
        editorclass = getEditor(node.getValueType())
        assert editorclass is not None, 'No editor available for node of type "%s".' % node.getValueType()
        
    if issubclass(editorclass,AbstractSelectEditor) or not node.templatenode.hasAttribute('hasoptions'):
        editor = editorclass(parent,node,**kwargs)
    else:
        if selectwithradio:
            editor = SelectEditorRadio(parent,node,**kwargs)
        else:
            lineedit = None
            if node.templatenode.hasAttribute('editable'): lineedit = editorclass(parent,node,**kwargs)
            assert lineedit is None or isinstance(lineedit,QtWidgets.QLineEdit), 'Editor class must derive from QLineEdit.'
            editor = SelectEditor(parent,node,lineedit=lineedit,**kwargs)
            
    if editor is not None and hasattr(editor,'separate'):
        editor = PrivateWindowEditor(node,editor,parent)
        
    return editor

def registerEditor(typename,editorclass):
    """Registers an editor class for a user-defined data type.
    """
    assert issubclass(editorclass,AbstractPropertyEditor), 'Custom data editors must derive from xmlstore.AbstractPropertyEditor.'
    getEditors()[typename] = editorclass

class AbstractPropertyEditor(object):
    """Abstract class for editing the value of a node in the TypedStore.
    Methods value and setValue must be implemented by inheriting classes.

    Also, these classes must call onPropertyEditingFinished after the user has changed
    the value in the editor. The moment where this should happen will differ
    between editors: a line edit control should not call it while the user
    is still changing the string - it must therefore call it only after the
    control loses focus. A combobox might call it directly after the currently
    selected item changes.
    """
    def __init__(self,parent,node):
        self.propertyEditingFinished_callbacks = []

    def setValue(self,value):
        pass

    def value(self):
        pass

    def onPropertyEditingFinished(self,*args,**kwargs):
        for callback in self.propertyEditingFinished_callbacks:
            callback(kwargs.get('forceclose', False))

    # Optional (static) methods that classes should implement if the value can
    # be represented by a QtCore.QVariant object.
    @staticmethod
    def convertFromQVariant(value):
        #return value.toPyObject()
        #return loads(value.toString())
        return value

    @staticmethod
    def convertToQVariant(value):
        #return QtCore.QVariant(value)
        #return QtCore.QVariant(dumps(value))
        return value

    @staticmethod
    def displayValue(delegate,painter,option,index):
        QtWidgets.QItemDelegate.paint(delegate,painter,option,index)
        
# =======================================================================
# Functions for converting between Qt date/time object and Python
# datetime objects
# =======================================================================

def qtdatetime2datetime(qtdatetime):
    """Convert Qt QDateTime object to Python datetime object
    """
    qdt = qtdatetime.toUTC()
    d = qdt.date()
    t = qdt.time()
    return datetime.datetime(d.year(),d.month(),d.day(),t.hour(),t.minute(),t.second(),tzinfo=util.getUTC())

def datetime2qtdatetime(dt):
    """Convert Python datetime object to Qt QDateTime object.
    """
    tm = dt.utctimetuple()
    return QtCore.QDateTime(QtCore.QDate(tm.tm_year,tm.tm_mon,tm.tm_mday),QtCore.QTime(tm.tm_hour,tm.tm_min,tm.tm_sec),QtCore.Qt.UTC)

# =======================================================================
# Editors for built-in data types
# =======================================================================

class StringEditor(AbstractPropertyEditor,QtWidgets.QLineEdit):
    """Editor for unicode string.
    """
    def __init__(self,parent,node,**kwargs):
        QtWidgets.QLineEdit.__init__(self,parent)
        AbstractPropertyEditor.__init__(self,parent,node)
        self.editingFinished.connect(self.onPropertyEditingFinished)
        
    def value(self):
        return unicode(QtWidgets.QLineEdit.text(self))

    def setValue(self,value):
        if value is None: value = ''
        QtWidgets.QLineEdit.setText(self,value)

    @staticmethod
    def convertFromQVariant(value):
        return unicode(value)

    @staticmethod
    def convertToQVariant(value):
        return unicode(value)

class IntEditor(AbstractPropertyEditor,QtWidgets.QSpinBox):
    """Editor for integer.
    """
    def __init__(self,parent,node,**kwargs):
        QtWidgets.QSpinBox.__init__(self,parent)
        AbstractPropertyEditor.__init__(self,parent,node)

        templatenode = node.templatenode
        if templatenode.hasAttribute('minInclusive'):
            self.setMinimum(int(templatenode.getAttribute('minInclusive')))
        else:
            self.setMinimum(-2147483648)
        if templatenode.hasAttribute('maxInclusive'):
            self.setMaximum(int(templatenode.getAttribute('maxInclusive')))
        else:
            self.setMaximum(2147483647)
        if kwargs.get('unitinside',False):
            unit = node.getUnit()
            if unit is not None: self.setSuffix(' '+unit)

        self.editingFinished.connect(self.onPropertyEditingFinished)

    def value(self):
        self.interpretText()
        return QtWidgets.QSpinBox.value(self)

    def setValue(self,value):
        if value is not None: QtWidgets.QSpinBox.setValue(self,value)

    @staticmethod
    def convertFromQVariant(value):
        return int(val)

    @staticmethod
    def convertToQVariant(value):
        return int(value)

class AbstractSelectEditor(AbstractPropertyEditor):
    def __init__(self,parent,node):
        AbstractPropertyEditor.__init__(self,parent,node)
        self.node = node

    def getOptions(self):
        options = util.findDescendantNode(self.node.templatenode,['options'])
        assert options is not None, 'Node %s lacks "options" childnode.' % node
        children = []
        ichild = 0
        for ch in options.childNodes:
            if ch.nodeType==ch.ELEMENT_NODE and ch.localName=='option' and ch.getAttribute('disabled')!='True':
                label = ch.getAttribute('label')
                if label=='': label = ch.getAttribute('value')
                children.append((ichild,label,ch.getAttribute('description')))
                ichild += 1
        return children

    def valueFromIndex(self,index):
        ichild = 0
        options = util.findDescendantNode(self.node.templatenode,['options'])
        for ch in options.childNodes:
            if ch.nodeType==ch.ELEMENT_NODE and ch.localName=='option' and ch.getAttribute('disabled')!='True':
                if ichild==index:
                    return self.node.getValueType(returnclass=True).fromXmlString(ch.getAttribute('value'),{},self.node.templatenode)
                ichild += 1
        return None

    def indexFromValue(self,value):
        if value is None: return 0
        ichild = 0
        options = util.findDescendantNode(self.node.templatenode,['options'])
        for ch in options.childNodes:
            if ch.nodeType==ch.ELEMENT_NODE and ch.localName=='option' and ch.getAttribute('disabled')!='True':
                chvalue = self.node.getValueType(returnclass=True).fromXmlString(ch.getAttribute('value'),{},self.node.templatenode)
                if value==chvalue: return ichild
                ichild += 1
        return None

class SelectEditor(AbstractSelectEditor,QtWidgets.QComboBox):
    """Editor for a selection from a list, represented by an integer.
    """
    def __init__(self,parent,node,lineedit=None,**kwargs):
        QtWidgets.QComboBox.__init__(self,parent)
        AbstractSelectEditor.__init__(self,parent,node)
        self.lineedit = lineedit
        if lineedit is not None:
            self.setEditable(True)
            self.setLineEdit(lineedit)
        self.populate(node)
        self.currentIndexChanged.connect(self.onPropertyEditingFinished)

    def populate(self,node):
        for ichild,label,description in self.getOptions():
            self.addItem(label,ichild)

    def value(self):
        icurrentindex = self.currentIndex()
        if self.isEditable() and self.currentText()!=self.itemText(icurrentindex):
            value = self.lineedit.value()
        else:
            ichild = self.itemData(icurrentindex)
            value = self.valueFromIndex(ichild)
            assert value is not None, 'Cannot obtain value for index %i.' % ichild
        return value

    def setValue(self,value):
        ichild = self.indexFromValue(value)
        if ichild is None and self.isEditable():
            self.lineedit.setValue(value)
        else:
            if ichild is None: ichild = 0
            self.setCurrentIndex(ichild)

class SimpleSelectEditor(SelectEditor):
    def getOptionList(self):
        return ()

    def getOptions(self):
        info = self.getOptionInfo()
        if isinstance(info,dict):
            # A dictionary linking values to descriptions was returned
            self.list = list(sorted(info.keys(),key=str.lower))
            return [(i,info[opt],'') for i,opt in enumerate(self.list)]
        else:
            # A list of values was returned
            self.list = info
            return [(i,opt,'') for i,opt in enumerate(self.list)]

    def valueFromIndex(self,index):
        if index<0 or index>=len(self.list): return None
        return self.list[index]

    def indexFromValue(self,value):
        if value is None: return 0
        for i,opt in enumerate(self.list):
            if opt==value: return i
        return None

class SelectEditorRadio(AbstractSelectEditor,QtWidgets.QButtonGroup):
    def __init__(self,parent,node,**kwargs):
        QtWidgets.QButtonGroup.__init__(self,parent)
        AbstractSelectEditor.__init__(self,parent,node)

        for ichild,label,description in self.getOptions():
            opt = QtWidgets.QRadioButton(label,parent)
            if description!='':
                opt.setWhatsThis(description)
            self.addButton(opt,ichild)
        self.buttonClicked.connect(self.onPropertyEditingFinished)

    def value(self):
        return self.valueFromIndex(self.checkedId())

    def setValue(self,value):
        ichild = self.indexFromValue(value)
        if ichild is None: ichild=0
        self.button(ichild).setChecked(True)

    def buttonFromValue(self,value):
        return self.button(self.indexFromValue(value))

class BoolEditor(AbstractPropertyEditor,QtWidgets.QComboBox):
    """Editor for a boolean value.
    """
    def __init__(self,parent,node,**kwargs):
        QtWidgets.QComboBox.__init__(self,parent)
        AbstractPropertyEditor.__init__(self,parent,node)
        self.addItem('Yes',True)
        self.addItem('No', False)
        self.currentIndexChanged.connect(self.onPropertyEditingFinished)

    def value(self):
        return bool(self.itemData(self.currentIndex()))

    def setValue(self,value):
        if value is None: value = True
        for ioption in range(self.count()):
            optionvalue = bool(self.itemData(ioption))
            if optionvalue==value:
                self.setCurrentIndex(ioption)
                break

    @staticmethod
    def convertFromQVariant(value):
        return bool(value)

    @staticmethod
    def convertToQVariant(value):
        return bool(value)

class DateTimeEditor(AbstractPropertyEditor,QtWidgets.QDateTimeEdit):
    """Editor for a datetime object.
    """
    def __init__(self,parent,node,**kwargs):
        QtWidgets.QDateTimeEdit.__init__(self,parent)
        AbstractPropertyEditor.__init__(self,parent,node)
        self.editingFinished.connect(self.onPropertyEditingFinished)

    def value(self):
        value = self.dateTime()
        value.setTimeSpec(QtCore.Qt.UTC)
        return qtdatetime2datetime(value)

    def setValue(self,value):
        if value is None:
            value = QtCore.QDateTime()
        else:
            value = datetime2qtdatetime(value)
        self.setDateTime(value)

    @staticmethod
    def convertFromQVariant(value):
        return qtdatetime2datetime(value)

    @staticmethod
    def convertToQVariant(value):
        assert isinstance(value,datetime.datetime), 'Supplied object is not of class datetime.datetime.'
        return datetime2qtdatetime(value)

class DurationEditor(AbstractPropertyEditor,QtWidgets.QWidget):
    """Editor for a duration (time span).
    """
    def __init__(self,parent,node,**kwargs):
        QtWidgets.QWidget.__init__(self, parent)
        AbstractPropertyEditor.__init__(self, parent, node)

        lo = QtWidgets.QHBoxLayout()

        self.spinValue = QtWidgets.QDoubleSpinBox(self)
        self.spinValue.setMinimum(0.)

        self.comboUnits = QtWidgets.QComboBox(self)
        self.comboUnits.addItems(['seconds','minutes','hours','days'])

        lo.addWidget(self.spinValue)
        lo.addWidget(self.comboUnits)

        lo.setContentsMargins(0,0,0,0)

        self.spinValue.editingFinished.connect(self.onPropertyEditingFinished)
        self.comboUnits.currentIndexChanged.connect(self.onUnitChange)

        self.setLayout(lo)

    def setValue(self,delta=None):
        if delta is None: delta = datatypes.TimeDelta()
        seconds = delta.seconds + delta.microseconds/1000000.
        if delta.days>0:
            self.comboUnits.setCurrentIndex(3)
            self.spinValue.setValue(delta.days+seconds/86400.)
        elif delta.seconds>=3600:
            self.comboUnits.setCurrentIndex(2)
            self.spinValue.setValue(seconds/3600)
        elif delta.seconds>=60:
            self.comboUnits.setCurrentIndex(1)
            self.spinValue.setValue(seconds/60)
        else:
            self.comboUnits.setCurrentIndex(0)
            self.spinValue.setValue(seconds)

    def value(self):
        unit = self.comboUnits.currentIndex()
        if   unit==0:
            return datatypes.TimeDelta(seconds=self.spinValue.value())
        elif unit==1:
            return datatypes.TimeDelta(seconds=self.spinValue.value()*60)
        elif unit==2:
            return datatypes.TimeDelta(seconds=self.spinValue.value()*3600)
        elif unit==3:
            return datatypes.TimeDelta(days=self.spinValue.value())

    def onUnitChange(self,unit):
        if   unit==0:
            self.spinValue.setMaximum(60.)
        elif unit==1:
            self.spinValue.setMaximum(60.)
        elif unit==2:
            self.spinValue.setMaximum(24.)
        elif unit==3:
            self.spinValue.setMaximum(3650.)
        self.onPropertyEditingFinished()

    @staticmethod
    def convertFromQVariant(value):
        days,secs,musecs = value
        return datatypes.TimeDelta(days=days,seconds=secs,microseconds=musecs)

    @staticmethod
    def convertToQVariant(value):
        return [int(value.days),int(value.seconds),float(value.microseconds)]

class ScientificDoubleValidator(QtGui.QValidator):
    """Qt validator for floating point values
    Less strict than the standard QDoubleValidator, in the sense that is
    also accepts values in scientific format (e.g. 1.2e6)
    Also has properties 'minimum' and 'maximum', used for validation and
    fix-up.
    """
    def __init__(self,parent=None):
        QtGui.QValidator.__init__(self,parent)
        self.minimum = None
        self.maximum = None
        self.suffix = ''

    def validate(self,input,pos):
        assert isinstance(input, (str, u''.__class__)),'input argument is not a string (old PyQt4 API?)'

        # Check for suffix (if ok, cut it off for further value checking)
        if not input.endswith(self.suffix): return (QtGui.QValidator.Invalid,input,pos)
        vallength = len(input)-len(self.suffix)

        # Check for invalid characters
        rx = QtCore.QRegExp('[^\d\-+eE,.]')
        if rx.indexIn(input[:vallength])!=-1: return (QtGui.QValidator.Invalid,input,pos)

        # Check if we can convert it into a floating point value
        try:
            v = float(input[:vallength])
        except ValueError:
            return (QtGui.QValidator.Intermediate,input,pos)

        # Check for minimum and maximum.
        if self.minimum is not None and v<self.minimum: return (QtGui.QValidator.Intermediate,input,pos)
        if self.maximum is not None and v>self.maximum: return (QtGui.QValidator.Intermediate,input,pos)

        return (QtGui.QValidator.Acceptable,input,pos)

    def fixup(self,input):
        assert isinstance(input, (str, u''.__class__)),'input argument is not a string (old PyQt4 API?)'
        if not input.endswith(self.suffix): return input

        try:
            v = float(input[:len(input)-len(self.suffix)])
        except ValueError:
            return input

        if self.minimum is not None and v<self.minimum: input = u'%s%s' % (self.minimum,self.suffix)
        if self.maximum is not None and v>self.maximum: input = u'%s%s' % (self.maximum,self.suffix)
        return input

    def setSuffix(self,suffix):
        self.suffix = suffix

class ScientificDoubleEditor(AbstractPropertyEditor,QtWidgets.QLineEdit):
    """Editor for a floating point value.
    """
    def __init__(self,parent,node=None,**kwargs):
        QtWidgets.QLineEdit.__init__(self,parent)
        AbstractPropertyEditor.__init__(self, parent, node)

        self.curvalidator = ScientificDoubleValidator(self)
        self.setValidator(self.curvalidator)
        self.suffix = ''
        self.editingFinished.connect(self.onPropertyEditingFinished)

        if node is not None:
            templatenode = node.templatenode        
            if templatenode.hasAttribute('minInclusive'):
                self.setMinimum(float(templatenode.getAttribute('minInclusive')))
            if templatenode.hasAttribute('maxInclusive'):
                self.setMaximum(float(templatenode.getAttribute('maxInclusive')))
            if kwargs.get('unitinside',False):
                unit = node.getUnit()
                if unit is not None: self.setSuffix(' '+unit)

    def setSuffix(self,suffix):
        value = self.value()
        self.suffix = suffix
        self.curvalidator.setSuffix(suffix)
        self.setValue(value)

    def value(self):
        text = self.text()
        text = text[:len(text)-len(self.suffix)]
        if text=='': return 0
        return float(text)

    def setValue(self,value,format=None):
        if value is None:
            strvalue = ''
        else:  
            if format is None:
                strvalue = unicode(value)
            else:
                strvalue = format % value
        self.setText(strvalue+self.suffix)

    def focusInEvent(self,e):
        QtWidgets.QLineEdit.focusInEvent(self,e)
        self.selectAll()

    def selectAll(self):
        QtWidgets.QLineEdit.setSelection(self,0,len(self.text())-len(self.suffix))

    def setMinimum(self,minimum):
        self.curvalidator.minimum = minimum

    def setMaximum(self,maximum):
        self.curvalidator.maximum = maximum

    def interpretText(self):
        if not self.hasAcceptableInput():
            text = self.text()
            textnew = self.curvalidator.fixup(text)
            if textnew is None: textnew = text
            self.setText(textnew)

    @staticmethod
    def convertFromQVariant(value):
        return float(val)

    @staticmethod
    def convertToQVariant(value):
        return float(value)

class ColorEditor(AbstractPropertyEditor,QtWidgets.QComboBox):
    """Editor for a color. Allows selection from a list of predefined colors,
    or defining a custom color via the last entry in the list.
    """
    def __init__(self,parent,node=None,**kwargs):
        QtWidgets.QComboBox.__init__(self,parent)
        AbstractPropertyEditor.__init__(self, parent, node)

        self.activated.connect(self.onActivated)
        self.allownone = (node is not None and node.templatenode.getAttribute('allownone')) or (node is None and kwargs.get('allownone',False))
        if self.allownone:
            # add none option
            self.addColor('none')
        for cn in QtGui.QColor.colorNames():
            c = QtGui.QColor(cn)
            if c.alpha()<255: continue
            self.addColor(cn,c)
        self.addColor('custom...',QtGui.QColor(255,255,255))
        self.currentIndexChanged.connect(self.onPropertyEditingFinished)

    def setValue(self,value):
        if not value.isValid():
            assert self.allownone, 'An value of none was specified, but this color must have a value.'
            self.setCurrentIndex(0)
            return

        # If the value is missing, default to white
        if value is None: value = datatypes.Color(255,255,255)

        qcolor = QtGui.QColor(value.red,value.green,value.blue)
        for i in range(self.count()-1):
            if QtGui.QColor(self.itemData(i))==qcolor:
                self.setCurrentIndex(i)
                break
        else:
            index = self.count()-1
            self.setItemColor(index,qcolor)
            self.setCurrentIndex(index)

    def value(self):
        return self.convertFromQVariant(self.itemData(self.currentIndex()))

    def onActivated(self,index):
        if index==self.count()-1:
            col = QtWidgets.QColorDialog.getColor(QtGui.QColor(self.itemData(index)),self)
            self.setItemColor(index,col)
            self.onPropertyEditingFinished()

    def addColor(self,text,color=None):
        if color is None:
            self.addItem(text)
        else:
            iconsize = self.iconSize()
            qPixMap = ColorEditor.createPixmap(color,iconsize.width()-2,iconsize.height()-2)
            self.addItem(QtGui.QIcon(qPixMap),text,color)

    def setItemColor(self,index,color):
        iconsize = self.iconSize()
        qPixMap = ColorEditor.createPixmap(color,iconsize.width()-2,iconsize.height()-2)
        self.setItemIcon(index,QtGui.QIcon(qPixMap))
        self.setItemData(index,color)

    @staticmethod
    def createPixmap(color,width,height):
        qPixMap = QtGui.QPixmap(width,height)
        qPixMap.fill(color)

        # Add border
        p = QtGui.QPainter(qPixMap)
        penwidth = p.pen().width()
        if penwidth==0: penwidth=1
        p.drawRect(QtCore.QRectF(0,0,width-penwidth,height-penwidth))

        return qPixMap

    @staticmethod
    def convertFromQVariant(value):
        if value is None: return datatypes.Color()
        col = QtGui.QColor(value)
        return datatypes.Color(col.red(),col.green(),col.blue())

    @staticmethod
    def convertToQVariant(value):
        if value.red is None or value.green is None or value.blue is None: return None
        return QtGui.QColor(value.red,value.green,value.blue)

    @staticmethod
    def displayValue(delegate,painter,option,index):
        value = index.data(QtCore.Qt.EditRole)
        if not value.isValid(): return QtWidgets.QItemDelegate.paint(delegate,painter,option,index)
        value = QtGui.QColor(value)

        # Get the rectangle to fill
        style = QtWidgets.qApp.style()
        xOffset = style.pixelMetric(QtWidgets.QStyle.PM_FocusFrameHMargin,option)
        yOffset = style.pixelMetric(QtWidgets.QStyle.PM_FocusFrameVMargin,option)
        rect = option.rect.adjusted(xOffset,yOffset,-xOffset,-yOffset)
        rect.setWidth(rect.height())

        qPixMap = ColorEditor.createPixmap(value,rect.width(),rect.height())
        option.decorationAlignment = QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter
        delegate.drawBackground(painter,option,index)
        delegate.drawDecoration(painter,option,rect,qPixMap)
        delegate.drawFocus(painter,option,option.rect)

    color2name = None
    @staticmethod
    def valueToString(value):
        if value.red is None or value.green is None or value.blue is None: return 'none'
        if ColorEditor.color2name is None:
            ColorEditor.color2name = {}
            for cn in reversed(QtGui.QColor.colorNames()):
                c = QtGui.QColor(cn)
                if c.alpha()<255: continue
                ColorEditor.color2name[(c.red(),c.green(),c.blue())] = cn
        coltup = (value.red,value.green,value.blue)
        return ColorEditor.color2name.get(coltup,'custom')

class PrivateWindowEditor(AbstractPropertyEditor,QtWidgets.QWidget):
    def __init__(self,node,editor,parent=None):
        QtWidgets.QWidget.__init__(self,parent)
        AbstractPropertyEditor.__init__(self, parent, node)

        self.node = node
        self.editor = editor

    def setValue(self,value=None):
        return self.editor.setValue(value)

    def value(self):
        return self.editor.value()

    def showEvent(self,ev):
        dialog = QtWidgets.QDialog(self,QtCore.Qt.Tool)
        dialog.setWindowTitle(self.node.getText(detail=1))
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(self.editor)
        dialog.setLayout(layout)

        ret = dialog.exec_()
        self.onPropertyEditingFinished(forceclose=True)
        dialog.destroy()

class StringWithImageEditor(AbstractPropertyEditor,QtWidgets.QComboBox):
    """Widget for selecting an image, represented internally by a string.
    """
    class Delegate(QtWidgets.QItemDelegate):
        def __init__(self,parent):
            QtWidgets.QItemDelegate.__init__(self,parent)
            self.owner = parent

        def paint(self,painter,option,index):
            self.owner.displayValue(self,painter,option,index)

        def sizeHint(self,option,index):
            h = max(option.fontMetrics.height(),self.owner.height)
            w = self.owner.width+2*QtWidgets.QStyle.PM_FocusFrameHMargin
            #if label: w += option.fontMetrics.width(label)+2*QtWidgets.QStyle.PM_FocusFrameHMargin
            return QtCore.QSize(w,h)

    class Model(QtCore.QAbstractListModel):
        def __init__(self,parent):
            QtCore.QAbstractListModel.__init__(self,parent)
            self.owner = parent

        def rowCount(self,parent):
            if parent.isValid(): return 0
            return len(self.owner.items)

        def data(self,index,role):
            irow = index.row()
            name = self.owner.items[irow]
            if role==QtCore.Qt.DecorationRole:
                pixmap = self.owner.getPixMap(name,self.owner.width,self.owner.height,self.owner.logicalDpiX())
                if pixmap: return pixmap
            elif role==QtCore.Qt.DisplayRole:
                label = self.owner.getLabel(name)
                if label: return label
            elif role==QtCore.Qt.EditRole:
                return name
            return None

    def __init__(self,parent,node,items,**kwargs):
        QtWidgets.QComboBox.__init__(self,parent)
        AbstractPropertyEditor.__init__(self,parent,node)

        self.items = items

        self.delegate = StringWithImageEditor.Delegate(self)
        self.setItemDelegate(self.delegate)

        self.model = StringWithImageEditor.Model(self)
        self.setModel(self.model)

        self.currentIndexChanged.connect(self.onPropertyEditingFinished)
        self.setIconSize(QtCore.QSize(self.width,self.height))
        #self.view().setUniformItemSizes(True)  # Commented out because returned QAbstractItemView does not have setUniformItemSizes

    def value(self):
        return self.items[self.currentIndex()]

    def setValue(self,value):
        for i in range(self.count()):
            if self.items[i]==value:
                self.setCurrentIndex(i)
                break

    @classmethod
    def getPixMap(cls,value,width,height,dpi):
        if not hasattr(cls,'cache'): cls.cache = {}
        qPixMap = cls.cache.get(value,None)
        if qPixMap is None or qPixMap.width()!=width or qPixMap.height()!=height:
            qPixMap = cls.createPixMap(value,width,height,dpi)
            cls.cache[value] = qPixMap
        return qPixMap

    @classmethod
    def getLabel(cls,name):
        return name

    @classmethod
    def displayValue(cls,delegate,painter,option,index):
        value = cls.convertFromQVariant(index.data(QtCore.Qt.EditRole))
        rect = option.rect
        dpi = painter.device().logicalDpiX()
        #dpi = option.widget.logicalDpiX()
        qPixMap = cls.getPixMap(value,cls.width,cls.height,dpi)
        if qPixMap:
            option.decorationAlignment = QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter
            delegate.drawBackground(painter,option,index)
            xOffset = QtWidgets.qApp.style().pixelMetric(QtWidgets.QStyle.PM_FocusFrameHMargin,option)
            delegate.drawDecoration(painter,option,rect.adjusted(xOffset,0,0,0),qPixMap)
            rect = rect.adjusted(xOffset*2+qPixMap.width(),0,0,0)
        label = cls.getLabel(value)
        if label:
            delegate.drawDisplay(painter,option,rect,label)
        delegate.drawFocus(painter,option,option.rect)

    @staticmethod
    def convertFromQVariant(value):
        return StringEditor.convertFromQVariant(value)

    @staticmethod
    def convertToQVariant(value):
        return StringEditor.convertToQVariant(value)

# =======================================================================
# PropertyDelegate: a Qt delegate used to create editors for property
# values.
# =======================================================================

class PropertyDelegate(QtWidgets.QItemDelegate):
    """a Qt delegate used to create editors for property values.
    Built to handle properties from our custom TypedStore,
    which stores typed properties in hierarchical structure (XML)
    The internalPointer attribute of provided model indices must refer
    to a node in the TypedStore.
    """

    def __init__(self,parent=None,**kwargs):
        super(PropertyDelegate,self).__init__(parent)
        self.properties = dict(kwargs.items())

    def createEditor(self, parent, option, index):
        """Creates the editor widget for the model item at the given index.
        Inherited from QtWidgets.QItemDelegate.
        """
        node = index.internalPointer()

        editor = createEditor(node,parent,**self.properties)

        lo = editor.layout()
        if lo is not None:
            lo.setContentsMargins(0,0,0,0)
            lo.setSpacing(0)

        # Install event filter that captures key events for view from the editor (e.g. return press).
        editor.installEventFilter(self)
        editor.propertyEditingFinished_callbacks.append(self.editingFinished)

        return editor

    def editingFinished(self,forceclose):
        if not forceclose: return
        editor = self.sender()
        self.commitData.emit(editor)
        self.closeEditor.emit(editor,QtWidgets.QAbstractItemDelegate.NoHint)

    def paint(self,painter,option,index):
        """Paints the current value for display (not editing!)
        Inherited from QtWidgets.QItemDelegate.
        """
        node = index.internalPointer()
        if index.column()==1 and node.canHaveValue():
            fieldtype = node.getValueType()
            editorclass = getEditor(fieldtype)
            if editorclass is None: editorclass = AbstractPropertyEditor
            editorclass.displayValue(self,painter,option,index)
        else:
            QtWidgets.QItemDelegate.paint(self,painter,option,index)

    def setEditorData(self, editor,index):
        """Sets value in the editor widget, for the model item at the given index.
        Inherited from QtWidgets.QItemDelegate.
        """
        node = index.internalPointer()
        value = node.getValue(usedefault=True)
        editor.setValue(value)
        if isinstance(value,util.referencedobject): value.release()

    def setModelData(self, editor, model, index):
        """Obtains the value from the editor widget, and set it for the model item
        at the given index.
        Inherited from QtWidgets.QItemDelegate.
        """
        node = index.internalPointer()
        value = editor.value()
        node.setValue(value)
        if isinstance(value,util.referencedobject): value.release()

        # Below we clean up the editor ourselves. Qt would normally take
        # care of that, but for our own editors that live partially in
        # Python the Qt4/PyQt4 destructor fails to call the Python destroy.
        # That would disable clean-up, so we do it here explicitly.
        editor.hide()
        editor.destroy()

class ArrayEditor(AbstractPropertyEditor,QtWidgets.QTableView):
    separate = True

    class Delegate(PropertyDelegate):
        """Property delegate that uses the official index.data() to obtain
        the current value, and model.setData(index,value) to set the value.
        
        This works only for data types that support conversion to/from QVariant,
        which excludes generic Python objects in PyQt <4.5.
        
        When we can safely expect the user base to use PyQt4 >=4.5, we can insert
        the overridden methods in this class into the original PropertyDelegate.
        """
        
        def setEditorData(self, editor,index):
            value = index.data(QtCore.Qt.EditRole)
            if value.isValid():
                value = self.properties['editorclass'].convertFromQVariant(value)
            else:
                value = None
            editor.setValue(value)
            if isinstance(value,util.referencedobject): value.release()

        def setModelData(self, editor, model, index):
            value = editor.value()
            if value is not None:
                value = self.properties['editorclass'].convertToQVariant(value)
            model.setData(index,value)
            if isinstance(value,util.referencedobject): value.release()
                
            # Below we clean up the editor ourselves. Qt would normally take
            # care of that, but for our own editors that live partially in
            # Python the Qt4/PyQt4 destructor fails to call the Python destroy.
            # That would disable clean-up, so we do it here explicitly.
            editor.hide()
            editor.destroy()      

        def paint(self,painter,option,index):
            self.properties['editorclass'].displayValue(self,painter,option,index)
        
    class Model(QtCore.QAbstractItemModel):
        def __init__(self,shape,data,node,editorclass):
            QtCore.QAbstractItemModel.__init__(self)
            if data is None: data = []
            def convert(arr):
                res = []
                for e in arr:
                    if isinstance(e,(list,tuple)):
                        e = convert(e)
                    elif e is xmlstore.datatypes.DataTypeArray.empty:
                        e = None
                    res.append(e)
                return res
            self.shape = shape
            self.arraydata = convert(data)
            self.editorclass = editorclass
            self.node = node
            
        def getDataMatrix(self):
            nrow,ncol,hascolumns = None,None,False
            if self.shape is not None:
                if len(self.shape)>0 and self.shape[0] is not None: nrow = self.shape[0]
                hascolumns = len(self.shape)>1
                if hascolumns and self.shape[1] is not None: ncol = self.shape[1]
            
            if nrow is None:
                # Count the number of rows (ignore trailing missing values)
                nrow = len(self.arraydata)
                for rowdata in reversed(self.arraydata):
                    if rowdata is not None: break
                    nrow -= 1
                    
            if hascolumns and ncol is None:
                # Count the number of columns (ignore trailing missing values)
                ncol = 0
                for rowdata in self.arraydata[:nrow]:
                    if rowdata is None or len(rowdata)<=ncol: continue
                    curncol = len(rowdata)
                    for coldata in reversed(rowdata):
                        if coldata is not None: break
                        curncol -= 1
                    ncol = max(ncol,curncol)
                
            if not hascolumns:
                # Take all rows except trailing missing values.
                data = self.arraydata[:nrow]
            else:
                # Make sure each row has the desired number of columns, then
                # return all except trailing missing values.
                data = []
                for rowdata in self.arraydata[:nrow]:
                    if len(rowdata)<ncol:
                        rowdata = list(rowdata)
                        rowdata += [None]*(ncol-len(rowdata))
                    data.append(rowdata[:ncol])
                    
            return data
            
        def index(self,irow,icolumn,parent=None):
            if parent is None: parent = QtCore.QModelIndex()
            assert not parent.isValid(), 'Only the root can have child nodes.'
            return self.createIndex(irow,icolumn,self.node)

        def parent(self,index):
            return QtCore.QModelIndex()
            
        def rowCount(self,parent=None):
            if parent is None: parent = QtCore.QModelIndex()
            
            # Only the root node has children - return 0 rows if this is not the root.
            if parent.isValid(): return 0
            
            l = self.shape[0]
            if l is None: l = 256*256
            return l

        def columnCount(self,parent=None):
            if parent is None: parent = QtCore.QModelIndex()

            # Only the root node has children - return 0 rows if this is not the root.
            if parent.isValid(): return 0
            if len(self.shape)==1: return 1
            
            l = self.shape[1]
            if l is None: l = 256*256
            return l
            
        def headerData(self,section,orientation,role):
            # Only process display role.
            if role!=QtCore.Qt.DisplayRole:
                return QtCore.QAbstractItemModel.headerData(self,section,orientation,role)
                
            if orientation==QtCore.Qt.Horizontal:
                # Use Excel-style column names (A-Z, AA-ZZ, AAA-ZZZ, ...).
                string = ''
                quot = section
                while True:
                    quot,rem = divmod(quot,26)
                    string = chr(ord('A')+rem)+string
                    if quot==0: break
                    quot -= 1
                return string
            else:
                # Use row number (1-based) as row name.
                return str(section+1)

        def data(self,index,role=QtCore.Qt.DisplayRole):
            if role==QtCore.Qt.DisplayRole or role==QtCore.Qt.EditRole:
                irow = index.row()
                val = None
                if irow<len(self.arraydata):
                    val = self.arraydata[irow]
                    if len(self.shape)>1:
                        icol = index.column()
                        if val is not None and icol<len(val):
                            val = val[icol]
                if val is None: return None
                if role==QtCore.Qt.DisplayRole:
                    cls = self.node.getValueType(returnclass=True).elementclass
                    if not isinstance(val,cls): val = cls(val)
                    return val.toPrettyString()
                return self.editorclass.convertToQVariant(val)
                
            return None
            
        def clearData(self,index):
            self.setData(index,None)
            
        def setData(self,index,value,role=QtCore.Qt.EditRole):
            # Only process edit role
            if role!=QtCore.Qt.EditRole: return False
            
            # Get value in native data type (convert from QVariant)
            if not value.isValid():
                value = None
            else:
                value = self.editorclass.convertFromQVariant(value)
                
            # Get row index
            irow = index.row()
            
            # Append additional rows if needed
            if irow>=len(self.arraydata):
                if value is None: return True
                self.arraydata += [None]*(irow-len(self.arraydata)+1)
                
            if len(self.shape)>1:
                # 2D array
                icol = index.column()
                
                # Make sure the specified row exists and has the desired length.
                if self.arraydata[irow] is None: self.arraydata[irow] = []
                if icol>=len(self.arraydata[irow]):
                    if value is None: return True
                    self.arraydata[irow] += [None]*(icol-len(self.arraydata[irow])+1)
                    
                self.arraydata[irow][icol] = value
            else:
                # 1D array
                self.arraydata[irow] = value
                
            # Notify that data have changed.
            self.dataChanged.emit(index,index)
            
            # Return True (data successfully set)
            return True

        def flags(self,index):
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable

    def __init__(self,parent,node,**kwargs):
        QtWidgets.QTableView.__init__(self,parent)
        AbstractPropertyEditor.__init__(self, parent, node)
        self.setItemDelegate(self.Delegate(self,editorclass=self.elementeditorclass,**kwargs))
        self.node = node
        self.datamodel = None

    def keyPressEvent(self,event):
        if event.key()==QtCore.Qt.Key_Delete:
            for ind in self.selectionModel().selectedIndexes():
                self.datamodel.clearData(ind)
        else:
            QtWidgets.QTableView.keyPressEvent(self,event)

    def value(self):
        return self.datamodel.getDataMatrix()

    def setValue(self,value=None):
        strshape = self.node.templatenode.getAttribute('shape')
        shape = None
        if strshape!='':
            shape = []
            for l in strshape.split(','):
                if l==':':
                    shape.append(None)
                else:
                    shape.append(int(l))

        self.datamodel = self.Model(shape,value,self.node,self.elementeditorclass)
        #self.horizontalHeader().setVisible(len(shape)>1)
        self.setModel(self.datamodel)
        
# =======================================================================
# TypedStoreModel: a Qt item model that encapsulates TypedStore
# =======================================================================

class TypedStoreModel(QtCore.QAbstractItemModel):
    """Qt item model that encapsulates TypedStore, used for hierarchical storage
    of typed properties.
    """
    
    def __init__(self,typedstore,nohide = False, novalues = False, checkboxes = False):
        QtCore.QAbstractItemModel.__init__(self)

        self.typedstore = typedstore
        self.nohide = nohide
        self.novalues = novalues
        self.checkboxes = checkboxes

        self.storeinterface = self.typedstore.getInterface(showhidden=self.nohide,omitgroupers=True)
        self.storeinterface.processDefaultChange = 1    # Warn always if a default changes (even if it is not used)

        self.storeinterface.connect('beforeVisibilityChange',self.beforeNodeVisibilityChange)
        self.storeinterface.connect('afterVisibilityChange', self.afterNodeVisibilityChange)
        self.storeinterface.connect('afterChange',self.onNodeChanged)
        self.storeinterface.connect('beforeStoreChange',self.beginResetModel)
        self.storeinterface.connect('afterStoreChange',self.endResetModel)

        self.inheritingchecks = False
        
        # For debugging: model test functionality
        #import modeltest
        #self.mt = modeltest.ModelTest(self,self)
        
    def unlink(self):
        self.typedstore.disconnectInterface(self.storeinterface)
        self.storeinterface = None
        
    def index(self,irow,icolumn,parent):
        """Supplies unique index for the node at the given (row,column) position
        below the given parent (specified as index).
        inherited from QtCore.QAbstractItemModel
        """
        # Check whether row and column indices are valid.
        if irow<0 or icolumn<0 or icolumn>1: return QtCore.QModelIndex()

        # Obtain the parent node        
        if not parent.isValid():
            parentnode = self.typedstore.root
        else:
            parentnode = parent.internalPointer()
            
        # Get the child at the specified row index
        child = self.storeinterface.getChildByIndex(parentnode,irow)
        if child is None: return QtCore.QModelIndex()
        assert isinstance(child,xmlstore.Node), 'Object returned by getChildByIndex is not of type "Node" (but "%s").' % child

        # Return a newly created index for the child node.
        return self.createIndex(irow,icolumn,child)

    def parent(self,index):
        """Supplies unique index for the parent of the given node (specified as index).
        inherited from QtCore.QAbstractItemModel
        """
        # We must have a valid index.
        if not index.isValid(): return QtCore.QModelIndex()

        # Get the node belonging to the provided index.
        current = index.internalPointer()
        assert isinstance(current,xmlstore.Node), 'Node data is not a Node, but: %s.' % current
        
        # Get the parent node.
        parent = self.storeinterface.getParent(current)
        assert isinstance(parent,xmlstore.Node), 'Object returned by getParent is not of type "Node" (but "%s").' % (parent,)

        # If we reached the root, return an invalid index signifying the root.        
        if parent.parent is None: return QtCore.QModelIndex()

        # Get the row index of the parent.
        iparentrow = self.storeinterface.getOwnIndex(parent)
        
        # Return a newly created index for the parent.
        return self.createIndex(iparentrow,0,parent)

    def rowCount(self,parent=QtCore.QModelIndex()):
        """Returns the number of child rows below the given parent (specified as index).
        inherited from QtCore.QAbstractItemModel
        """
        if not parent.isValid():
            parentnode = self.typedstore.root
        else:
            if parent.column()!=0: return 0
            parentnode = parent.internalPointer()
        return self.storeinterface.getChildCount(parentnode)

    def columnCount(self,parent):
        """Returns the number of child columns below the given parent (specified as index).
        inherited from QtCore.QAbstractItemModel
        """
        if self.novalues:
            return 1
        else:
            return 2

    def data(self,index,role=QtCore.Qt.DisplayRole):
        """Returns data for the given node (specified as index), and the given role.
        inherited from QtCore.QAbstractItemModel
        """

        # In some cases (e.g. when using What's-this) this function is called for the root node
        # (i.e. with an invalid index). In that case we just return the default data value.
        if not index.isValid(): return None
        
        # Shortcut to the xmlstore.TypedStore node (used below in many places)
        node = index.internalPointer()

        # First handle roles that are shared over the whole row.
        if role==QtCore.Qt.WhatsThisRole:
            templatenode = node.templatenode
            text = node.getText(detail=2)
            nodetype = node.getValueType()
            if templatenode.hasAttribute('hasoptions'):
                optionsroot = util.findDescendantNode(templatenode,['options'])
                assert optionsroot is not None, 'Variable with "select" type lacks "options" element below.'
                optionnodes = util.findDescendantNodes(optionsroot,['option'])
                assert len(optionnodes)>0, 'Variable with "select" type does not have any options assigned to it.'
                text += '\n\nAvailable options:'
                for optionnode in optionnodes:
                    if optionnode.getAttribute('disabled')=='True': continue
                    text += '\n- '
                    if optionnode.hasAttribute('description'):
                        text += optionnode.getAttribute('description')
                    else:
                        text += optionnode.getAttribute('label')
            elif nodetype=='int' or nodetype=='float':
                if templatenode.hasAttribute('minInclusive'): text += '\nminimum value: '+templatenode.getAttribute('minInclusive')
                if templatenode.hasAttribute('maxInclusive'): text += '\nmaximum value: '+templatenode.getAttribute('maxInclusive')
            return text
        elif role==QtCore.Qt.TextColorRole:
            if self.nohide and not node.visible:
                # If we should show hidden nodes too, color them blue to differentiate.
                return QtGui.QColor(0,0,255)
            elif index.column()==1 and node.isReadOnly():
                # Color read-only nodes grey to differentiate.
                return QtGui.QColor(128,128,128)
        elif self.checkboxes and role==QtCore.Qt.CheckStateRole:
            if node.canHaveValue():
                # Node has own checkbox.
                if node.getValue():
                    return QtCore.Qt.Checked
                else:
                    return QtCore.Qt.Unchecked
            elif node.hasChildren():
                # Node is parent of other nodes with their own checkbox; check value is derived from children.
                state = None
                for i in range(self.rowCount(index)):
                    chstate = index.child(i,0).data(QtCore.Qt.CheckStateRole)
                    if chstate==QtCore.Qt.PartiallyChecked:
                        return QtCore.Qt.PartiallyChecked
                    elif state is None:
                        state = chstate
                    elif chstate!=state:
                        return QtCore.Qt.PartiallyChecked
                return state

        # Now handle column-specific roles.
        if index.column()==0:
            if role==QtCore.Qt.DisplayRole:
                return node.getText(detail=1)
            else:
                return None
        else:
            # We only process the 'display', 'decoration', 'edit' and 'font' roles.
            if role not in (QtCore.Qt.DisplayRole,QtCore.Qt.EditRole,QtCore.Qt.FontRole): return None

            # Column 1 is only used for variables that can have a value.
            if not node.canHaveValue(): return None

            fieldtype = node.getValueType()
            if role==QtCore.Qt.FontRole:
                # Return bold font if the node value is set to something different than the default.
                if self.typedstore.defaultstore is None: return None
                font = QtGui.QFont()
                font.setBold(not node.hasDefaultValue())
                return font
            elif role==QtCore.Qt.DisplayRole:
                return node.getValueAsString(usedefault=True)
            elif role==QtCore.Qt.EditRole:
                value = node.getValue(usedefault=True)
                if value is None: return None
                editorclass = getEditor(fieldtype)
                assert editorclass is not None, 'No editor class defined for data type "%s".' % fieldtype
                result = editorclass.convertToQVariant(value)
                #if isinstance(value,util.referencedobject): value.release()
                return result
            else:
                assert False, 'Don\'t know how to handle role %s.' % role

    def setData(self,index,value,role=QtCore.Qt.EditRole):
        """Set data for the given node (specified as index), and the given role.
        inherited from QtCore.QAbstractItemModel
        """
        # Get node (XML element) from given node index (QtCore.QModelIndex)
        node = index.internalPointer()

        # Handle the case where nodes have checkboxes, and the check state changed.
        if self.checkboxes and role==QtCore.Qt.CheckStateRole:
            if node.canHaveValue():
                node.setValue(value)
                self.dataChanged.emit(index,index)
            elif node.hasChildren():
                checkroot = (not self.inheritingchecks)
                self.inheritingchecks = True
                for i in range(self.rowCount(index)):
                    self.setData(index.child(i,0),value,role=QtCore.Qt.CheckStateRole)
                self.dataChanged.emit(index,index)
                if checkroot: self.inheritingchecks = False
            if not self.inheritingchecks:
                par = index.parent()
                while par.isValid():
                    self.dataChanged.emit(par,par)
                    par = par.parent()
            return True

        # From this point on, we only process the EditRole for column 1.
        if role!=QtCore.Qt.EditRole or index.column()!=1: return False

        if not value.isValid():
            # An invalid QVariant was passed: clear the node value.
            node.clearValue()
        else:
            # Convert the supplied QVariant to the node data type,
            # set the node value, and release the value object if applicable.
            fieldtype = node.getValueType()
            editorclass = getEditor(fieldtype)
            assert editorclass is not None, 'No editor class defined for data type "%s".' % fieldtype
            value = editorclass.convertFromQVariant(value)
            node.setValue(value)
            if isinstance(value,util.referencedobject): value.release()

        # Emit the data-changed signal.
        self.dataChanged.emit(index,index)

        # Return True: setData succeeded.
        return True

    def flags(self,index):
        """Returns flags applicable to the given node.
        inherited from QtCore.QAbstractItemModel
        """
        # If we do not have a valid index, return the default.
        if not index.isValid(): return QtCore.QAbstractItemModel.flags(self,index)

        # Default flags: selectable and enabled
        f = QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled

        node = index.internalPointer()

        # Add checkbox if needed
        if self.checkboxes:
            f |= QtCore.Qt.ItemIsUserCheckable
            if node.hasChildren(): f |= QtCore.Qt.ItemIsTristate

        # Make editable if it's the 1st column and the node is editable.
        if index.column()==1 and node.canHaveValue() and (not node.isReadOnly()): f |= QtCore.Qt.ItemIsEditable
            
        return f

    def headerData(self,section,orientation,role):
        """Returns the header for the given row or column (in our case columns only).
        inherited from QtCore.QAbstractItemModel
        """
        if role==QtCore.Qt.DisplayRole:
            if section==0:
                return 'variable'
            elif section==1:
                return 'value'
        return None
        
    def indexFromNode(self,node,column=0):
        assert isinstance(node,xmlstore.Node), 'indexFromNode: supplied object is not of type "Node" (but "%s").' % (node,)
        irow = self.storeinterface.getOwnIndex(node)
        return self.createIndex(irow,column,node)

    def beforeNodeVisibilityChange(self,nodes,newvisibility,showhide):
        """Event handler. Called by the TypedStore just before a node is hidden/deleted
        or shown/added.
        If the change is in visibility, showhide will be True. If a node is removed or
        added showhide will be False. If the node is shown or added, newvisibility will
        be True; if the node is hidden or deleted, newvisibility will be False.
        """
        # Debug check of function arguments (must be a list of nodes)
        for node in nodes:
            assert isinstance(node,xmlstore.Node), 'Supplied object is not of type "Node" (but "%s").' % node

        # If we will show hidden nodes and the change refers to visibility, do nothing.
        if self.nohide and showhide: return
        
        # Get row number and parent index of the first node.
        ifirstrow = self.storeinterface.getOwnIndex(nodes[0])
        par = self.parent(self.createIndex(ifirstrow,1,nodes[0]))
        
        # Get row number of last node, and make sure the nodes are contiguous.
        if len(nodes)>1:
            ilastrow = self.storeinterface.getOwnIndex(nodes[-1])
            assert par==self.parent(self.createIndex(ilastrow,1,nodes[-1])), 'Nodes supplied to beforeNodeVisibilityChange do not share the same parent.'
            assert ilastrow-ifirstrow+1==len(nodes), 'Node block supplied to beforeNodeVisibilityChange is not contiguous.'
        else:
            ilastrow = ifirstrow

        # Notify Qt4 about impending visibility change.
        if newvisibility:
            self.beginInsertRows(par,ifirstrow,ilastrow)
        else:
            self.beginRemoveRows(par,ifirstrow,ilastrow)

    def afterNodeVisibilityChange(self,nodes,newvisibility,showhide):
        """Event handler. Called by the TypedStore just after a node is hidden/deleted
        or shown/added.
        If the change is in visibility, showhide will be True. If a node is removed or
        added showhide will be False. If the node is shown or added, newvisibility will
        be True; if the node is hidden or deleted, newvisibility will be False.
        """
        # Debug check of function arguments (must be a list of nodes)
        for node in nodes:
            assert isinstance(node,xmlstore.Node), 'Supplied object is not of type "Node" (but "%s").' % node
        
        # If we show hidden nodes and the change refers to visibility,
        # only the color of the node will change: make Qt4 update the node display.
        if self.nohide and showhide:
            for node in nodes: self.onNodeChanged(node,'visibility',headertoo=True)
            return
        
        # Notify Qt4 about visibility change.
        if newvisibility:
            self.endInsertRows()
        else:
            self.endRemoveRows()

    def onNodeChanged(self,node,feature,headertoo = False):
        """Event handler. Called by the TypedStore just after a property of the node
        has changed. Typically the property changed is the node value (feature == "value"),
        but it can also be the node unit (feature == "unit"). The argument headertoo is
        used only internally, and specified that the header (i.e., descriptive name)
        has also changed and must be redrawn.
        """
        assert isinstance(node,xmlstore.Node), 'Supplied object is not of type "Node" (but "%s").' % node
        irow = self.storeinterface.getOwnIndex(node)
        index = self.createIndex(irow,1,node)
        self.dataChanged.emit(index,index)

        if headertoo:
            index = self.createIndex(irow,0,node)
            self.dataChanged.emit(index,index)

    def resetData(self,index,recursive=False):
        """Clears the value of the node identified by the supplied index, causing it
        to display its default value. If recursive is set, all descendants of the node
        are reset as well.
        """
        node = index.internalPointer()
        node.clearValue(recursive=recursive,skipreadonly=True,deleteclones=False)

    def hasDefaultValue(self,index):
        """Returns whether the node identified by the supplied index is currently
        set to its default value.
        """
        node = index.internalPointer()
        if node is None or not node.canHaveValue(): return True
        return node.hasDefaultValue()

    def getCheckedNodes(self,index=None):
        """Returns a list of all nodes that have been checked. Applies only if the
        model has checkboxes in from of each node.
        """
        if index is None: index = QtCore.QModelIndex()
        res = []
        for irow in range(self.rowCount(index)):
            child = self.index(irow,0,index)
            state = child.data(QtCore.Qt.CheckStateRole)
            if state==QtCore.Qt.Checked:
                res.append(child.internalPointer())
            res += self.getCheckedNodes(child)
        return res

# =======================================================================
# ExtendedTreeView: based on Qt QTreeView, additionally supports batch
# collapse/expand.
# =======================================================================

class ExtendedTreeView(QtWidgets.QTreeView):
    """Extended QTreeView class, providing support for selectively expanding/
    collapsing parts of the tree, and for showing a context menu that allows the
    uses to reset nodes or branches. Works only with TypedStoreModel.
    """

    def __init__(self,parent=None,autoexpandnondefaults=False):
        super(ExtendedTreeView,self).__init__(parent)
        self.autoexpandnondefaults = autoexpandnondefaults

    def setExpandedAll(self,value=True,maxdepth=1000,root=None,depth=0):
        """Expands/collapses all branches in the tree below the given root node
        (if not specified the actual model root is used), upto the specified depth.
        E.g. if depth equals one, the direct children of the root node are expanded,
        and everything else is left alone. If the depth is not specified, all nodes
        are processed. Argument "value" determines whether to expand nodes.
        (value==True, default) or collapse them (value==False).
        """
        model = self.model()
        if root is None: root=QtCore.QModelIndex()
        rc = model.rowCount(root)
        if rc>0:
            self.setExpanded(root,value)
            if depth<maxdepth:
                for ich in range(rc):
                    ch = model.index(ich,0,root)
                    self.setExpandedAll(value=value,root=ch,depth=depth+1,maxdepth=maxdepth)

    def expandNonDefaults(self,root=None):
        """Selectively expands branches of the tree to ensure that all nodes that are
        set to a value other than the default are visible.
        """
        model = self.model()
        if root is None: root=QtCore.QModelIndex()
        exp = False
        for ich in range(model.rowCount(root)):
            ch = model.index(ich,0,root)
            if self.expandNonDefaults(root=ch):
                exp = True
        if exp: self.expand(root)
        if not model.hasDefaultValue(root): exp = True
        return exp

    def contextMenuEvent(self,e):
        """Called internally when the user wants to display a context menu.
        Then a context menu is shown that allows the user to reset a node or
        entire branch to the default value(s).
        """
        index = self.indexAt(e.pos())
        if not index.isValid(): return

        # We will handle the context menu event.
        e.accept()
        
        # Get indices of name and value cell.
        if index.column()==0:
            nameindex = index
            valueindex = index.sibling(index.row(),1)
        else:
            nameindex = index.sibling(index.row(),0)
            valueindex = index

        # Check whether we can reset the current value and/or its decendants. Stop if not.
        model = self.model()
        resetself = (model.flags(valueindex) & QtCore.Qt.ItemIsEditable) and not model.hasDefaultValue(valueindex)
        resetchildren = model.hasChildren(nameindex)
        if not (resetself or resetchildren): return
        
        # Build context menu
        menu = QtWidgets.QMenu(self)
        if resetself:     actReset = menu.addAction('Reset value')
        if resetchildren: actResetChildren = menu.addAction('Reset entire branch')
        actChosen = menu.exec_(e.globalPos())
        if resetself and actChosen is actReset:
            model.resetData(nameindex)
        elif resetchildren and actChosen is actResetChildren:
            model.resetData(nameindex,recursive=True)

    def rowsInserted(self,parent,start,end):
        """Called internally after one or more rows have been added to the model.
        Currently, if the addition of rows gave the parent its very first child, the
        parent node is automatically expanded.
        """
        QtWidgets.QTreeView.rowsInserted(self,parent,start,end)
                
        # If needed, expand all child rows that were set to a non-default value.
        if self.autoexpandnondefaults:
            for i in range(start,end+1):
                self.expandNonDefaults(parent.child(i,0))
                
        # Auto-expand if the newly inserted rows were the very first children of the parent.
        # This will make sure that insertion of rows will not go unnoticed.
        model = self.model()
        if model.rowCount(parent)==end-start+1:
            self.expand(parent)

class TypedStoreTreeView(ExtendedTreeView):
    
    def __init__(self,parent,store,rootnode=None,expanddepth=1,resizecolumns=True,autoexpandnondefaults=True,**kwargs):
        ExtendedTreeView.__init__(self, parent, autoexpandnondefaults)

        self.store = store
        self.rootnode = rootnode
        self.expanddepth = expanddepth
        self.resizecolumns = resizecolumns

        # Set up model/treeview
        self.storemodel = TypedStoreModel(self.store,nohide=False)
        self.storedelegate = PropertyDelegate(self,fileprefix='',unitinside=True,autoopen=True,**kwargs)
        self.setItemDelegate(self.storedelegate)
        self.setUniformRowHeights(True)

        if self.rootnode is not None:
            # Get interface to scenario that allows us to find out when
            # the root node becomes visible/hidden.
            self.storeinterface = store.getInterface()
            self.storeinterface.connect('afterVisibilityChange', self.afterNodeVisibilityChange)

        self.configure(resizeheader=False)

        self.setIconSize(QtCore.QSize(0,0))
        
    def showEvent(self,event):
        if self.model() is not None and self.resizecolumns:
            self.header().resizeSection(0,.65*self.width())
            
    def configure(self,resizeheader=True):
        if self.rootnode is None or not self.rootnode.isHidden():
            self.setModel(self.storemodel)
            if self.rootnode is not None: self.setRootIndex(self.storemodel.indexFromNode(self.rootnode))
            self.setExpandedAll(maxdepth=self.expanddepth)
            self.expandNonDefaults()
            if resizeheader: self.header().resizeSection(0,.65*self.width())
        else:
            self.setModel(None)

    def afterNodeVisibilityChange(self,nodes,newvisibility,showhide):
        if self.rootnode in nodes: self.configure()

    def destroy(self,destroyWindow = True,destroySubWindows = True):
        self.setModel(None)
        self.storemodel.unlink()
        if self.rootnode is not None:
            self.store.disconnectInterface(self.storeinterface)
            self.storeinterface = None
        ExtendedTreeView.destroy(self,destroyWindow,destroySubWindows)
        
            
class PropertyEditorDialog(QtWidgets.QDialog):
    """Minimal dialog that can be used to edit the values of a TypedStore.
    Incoporates the ExtendedTreeView attached to a TypedStoreModel.
    """
    
    def __init__(self,parent,store,title='',instructions='',loadsave=False,flags=QtCore.Qt.Dialog,icon=None,loadhook=None,rootnode=None):
        if icon is not None: flags |= QtCore.Qt.WindowSystemMenuHint
        QtWidgets.QDialog.__init__(self, parent, flags)

        self.store = store
        self.tree = TypedStoreTreeView(self,self.store,expanddepth=3,resizecolumns=False,rootnode=rootnode)

        self.setSizeGripEnabled(True)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0,0,0,0)

        if instructions!='':
            lab = QtWidgets.QLabel(instructions,self)
            lab.setWordWrap(True)
            layout.addWidget(lab)

        layout.addWidget(self.tree)
        
        if loadsave:
            bnLoad = QtWidgets.QPushButton('Load...')
            bnSave = QtWidgets.QPushButton('Save...')
            bnReset = QtWidgets.QPushButton('Reset')
            layoutButtons = QtWidgets.QHBoxLayout()
            layoutButtons.addWidget(bnLoad)
            layoutButtons.addWidget(bnSave)
            layoutButtons.addWidget(bnReset)
            layoutButtons.addStretch(1)
            layout.addLayout(layoutButtons)
            bnLoad.clicked.connect(self.onLoad)
            bnSave.clicked.connect(self.onSave)
            bnReset.clicked.connect(self.onReset)

        self.setLayout(layout)

        if title!='':
            self.setWindowTitle(title)
        if icon is not None:
            self.setWindowIcon(icon)

        self.lastpath = ''
        self.loadhook = loadhook

    def resizeColumns(self):
        """Intelligently resize the column widths.
        """
        self.tree.header().resizeSections(QtWidgets.QHeaderView.Stretch)
        self.tree.resizeColumnToContents(0)
        maxwidth = int(0.65 * self.width())
        if self.tree.columnWidth(0)>maxwidth: self.tree.setColumnWidth(0,maxwidth)

    def onLoad(self):
        path,selectedFilter = QtWidgets.QFileDialog.getOpenFileNameAndFilter(self,'',self.lastpath,'XML files (*.xml);;All files (*.*)')
        path = unicode(path)
        if path=='': return
        try:
            if self.loadhook:
                self.loadhook(path)
            else:
                self.store.load(path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Unable to load settings from file', unicode(e), QtWidgets.QMessageBox.Ok, QtWidgets.QMessageBox.NoButton)
        self.lastpath = path

    def onSave(self):
        path,selectedFilter = QtWidgets.QFileDialog.getSaveFileNameAndFilter(self,'',self.lastpath,'XML files (*.xml);;All files (*.*)')
        path = unicode(path)
        if path=='': return
        self.store.save(path)
        self.lastpath = path

    def onReset(self):
        self.store.root.clearValue(recursive=True,deleteclones=False)

class PropertyEditorFactory(object):
    """Class that provides editors for nodes in a TypedStore. Multiple editors
    can be active at once (cf. QItemDelegate). If nodes in the TypedStore are
    hidden, any associated editors are disabled or hidden as well.
    """

    def __init__(self,typedstore,live=False,allowhide=False,unitinside=False,**kwargs):
        self.store = typedstore
        self.changed = False
        self.live = live
        self.properties = dict(kwargs.items())
        self.properties['allowhide' ] = allowhide
        self.properties['unitinside'] = unitinside
        self.editors = []
        self.externaleditors = []

        if self.live:
            self.storeinterface = self.store.getInterface()
            self.storeinterface.connect('afterChange',self.onStoreNodeChanged)
            self.storeinterface.connect('afterVisibilityChange',self.onStoreVisibilityChanged)
            
    def unlink(self):
        if self.live:
            self.store.disconnectInterface(self.storeinterface)
            self.storeinterface = None
        for editor in self.editors:
            editor.destroy()

    def createEditor(self,location,parent,**kwargs):
        """Create a new editor for the specified location, which may be a node in the
        TypedStore or a path (string) to a node. The parent should be derived from
        QWidget and will be used as parent of the to-be-created editor. Any named
        arguments that are specified will be transfered to the editor; these will then
        override any arguments with the same name that were specified upon creation of
        the PropertyEditorFactory.
        """
        assert location is not None, 'Specified node is None (non-existent?).'
        if isinstance(location,xmlstore.Node):
            node = location
        else:
            node = self.store[location]
            assert node is not None, 'Unable to create editor for "%s"; this node does not exist.' % location

        # The editor inherits some optional arguments from the responsible factory.
        editorargs = dict(self.properties.items())
        editorargs.update(kwargs)

        # Create the editor object.        
        editor = PropertyEditor(node,parent,**editorargs)
        
        # If we are "live", update the enabled/disabled state or visibility of the editor.
        if self.live: editor.updateEditorEnabled()
        
        # Make sure we receive notifications when the value in the editor changes.
        editor.addChangeHandler(self.onNodeEdited)
        
        # Add the editor to our list of editors.
        self.editors.append(editor)
        
        return editor
        
    def destroyEditor(self,editor,layout=None):
        """Destroys the specified editor. If layout is specified, it must an object
        derived from QLayout. The editor will then be removed from the layout before
        being destroyed.
        """
        for i in range(len(self.editors)-1,-1,-1):
            if self.editors[i] is editor:
                del self.editors[i]
                editor.destroy(layout)
                break

    def updateStore(self):
        """Updates the TypedStore with the values currently set in all attached editors.
        """
        for editor in self.editors:
            editor.updateStore()

    def hasChanged(self):
        """Returns True if the value set in of of the editors has changed since its
        inception.
        """
        return self.changed

    def onStoreNodeChanged(self,node,feature):
        """Event handler, called directly after the value of a node in the TypedStore has
        changed. Here we make sure that any editors associated with the changed node show
        the new value.
        """
        for editor in self.editors:
            if editor.node is node:
                editor.updateEditorValue()
                break
        for (editor,conditionnode,conditiontype,conditionvalue) in self.externaleditors:
            if conditionnode==node and conditiontype!='visibility':
                valuematch = node.getValue(usedefault=True)==conditionvalue
                newviz = (conditiontype=='eq' and valuematch) or (conditiontype=='ne' and not valuematch)
                editor.setVisible(newviz)

    def onStoreVisibilityChanged(self,nodes,visible,showhide):
        """Event handler, called directly after the visibility of a node in the TypedStore
        has changed (because it is removed/hidden/added/shown). Currently we only process
        show/hide events (node addition/removal is ignored); when we recieve such events,
        the editor updates its state, which may mean change its visibility, or change its
        state from enabled to disabled, or vice versa.
        """
        if not showhide: return
        for node in nodes:
            nodeloc = '/'.join(node.location)
            for editor in self.editors:
                #if node is editor.node:
                if ('/'.join(editor.node.location)).startswith(nodeloc):
                    editor.updateEditorEnabled()
            for (editor,conditionnode,conditiontype,conditionvalue) in self.externaleditors:
                if conditionnode==node and conditiontype=='visibility':
                    editor.setVisible(visible)

    def onNodeEdited(self,editor):
        """Called by attached editors after their value has changed.
        """
        self.changed = True
        if self.live:
            if not editor.updateStore(): editor.updateEditorValue()
            
    def getEditedNodes(self):
        """Returns a list of all nodes associated with this PropertyEditorFactory.
        """
        return [editor.node for editor in self.editors]
        
    def attachExternalEditor(self,editor,node,conditiontype='visibility',conditionvalue=None):
        if isinstance(node, (str, u''.__class__)):
            node = self.store[node]
        self.externaleditors.append((editor,node,conditiontype,conditionvalue))
        if conditiontype=='visibility':
            newviz = not node.isHidden()
        else:
            valuematch = node.getValue(usedefault=True)==conditionvalue
            newviz = (conditiontype=='eq' and valuematch) or (conditiontype=='ne' and not valuematch)
        editor.setVisible(newviz)

class PropertyEditor(object):
    """Class representing an editor of a node in the TypedStore, plus some associated
    widgets such as a label and unit specifier (cf. AbstractPropertyEditor). Contains
    some convenience functions that add all widgets that are part of the editor to
    common layout types (addToGridLayout, addToBoxLayout), and to show/hide/enable/
    disable/destroy all those widgets simultaneously. Also processes changes in the
    edited node value/unit by external parties (through notification by the
    PropertyEditorFactory), and sends notifications of changes in the editor to the
    PropertyEditorFactory.
    """

    def __init__(self,node,parent,allowhide=False,unitinside=False,**kwargs):
        self.node = node
        self.unit = None
        self.label = None
        self.icon = None
        self.allowhide = allowhide
        self.unitinside = unitinside

        if 'editor' in kwargs:
            self.editor = kwargs['editor']
        else:
            self.editor = self.createEditor(node,parent,**kwargs)
            self.updateEditorValue()
        
        self.changehandlers = []
        self.suppresschangeevent = False
        self.location = node.location[:]
        
    def addToGridLayout(self,gridlayout,irow=None,icolumn=0,rowspan=1,colspan=1,label=True,unit=True,icon=None):
        """Adds the editor plus label to an existing QGridLayout, in the specified row, starting at the specified column.
        """
        if irow is None: irow = gridlayout.rowCount()
        if icon is None: icon = (self.node.getText(detail=2,minimumdetail=2) is not None)

        if label:
            if self.label is None: self.createLabel()
            gridlayout.addWidget(self.label,irow,icolumn)
            icolumn += 1

        gridlayout.addWidget(self.editor,irow,icolumn,rowspan,colspan)
        icolumn += colspan

        if unit and not self.unitinside:
            if self.unit is None: self.createUnit()
            gridlayout.addWidget(self.unit,irow,icolumn)
            icolumn += 1

    def addToBoxLayout(self,boxlayout,label=True,unit=True,addstretch=True,icon=None):
        """Adds the editor plus label to an existing QBoxLayout.
        """
        if icon is None: icon = (self.node.getText(detail=2,minimumdetail=2) is not None)

        if not isinstance(boxlayout,QtWidgets.QHBoxLayout):
            layout = QtWidgets.QHBoxLayout()
        else:
            layout = boxlayout
        
        if label:
            if self.label is None: self.createLabel()
            layout.addWidget(self.label)
            
        layout.addWidget(self.editor)
        
        if unit and not self.unitinside:
            if self.unit is None: self.createUnit()
            layout.addWidget(self.unit)
            
        if addstretch:
            layout.addStretch(1)
            
        if layout is not boxlayout:
            boxlayout.addLayout(layout)

    def createUnit(self):
        """Creates a label with the unit of the editor, based on the description in the source node.
        This function can be called only once in the life time of the object.
        """
        assert self.unit is None, 'Cannot create unit because it has already been created.'
        unittext = self.node.getUnit()
        if unittext is None: unittext=''
        self.unit = QtWidgets.QLabel(unittext,self.editor.parent())
        if self.allowhide and self.node.isHidden(): self.unit.setVisible(False)
        return self.unit
        
    def createLabel(self,detail=1,wrap=False,addcolon=True,text=None):
        """Creates a label for the editor, based on the description in the source node.
        This function can be called only once in the life time of the object.
        """
        assert self.label is None, 'Cannot create label because it has already been created.'
        if text is None:
            text = self.node.getText(detail=detail,capitalize=True)
            if addcolon: text += ': '
        self.label = QtWidgets.QLabel(text,self.editor.parent())
        if wrap: self.label.setWordWrap(True)
        if self.allowhide and self.node.isHidden(): self.label.setVisible(False)
        return self.label
        
    def setVisible(self,visible):
        """Sets the visibility of the editor and label (if any).
        """
        if self.label is not None: self.label.setVisible(visible)
        if self.icon  is not None: self.icon.setVisible(visible)
        if self.unit  is not None: self.unit.setVisible(visible)
        if isinstance(self.editor,QtWidgets.QWidget):
            self.editor.setVisible(visible)
        elif isinstance(self.editor,QtWidgets.QButtonGroup):
            for bn in self.editor.buttons(): bn.setVisible(visible)

    def destroy(self,layout=None):
        """Removes all widgets belonging to this editor from the layout.
        """
        if layout is not None:
            if self.label is not None: layout.removeWidget(self.label)
            if self.icon  is not None: layout.removeWidget(self.icon)
            if self.unit  is not None: layout.removeWidget(self.unit)
            layout.removeWidget(self.editor)

        if self.label is not None:
            self.label.destroy()
            self.label = None
        if self.icon is not None:
            self.icon.destroy()
            self.icon = None
        if self.unit is not None:
            self.unit.destroy()
            self.unit = None
        if isinstance(self.editor,QtWidgets.QWidget):
            self.editor.destroy()
        self.editor = None

    def updateStore(self):
        """Updates the value of the source node with the current value of the editor.
        """
        return self.setNodeData(self.editor,self.node)

    def updateEditorValue(self):
        """Updates the value in the editor, so it reflects the current value of the source node.
        """
        self.setEditorData(self.editor,self.node)
        if self.unit is not None:
            unittext = self.node.getUnit()
            if unittext is None: unittext=''
            self.unit.setText(unittext)

    def updateEditorEnabled(self):
        """Enables/disables or shows/hides the editor (and label, if any) based on the visibility of the source node.
        Called by the responsible factory when the "hidden" state of the source node changes.
        """
        visible = not self.node.isHidden()
        if self.allowhide: return self.setVisible(visible)
        if isinstance(self.editor,QtWidgets.QWidget):
            self.editor.setEnabled(visible)
        elif isinstance(self.editor,QtWidgets.QButtonGroup):
            for bn in self.editor.buttons(): bn.setEnabled(visible)

    def addChangeHandler(self,callback):
        """Registers an event handler to be called when the value in the editor changes.
        Used by the responsible factory to immediately update the source node, if editing is "live".
        """
        self.changehandlers.append(callback)

    def onChange(self,*args,**kwargs):
        """Called internally after the value in the editor has changed.
        Dispatches the change event to the attached event handlers (if any).
        """
        if not self.suppresschangeevent:
            for callback in self.changehandlers:
                callback(self)

    def createEditor(self,node,parent,boolwithcheckbox=False,groupbox=False,whatsthis=True,**kwargs):
        """Creates an editor for the specified node, below the specified parent.
        Any additional named arguments are sent unmodified to the editor.
        """
        templatenode = node.templatenode
        nodetype = node.getValueType()
        editor = None
        
        if groupbox:
            # We have to create a group box (not really an editor)
            editor = QtWidgets.QGroupBox(node.getText(detail=1,capitalize=True),parent)
            #editor.setFlat(True)
            whatsthis = False
        elif nodetype=='bool' and boolwithcheckbox:
            # We have to create an editor for a boolean, and use a checkbox rather
            # than the default editor (combobox-like)
            editor = QtWidgets.QCheckBox(node.getText(detail=1,capitalize=True),parent)
            editor.stateChanged.connect(self.onChange)
        else:
            # Create a normal editor that derives from AbstractPropertyEditor
            editor = createEditor(node,parent,**kwargs)
            editor.propertyEditingFinished_callbacks.append(self.onChange)
            
        # Add what's-this information.
        if whatsthis and isinstance(editor,QtWidgets.QWidget):
            editor.setWhatsThis(node.getText(detail=2,capitalize=True))

        return editor

    def setEditorData(self,editor,node):
        """Set the value of the editor to the current value of the underlying node.
        """
        if not isinstance(editor,(AbstractPropertyEditor,QtWidgets.QCheckBox,QtWidgets.QButtonGroup)): return
        self.suppresschangeevent = True
        value = node.getValue(usedefault=True)
        if value is None: return
        nodetype = node.getValueType()
        if isinstance(editor,AbstractPropertyEditor):
            editor.setValue(value)
        elif nodetype=='bool':
            # Checkbox for boolean
            editor.setChecked(value is not None and value)
        if isinstance(value,util.referencedobject): value.release()
        self.suppresschangeevent = False

    def setNodeData(self,editor,node):
        """Set the value of the underlying node to the current value of the editor.
        """
        if not isinstance(editor,(AbstractPropertyEditor,QtWidgets.QCheckBox,QtWidgets.QButtonGroup)): return True
        nodetype = node.getValueType()
        if isinstance(editor,AbstractPropertyEditor):
            value = editor.value()
            ret = node.setValue(value)
            if isinstance(value,util.referencedobject): value.release()
            return ret
        elif nodetype=='bool':
            # Checkbox for boolean
            return node.setValue(editor.checkState()==QtCore.Qt.Checked)
            
