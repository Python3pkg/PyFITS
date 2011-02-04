#This is the configuration file for the pyfits namespace.

from __future__ import division # confidence high

# I've seen one example of code that's using datetime from pyfits;
# That code should be fixed, but in the meantime this is here for
# compatibility
import datetime

# Define the version of the pyfits package.
try:
    from pyfits import svn_version
    __svn_version__ = svn_version.__svn_version__
except ImportError:
    __svn_version__ = 'Unable to determine SVN revision'

__version__ = '2.4.0' + __svn_version__

# Import the pyfits core module.
import pyfits.core
from pyfits.core import *
__doc__ = pyfits.core.__doc__

# Define modules available using from pyfits import *.
__locals = list(locals())
for __l in __locals[::-1]:
    if __l[0] == '_' or __l in ['os', 'chararray', 'rec', 'open', 'warnings']:
        __locals.remove(__l)
__all__ = __locals

try:
    import pytools.tester
    def test(*args,**kwds):
        pytools.tester.test(modname=__name__, *args, **kwds)
except ImportError:
    pass

