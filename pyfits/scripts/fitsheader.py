# Licensed under a 3-clause BSD style license - see LICENSE.rst
"""
``fitsheader`` is a command line script based on pyfits for printing the
header(s) of one or more FITS file(s) to the standard output in a human-
readable format.

Example uses of fitsheader:

1. Print the header of all the HDUs of a .fits file::

    $ fitsheader filename.fits

2. Print the header of the third and fifth HDU extension::

    $ fitsheader --ext 3 --ext 5 filename.fits

3. Print the header of a named extension, e.g. to select the HDU with header
   keywords EXTNAME='SCI' and EXTVER='2'::

    $ fitsheader --ext "SCI,2" filename.fits

4. Print only specific keywords::

    $ fitsheader --keyword BITPIX --keyword NAXIS filename.fits

5. Print the headers of all fits files in a directory::

    $ fitsheader *.fits

Note that compressed images (HDUs of type
:class:`~pyfits.CompImageHDU`) really have two headers: a real
BINTABLE header to describe the compressed data, and a fake IMAGE header
representing the image that was compressed. PyFITS returns the latter by
default. You must supply the ``--compressed`` option if you require the real
header that describes the compression.

With PyFITS installed, please run ``fitsheader --help`` to see the full usage
documentation.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import optparse
import logging
import pyfits

log = logging.getLogger('fitscheck')


class FormattingException(Exception):
    """
    Exception raised if the header cannot be formatted for printing,
    e.g. because the user specified a non-existent HDU or keyword.
    """
    pass


class HeaderFormatter(object):
    """
    Base class to format the header(s) of a FITS file for terminal display.

    Parameters
    ----------
    filename : str
        Path to the FITS file.

    compressed : boolean, optional
        show the header describing the compression (for CompImageHDU's only)
    """
    def __init__(self, filename, compressed=False):
        try:
            self.hdulist = pyfits.open(filename)
        except IOError as e:
            raise FormattingException(str(e))
        self.compressed = compressed

    def parse(self, extension=None, keywords=None):
        """
        Returns the FITS file header(s) in a readable format.

        Parameters
        ----------
        extension : list of int or str, optional
            Format only specific HDU(s), identified by number or name.
            In the case of a name, it should be specified using a string
            composed of the "EXTNAME" or "EXTNAME,EXTVER" keywords.

        keywords : list of str, optional
            Keywords for which the value(s) should be returned.
            If not specified, then the entire header is returned.

        Returns
        -------
        formatted_header : str
            Nicely formatted header information.
        """
        # `hdukeys` will hold the keys of the HDUList items to display
        if extension is None:
            hdukeys = range(len(self.hdulist))  # Display all by default
        else:
            hdukeys = []
            for myextension in extension:
                try:
                    # HDU may be specified by number
                    hdukeys.append(int(myextension))
                except ValueError:
                    # The user can specify "EXTNAME" or "EXTNAME,EXTVER"
                    parts = myextension.split(',')
                    if len(parts) > 1:
                        extname = ','.join(parts[0:-1])
                        extver = int(parts[-1])
                        hdukeys.append((extname, extver))
                    else:
                        hdukeys.append(myextension)

        # Having established which HDUs the user wants, we now format these:
        return self._parse_internal(hdukeys, keywords=keywords)

    def _parse_internal(self, hdukeys, keywords=None):
        """
        The meat of the parse method; in a separate method to allow overriding.
        """
        result = []
        for i, hdukey in enumerate(hdukeys):
            if i > 0:  # Separate different HDUs by a blank line
                result.append('\n')
            result.append('# HDU {hdukey} in {filename}:\n'.format(
                          filename=self.hdulist.filename(),
                          hdukey=hdukey
                          ))
            if keywords:  # Are specific keywords requested?
                for kw in keywords:
                    try:
                        card = self._get_header(hdukey).cards[kw]
                        if type(card) is pyfits.Card:
                            prettycard = str(card)
                        else:  # Allow for wildcard access
                            prettycard = '\n'.join([str(c) for c in card])
                        result.append('{0}\n'.format(prettycard))
                    except KeyError as e:  # Keyword does not exist
                        log.warning('{filename} (HDU {hdukey}): '
                                    'Keyword {kw} not found.'.format(
                                        filename=self.hdulist.filename(),
                                        hdukey=hdukey,
                                        kw=kw))
            else:  # Print the entire header instead of specific keywords
                result.append('{0}\n'.format(
                              self._get_header(hdukey)
                              .tostring(sep='\n', padding=False)
                              ))
        return ''.join(result)

    def _get_header(self, hdukey):
        """
        Returns the `pyfits.header.Header` object for an HDU.

        This function will return the desired header object, taking into
        account the user's preference to see the compressed or uncompressed
        version. A `FormattingException` is raised if `hdukey` is invalid.

        Parameters
        ----------
        hdukey : int or str
            Key of the HDU in the HDUList.
        """
        try:
            if self.compressed:
                # In the case of a compressed image, return the header before
                # decompression (not the default behavior)
                return self.hdulist[hdukey]._header
            else:
                return self.hdulist[hdukey].header
        except IndexError:
            raise FormattingException('{0}: Extension #{1} not found.'.
                                      format(self.hdulist.filename(), hdukey))
        except KeyError as e:
            raise FormattingException('{0}: {1}'.format(
                                      self.hdulist.filename(), str(e)))


def main(args=None):
    parser = argparse.OptionParser(
        description=('Print the header(s) of a FITS file. '
                     'Optional arguments allow the desired extension(s), '
                     'keyword(s), and output format to be specified. '
                     'Note that in the case of a compressed image, '
                     'the decompressed header is shown by default.'))
    parser.add_option('-e', '--ext', metavar='HDU', action='append',
                      help='specify the extension by name or number; '
                           'this argument can be repeated '
                           'to select multiple extensions')
    parser.add_option('-k', '--keyword', action='append',
                      help='specify a keyword; this argument can be '
                           'repeated to select multiple keywords; '
                           'also supports wildcards')
    parser.add_option('-c', '--compressed', action='store_true',
                      help='for compressed image data, '
                           'show the true header which describes '
                           'the compression rather than the data')
    parser.add_option('filename', nargs='+',
                      help='path to one or more files; '
                           'wildcards are supported')
    args = parser.parse_args(args)

    try:
        for i, filename in enumerate(args.filename):
            if i > 0 and not args.keyword:
                print()  # newline between different headers
            print(HeaderFormatter(filename, args.compressed)
                  .parse(args.ext, args.keyword), end='')
    except FormattingException as e:
        log.error(e)
    except IOError as e:
        # A 'Broken pipe' IOError may occur when stdout is closed prematurely,
        # eg when using `fitsheader file.fits | head`. We let this pass.
        pass
