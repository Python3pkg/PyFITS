from pyfits.card import Card
from pyfits.hdu.base import _ValidHDU
from pyfits.util import lazyproperty, _is_int, _with_extensions


class _ExtensionHDU(_ValidHDU):
    """
    An extension HDU class.

    This class is the base class for the `TableHDU`, `ImageHDU`, and
    `BinTableHDU` classes.
    """

    _extension = ''

    def __init__(self, data=None, header=None, **kwargs):
        super(_ExtensionHDU, self).__init__(data=data, header=header)
        if header:
            if 'EXTNAME' in header and not self.name:
                self.name = header['EXTNAME']

            if not hasattr(self, '_extver'):
                if 'EXTVER' in header:
                    self._extver = header['EXTVER']
                else:
                    self._extver = 1

    def __setattr__(self, attr, value):
        """
        Set an HDU attribute.
        """

        from pyfits.core import EXTENSION_NAME_CASE_SENSITIVE

        if attr == 'name' and value:
            if not isinstance(value, basestring):
                raise TypeError("'name' attribute must be a string")
            if not EXTENSION_NAME_CASE_SENSITIVE:
                value = value.upper()
            if 'EXTNAME' in self._header:
                self._header['EXTNAME'] = value
            else:
                self._header.ascard.append(
                    Card('EXTNAME', value, 'extension name'))

        super(_ExtensionHDU, self).__setattr__(attr, value)

    @_with_extensions
    def writeto(self, name, output_verify='exception', clobber=False,
                classExtensions={}, checksum=False):
        """
        Works similarly to the normal writeto(), but prepends a default
        `PrimaryHDU` are required by extension HDUs (which cannot stand on
        their own).
        """

        from pyfits.hdu.hdulist import HDUList
        from pyfits.hdu.image import PrimaryHDU

        hdulist = HDUList([PrimaryHDU(), self])
        hdulist.writeto(name, output_verify, clobber=clobber,
                        checksum=checksum)

    def _verify(self, option='warn'):

        errs = super(_ExtensionHDU, self)._verify(option=option)

        # Verify location and value of mandatory keywords.
        naxis = self._header.get('NAXIS', 0)
        self.req_cards('PCOUNT', naxis + 3, lambda v: (_is_int(v) and v >= 0),
                       0, option, errs)
        self.req_cards('GCOUNT', naxis + 4, lambda v: (_is_int(v) and v == 1),
                       1, option, errs)
        return errs


class _NonstandardExtHDU(_ExtensionHDU):
    """
    A Non-standard Extension HDU class.

    This class is used for an Extension HDU when the ``XTENSION``
    `Card` has a non-standard value.  In this case, pyfits can figure
    out how big the data is but not what it is.  The data for this HDU
    is read from the file as a byte stream that begins at the first
    byte after the header ``END`` card and continues until the
    beginning of the next header or the end of the file.
    """

    def _summary(self):
        return "%-6s  %-10s  %3d" % (self.name, 'NonstandardExtHDU',
                                     len(self._header.ascard))

    @lazyproperty
    def data(self):
        """
        Return the file data.
        """

        self._file.seek(self._datLoc)
        self._data_loaded = True
        return self._file.read()
