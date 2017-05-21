# Licensed under a 3-clause BSD style license - see LICENSE.rst
"""
``fitsheader`` is a command line script based on pyfits for printing the
header(s) of one or more FITS file(s) to the standard output in a human-
readable format.

Example uses of fitsheader:

1. Print the header of all the HDUs of a .fits file::

    $ fitsheader filename.fits

2. Print the header of the third and fifth HDU extension::

    $ fitsheader --extension 3 --extension 5 filename.fits

3. Print the header of a named extension, e.g. select the HDU containing
   keywords EXTNAME='SCI' and EXTVER='2'::

    $ fitsheader --extension "SCI,2" filename.fits

4. Print only specific keywords::

    $ fitsheader --keyword BITPIX --keyword NAXIS filename.fits

5. Print keywords NAXIS, NAXIS1, NAXIS2, etc using a wildcard::

    $ fitsheader --keyword NAXIS* filename.fits

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


class ExtensionNotFoundException(Exception):
    """Raised if an HDU extension requested by the user does not exist."""
    pass


class HeaderFormatter(object):
    """Class to format the header(s) of a FITS file for display by the
    `fitsheader` tool; essentially a wrapper around a `HDUList` object.

    Example usage:
    fmt = HeaderFormatter('/path/to/file.fits')
    print(fmt.parse(extensions=[0, 3], keywords=['NAXIS', 'BITPIX']))

    Parameters
    ----------
    filename : str
        Path to a single FITS file.

    Raises
    ------
    IOError
        If `filename` does not exist or cannot be read.
    """
    def __init__(self, filename):
        self.filename = filename
        self._hdulist = pyfits.open(filename)

    def parse(self, extensions=None, keywords=None, compressed=False):
        """Returns the FITS file header(s) in a readable format.

        Parameters
        ----------
        extensions : list of int or str, optional
            Format only specific HDU(s), identified by number or name.
            The name can be composed of the "EXTNAME" or "EXTNAME,EXTVER"
            keywords.

        keywords : list of str, optional
            Keywords for which the value(s) should be returned.
            If not specified, then the entire header is returned.

        compressed : boolean, optional
            If True, shows the header describing the compression, rather than
            the header obtained after decompression. (Affects FITS files
            containing `CompImageHDU` extensions only.)

        Returns
        -------
        formatted_header : str or astropy.table.Table
            Traditional 80-char wide format in the case of `HeaderFormatter`;
            an Astropy Table object in the case of `TableHeaderFormatter`.
        """
        # `hdukeys` will hold the keys of the HDUList items to display
        if extensions is None:
            hdukeys = list(range(len(self._hdulist)))  # Display all by default
        else:
            hdukeys = []
            for ext in extensions:
                try:
                    # HDU may be specified by number
                    hdukeys.append(int(ext))
                except ValueError:
                    # The user can specify "EXTNAME" or "EXTNAME,EXTVER"
                    parts = ext.split(',')
                    if len(parts) > 1:
                        extname = ','.join(parts[0:-1])
                        extver = int(parts[-1])
                        hdukeys.append((extname, extver))
                    else:
                        hdukeys.append(ext)

        # Having established which HDUs the user wants, we now format these:
        return self._parse_internal(hdukeys, keywords, compressed)

    def _parse_internal(self, hdukeys, keywords, compressed):
        """The meat of the formatting; in a separate method to allow overriding.
        """
        result = []
        for idx, hdu in enumerate(hdukeys):
            try:
                cards = self._get_cards(hdu, keywords, compressed)

                if idx > 0:  # Separate HDUs by a blank line
                    result.append('\n')
                result.append('# HDU {hdu} in {filename}:\n'.format(
                              filename=self.filename,
                              hdu=hdu
                              ))
                result.append('{0}\n'.format('\n'.join([str(c)
                                                        for c in cards])))
            except ExtensionNotFoundException:
                pass
        return ''.join(result)

    def _get_cards(self, hdukey, keywords, compressed):
        """Returns a list of `pyfits.card.Card` objects.

        This function will return the desired header cards, taking into
        account the user's preference to see the compressed or uncompressed
        version.

        Parameters
        ----------
        hdukey : int or str
            Key of a single HDU in the HDUList.

        keywords : list of str, optional
            Keywords for which the cards should be returned.

        compressed : boolean, optional
            If True, shows the header describing the compression.

        Raises
        ------
        ExtensionNotFoundException
            If the hdukey does not correspond to an extension.
        """
        # First we obtain the desired header
        try:
            if compressed:
                # In the case of a compressed image, return the header before
                # decompression (not the default behavior)
                header = self._hdulist[hdukey]._header
            else:
                header = self._hdulist[hdukey].header
        except (IndexError, KeyError):
            message = '{0}: Extension {1} not found.'.format(self.filename,
                                                             hdukey)
            log.warning(message)
            raise ExtensionNotFoundException(message)

        if not keywords:  # return all cards
            cards = header.cards
        else:  # specific keywords are requested
            cards = []
            for kw in keywords:
                try:
                    crd = header.cards[kw]
                    if isinstance(crd, pyfits.card.Card):  # Single card
                        cards.append(crd)
                    else:  # Allow for wildcard access
                        cards.extend(crd)
                except KeyError as e:  # Keyword does not exist
                    log.warning('{filename} (HDU {hdukey}): '
                                'Keyword {kw} not found.'.format(
                                    filename=self.filename,
                                    hdukey=hdukey,
                                    kw=kw))
        return cards


def print_headers_traditional(args):
    """Prints FITS header(s) using the traditional 80-char format.

    Parameters
    ----------
    args : argparse.Namespace
        Arguments passed from the command-line as defined below.
    """
    for idx, filename in enumerate(args.filename):  # support wildcards
        if idx > 0 and not args.keywords:
            print()  # print a newline between different files
        try:
            formatter = HeaderFormatter(filename)
            print(formatter.parse(args.extensions,
                                  args.keywords,
                                  args.compressed), end='')
        except IOError as e:
            log.error(str(e))


def main(args=None):
    """This is the main function called by the `fitsheader` script."""

    parser = argparse.OptionParser(
        description=('Print the header(s) of a FITS file. '
                     'Optional arguments allow the desired extension(s), '
                     'keyword(s), and output format to be specified. '
                     'Note that in the case of a compressed image, '
                     'the decompressed header is shown by default.'))
    parser.add_option('-e', '--ext', metavar='HDU',
                      action='append', dest='extensions',
                      help='specify the extension by name or number; '
                           'this argument can be repeated '
                           'to select multiple extensions')
    parser.add_option('-k', '--keyword', metavar='KEYWORD',
                      action='append', dest='keywords',
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

    # Now print the desired headers
    try:
        print_headers_traditional(args)
    except IOError as e:
        # A 'Broken pipe' IOError may occur when stdout is closed prematurely,
        # eg. when calling `fitsheader file.fits | head`. We let this pass.
        pass
