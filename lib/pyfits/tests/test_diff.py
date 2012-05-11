from pyfits.diff import FitsDiff, HeaderDiff
from pyfits.hdu import HDUList, PrimaryHDU
from pyfits.header import Header
from pyfits.tests import PyfitsTestCase

from nose.tools import (assert_true, assert_false, assert_equal,
                        assert_not_equal)


class TestDiff(PyfitsTestCase):
    def test_identical_headers(self):
        ha = Header([('A', 1), ('B', 2), ('C', 3)])
        hb = ha.copy()
        assert_true(HeaderDiff(ha, hb).identical)

    def test_slightly_different_headers(self):
        ha = Header([('A', 1), ('B', 2), ('C', 3)])
        hb = ha.copy()
        hb['C'] = 4
        assert_false(HeaderDiff(ha, hb).identical)

    def test_common_keywords(self):
        ha = Header([('A', 1), ('B', 2), ('C', 3)])
        hb = ha.copy()
        hb['C'] = 4
        hb['D'] = (5, 'Comment')
        assert_equal(HeaderDiff(ha, hb).common_keywords, ['A', 'B', 'C'])

    def test_different_keyword_count(self):
        ha = Header([('A', 1), ('B', 2), ('C', 3)])
        hb = ha.copy()
        del hb['B']
        diff = HeaderDiff(ha, hb)
        assert_false(diff.identical)
        assert_equal(diff.diff_keyword_count, (3, 2))

        # But make sure the common keywords are at least correct
        assert_equal(diff.common_keywords, ['A', 'C'])

    def test_different_keywords(self):
        ha = Header([('A', 1), ('B', 2), ('C', 3)])
        hb = ha.copy()
        hb['C'] = 4
        hb['D'] = (5, 'Comment')
        ha['E'] = (6, 'Comment')
        ha['F'] = (7, 'Comment')
        diff = HeaderDiff(ha, hb)
        assert_false(diff.identical)
        assert_equal(diff.diff_keywords, (['E', 'F'], ['D']))

    def test_different_keyword_values(self):
        ha = Header([('A', 1), ('B', 2), ('C', 3)])
        hb = ha.copy()
        hb['C'] = 4
        diff = HeaderDiff(ha, hb)
        assert_false(diff.identical)
        assert_equal(diff.diff_keyword_values, {'C': [(3, 4)]})

    def test_different_keyword_comments(self):
        ha = Header([('A', 1), ('B', 2), ('C', 3, 'comment 1')])
        hb = ha.copy()
        hb.comments['C'] = 'comment 2'
        diff = HeaderDiff(ha, hb)
        assert_false(diff.identical)
        assert_equal(diff.diff_keyword_comments,
                     {'C': [('comment 1', 'comment 2')]})

    def test_different_keyword_values_with_duplicate(self):
        ha = Header([('A', 1), ('B', 2), ('C', 3)])
        hb = ha.copy()
        ha.append(('C', 4))
        hb.append(('C', 5))
        diff = HeaderDiff(ha, hb)
        assert_false(diff.identical)
        assert_equal(diff.diff_keyword_values, {'C': [None, (4, 5)]})

    def test_asymmetric_duplicate_keywords(self):
        ha = Header([('A', 1), ('B', 2), ('C', 3)])
        hb = ha.copy()
        ha.append(('A', 2, 'comment 1'))
        ha.append(('A', 3, 'comment 2'))
        hb.append(('B', 4, 'comment 3'))
        hb.append(('C', 5, 'comment 4'))
        diff = HeaderDiff(ha, hb)
        assert_false(diff.identical)
        assert_equal(diff.diff_keyword_values, {})
        assert_equal(diff.diff_duplicate_keywords,
                     {'A': (3, 1), 'B': (1, 2), 'C': (1, 2)})

    def test_floating_point_tolerance(self):
        ha = Header([('A', 1), ('B', 2.00001), ('C', 3.000001)])
        hb = ha.copy()
        hb['B'] = 2.00002
        hb['C'] = 3.000002
        diff = HeaderDiff(ha, hb)
        assert_false(diff.identical)
        assert_equal(diff.diff_keyword_values,
                     {'B': [(2.00001, 2.00002)], 'C': [(3.000001, 3.000002)]})
        diff = HeaderDiff(ha, hb, tolerance=1e-6)
        assert_false(diff.identical)
        assert_equal(diff.diff_keyword_values, {'B': [(2.00001, 2.00002)]})

    def test_ignore_blanks(self):
        ha = Header([('A', 1), ('B', 2), ('C', 'A       ')])
        hb = ha.copy()
        hb['C'] = 'A'
        assert_not_equal(ha['C'], hb['C'])

        diff = HeaderDiff(ha, hb)
        # Trailing blanks are ignored by default
        assert_true(diff.identical)
        assert_equal(diff.diff_keyword_values, {})

        # Don't ignore blanks
        diff = HeaderDiff(ha, hb, ignore_blanks=False)
        assert_false(diff.identical)
        assert_equal(diff.diff_keyword_values, {'C': [('A       ', 'A')]})

    def test_ignore_keyword_values(self):
        ha = Header([('A', 1), ('B', 2), ('C', 3)])
        hb = ha.copy()
        hb['B'] = 4
        hb['C'] = 5
        diff = HeaderDiff(ha, hb, ignore_keywords=['*'])
        assert_true(diff.identical)
        diff = HeaderDiff(ha, hb, ignore_keywords=['B'])
        assert_false(diff.identical)
        assert_equal(diff.diff_keyword_values, {'C': [(3, 5)]})
