from __future__ import division

import copy
import itertools
import os
import re
import warnings

from collections import defaultdict

from pyfits.card import Card, CardList, create_card, _pad, _int_or_float
from pyfits.file import _File, PYTHON_MODES
from pyfits.util import (BLOCK_SIZE, deprecated, isiterable, decode_ascii,
                         fileobj_mode, _pad_length)


HEADER_END_RE = re.compile('END {77}')


class Header(object):
    # TODO: Fix up this docstring and all other docstrings in the class
    """
    FITS header class.

    The purpose of this class is to present the header like a
    dictionary as opposed to a list of cards.

    The header class uses the card's keyword as the dictionary key and
    the cards value is the dictionary value.

    The header may be indexed by keyword value and like a dictionary, the
    associated value will be returned.  When the header contains cards
    with duplicate keywords, only the value of the first card with the
    given keyword will be returned.  It is also possible to use a 2-tuple as
    the index in the form (keyword, n)--this returns the n-th value with that
    keyword, in the case where there are duplicate keywords.

    The header may also be indexed by card list index number.  In that
    case, the value of the card at the given index in the card list
    will be returned.
    """

    # TODO: Allow the header to take a few other types of inputs, for example
    # a list of (key, value) tuples, (key, value, comment) tuples, or a dict
    # of either key: value or key: (value, comment) mappings.  This could all
    # be handled by the underlying CardList I suppose.
    def __init__(self, cards=[], txtfile=None):
        """
        Construct a `Header` from an iterable and/or text file.

        Parameters
        ----------
        cards : A list of `Card` objects, (optional)
            The cards to initialize the header with.

        txtfile : file path, file object or file-like object (optional)
            Input ASCII header parameters file.
        """

        self.clear()
        self._modified = False

        if txtfile:
            warnings.warn(
                'The txtfile argument is deprecated.  Use Header.fromfile to '
                'create a new Header object from a text file.',
                DeprecationWarning)
            # get the cards from the input ASCII file
            self.update(self.fromfile(txtfile))
            return

        if isinstance(cards, Header):
            cards = cards.cards

        for card in cards:
            self.append(card, end=True)

    def __len__(self):
        return len(self._cards)

    def __iter__(self):
        for card in self._cards:
            yield card.keyword

    def __contains__(self, keyword):
        """
        Check for existence of a keyword.

        Parameters
        ----------
        key : str or int
           Keyword name.  If given an index, always returns 0.

        Returns
        -------
        has_key : bool
            Returns `True` if found, otherwise, `False`.
        """

        try:
            self._cardindex(keyword)
        except (KeyError, IndexError):
            return False
        return True

    def __getitem__ (self, key):
        """
        Get a header keyword value.  Slices return a new header.
        """

        if isinstance(key, slice):
            return Header([copy.copy(c) for c in self._cards[key]])
        elif self._haswildcard(key):
            return Header([copy.copy(self._cards[idx])
                           for idx in self._wildcardmatch(key)])
        elif (isinstance(key, basestring) and
              key.upper() in Card._commentary_keywords):
            key = key.upper()
            # Special case for commentary cards
            return _HeaderCommentaryCards(self, key)
        return self._cards[self._cardindex(key)].value

    def __setitem__ (self, key, value):
        """
        Set a header keyword value.
        """

        if isinstance(key, slice) or self._haswildcard(key):
            if isinstance(key, slice):
                indices = xrange(*key.indices(len(self)))
            else:
                indices = self._wildcardmatch(key)
            if isinstance(value, basestring) or not isiterable(value):
                value = itertools.repeat(value, len(indices))
            for idx, val in itertools.izip(indices, value):
                self[idx] = val
            return


        if isinstance(value, tuple):
            if not (0 < len(value) <= 2):
                raise ValueError(
                    'A Header item may be set with either a scalar value, '
                    'a 1-tuple containing a scalar value, or a 2-tuple '
                    'containing a scalar value and comment string.')
            if len(value) == 1:
                value, comment = value[0], None
                if value is None:
                    value = ''
            elif len(value) == 2:
                value, comment = value
                if value is None:
                    value = ''
                if comment is None:
                    comment = ''
        else:
            comment = None

        if isinstance(key, int):
            card = self._cards[key]
            card.value = value
            if comment is not None:
                card.comment = comment
            if card._modified:
                self._modified = True
        else:
            # If we get an IndexError that should be raised; we don't allow
            # assignment to non-existing indices
            self._update((key, value, comment))

    def __delitem__(self, key):
        """
        Delete card(s) with the name `key`.
        """

        if isinstance(key, slice) or self._haswildcard(key):
            # This is very inefficient but it's not a commonly used feature.
            # If someone out there complains that they make heavy use of slice
            # deletions and it's too slow, well, we can worry about it then
            # [the solution is not too complicated--it would be wait 'til all
            # the cards are deleted before updating _keyword_indices rather
            # than updating it once for each card that gets deleted]
            if isinstance(key, slice):
                indices = xrange(*key.indices(len(self)))
                # If the slice step is backwards we want to reverse it, because
                # it will be reversed in a few lines...
                if slice.step < 0:
                    indices = reversed(indices)
            else:
                indices = self._wildcardmatch(key)
            for idx in reversed(indices):
                del self[idx]
            return
        elif isinstance(key, basestring):
            # delete ALL cards with the same keyword name
            key = Card.normalize_keyword(key)
            if key not in self._keyword_indices:
                # TODO: The old Header implementation allowed deletes of
                # nonexistent keywords to pass
                # There needs to be a note in the documentation that this
                # behavior has changed
                raise KeyError("Keyword '%s' not found." % key)
            for idx in reversed(self._keyword_indices[key]):
                # Have to copy the indices list since it will be modified below
                del self[idx]
            return

        idx = self._cardindex(key)
        keyword = self._cards[idx].keyword
        del self._cards[idx]
        indices = self._keyword_indices[keyword]
        indices.remove(idx)
        if not indices:
            del self._keyword_indices[keyword]

        # We also need to update all other indices
        self._updateindices(idx, increment=False)
        self._modified = True

    def __repr__(self):
        return self.tostring(sep='\n', endcard=False, padding=False)

    def __str__(self):
        return self.tostring()

    def __add__(self, other):
        temp = self.copy(strip=False)
        temp.extend(other)
        return temp

    def __iadd__(self, other):
        self.extend(other)
        return self

    @property
    def cards(self):
        """
        The underlying physical cards that make up this Header; it can be
        looked at, but it should not be modified directly.
        """

        return tuple(self._cards)

    @property
    def comments(self):
        """View the comments associated with each keyword, if any."""

        return _HeaderComments(self)

    @classmethod
    def fromstring(cls, data, sep=''):
        """
        Creates an HDU header from a byte string containing the entire header
        data.

        Parameters
        ----------
        data : str
           String containing the entire header.

        sep : str (optional)
            The string separating cards from each other, such as a newline.  By
            default there is no card separator.
        """

        actual_block_size = _block_size(sep)

        if (len(data) % actual_block_size) != 0:
            # This error message ignores the length of the separator for now,
            # but maybe it shouldn't?
            raise ValueError('Header size is not multiple of %d: %d'
                             % (BLOCK_SIZE,
                                len(data) - actual_block_size + BLOCK_SIZE))

        cards = []

        # Split the header into individual cards
        idx = 0

        def peeknext():
            if idx + Card.length < len(data):
                return data[idx + Card.length:idx + Card.length * 2]
            else:
                return None

        end = 'END' + ' ' * 77

        while idx < len(data):
            image = [data[idx:idx + Card.length]]
            if image[0] == end:
                break

            next = peeknext()
            while next and next[:8] == 'CONTINUE':
                image.append(next)
                idx += Card.length + len(sep)
                next = peeknext()

            cards.append(Card.fromstring(''.join(image)))
            idx += Card.length

        return cls(cards)

    @classmethod
    def fromfile(cls, fileobj, sep='', endcard=True):
        close_file = False
        if isinstance(fileobj, basestring):
            fileobj = open(fileobj, 'r')
            close_file = True

        actual_block_size = _block_size(sep)

        try:
            # Read the first header block.
            block = decode_ascii(fileobj.read(actual_block_size))
            if block == '':
                raise EOFError()

            blocks = []

            # continue reading header blocks until END card is reached
            while True:
                # find the END card
                mo = HEADER_END_RE.search(block)
                if mo is None:
                    blocks.append(block)
                    block = decode_ascii(fileobj.read(actual_block_size))
                    if block == '':
                        break
                else:
                    break
            blocks.append(block)

            if not HEADER_END_RE.search(block) and endcard:
                raise IOError('Header missing END card.')

            return cls.fromstring(''.join(blocks), sep=sep)
        finally:
            if close_file:
                fileobj.close()

    def tostring(self, sep='', endcard=True, padding=True):
        """
        Returns a string representation of the header.

        By default this uses no
        separator between cards, adds the END card, and pads the string with
        spaces to the next multiple of 2880 bytes.  That is, it returns the
        header exactly as it would appear in a FITS file.

        Parameters
        ----------
        sep : str (optional)
            The character or string with which to separate cards.  By default
            there is no separator, but one could use '\n', for example, to
            separate each card with a new line

        endcard : bool (optional)
            If True (default) adds the END card to the end of the header
            string

        padding : bool (optiona)
            If True (default) pads the string with spaces out to the next
            multiple of 2880 characters
        """

        s = sep.join(str(card) for card in self._cards)
        if endcard:
            s += sep + _pad('END')
        if padding:
            s += ' ' * _pad_length(len(s))
        return s

    def tofile(self, fileobj, sep='', endcard=True, padding=True,
               clobber=False):
        """
        Writes the header to file or file-like object.

        By default this writes the header exactly as it would be written to a
        FITS file, with the END card included and padding to the next multiple
        of 2880 bytes.  However, aspects of this may be controlled.

        Parameters
        ----------
        fileobj : str, file (optional)
            Either the pathname of a file, or an open file handle or file-like
            object

        sep : str (optional)
            The character or string with which to separate cards.  By default
            there is no separator, but one could use `'\n'`, for example, to
            separate each card with a new line

        endcard : bool (optional)
            If `True` (default) adds the END card to the end of the header
            string

        padding : bool (optional)
            If `True` (default) pads the string with spaces out to the next
            multiple of 2880 characters

        clobber : bool (optional)
            If `True`, overwrites the output file if it already exists
        """

        close_file = False

        # check if the output file already exists
        # TODO: Perhaps this sort of thing could be handled by the _File
        # initializer...
        if isinstance(fileobj, basestring):
            if os.path.exists(fileobj) and os.path.getsize(fileobj) != 0:
                if clobber:
                    warnings.warn("Overwriting existing file '%s'." % fileobj)
                    os.remove(fileobj)
                else:
                    raise IOError("File '%s' already exists." % fileobj)

            fileobj = open(fileobj, 'w')
            close_file = True

        if not isinstance(fileobj, _File):
            # TODO: There needs to be a way of handling this built into the
            # _File class.  I think maybe there used to be, but I took it out;
            # now the design is such that it would be better for it to go back
            # in
            mode = 'append'
            fmode = fileobj_mode(fileobj) or 'ab+'
            for key, val in PYTHON_MODES.iteritems():
                if val == fmode:
                    mode = key
                    break
            fileobj = _File(fileobj, mode=mode)

        try:
            blocks = self.tostring(sep=sep, endcard=endcard, padding=padding)
            actual_block_size = _block_size(sep)
            if padding and len(blocks) % actual_block_size != 0:
                raise IOError('Header size (%d) is not a multiple of block '
                              'size (%d).' %
                              (len(blocks) - actual_block_size + BLOCK_SIZE,
                               BLOCK_SIZE))

            if not fileobj.simulateonly:
                fileobj.flush()
                try:
                    offset = fileobj.tell()
                except (AttributeError, IOError):
                    offset = 0
                fileobj.write(blocks.encode('ascii'))
                fileobj.flush()
        finally:
            if close_file:
                fileobj.close()

    def clear(self):
        """
        Remove all cards from the header.
        """

        self._cards = []
        self._keyword_indices = defaultdict(list)

    def copy(self, strip=False):
        """
        Make a copy of the `Header`.

        Parameters
        ----------
        strip : bool (optional)
           If True, strip any headers that are specific to one of the standard
           HDU types, so that this header can be used in a different HDU.
        """

        tmp = Header([copy.copy(card) for card in self._cards])
        if strip:
            tmp._strip()
        return tmp

    @classmethod
    def fromkeys(cls, iterable, value=None):
        d = cls()
        if not isinstance(value, tuple):
            value = (value,)
        for key in iterable:
            d.append((key,) + value)
        return d

    def get(self, key, default=None):
        try:
            return self[key]
        except (KeyError, IndexError):
            return default

    def set(self, keyword, value=None, comment=None, before=None, after=None):
        """
        Set the value and/or comment and/or position of a specified keyword.

        If the keyword does not already exist in the header, a new keyword is
        created in the specified position, or appended to the end of the header
        if no position is specified.

        This method is similar to `Header.update()` prior to PyFITS 3.1.

        It should be noted that header.set(keyword, value) and
        header.set(keyword, value, comment) are equivalent to
        header[keyword] = value and header[keyword] = (value, comment)
        respectfully.  The main advantage to using `Header.set()` is that it
        may also specify the required location of the keyword using the before
        or after arguments.

        Parameters
        ----------
        keyword : str
            A header keyword

        value : str (optional)
            The value to set for the given keyword; if None the existing value
            is kept, but '' may be used to set a blank value

        comment : str (optional)
            The comment to set for the given keyword; if None the existing
            comment is kept, but '' may be used to set a blank comment

        before : str, int (optional)
            Name of the keyword, or index of the `Card` before which
            this card should be located in the header.  The argument `before`
            takes precedence over `after` if both specified.

        after : str, int (optional)
            Name of the keyword, or index of the `Card` after which this card
            should be located in the header.

        """

        # Create a temporary card that looks like the one being set; if the
        # temporary card turns out to be a RVKC this will make it easier to
        # deal with the idiosyncrasies thereof
        new_card = Card(keyword, value, comment)

        if new_card.keyword in self:
            if comment is None:
                comment = self.comments[keyword]
            if value is None:
                value = self[keyword]

            setval = (value, comment)

            if before is None and after is None:
                self[keyword] = setval
            else:
                self[keyword] = setval
                idx = self._cardindex(keyword)
                card = self._cards[idx]
                del self[idx]
                self._relativeinsert(card, before=before, after=after)
        elif before is not None or after is not None:
            self._relativeinsert((keyword, value, comment), before=before,
                                 after=after)
        else:
            self[keyword] = (value, comment)

    @deprecated(alternative='`key in header` syntax')
    def has_key(self, key):
        return key in self

    def items(self):
        return list(self.iteritems())

    def iteritems(self):
        for card in self._cards:
            yield (card.keyword, card.value)

    def iterkeys(self):
        return self.__iter__()

    def itervalues(self):
        for _, v in self.iteritems():
            yield v

    def keys(self):
        """
        Return a list of keys with duplicates removed.
        """

        seen = set()
        retval = []

        for card in self._cards:
            # Blank keywords are ignored
            keyword = card.keyword
            if keyword and keyword not in seen:
                seen.add(keyword)
                retval.append(keyword)

        return retval

    def pop(self, *args):
        """
        Works like list.pop() if no arguments or an index argument are
        supplied; otherwise works like dict.pop().
        """

        if len(args) > 2:
            raise TypeError('Header.pop expected at most 2 arguments, got '
                            '%d' % len(args))

        if len(args) == 0:
            key = -1
        else:
            key = args[0]

        try:
            value = self[key]
        except (KeyError, IndexError):
            if len(args) == 2:
                return args[1]
            raise

        del self[key]
        return value

    def popitem(self):
        try:
            k, v = self.iteritems().next()
        except StopIteration:
            raise KeyError('Header is empty')
        del self[k]
        return k, v

    def setdefault(self, key, default=None):
        try:
            return self[key]
        except (KeyError, IndexError):
            self[key] = default
        return default

    def update(self, *args, **kwargs):
        """
        Update the Header with new keyword values, updating the values of
        existing keywords and appending new keywords otherwise; similar to
        dict.update().

        update() accepts either a dict-like object or an iterable.  In the
        former case the keys must be header keywords and the values may be
        either scalar values or (value, comment) tuples.  In the case of an
        iterable the items must be (keyword, value) tuples or
        (keyword, value, comment) tuples.

        Arbitrary arguments are also accepted, in which case the update() is
        called again with the kwargs dict as its only argument.

        Parameters
        ----------
        other : dict, iterable (optional)
            The dict or iterable from which to update the Header

        Note: As this method works similarly to dict.update() it is very
        different from the Header.update() method in PyFITS versions prior to
        3.1.0.  However, support for the old API is also maintained for
        backwards compatibility.  If update() is called with at least two
        positional arguments then it can be assumed that the old API is being
        used.  For reference, the old documentation is provided below:

        Update one header card.

        If the keyword already exists, it's value and/or comment will
        be updated.  If it does not exist, a new card will be created
        and it will be placed before or after the specified location.
        If no `before` or `after` is specified, it will be appended at
        the end.

        Parameters
        ----------
        key : str
            keyword

        value : str
            value to be used for updating

        comment : str (optional)
            to be used for updating, default=None.

        before : str, int (optional)
            name of the keyword, or index of the `Card` before which
            the new card will be placed.  The argument `before` takes
            precedence over `after` if both specified.

        after : str, int (optional)
            name of the keyword, or index of the `Card` after which
            the new card will be placed.

        savecomment : bool (optional)
            When `True`, preserve the current comment for an existing
            keyword.  The argument `savecomment` takes precedence over
            `comment` if both specified.  If `comment` is not
            specified then the current comment will automatically be
            preserved.

        """

        legacy_kwargs = ['comment', 'before', 'after', 'savecomment']

        if len(args) >= 2:
            # This must be a legacy update()
            # TODO: Issue a deprecation warning for this; tell the user to use
            # Header.set() instead
            keyword = args[0]
            value = args[1]
            for k, v in zip(legacy_kwargs, args[2:]):
                if k in kwargs:
                    raise TypeError(
                        '%s.update() got multiple values for keyword '
                        'argument %r' % (self.__class__.__name__, k))
                kwargs[k] = v

            comment = kwargs.get('comment')
            before = kwargs.get('before')
            after = kwargs.get('after')
            savecomment = kwargs.get('savecomment')

            # Handle the savecomment argument which is not currently used by
            # Header.set()
            if keyword in self and savecomment:
                comment = None

            self.set(keyword, value, comment, before, after)
        else:
            # The rest of this should work similarly to dict.update()
            if args:
                other = args[0]
            else:
                other = None

            def update_from_dict(k, v):
                if not isinstance(v, tuple):
                    card = Card(k, v)
                elif 0 < len(v) <= 2:
                    card = Card(*((k,) + v))
                else:
                    raise ValueError(
                            'Header update value for key %r is invalid; the '
                            'value must be either a scalar, a 1-tuple '
                            'containing the scalar value, or a 2-tuple '
                            'containing the value and a comment string.' % k)
                self._update(card)

            if other is None:
                pass
            elif hasattr(other, 'iteritems'):
                for k, v in other.iteritems():
                    update_from_dict(k, v)
            elif hasattr(other, 'keys'):
                for k in other.keys():
                    update_from_dict(k, other[k])
            else:
                for idx, card in enumerate(other):
                    if isinstance(card, Card):
                        self._update(card)
                    elif isinstance(card, tuple) and (1 < len(card) <= 3):
                        self._update(Card(*card))
                    else:
                        raise ValueError(
                                'Header update sequence item #%d is invalid; '
                                'the item must either be a 2-tuple containing '
                                'a keyword and value, or a 3-tuple containing '
                                'a keyword, value, and comment string.' % idx)
            if kwargs:
                self.update(kwargs)

    def values(self):
        """Returns a list of the values of all cards in the header."""

        return [v for _, v in self.iteritems()]

    def append(self, card=None, useblanks=True, bottom=False, end=False):
        """
        Appends a new keyword+value card to the end of the Header, similar
        to list.append().

        By default if the last cards in the Header have commentary keywords,
        this will append the new keyword before the commentary.

        Also differs from list.append() in that it can be called with no
        arguments: In this case a blank card is appended to the end of the
        Header.  In the case all the keyword arguments are ignored.

        Paramters
        ---------
        card : str, tuple
            A keyword or a (keyword, value, [comment]) tuple representing a
            single header card; the comment is optional in which case a
            2-tuple may be used

        useblanks : bool (optional)
            If there are blank cards at the end of the Header, replace the
            first blank card so that the total number of cards in the Header
            does not increase.  Otherwise preserve the number of blank cards.

        bottom : bool (optional)
            If True, instead of appending after the last non-commentary card,
            append after the last non-blank card.

        end : bool (optional):
            If True, ignore the useblanks and bottom options, and append at the
            very end of the Header.

        """

        if isinstance(card, basestring):
            card = Card(card)
            self._cards.append(card)
        elif isinstance(card, tuple):
            card = Card(*card)
        elif card is None:
            card = Card()
        elif not isinstance(card, Card):
            raise ValueError(
                'The value appended to a Header must be either a keyword or '
                '(keyword, value, [comment]) tuple; got: %r' % card)

        blank = ' ' * Card.length
        if str(card) == blank:
            # Blank cards should always just be appended to the end
            end = True

        if end:
            self._cards.append(card)
            idx = len(self._cards) - 1
        else:
            idx = len(self._cards) - 1
            while idx >=0 and str(self._cards[idx]) == blank:
                idx -= 1

            if not bottom:
                while (idx >= 0 and
                       self._cards[idx].keyword in Card._commentary_keywords):
                    idx -= 1

            idx += 1
            self._cards.insert(idx, card)
            self._updateindices(idx)

        keyword = card.keyword
        self._keyword_indices[keyword].append(idx)

        if not end:
            # If the appended card was a commentary card, and it was appended
            # before existing cards with the same keyword, the indices for
            # cards with that keyword may have changed
            if not bottom and card.keyword in Card._commentary_keywords:
                self._keyword_indices[keyword].sort()

            # Finally, if useblanks, delete a blank cards from the end
            if useblanks:
                self._useblanks(len(str(card)) // Card.length)

        self._modified = True

    def extend(self, cards, strip=True):
        """
        Appends multiple keyword+value cards to the end of the header, similar
        to list.extend().

        Parameters
        ----------
        cards : iterable
            An iterable of (keyword, value, [comment]) tuples; see
            Header.append()

        strip : bool (optional)
            Remove any keywords that have meaning only to specific types of
            HDUs, so that only more general keywords are added from extension
            Header or Card list (default: True).
        """

        temp = Header(cards)
        if strip:
            temp._strip()

        for card in temp.cards:
            self.append(card)

    def count(self, keyword):
        """
        Returns the count of the given keyword in the header, similar to
        list.count() if the Header object is treated as a list of keywords.

        Parameters
        ----------
        keyword : str
            The keyword to count instances of in the header

        """

        # We have to look before we leap, since otherwise _keyword_indices,
        # being a defaultdict, will create an entry for the nonexistent keyword
        if keyword not in self._keyword_indices:
            raise KeyError("Keyword %r not found." % keyword)
        return len(self._keyword_indices[keyword])

    def index(self, keyword, start=None, stop=None):
        """
        Returns the index if the first instance of the given keyword in the
        header, similar to list.index() if the Header object is treated as a
        list of keywords.

        Parameters
        ----------
        keyword : str
            The keyword to look up in the list of all keywords in the header

        start : int (optional)
            The lower bound for the index

        stop : int (optional)
            The upper bound for the index

        """

        if start is None:
            start = 0

        if stop is None:
            stop = len(self._cards)

        if stop < start:
            step = -1
        else:
            step = 1

        for idx in xrange(start, stop, step):
            if self._cards[idx].keyword == keyword:
                return idx
        else:
            raise ValueError('The keyword %r is not in the header.' % keyword)

    def insert(self, idx, card, useblanks=True):
        """
        Inserts a new keyword+value card into the Header at a given location,
        similar to list.insert().

        Parameters
        ----------
        idx : int
            The index into the the list of header keywords before which the
            new keyword should be inserted

        card : str, tuple
            A keyword or a (keyword, value, [comment]) tuple; see
            Header.append()

        useblanks : bool (optional)
            If there are blank cards at the end of the Header, replace the
            first blank card so that the total number of cards in the Header
            does not increase.  Otherwise preserve the number of blank cards.

        """

        if idx >= len(self._cards):
            # This is just an append
            self.append(card)
            return

        if isinstance(card, basestring):
            card = Card(card)
        elif isinstance(card, tuple):
            card = Card(*card)
        elif not isinstance(card, Card):
            raise ValueError(
                'The value inserted into a Header must be either a keyword or '
                '(keyword, value, [comment]) tuple; got: %r' % card)

        self._cards.insert(idx, card)

        keyword = card.keyword

        # If idx was < 0, determine the actual index according to the rules
        # used by list.insert()
        if idx < 0:
            idx += len(self._cards) - 1
            if idx < 0:
                idx = 0

        # All the keyword indices above the insertion point must be updated
        self._updateindices(idx)

        self._keyword_indices[keyword].append(idx)
        count = len(self._keyword_indices[keyword])
        if count > 1:
            # There were already keywords with this same name
            # TODO: Maybe issue a warning when this occurs (and the keyword is
            # non-commentary)
            self._keyword_indices[keyword].sort()

        if useblanks:
            self._useblanks(len(str(card)) // Card.length)

        self._modified = True

    def remove(self, keyword):
        """
        Removes the first instance of the given keyword from the header
        similar to list.remove() if the Header object is treated as a list of
        keywords.

        Parameters
        ----------
        value : str
            The keyword of which to remove the first instance in the header

        """

        del self[self.index(keyword)]

    def _update(self, card):
        """
        The real update code.  If keyword already exists, its value and/or
        comment will be updated.  Otherwise a new card will be appended.

        This will not create a duplicate keyword except in the case of
        commentary cards.  The only other way to force creation of a duplicate
        is to use the insert(), append(), or extend() methods.
        """

        if not isinstance(card, Card):
            comment = card[-1]
            card = Card(*card)
        else:
            comment = card.comment

        keyword = card.keyword

        if (keyword not in Card._commentary_keywords and
                keyword in self._keyword_indices):
            # Easy; just update the value/comment
            idx = self._keyword_indices[keyword][0]
            existing_card = self._cards[idx]
            existing_card.value = card.value
            if comment is not None:
                # '' should be used to explictly blank a comment
                existing_card.comment = card.comment
            if existing_card._modified:
                self._modified = True
        elif keyword in Card._commentary_keywords:
            # Append after the last keyword of the same type
            idx = self.index(keyword, start=len(self) - 1, stop=-1)
            isblank = not (card.keyword or card.value or card.comment)
            self.insert(idx + 1, card, useblanks=(not isblank))
        else:
            # A new keyword! self.append() will handle updating _modified
            self.append(card)

    def _cardindex(self, key):
        """Returns an index into the ._cards list given a valid lookup key."""

        if isinstance(key, slice):
            return key
        elif isinstance(key, int):
            # If < 0, determine the actual index
            if key < 0:
                key += len(self._cards)
            if key < 0 or key >= len(self._cards):
                raise IndexError('Header index out of range.')
            return key


        if isinstance(key, basestring):
            key = (Card.normalize_keyword(key), 0)

        if isinstance(key, tuple):
            if (len(key) != 2 or not isinstance(key[0], basestring) or
                    not isinstance(key[1], int)):
                raise ValueError(
                        'Tuple indices must be 2-tuples consisting of a '
                        'keyword string and an integer index.')
            keyword, n = key
            keyword = Card.normalize_keyword(keyword)
            # Returns the index into _cards for the n-th card with the given
            # keyword (where n is 0-based)
            if keyword not in self._keyword_indices:
                if len(keyword) > 8:
                    raise KeyError("Keyword %r not found." % keyword)
                # Great--now we have to check if there's a RVKC that starts
                # with the given keyword, making failed lookups fairly
                # expensive
                # TODO: Have a flag for whether or not the header contains any
                # RVKCs (the most common case) so that we can avoid having to
                # deal with them when possible
                keyword = keyword + '.'
                found = 0
                for idx, card in enumerate(self._cards):
                    if (card.field_specifier and
                        card.keyword.startswith(keyword)):
                        if found == n:
                            return idx
                        found += 1
                else:
                    raise KeyError("Keyword %r not found." % keyword)
            try:
                return self._keyword_indices[keyword][n]
            except IndexError:
                raise IndexError('There are only %d %r cards in the header.' %
                                 (len(self._keyword_indices[keyword]),
                                  keyword))
        else:
            raise ValueError(
                    'Header indices must be either a string, a 2-tuple, or '
                    'an integer.')
        # TODO: Handle and reraise key/index errors as well.

    def _relativeinsert(self, card, before=None, after=None):
        """
        Inserts a new card before or after an existing card; used to
        implement support for the legacy before/after keyword arguments to
        Header.update().
        """

        if before is None:
            insertionkey = after
        else:
            insertionkey = before
        if not (isinstance(insertionkey, int) and
                insertionkey >= len(self._cards)):
            # Don't bother looking up the card index if idx is above the last
            # card--this just means append to the end, and would otherwise
            # result in an IndexError
            idx = self._cardindex(insertionkey)
        else:
            idx = insertionkey
        if before is not None:
            self.insert(idx, card)
        else:
            self.insert(idx + 1, card)

    def _updateindices(self, idx, increment=True):
        """
        For all cards with index above idx, increment or decrement its index
        value in the keyword_indices dict.
        """

        if idx > len(self._cards):
            # Save us some effort
            return

        increment = 1 if increment else -1

        for indices in self._keyword_indices.itervalues():
            for jdx, keyword_index in enumerate(indices):
                if keyword_index >= idx:
                    indices[jdx] += increment

    def _countblanks(self):
        """Returns the number of blank cards at the end of the Header."""

        blank = ' ' * 80
        for idx in xrange(1, len(self._cards)):
            if str(self._cards[-idx]) != blank:
                return idx - 1
        return 0

    def _useblanks(self, count):
        blank = ' ' * 80
        for _ in range(count):
            if str(self._cards[-1]) == blank:
                del self[-1]
            else:
                break

    def _haswildcard(self, keyword):
        """Return `True` if the input keyword contains a wildcard pattern."""

        return (isinstance(keyword, basestring) and
                (keyword.endswith('...') or '*' in keyword or '?' in keyword))

    def _wildcardmatch(self, pattern):
        """
        Returns a list of indices of the cards matching the given wildcard
        pattern.

         * '*' matches 0 or more alphanumeric characters or _
         * '?' matches a single alphanumeric character or _
         * '...' matches 0 or more of any non-whitespace character
        """

        pattern = pattern.replace('*', r'\w*').replace('?', r'\w')
        pattern = pattern.replace('...', r'\S*') + '$'
        pattern_re = re.compile(pattern, re.I)

        return [idx for idx, card in enumerate(self._cards)
                if pattern_re.match(card.keyword)]

    def _strip(self):
        """
        Strip cards specific to a certain kind of header.

        Strip cards like ``SIMPLE``, ``BITPIX``, etc. so the rest of
        the header can be used to reconstruct another kind of header.
        """

        # TODO: Previously this only deleted some cards specific to an HDU if
        # _hdutype matched that type.  But it seemed simple enough to just
        # delete all desired cards anyways, and just ignore the KeyErrors if
        # they don't exist.
        # However, it might be desirable to make this extendable somehow--have
        # a way for HDU classes to specify some headers that are specific only
        # to that type, and should be removed otherwise.

        if 'NAXIS' in self:
            naxis = self['NAXIS']
        else:
            naxis = 0

        if 'TFIELDS' in self:
            tfields = self['TFIELDS']
        else:
            tfields = 0

        for idx in range(naxis):
            try:
                del self['NAXIS' + str(idx + 1)]
            except KeyError:
                pass

        for name in ('TFORM', 'TSCAL', 'TZERO', 'TNULL', 'TTYPE',
                     'TUNIT', 'TDISP', 'TDIM', 'THEAP', 'TBCOL'):
            for idx in range(tfields):
                try:
                    del self[name + str(idx + 1)]
                except KeyError:
                    pass

        for name in ('SIMPLE', 'XTENSION', 'BITPIX', 'NAXIS', 'EXTEND',
                     'PCOUNT', 'GCOUNT', 'GROUPS', 'BSCALE', 'TFIELDS'):
            try:
                del self[name]
            except KeyError:
                pass


    # The following properties/methods are for legacy API backwards
    # compatibility

    @property
    def ascard(self):
        """
        Returns a CardList object wrapping this Header; provided for
        backwards compatibility for the old API (where Headers had an
        underlying CardList).
        """

        return CardList(self)

    @deprecated(alternative='the ascard attribute')
    def ascardlist(self):
        """
        Returns a `CardList` object.
        """

        return self.ascard

    def rename_key(self, oldkey, newkey, force=False):
        """
        Rename a card's keyword in the header.

        Parameters
        ----------
        oldkey : str or int
            old keyword

        newkey : str
            new keyword

        force : bool
            When `True`, if new key name already exists, force to have
            duplicate name.
        """

        oldkey = Card.normalize_keyword(oldkey)
        newkey = Card.normalize_keyword(newkey)

        if newkey == 'CONTINUE':
            raise ValueError('Can not rename to CONTINUE')

        if (newkey in Card._commentary_keywords or
            oldkey in Card._commentary_keywords):
            if not (newkey in Card._commentary_keywords and
                    oldkey in Card._commentary_keywords):
                raise ValueError('Regular and commentary keys can not be '
                                 'renamed to each other.')
        elif (force == 0) and newkey in self:
            raise ValueError('Intended keyword %s already exists in header.'
                             % newkey)

        idx = self.ascard.index_of(oldkey)
        comment = self.ascard[idx].comment
        value = self.ascard[idx].value
        self.ascard[idx] = create_card(newkey, value, comment)

    def add_history(self, value, before=None, after=None):
        """
        Add a ``HISTORY`` card.

        Parameters
        ----------
        value : str
            history text to be added.

        before : str or int, optional
            same as in `Header.update`

        after : str or int, optional
            same as in `Header.update`
        """

        self._add_commentary('HISTORY', value, before=before, after=after)

    def add_comment(self, value, before=None, after=None):
        """
        Add a ``COMMENT`` card.

        Parameters
        ----------
        value : str
            text to be added.

        before : str or int, optional
            same as in `Header.update`

        after : str or int, optional
            same as in `Header.update`
        """

        self._add_commentary('COMMENT', value, before=before, after=after)

    def add_blank(self, value='', before=None, after=None):
        """
        Add a blank card.

        Parameters
        ----------
        value : str, optional
            text to be added.

        before : str or int, optional
            same as in `Header.update`

        after : str or int, optional
            same as in `Header.update`
        """

        self._add_commentary(' ', value, before=before, after=after)

    @deprecated(alternative="header['HISTORY']", pending=True)
    def get_history(self):
        """
        Get all history cards as a list of string texts.
        """

        return self['HISTORY']

    @deprecated(alternative="header['COMMENT']", pending=True)
    def get_comment(self):
        """
        Get all comment cards as a list of string texts.
        """

        return self['COMMENT']

    @deprecated(alternative="tofile(sep='\n', endcard=False, padding=False)")
    def toTxtFile(self, fileobj, clobber=False):
        """
        Output the header parameters to a file in ASCII format.

        Parameters
        ----------
        fileobj : file path, file object or file-like object
            Output header parameters file.

        clobber : bool
            When `True`, overwrite the output file if it exists.
        """

        self.tofile(fileobj, sep='\n', endcard=False, padding=False)

    def fromTxtFile(self, fileobj, replace=False):
        """
        Input the header parameters from an ASCII file.

        The input header cards will be used to update the current
        header.  Therefore, when an input card key matches a card key
        that already exists in the header, that card will be updated
        in place.  Any input cards that do not already exist in the
        header will be added.  Cards will not be deleted from the
        header.

        Parameters
        ----------
        fileobj : file path, file object or file-like object
            Input header parameters file.

        replace : bool, optional
            When `True`, indicates that the entire header should be
            replaced with the contents of the ASCII file instead of
            just updating the current header.
        """

        close_file = False

        if isinstance(fileobj, basestring):
            fileobj = open(fileobj, 'r')
            close_file = True

        lines = fileobj.readlines()

        if close_file:
            fileobj.close()

        if len(self.ascard) > 0 and not replace:
            prevKey = 0
        else:
            if replace:
                self.ascard = CardList([])
            prevKey = 0

        for line in lines:
            card = Card.fromstring(line[:min(80, len(line)-1)])
            card.verify('silentfix')

            if card.keyword == 'SIMPLE':
                if self.get('EXTENSION'):
                    del self.ascard['EXTENSION']

                self.set(card.keyword, card.value, card.comment, before=0)
                prevKey = 0
            elif card.keyword == 'EXTENSION':
                if self.get('SIMPLE'):
                    del self.ascard['SIMPLE']

                self.set(card.keyword, card.value, card.comment, before=0)
                prevKey = 0
            elif card.keyword == 'HISTORY':
                if not replace:
                    items = self.items()
                    idx = 0

                    for item in items:
                        if item[0] == card.keyword and item[1] == card.value:
                            break
                        idx += 1

                    if idx == len(self.ascard):
                        self.add_history(card.value, after=prevKey)
                        prevKey += 1
                else:
                    self.add_history(card.value, after=prevKey)
                    prevKey += 1
            elif card.keyword == 'COMMENT':
                if not replace:
                    items = self.items()
                    idx = 0

                    for item in items:
                        if item[0] == card.keyword and item[1] == card.value:
                            break
                        idx += 1

                    if idx == len(self.ascard):
                        self.add_comment(card.value, after=prevKey)
                        prevKey += 1
                else:
                    self.add_comment(card.value, after=prevKey)
                    prevKey += 1
            elif card.keyword == '        ':
                if not replace:
                    items = self.items()
                    idx = 0

                    for item in items:
                        if item[0] == card.keyword and item[1] == card.value:
                            break
                        idx += 1

                    if idx == len(self.ascard):
                        self.add_blank(card.value, after=prevKey)
                        prevKey += 1
                else:
                    self.add_blank(card.value, after=prevKey)
                    prevKey += 1
            else:
                self.set(card.keyword, card.value, card.comment,
                         after=prevKey)
                prevKey += 1

    def _add_commentary(self, key, value, before=None, after=None):
        """
        Add a commentary card.

        If `before` and `after` are `None`, add to the last occurrence
        of cards of the same name (except blank card).  If there is no
        card (or blank card), append at the end.
        """

        if before is not None or after is not None:
            self._relativeinsert((key, value), before=before, after=after)
        else:
            self[key] = value


class _CardAccessor(object):
    """
    This is a generic class for wrapping a Header in such a way that you can
    use the header's slice/filtering capabilities to return a subset of cards
    and do something of them.

    This is sort of the opposite notion of the old CardList class--whereas
    Header used to use CardList to get lists of cards, this uses Header to get
    lists of cards.
    """


    # TODO: Consider giving this dict/list methods like Header itself
    def __init__(self, header):
        self._header = header

    def __repr__(self):
        '\n'.join(str(c) for c in self._header._cards)

    def __len__(self):
        return len(self._header)

    def __eq__(self, other):
        if isiterable(other):
            for a, b in itertools.izip(self, other):
                if a != b:
                    return False
            else:
                return True
        return False

    def __getitem__(self, item):
        if isinstance(item, slice) or self._header._haswildcard(item):
            return self.__class__(self._header[item])

        idx = self._header._cardindex(item)
        return self._header._cards[idx]


class _HeaderComments(_CardAccessor):
    """
    A class used internally by the Header class for the Header.comments
    attribute access.

    This object can be used to display all the keyword comments in the Header,
    or look up the comments on specific keywords.  It allows all the same forms
    of keyword lookup as the Header class itself, but returns comments instead
    of values.
    """

    def __repr__(self):
        """Returns a simple list of all keywords and their comments."""

        # TODO: Fix Card class so that cards containing 'only' a comment have
        # that comment in card.comment instead of card.value
        keyword_width = 8
        for card in self._header._cards:
            keyword_width = max(keyword_width, len(card.keyword))
        return '\n'.join('%*s  %s' % (keyword_width, c.keyword, c.comment)
                         for c in self._header._cards)

    def __getitem__(self, item):
        """
        Slices and filter strings return a new _HeaderComments containing the
        returned cards.  Otherwise the comment of a single card is returned.
        """

        item = super(_HeaderComments, self).__getitem__(item)
        if isinstance(item, _HeaderComments):
            return item
        return item.comment

    def __setitem__(self, item, comment):
        """
        Set the comment on specified card or cards.

        Slice/filter updates work similarly to how Header.__setitem__ works.
        """

        if isinstance(item, slice) or self._header._haswildcard(item):
            if isinstance(item, slice):
                indices = xrange(*item.indices(len(self._header)))
            else:
                indices = self._header._wildcardmatch(item)
            if isinstance(comment, basestring) or not isiterable(comment):
                comment = itertools.repeat(comment, len(indices))
            for idx, val in itertools.izip(indices, comment):
                self[idx] = val
            return

        # In this case, key/index errors should be raised; don't update
        # comments of nonexistent cards
        idx = self._header._cardindex(item)
        value = self._header[idx]
        self._header[idx] = (value, comment)


class _HeaderCommentaryCards(_CardAccessor):
    def __init__(self, header, keyword=''):
        super(_HeaderCommentaryCards, self).__init__(header)
        self._keyword = keyword

    def __repr__(self):
        # TODO: Maybe prefix each line with an index #
        return '\n'.join(str(c.value) for c in self._header._cards
                         if c.keyword == self._keyword)

    def __getitem__(self, idx):
        if not isinstance(idx, int):
            raise ValueError('%s index must be an integer' % self._keyword)
        return self._header[(self._keyword, idx)]


def _block_size(sep):
    """
    Determine the size of a FITS header block if a non-blank separator is used
    between cards.
    """

    return BLOCK_SIZE + (len(sep) * (BLOCK_SIZE // Card.length - 1))

