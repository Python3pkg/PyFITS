from pyfits.column import Column
from pyfits.diff import *
from pyfits.hdu import HDUList, PrimaryHDU, ImageHDU
from pyfits.hdu.table import new_table
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

    def test_trivial_identical_images(self):
        ia = np.arange(100).reshape((10, 10))
        ib = np.arange(100).reshape((10, 10))
        diff = ImageDataDiff(ia, ib)
        assert_true(diff.identical)
        assert_equal(diff.total_diffs, 0)

    def test_identical_within_tolerance(self):
        ia = np.ones((10, 10)) - 0.00001
        ib = np.ones((10, 10)) - 0.00002
        diff = ImageDataDiff(ia, ib, tolerance=1.0e-4)
        assert_true(diff.identical)
        assert_equal(diff.total_diffs, 0)

    def test_different_dimensions(self):
        ia = np.arange(100).reshape((10, 10))
        ib = np.arange(100) - 1

        # Although ib could be reshaped into the same dimensions, for now the
        # data is not compared anyways
        diff = ImageDataDiff(ia, ib)
        assert_false(diff.identical)
        assert_equal(diff.diff_dimensions, ((10, 10), (100,)))
        assert_equal(diff.total_diffs, 0)

    def test_different_pixels(self):
        ia = np.arange(100).reshape((10, 10))
        ib = np.arange(100).reshape((10, 10))
        ib[0,0] = 10
        ib[5,5] = 20
        diff = ImageDataDiff(ia, ib)
        assert_false(diff.identical)
        assert_equal(diff.diff_dimensions, ())
        assert_equal(diff.total_diffs, 2)
        assert_equal(diff.diff_ratio, 0.02)
        assert_equal(diff.diff_pixels, [((0, 0), (0, 10)), ((5, 5), (55, 20))])

    def test_identical_tables(self):
        c1 = Column('A', format='L', array=[True, False])
        c2 = Column('B', format='X', array=[[0], [1]])
        c3 = Column('C', format='4I', dim='(2, 2)',
                    array=[[0, 1, 2, 3], [4, 5, 6, 7]])
        c4 = Column('D', format='J', bscale=2.0, array=[0, 1])
        c5 = Column('E', format='A3', array=['abc', 'def'])
        c6 = Column('F', format='E', unit='m', array=[0.0, 1.0])
        c7 = Column('G', format='D', bzero=-0.1, array=[0.0, 1.0])
        c8 = Column('H', format='C', array=[0.0+1.0j, 2.0+3.0j])
        c9 = Column('I', format='M', array=[4.0+5.0j, 6.0+7.0j])
        c10 = Column('J', format='PI(2)', array=[[0, 1], [2, 3]])

        ta = new_table([c1, c2, c3, c4, c5, c6, c7, c8, c9, c10])
        tb = new_table([c1, c2, c3, c4, c5, c6, c7, c8, c9, c10])

        diff = TableDataDiff(ta.data, tb.data)
        assert_true(diff.identical)
        assert_equal(len(diff.common_columns), 10)
        assert_equal(diff.common_column_names,
                     set(['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j']))
        assert_equal(diff.diff_ratio, 0)
        assert_equal(diff.total_diffs, 0)

    def test_ignore_table_fields(self):
        c1 = Column('A', format='L', array=[True, False])
        c2 = Column('B', format='X', array=[[0], [1]])
        c3 = Column('C', format='4I', dim='(2, 2)',
                    array=[[0, 1, 2, 3], [4, 5, 6, 7]])

        c4 = Column('B', format='X', array=[[1], [0]])
        c5 = Column('C', format='4I', dim='(2, 2)',
                    array=[[1, 2, 3, 4], [5, 6, 7, 8]])

        ta = new_table([c1, c2, c3])
        tb = new_table([c1, c4, c5])

        diff = TableDataDiff(ta.data, tb.data, ignore_fields=['B', 'C'])
        assert_true(diff.identical)

        # The only common column should be c1
        assert_equal(len(diff.common_columns), 1)
        assert_equal(diff.common_column_names, set(['a']))
        assert_equal(diff.diff_ratio, 0)
        assert_equal(diff.total_diffs, 0)

    def test_different_table_field_names(self):
        ca = Column('A', format='L', array=[True, False])
        cb = Column('B', format='L', array=[True, False])
        cc = Column('C', format='L', array=[True, False])

        ta = new_table([ca, cb])
        tb = new_table([ca, cc])

        diff = TableDataDiff(ta.data, tb.data)

        assert_false(diff.identical)
        assert_equal(len(diff.common_columns), 1)
        assert_equal(diff.common_column_names, set(['a']))
        assert_equal(diff.diff_column_names, (['B'], ['C']))
        assert_equal(diff.diff_ratio, 0)
        assert_equal(diff.total_diffs, 0)

    def test_different_table_field_counts(self):
        ca = Column('A', format='L', array=[True, False])
        cb = Column('B', format='L', array=[True, False])
        cc = Column('C', format='L', array=[True, False])

        ta = new_table([cb])
        tb = new_table([ca, cb, cc])

        diff = TableDataDiff(ta.data, tb.data)

        assert_false(diff.identical)
        assert_equal(diff.diff_column_count, (1, 3))
        assert_equal(len(diff.common_columns), 1)
        assert_equal(diff.common_column_names, set(['b']))
        assert_equal(diff.diff_column_names, ([], ['A', 'C']))
        assert_equal(diff.diff_ratio, 0)
        assert_equal(diff.total_diffs, 0)

    def test_identical_files_basic(self):
        """Test identicality of two simple, extensionless files."""

        a = np.arange(100).reshape((10, 10))
        hdu = PrimaryHDU(data=a)
        hdu.writeto(self.temp('testa.fits'))
        hdu.writeto(self.temp('testb.fits'))
        diff = FITSDiff(self.temp('testa.fits'), self.temp('testb.fits'))
        assert_true(diff.identical)

    def test_partially_identical_files1(self):
        """
        Test files that have some identical HDUs but a different extension
        count.
        """

        a = np.arange(100).reshape((10, 10))
        phdu = PrimaryHDU(data=a)
        ehdu = ImageHDU(data=a)
        hdula = HDUList([phdu, ehdu])
        hdulb = HDUList([phdu, ehdu, ehdu])
        diff = FITSDiff(hdula, hdulb)
        assert_false(diff.identical)
        assert_equal(diff.diff_extension_count, (2, 3))

        # diff_extensions should be empty, since the third extension in hdulb
        # has nothing to compare against
        assert_equal(diff.diff_extensions, [])

    def test_partially_identical_files2(self):
        """
        Test files that have some identical HDUs but one different HDU.
        """

        a = np.arange(100).reshape((10, 10))
        phdu = PrimaryHDU(data=a)
        ehdu = ImageHDU(data=a)
        ehdu2 = ImageHDU(data=(a + 1))
        hdula = HDUList([phdu, ehdu, ehdu])
        hdulb = HDUList([phdu, ehdu2, ehdu])
        diff = FITSDiff(hdula, hdulb)

        assert_false(diff.identical)
        assert_equal(diff.diff_extension_count, ())
        assert_equal(len(diff.diff_extensions), 1)
        assert_equal(diff.diff_extensions[0][0], 1)

        hdudiff = diff.diff_extensions[0][1]
        assert_false(hdudiff.identical)
        assert_equal(hdudiff.diff_extnames, ())
        assert_equal(hdudiff.diff_extvers, ())
        assert_equal(hdudiff.diff_extension_types, ())
        assert_true(hdudiff.diff_headers.identical)
        assert_false(hdudiff.diff_data is None)

        datadiff = hdudiff.diff_data
        assert_true(isinstance(datadiff, ImageDataDiff))
        assert_false(datadiff.identical)
        assert_equal(datadiff.diff_dimensions, ())
        assert_equal(datadiff.diff_pixels,
                     [((0, y), (y, y + 1)) for y in range(10)])
        assert_equal(datadiff.diff_ratio, 1.0)
        assert_equal(datadiff.total_diffs, 100)
