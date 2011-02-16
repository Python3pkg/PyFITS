import numpy as np

from pyfits.column import Column, ColDefs, FITS2NUMPY
from pyfits.fitsrec import FITS_rec, FITS_record
from pyfits.hdu.base import _AllHDU, _isInt
from pyfits.hdu.image import _ImageBaseHDU, PrimaryHDU
from pyfits import rec


class GroupsHDU(PrimaryHDU):
    """
    FITS Random Groups HDU class.
    """

    _dict = {8:'B', 16:'I', 32:'J', 64:'K', -32:'E', -64:'D'}

    def __init__(self, data=None, header=None, name=None):
        """
        TODO: Write me
        """
        PrimaryHDU.__init__(self, data=data, header=header)
        self._header._hdutype = GroupsHDU
        self.name = name

        if self._header['NAXIS'] <= 0:
            self._header['NAXIS'] = 1
        self._header.update('NAXIS1', 0, after='NAXIS')


    def __getattr__(self, attr):
        """
        Get the `data` or `columns` attribute.  The data of random
        group FITS file will be like a binary table's data.
        """

        from pyfits.hdu.table import _get_tbdata

        if attr == 'data': # same code as in _TableBaseHDU
            size = self.size()
            if size:
                self._file.seek(self._datLoc)
                data = GroupData(_get_tbdata(self))
                data._coldefs = self.columns
                data.formats = self.columns.formats
                data.parnames = self.columns._pnames
            else:
                data = None
            self.__dict__[attr] = data

        elif attr == 'columns':
            _cols = []
            _pnames = []
            _pcount = self._header['PCOUNT']
            _format = GroupsHDU._dict[self._header['BITPIX']]
            for i in range(self._header['PCOUNT']):
                _bscale = self._header.get('PSCAL'+`i+1`, 1)
                _bzero = self._header.get('PZERO'+`i+1`, 0)
                _pnames.append(self._header['PTYPE'+`i+1`].lower())
                _cols.append(Column(name='c'+`i+1`, format = _format, bscale = _bscale, bzero = _bzero))
            data_shape = self._dimShape()[:-1]
            dat_format = `int(np.array(data_shape).sum())` + _format

            _bscale = self._header.get('BSCALE', 1)
            _bzero = self._header.get('BZERO', 0)
            _cols.append(Column(name='data', format = dat_format, bscale = _bscale, bzero = _bzero))
            _coldefs = ColDefs(_cols)
            _coldefs._shape = self._header['GCOUNT']
            _coldefs._dat_format = FITS2NUMPY[_format]
            _coldefs._pnames = _pnames
            self.__dict__[attr] = _coldefs

        elif attr == '_theap':
            self.__dict__[attr] = 0
        else:
            return _AllHDU.__getattr__(self,attr)

        try:
            return self.__dict__[attr]
        except KeyError:
            raise AttributeError(attr)

    # 0.6.5.5
    def size(self):
        """
        Returns the size (in bytes) of the HDU's data part.
        """
        size = 0
        naxis = self._header.get('NAXIS', 0)

        # for random group image, NAXIS1 should be 0, so we skip NAXIS1.
        if naxis > 1:
            size = 1
            for j in range(1, naxis):
                size = size * self._header['NAXIS'+`j+1`]
            bitpix = self._header['BITPIX']
            gcount = self._header.get('GCOUNT', 1)
            pcount = self._header.get('PCOUNT', 0)
            size = abs(bitpix) * gcount * (pcount + size) // 8
        return size

    def _verify(self, option='warn'):
        _err = PrimaryHDU._verify(self, option=option)

        # Verify locations and values of mandatory keywords.
        self.req_cards('NAXIS', '== 2', _isInt+" and val >= 1 and val <= 999", 1, option, _err)
        self.req_cards('NAXIS1', '== 3', _isInt+" and val == 0", 0, option, _err)
        _after = self._header['NAXIS'] + 3

        # if the card EXTEND exists, must be after it.
        try:
            _dum = self._header['EXTEND']
            #_after += 1
        except KeyError:
            pass
        _pos = '>= '+`_after`
        self.req_cards('GCOUNT', _pos, _isInt, 1, option, _err)
        self.req_cards('PCOUNT', _pos, _isInt, 0, option, _err)
        self.req_cards('GROUPS', _pos, 'val == True', True, option, _err)
        return _err

    def _calculate_datasum(self, blocking):
        """
        Calculate the value for the ``DATASUM`` card in the HDU.
        """
        if self.__dict__.has_key('data') and self.data != None:
            # We have the data to be used.
            # Check the byte order of the data.  If it is little endian we
            # must swap it before calculating the datasum.
            byteorder = \
                     self.data.dtype.fields[self.data.dtype.names[0]][0].str[0]

            if byteorder != '>':
                byteswapped = True
                d = self.data.byteswap(True)
                d.dtype = d.dtype.newbyteorder('>')
            else:
                byteswapped = False
                d = self.data

            cs = self._compute_checksum(np.fromstring(d, dtype='ubyte'), blocking=blocking)

            # If the data was byteswapped in this method then return it to
            # its original little-endian order.
            if byteswapped:
                d.byteswap(True)
                d.dtype = d.dtype.newbyteorder('<')

            return cs
        else:
            # This is the case where the data has not been read from the file
            # yet.  We can handle that in a generic manner so we do it in the
            # base class.  The other possibility is that there is no data at
            # all.  This can also be handled in a gereric manner.
            return super(GroupsHDU,self)._calculate_datasum(blocking=blocking)


class GroupData(FITS_rec):
    """
    Random groups data object.

    Allows structured access to FITS Group data in a manner analogous
    to tables.
    """

    def __new__(subtype, input=None, bitpix=None, pardata=None, parnames=[],
                 bscale=None, bzero=None, parbscales=None, parbzeros=None):
        """
        Parameters
        ----------
        input : array or FITS_rec instance
            input data, either the group data itself (a
            `numpy.ndarray`) or a record array (`FITS_rec`) which will
            contain both group parameter info and the data.  The rest
            of the arguments are used only for the first case.

        bitpix : int
            data type as expressed in FITS ``BITPIX`` value (8, 16, 32,
            64, -32, or -64)

        pardata : sequence of arrays
            parameter data, as a list of (numeric) arrays.

        parnames : sequence of str
            list of parameter names.

        bscale : int
            ``BSCALE`` of the data

        bzero : int
            ``BZERO`` of the data

        parbscales : sequence of int
            list of bscales for the parameters

        parbzeros : sequence of int
            list of bzeros for the parameters
        """

        if not isinstance(input, FITS_rec):
            _formats = ''
            _cols = []
            if pardata is None:
                npars = 0
            else:
                npars = len(pardata)

            if parbscales is None:
                parbscales = [None]*npars
            if parbzeros is None:
                parbzeros = [None]*npars

            if bitpix is None:
                bitpix = _ImageBaseHDU.ImgCode[input.dtype.name]
            fits_fmt = GroupsHDU._dict[bitpix] # -32 -> 'E'
            _fmt = FITS2NUMPY[fits_fmt] # 'E' -> 'f4'
            _formats = (_fmt+',') * npars
            data_fmt = '%s%s' % (`input.shape[1:]`, _fmt)
            _formats += data_fmt
            gcount = input.shape[0]
            for i in range(npars):
                _cols.append(Column(name='c'+`i+1`,
                                    format = fits_fmt,
                                    bscale = parbscales[i],
                                    bzero = parbzeros[i]))
            _cols.append(Column(name='data',
                                format = fits_fmt,
                                bscale = bscale,
                                bzero = bzero))
            _coldefs = ColDefs(_cols)

            self = FITS_rec.__new__(subtype,
                                    rec.array(None,
                                              formats=_formats,
                                              names=_coldefs.names,
                                              shape=gcount))
            self._coldefs = _coldefs
            self.parnames = [i.lower() for i in parnames]

            for i in range(npars):
                (_scale, _zero)  = self._get_scale_factors(i)[3:5]
                if _scale or _zero:
                    self._convert[i] = pardata[i]
                else:
                    rec.recarray.field(self,i)[:] = pardata[i]
            (_scale, _zero)  = self._get_scale_factors(npars)[3:5]
            if _scale or _zero:
                self._convert[npars] = input
            else:
                rec.recarray.field(self,npars)[:] = input
        else:
             self = FITS_rec.__new__(subtype,input)
        return self

    def __getattribute__(self, attr):
        if attr == 'data':
            return self.field('data')
        else:
            return super(GroupData, self).__getattribute__(attr)

    def __getattr__(self, attr):
        if attr == '_unique':
            _unique = {}
            for i in range(len(self.parnames)):
                _name = self.parnames[i]
                if _name in _unique:
                    _unique[_name].append(i)
                else:
                    _unique[_name] = [i]
            self.__dict__[attr] = _unique
        try:
            return self.__dict__[attr]
        except KeyError:
            raise AttributeError(attr)

    def par(self, parName):
        """
        Get the group parameter values.
        """
        if isinstance(parName, (int, long, np.integer)):
            result = self.field(parName)
        else:
            indx = self._unique[parName.lower()]
            if len(indx) == 1:
                result = self.field(indx[0])

            # if more than one group parameter have the same name
            else:
                result = self.field(indx[0]).astype('f8')
                for i in indx[1:]:
                    result += self.field(i)

        return result

    def _getitem(self, key):
        row = (offset - self._byteoffset) // self._strides[0]
        return _Group(self, row)

    def __getitem__(self, key):
        return _Group(self,key,self.parnames)


class _Group(FITS_record):
    """
    One group of the random group data.
    """
    def __init__(self, input, row, parnames):
        super(_Group, self).__init__(input, row)
        self.parnames = parnames

    def __getattr__(self, attr):
        if attr == '_unique':
            _unique = {}
            for i in range(len(self.parnames)):
                _name = self.parnames[i]
                if _name in _unique:
                    _unique[_name].append(i)
                else:
                    _unique[_name] = [i]
            self.__dict__[attr] = _unique
        try:
             return self.__dict__[attr]
        except KeyError:
            raise AttributeError(attr)

    def __str__(self):
        """
        Print one row.
        """
        if isinstance(self.row, slice):
            if self.row.step:
                step = self.row.step
            else:
                step = 1

            if self.row.stop > len(self.array):
                stop = len(self.array)
            else:
                stop = self.row.stop

            outlist = []

            for i in range(self.row.start, stop, step):
                rowlist = []

                for j in range(self.array._nfields):
                    rowlist.append(`self.array.field(j)[i]`)

                outlist.append(" (" + ", ".join(rowlist) + ")")

            return "[" + ",\n".join(outlist) + "]"
        else:
            return super(_Group, self).__str__()

    def par(self, parName):
        """
        Get the group parameter value.
        """
        if isinstance(parName, (int, long, np.integer)):
            result = self.array[self.row][parName]
        else:
            indx = self._unique[parName.lower()]
            if len(indx) == 1:
                result = self.array[self.row][indx[0]]

            # if more than one group parameter have the same name
            else:
                result = self.array[self.row][indx[0]].astype('f8')
                for i in indx[1:]:
                    result += self.array[self.row][i]

        return result


    def setpar(self, parName, value):
        """
        Set the group parameter value.
        """
        if isinstance(parName, (int, long, np.integer)):
            self.array[self.row][parName] = value
        else:
            indx = self._unique[parName.lower()]
            if len(indx) == 1:
                self.array[self.row][indx[0]] = value

            # if more than one group parameter have the same name, the
            # value must be a list (or tuple) containing arrays
            else:
                if isinstance(value, (list, tuple)) and len(indx) == len(value):
                    for i in range(len(indx)):
                        self.array[self.row][indx[i]] = value[i]
                else:
                    raise ValueError, "parameter value must be a sequence " + \
                                      "with %d arrays/numbers." % len(indx)


