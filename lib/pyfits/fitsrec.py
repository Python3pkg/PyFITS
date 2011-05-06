import operator
import sys
import warnings

import numpy as np

from pyfits import rec
from pyfits.column import ASCIITNULL, FITS2NUMPY, TDIM_RE, Column, ColDefs, \
                          _FormatX, _FormatP, _VLF, _get_index, _wrapx, \
                          _unwrapx, _convert_format, _convert_ascii_format
from pyfits.util import _fromfile


class FITS_record(object):
    """
    FITS record class.

    `FITS_record` is used to access records of the `FITS_rec` object.
    This will allow us to deal with scaled columns.  It also handles
    conversion/scaling of columns in ASCII tables.  The `FITS_record`
    class expects a `FITS_rec` object as input.
    """

    def __init__(self, input, row=0, startColumn=0, endColumn=0):
        """
        Parameters
        ----------
        input : array
           The array to wrap.

        row : int, optional
           The starting logical row of the array.

        startColumn : int, optional
           The starting column in the row associated with this object.
           Used for subsetting the columns of the FITS_rec object.

        endColumn : int, optional
           The ending column in the row associated with this object.
           Used for subsetting the columns of the FITS_rec object.
        """

        self.array = input
        self.row = row
        len = self.array._nfields

        if startColumn > len:
            self.start = len + 1
        else:
            self.start = startColumn

        if endColumn <= 0 or endColumn > len:
            self.end = len
        else:
            self.end = endColumn

    def __getitem__(self, key):
        if isinstance(key, basestring):
            indx = _get_index(self.array.names, key)

            if indx < self.start or indx > self.end - 1:
                raise KeyError("Key '%s' does not exist." % key)
        elif isinstance(key, slice):
            # TODO: Maybe get step working?
            return FITS_record(self.array, self.row, key.start, key.stop)
        else:
            indx = key + self.start

            if indx > self.end - 1:
                raise IndexError('Index out of bounds')

        return self.array.field(indx)[self.row]

    def __setitem__(self, fieldname, value):
        if isinstance(fieldname, basestring):
            indx = _get_index(self.array._coldefs.names, fieldname)

            if indx < self.start or indx > self.end - 1:
                raise KeyError("Key '%s' does not exist." % fieldname)
        else:
            indx = fieldname + self.start

            if indx > self.end - 1:
                raise IndexError('Index out of bounds')

        self.array.field(indx)[self.row] = value

    def __len__(self):
        return min(self.end - self.start, self.array._nfields)

    def __repr__(self):
        """
        Display a single row.
        """

        outlist = []
        for idx in range(self.array._nfields):
            if idx >= self.start and idx < self.end:
                outlist.append(repr(self.array.field(idx)[self.row]))
        return '(%s)' % ', '.join(outlist)


    def field(self, fieldName):
        """
        Get the field data of the record.
        """

        return self.__getitem__(fieldName)


    def setfield(self, fieldName, value):
        """
        Set the field data of the record.
        """

        self.__setitem__(fieldName, value)


class FITS_rec(rec.recarray):
    """
    FITS record array class.

    `FITS_rec` is the data part of a table HDU's data part.  This is a
    layer over the `recarray`, so we can deal with scaled columns.

    It inherits all of the standard methods from `numpy.ndarray`.
    """

    def __new__(subtype, input):
        """
        Construct a FITS record array from a recarray.
        """

        # input should be a record array
        if input.dtype.subdtype is None:
            self = rec.recarray.__new__(subtype, input.shape, input.dtype,
                                        buf=input.data,
                                        heapoffset=input._heapoffset,
                                        file=input._file)
        else:
            self = rec.recarray.__new__(subtype, input.shape, input.dtype,
                                        buf=input.data, strides=input.strides,
                                        heapoffset=input._heapoffset,
                                        file=input._file)

        self._nfields = len(self.dtype.names)
        self._convert = [None] * len(self.dtype.names)
        self._coldefs = None
        self._gap = 0
        self.names = list(self.dtype.names)
        self.formats = None
        return self

    def __array_finalize__(self, obj):
        if obj is None:
            return

        if isinstance(obj, FITS_rec):
            self._convert = obj._convert
            self._coldefs = obj._coldefs
            self._nfields = obj._nfields
            self.names = obj.names
            self._gap = obj._gap
            self.formats = obj.formats
        else:
            # This will allow regular ndarrays with fields, rather than
            # just other FITS_rec objects
            self._nfields = len(obj.dtype.names)
            self._convert = [None] * len(obj.dtype.names)

            self._heapoffset = getattr(obj, '_heapoffset', 0)
            self._file = getattr(obj, '_file', None)

            self._coldefs = None
            self._gap = 0
            self.names = list(obj.dtype.names)
            self.formats = None

            attrs = ['_convert', '_coldefs', 'names', '_gap', 'formats']
            for attr in attrs:
                if hasattr(obj, attr):
                    value = getattr(obj, attr, None)
                    if value is None:
                        warnings.warn('Setting attribute %s as None' % attr)
                    setattr(self, attr, value)

            if self._coldefs is None:
                self._coldefs = ColDefs(self)
                self.formats = self._coldefs.formats

    def __repr__(self):
        return rec.recarray.__repr__(self)

    def __getitem__(self, key):
        if isinstance(key, basestring):
            return self.field(key)
        elif isinstance(key, (slice, np.ndarray)):
            out = rec.recarray.__getitem__(self, key)
            out._coldefs = ColDefs(self._coldefs)
            arrays = []
            out._convert = [None] * len(self.dtype.names)
            for idx in range(len(self.dtype.names)):
                #
                # Store the new arrays for the _coldefs object
                #
                arrays.append( self._coldefs._arrays[idx][key])

                # touch all fields to expand the original ._convert list
                # so the sliced FITS_rec will view the same scaled columns as
                # the original
                dummy = self.field(idx)
                if self._convert[idx] is not None:
                    out._convert[idx] = \
                        np.ndarray.__getitem__(self._convert[idx], key)
            del dummy

            out._coldefs._arrays = arrays
            out._coldefs._shape = len(arrays[0])

            return out

        # if not a slice, do this because Record has no __getstate__.
        # also more efficient.
        else:
            if isinstance(key, int) and key >= len(self):
                raise IndexError("Index out of bounds")

            newrecord = FITS_record(self, key)
            return newrecord

    def __setitem__(self, row, value):
        if isinstance(row, slice):
            end = min(len(self), row.stop)
            end = max(0, end)
            start = max(0, row.start)
            end = min(end, start + len(value))

            for idx in range(start, end):
                self.__setitem__(idx, value[idx - start])
            return

        if isinstance(value, FITS_record):
            for idx in range(self._nfields):
                self.field(self.names[idx])[row] = value.field(self.names[idx])
        elif isinstance(value, (tuple, list)):
            if self._nfields == len(value):
                for idx in range (self._nfields):
                    self.field(idx)[row] = value[idx]
            else:
               raise ValueError('Input tuple or list required to have %s '
                                'elements.' % self._nfields)
        else:
            raise TypeError('Assignment requires a FITS_record, tuple, or '
                            'list as input.')

    @property
    def columns(self):
        """
        A user-visible accessor for the coldefs.  See ticket #44.
        """

        return self._coldefs

    def field(self, key):
        """
        A view of a `Column`'s data as an array.
        """

        indx = _get_index(self.names, key)
        recformat = self._coldefs._recformats[indx]

        # If field's base is a FITS_rec, we can run into trouble because it
        # contains a reference to the ._coldefs object of the original data;
        # this can lead to a circular reference; see ticket #49
        base = self
        while isinstance(base, FITS_rec) and \
              isinstance(base.base, rec.recarray):
            base = base.base
        # base could still be a FITS_rec in some cases, so take care to
        # use rec.recarray.field to avoid a potential infinite
        # recursion
        field = rec.recarray.field(base, indx)

        if (self._convert[indx] is None):
            # for X format
            if isinstance(recformat, _FormatX):
                _nx = recformat._nx
                dummy = np.zeros(self.shape + (_nx,), dtype=np.bool_)
                _unwrapx(field, dummy, _nx)
                self._convert[indx] = dummy
                return self._convert[indx]

            (_str, _bool, _number, _scale, _zero, bscale, bzero, dim) = \
                self._get_scale_factors(indx)

            # for P format
            if isinstance(recformat, _FormatP):
                dummy = _VLF([None] * len(self))
                dummy._dtype = recformat._dtype
                for i in range(len(self)):
                    _offset = field[i,1] + self._heapoffset
                    self._file.seek(_offset)
                    if recformat._dtype == 'a':
                        count = field[i,0]
                        dt = recformat._dtype + str(1)
                        da = _fromfile(self._file, dtype=dt, count=count,
                                       sep='')
                        dummy[i] = np.char.array(da, itemsize=count)
                        if not issubclass(dummy[i].dtype.type, np.unicode_):
                            dummy[i] = dummy[i].astype(np.unicode_)
                    else:
                        count = field[i,0]
                        dt = recformat._dtype
                        dummy[i] = _fromfile(self._file, dtype=dt, count=count,
                                             sep='')
                        dummy[i].dtype = dummy[i].dtype.newbyteorder('>')

                # scale by TSCAL and TZERO
                if _scale or _zero:
                    for i in range(len(self)):
                        dummy[i][:] = dummy[i]*bscale+bzero

                # Boolean (logical) column
                if recformat._dtype is FITS2NUMPY['L']:
                    for i in range(len(self)):
                        dummy[i] = np.equal(dummy[i], ord('T'))

                self._convert[indx] = dummy
                return self._convert[indx]

            # ASCII table, convert strings to numbers
            if not _str and self._coldefs._tbtype == 'TableHDU':
                _fmap = {'I': np.int32, 'F': np.float32, 'E': np.float32,
                         'D': np.float64}
                _type = _fmap[self._coldefs.formats[indx][0]]

                # if the string = TNULL, return ASCIITNULL
                nullval = self._coldefs.nulls[indx].strip()
                dummy = field.replace('D', 'E')
                dummy = np.where(dummy.strip() == nullval, str(ASCIITNULL),
                                 dummy)
                dummy = np.array(dummy, dtype=_type)

                self._convert[indx] = dummy
            else:
                dummy = field

            # Test that the dimensions given in dim are sensible; otherwise
            # display a warning and ignore them
            if dim:
                # See if the dimensions already match, if not, make sure the
                # number items will fit in the specified dimensions
                if dummy.ndim > 1:
                    actual_shape = dummy[0].shape
                    if _str:
                        actual_shape = (dummy[0].itemsize,) + actual_shape
                else:
                    actual_shape = len(dummy[0])
                if dim == actual_shape:
                    # The array already has the correct dimensions, so we
                    # ignore dim and don't convert
                    dim = None
                else:
                    nitems = reduce(operator.mul, dim)
                    if _str:
                        actual_nitems = dummy.itemsize
                    else:
                        actual_nitems = dummy.shape[1]
                    if nitems != actual_nitems:
                        warnings.warn(
                            'TDIM%d value %s does not fit with the size of '
                            'the array items (%d).  TDIM%d will be ignored.'
                            % (indx + 1, self._coldefs.dims[indx],
                               actual_nitems, indx + 1))
                        dim = None

            # further conversion for both ASCII and binary tables
            if _number and (_scale or _zero):

                # only do the scaling the first time and store it in _convert
                self._convert[indx] = np.array(dummy, dtype=np.float64)
                if _scale:
                    np.multiply(self._convert[indx], bscale,
                                self._convert[indx])
                if _zero:
                    self._convert[indx] += bzero
            elif _bool:
                self._convert[indx] = np.equal(dummy, ord('T'))
            elif dim:
                self._convert[indx] = dummy
            elif _str:
                if not issubclass(dummy.dtype.type, np.unicode_):
                    try:
                        self._convert[indx] = dummy.astype(np.unicode_)
                    except UnicodeDecodeError:
                        return dummy
                else:
                    return dummy
            else:
                return dummy

            if dim:
                if _str:
                    dtype = ('|U%d' % dim[0], dim[1:])
                    self._convert[indx].dtype = dtype
                else:
                    self._convert[indx].shape = (dummy.shape[0],) + dim

        return self._convert[indx]

    def _clone(self, shape):
        """
        Overload this to make mask array indexing work properly.
        """

        from pyfits.hdu.table import new_table

        hdu = new_table(self._coldefs, nrows=shape[0])
        return hdu.data

    def _get_scale_factors(self, indx):
        """
        Get the scaling flags and factors for one field.

        `indx` is the index of the field.
        """

        if self._coldefs._tbtype == 'BinTableHDU':
            _str = 'a' in self._coldefs._recformats[indx]
            _bool = self._coldefs._recformats[indx][-2:] == FITS2NUMPY['L']
        else:
            _str = self._coldefs.formats[indx][0] == 'A'
            _bool = False             # there is no boolean in ASCII table
        _number = not(_bool or _str)
        bscale = self._coldefs.bscales[indx]
        bzero = self._coldefs.bzeros[indx]
        _scale = bscale not in ['', None, 1]
        _zero = bzero not in ['', None, 0]
        # ensure bscale/bzero are numbers
        if not _scale:
            bscale = 1
        if not _zero:
            bzero = 0
        dim = self._coldefs.dims[indx]
        m = dim and TDIM_RE.match(dim)
        if m:
            dim = m.group('dims')
            dim = tuple(int(d.strip()) for d in dim.split(','))
        else:
            # Ignore any dim values that don't specify a multidimensional
            # column
            dim = ''

        return (_str, _bool, _number, _scale, _zero, bscale, bzero, dim)

    def _scale_back(self):
        """
        Update the parent array, using the (latest) scaled array.
        """

        _fmap = {'A': 's', 'I': 'd', 'J': 'd', 'F': 'f', 'E': 'E', 'D': 'E'}
        # calculate the starting point and width of each field for ASCII table
        if self._coldefs._tbtype == 'TableHDU':
            loc = self._coldefs.starts
            widths = []

            idx = 0
            for idx in range(len(self.dtype.names)):
                f = _convert_ascii_format(self._coldefs.formats[idx])
                widths.append(f[1])
            loc.append(loc[-1] + super(FITS_rec, self).field(idx).itemsize)

        self._heapsize = 0
        for indx in range(len(self.dtype.names)):
            recformat = self._coldefs._recformats[indx]
            field = super(FITS_rec, self).field(indx)

            if self._convert[indx] is None:
                continue

            if isinstance(recformat, _FormatX):
                _wrapx(self._convert[indx], field, recformat._nx)
                continue

            (_str, _bool, _number, _scale, _zero, bscale, bzero, dim) = \
                self._get_scale_factors(indx)

            # add the location offset of the heap area for each
            # variable length column
            if isinstance(recformat, _FormatP):
                field[:] = 0 # reset
                npts = map(len, self._convert[indx])
                field[:len(npts),0] = npts
                dtype = np.array([], dtype=recformat._dtype)
                field[1:,1] = np.add.accumulate(field[:-1,0]) * dtype.itemsize

                field[:,1][:] += self._heapsize
                self._heapsize += field[:,0].sum() * dtype.itemsize

            # conversion for both ASCII and binary tables
            if _number or _str:
                if _number and (_scale or _zero):
                    dummy = self._convert[indx].copy()
                    if _zero:
                        dummy -= bzero
                    if _scale:
                        dummy /= bscale
                elif _str:
                    dummy = self._convert[indx]
                elif self._coldefs._tbtype == 'TableHDU':
                    dummy = self._convert[indx]
                else:
                    continue

                # ASCII table, convert numbers to strings
                if self._coldefs._tbtype == 'TableHDU':
                    format = self._coldefs.formats[indx].strip()
                    lead = self._coldefs.starts[indx] - loc[indx]
                    if lead < 0:
                        raise ValueError(
                            'Column `%s` starting point overlaps to the '
                            'previous column.' % indx + 1)
                    trail = loc[indx+1] - widths[indx] - \
                             self._coldefs.starts[indx]
                    if trail < 0:
                        raise ValueError(
                            'Column `%s` ending point overlaps to the next '
                            'column.' % indx + 1)
                    if 'A' in format:
                        _pc = '%-'
                    else:
                        _pc = '%'

                    fmt = (' ' * lead) + _pc + format[1:] + \
                          _fmap[format[0]] + (' ' * trail)

                    # not using numarray.strings's num2char because the
                    # result is not allowed to expand (as C/Python does).
                    for jdx in range(len(dummy)):
                        x = fmt % dummy[jdx]
                        if len(x) > (loc[indx+1] - loc[indx]):
                            raise ValueError(
                                "Number `%s` does not fit into the output's "
                                "itemsize of %s." % (x, widths[indx]))
                        else:
                            field[jdx] = x
                    # Replace exponent separator in floating point numbers
                    if 'D' in format:
                        field.replace('E', 'D')
                # binary table
                else:
                    if isinstance(field[0], np.integer):
                        dummy = np.around(dummy)
                    field[:] = dummy.astype(field.dtype)

                del dummy

            # ASCII table does not have Boolean type
            elif _bool:
                field[:] = np.choose(self._convert[indx],
                                     (np.array([ord('F')], dtype=np.int8)[0],
                                      np.array([ord('T')],dtype=np.int8)[0]))

