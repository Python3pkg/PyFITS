from __future__ import division # confidence high

import unittest
import pyfits
import numpy
import exceptions,os,sys
import numpy as num
from pyfits import rec
from numpy import char as chararray

# Define a junk file for redirection of stdout
jfile = "junkfile.fits"

def comparefloats(a, b):
    """Compare two float scalars or arrays and see if they are consistent

    Consistency is determined ensuring the difference is less than the
    expected amount. Return True if consistent, False if any differences"""
    aa = a
    bb = b
    # compute expected precision
    if aa.dtype.name=="float32" or bb.dtype.name=='float32':
        precision = 0.000001
    else:
        precision = 0.0000000000000001
    precision = 0.00001 # until precision problem is fixed in pyfits
#    print aa,aa.shape,type(aa)
#    print bb,bb.shape,type(bb)
    diff = num.absolute(aa-bb)
    mask0 = aa == 0
    masknz = aa != 0.
    if num.any(mask0):
        if diff[mask0].max() != 0.:
            return False
    if num.any(masknz):
        if (diff[masknz]/aa[masknz]).max() > precision:
            return False
    return True

def comparerecords(a, b):
    """Compare two record arrays

    Does this field by field, using approximation testing for float columns
    (Complex not yet handled.)
    Column names not compared, but column types and sizes are.
    """

    nfieldsa = len(a.dtype.names)
    nfieldsb = len(b.dtype.names)
    if nfieldsa != nfieldsb:
        print "number of fields don't match"
        return False
    for i in range(nfieldsa):
        fielda = a.field(i)
        fieldb = b.field(i)
        if type(fielda) != type(fieldb):
            print "type(fielda): ",type(fielda)," fielda: ",fielda
            print "type(fieldb): ",type(fieldb)," fieldb: ",fieldb
            print 'field %d type differs' % i
            return False
        if not isinstance(fielda, num.chararray) and \
               isinstance(fielda[0], num.floating):
            if not comparefloats(fielda, fieldb):
                print "fielda: ",fielda
                print "fieldb: ",fieldb
                print 'field %d differs' % i
                return False
        else:
            if num.any(fielda != fieldb):
                print "fielda: ",fielda
                print "fieldb: ",fieldb
                print 'field %d differs' % i
                return False
    return True


class TestPyfitsTableFunctions(unittest.TestCase):

    def setUp(self):
        # Perform set up actions (if any)
        pass

    def tearDown(self):
        # Perform clean-up actions (if any)
        try:
            os.remove('newtable.fits')
        except:
            pass

        try:
            os.remove('table1.fits')
        except:
            pass

        try:
            os.remove('table2.fits')
        except:
            pass

    def testOpen(self):
        # open some existing FITS files:
        tt=pyfits.open('tb.fits')
        fd=pyfits.open('test0.fits')

        # create some local arrays
        a1=chararray.array(['abc','def','xx'])
        r1=num.array([11.,12.,13.],dtype=num.float32)

        # create a table from scratch, using a mixture of columns from existing
        # tables and locally created arrays:

        # first, create individual column definitions

        c1=pyfits.Column(name='abc',format='3A', array=a1)
        c2=pyfits.Column(name='def',format='E', array=r1)
        a3=num.array([3,4,5],dtype='i2')
        c3=pyfits.Column(name='xyz',format='I', array=a3)
        a4=num.array([1,2,3],dtype='i2')
        c4=pyfits.Column(name='t1', format='I', array=a4)
        a5=num.array([3+3j,4+4j,5+5j],dtype='c8')
        c5=pyfits.Column(name='t2', format='C', array=a5)

        # Note that X format must be two-D array
        a6=num.array([[0],[1],[0]],dtype=num.uint8)
        c6=pyfits.Column(name='t3', format='X', array=a6)
        a7=num.array([101,102,103],dtype='i4')
        c7=pyfits.Column(name='t4', format='J', array=a7)
        a8=num.array([[1,1,0,1,0,1,1,1,0,0,1],[0,1,1,1,1,0,0,0,0,1,0],[1,1,1,0,0,1,1,1,1,1,1]],dtype=num.uint8)
        c8=pyfits.Column(name='t5', format='11X', array=a8)

        # second, create a column-definitions object for all columns in a table

        x = pyfits.ColDefs([c1,c2,c3,c4,c5,c6,c7,c8])

        # create a new binary table HDU object by using the new_table function

        tbhdu=pyfits.new_table(x)

        # another way to create a table is by using existing table's information:

        x2=pyfits.ColDefs(tt[1])
        t2=pyfits.new_table(x2, nrows=2)
        ra = rec.array([
            (1, 'abc', 3.7000002861022949, 0),
            (2, 'xy ', 6.6999998092651367, 1)], names='c1, c2, c3, c4')

        self.assertEqual(comparerecords(t2.data, ra),True)

        # the table HDU's data is a subclass of a record array, so we can access
        # one row like this:

        self.assertEqual(tbhdu.data[1][0], a1[1])
        self.assertEqual(tbhdu.data[1][1], r1[1])
        self.assertEqual(tbhdu.data[1][2], a3[1])
        self.assertEqual(tbhdu.data[1][3], a4[1])
        self.assertEqual(tbhdu.data[1][4], a5[1])
        self.assertEqual(tbhdu.data[1][5], a6[1])
        self.assertEqual(tbhdu.data[1][6], a7[1])
        self.assertEqual(tbhdu.data[1][7].all(), a8[1].all())

        # and a column like this:
        self.assertEqual(str(tbhdu.data.field('abc')),"['abc' 'def' 'xx']")

        # An alternative way to create a column-definitions object is from an
        # existing table.
        xx=pyfits.ColDefs(tt[1])

        # now we write out the newly created table HDU to a FITS file:
        fout = pyfits.HDUList(pyfits.PrimaryHDU())
        fout.append(tbhdu)
        fout.writeto('tableout1.fits', clobber=True)

        f2 = pyfits.open('tableout1.fits')
        temp = f2[1].data.field(7)
        self.assertEqual(str(temp[0]),"[ True  True False  True False  True  True  True False False  True]")
        f2.close()
        os.remove('tableout1.fits')


        # An alternative way to create an output table FITS file:
        fout2=pyfits.open('tableout2.fits','append')
        fout2.append(fd[0])
        fout2.append(tbhdu)
        fout2.close()
        os.remove("tableout2.fits")

    def testBinaryTable(self):
        # binary table:
        t=pyfits.open('tb.fits')
        self.assertEqual(t[1].header['tform1'],'1J')

        tmpfile = open(jfile,'w')
        sys.stdout = tmpfile
        t[1].columns.info()
        sys.stdout = sys.__stdout__
        tmpfile.close()
        tmpfile = open(jfile,'r')
        tmplist = tmpfile.readlines()
        tmpfile.close()
        os.remove(jfile)
        self.assertEqual(tmplist,['name:\n', "     ['c1', 'c2', 'c3', 'c4']\n",
                                  'format:\n', "     ['1J', '3A', '1E', '1L']\n",
                                  'unit:\n', "     ['', '', '', '']\n", 'null:\n',
                                  "     [-2147483647, '', '', '']\n", 'bscale:\n',
                                  "     ['', '', 3, '']\n", 'bzero:\n',
                                  "     ['', '', 0.40000000000000002, '']\n",
                                  'disp:\n', "     ['I11', 'A3', 'G15.7', 'L6']\n",
                                  'start:\n', "     ['', '', '', '']\n", 'dim:\n',
                                  "     ['', '', '', '']\n"])
        ra = rec.array([
            (1, 'abc', 3.7000002861022949, 0),
            (2, 'xy ', 6.6999998092651367, 1)], names='c1, c2, c3, c4')

        self.assertEqual(comparerecords(t[1].data, ra[:2]),True)

        # Change scaled field and scale back to the original array
        t[1].data.field('c4')[0] = 1
        t[1].data._scale_back()
        self.assertEqual(str(rec.recarray.field(t[1].data,'c4')),"[84 84]")

        # look at data column-wise
        self.assertEqual(t[1].data.field(0).all(),num.array([1, 2]).all())

        # When there are scaled columns, the raw data are in data._parent

    def testAsciiTable(self):
        # ASCII table
        a=pyfits.open('ascii.fits')
        ra1 = rec.array([
            (10.123000144958496, 37),
            (5.1999998092651367, 23),
            (15.609999656677246, 17),
            (0.0, 0),
            (345.0, 345)], names='c1, c2')
        self.assertEqual(comparerecords(a[1].data, ra1),True)

        # Test slicing
        a2 = a[1].data[2:][2:]
        ra2 = rec.array([(345.0,345)],names='c1, c2')

        self.assertEqual(comparerecords(a2, ra2),True)

        self.assertEqual(a2.field(1).all(),num.array([345]).all())

        ra3 = rec.array([
            (10.123000144958496, 37),
            (15.609999656677246, 17),
            (345.0, 345)
            ], names='c1, c2')

        self.assertEqual(comparerecords(a[1].data[::2], ra3),True)

        # Test Start Column

        a1 = chararray.array(['abcd','def'])
        r1 = numpy.array([11.,12.])
        c1 = pyfits.Column(name='abc',format='A3',start=19,array=a1)
        c2 = pyfits.Column(name='def',format='E',start=3,array=r1)
        c3 = pyfits.Column(name='t1',format='I',array=[91,92,93])
        hdu = pyfits.new_table([c2,c1,c3],tbtype='TableHDU')


        self.assertEqual(hdu.data.dtype.fields,{'abc':(numpy.dtype('|S3'),18),
                                                'def':(numpy.dtype('|S14'),2),
                                                't1':(numpy.dtype('|S10'),21)})
        hdu.writeto('toto.fits',clobber=True)
        hdul = pyfits.open('toto.fits')
        self.assertEqual(comparerecords(hdu.data,hdul[1].data),True)
        hdul.close()
        os.remove('toto.fits')


    def testVariableLengthColumns(self):
        col_list = []
        col_list.append(pyfits.Column(name='QUAL_SPE',format='PJ()',array=[[0]*1571]*225))
        tb_hdu = pyfits.new_table(col_list)
        pri_hdu = pyfits.PrimaryHDU()
        hdu_list = pyfits.HDUList([pri_hdu,tb_hdu])
        hdu_list.writeto('toto.fits', clobber=True)
        toto = pyfits.open('toto.fits')
        q = toto[1].data.field('QUAL_SPE')
        self.assertEqual(q[0][4:8].all(),num.array([0,0,0,0],dtype=numpy.uint8).all())
        toto.close()
        os.remove('toto.fits')

    def testEndianness(self):
        x = num.ndarray((1,), dtype=object)
        channelsIn = num.array([3], dtype='uint8')
        x[0] = channelsIn
        col = pyfits.Column(name="Channels", format="PB()", array=x)
        cols = pyfits.ColDefs([col])
        tbhdu = pyfits.new_table(cols)
        tbhdu.name = "RFI"
        tbhdu.writeto('testendian.fits', clobber=True)
        hduL = pyfits.open('testendian.fits')
        rfiHDU = hduL['RFI']
        data = rfiHDU.data
        channelsOut = data.field('Channels')[0]
        self.assertEqual(channelsIn.all(),channelsOut.all())
        hduL.close()
        os.remove('testendian.fits')

    def testPyfitsRecarrayToBinTableHDU(self):
        bright=pyfits.rec.array([(1,'Serius',-1.45,'A1V'),\
                                 (2,'Canopys',-0.73,'F0Ib'),\
                                 (3,'Rigil Kent',-0.1,'G2V')],\
                                formats='int16,a20,float32,a10',\
                                names='order,name,mag,Sp')
        hdu=pyfits.BinTableHDU(bright)
        self.assertEqual(comparerecords(hdu.data,bright),True)
        hdu.writeto('toto.fits', clobber=True)
        hdul = pyfits.open('toto.fits')
        self.assertEqual(comparerecords(hdu.data,hdul[1].data),True)
        self.assertEqual(comparerecords(bright,hdul[1].data),True)
        hdul.close()
        os.remove('toto.fits')

    def testNumpyNdarrayToBinTableHDU(self):
        desc=numpy.dtype({'names':['order','name','mag','Sp'],\
                          'formats':['int','S20','float32','S10']})
        a=numpy.array([(1,'Serius',-1.45,'A1V'),\
                       (2,'Canopys',-0.73,'F0Ib'),\
                       (3,'Rigil Kent',-0.1,'G2V')],dtype=desc)
        hdu=pyfits.BinTableHDU(a)
        self.assertEqual(comparerecords(hdu.data,a.view(pyfits.rec.recarray)),\
                         True)
        hdu.writeto('toto.fits', clobber=True)
        hdul = pyfits.open('toto.fits')
        self.assertEqual(comparerecords(hdu.data,hdul[1].data),True)
        hdul.close()
        os.remove('toto.fits')

    def testNewTableFromPyfitsRecarray(self):
        bright=pyfits.rec.array([(1,'Serius',-1.45,'A1V'),\
                                 (2,'Canopys',-0.73,'F0Ib'),\
                                 (3,'Rigil Kent',-0.1,'G2V')],\
                                formats='int16,a20,float32,a10',\
                                names='order,name,mag,Sp')
        hdu=pyfits.new_table(bright,nrows=2,tbtype='TableHDU')
        self.assertEqual(hdu.data.field(0).all(),
                         num.array([1,2],dtype=num.int16).all())
        self.assertEqual(hdu.data[0][1],'Serius')
        self.assertEqual(hdu.data[1][1],'Canopys')
        self.assertEqual(hdu.data.field(2).all(),
                         num.array([-1.45,-0.73],dtype=num.float32).all())
        self.assertEqual(hdu.data[0][3],'A1V')
        self.assertEqual(hdu.data[1][3],'F0Ib')
        hdu.writeto('toto.fits', clobber=True)
        hdul = pyfits.open('toto.fits')
        self.assertEqual(hdul[1].data.field(0).all(),
                         num.array([1,2],dtype=num.int16).all())
        self.assertEqual(hdul[1].data[0][1],'Serius')
        self.assertEqual(hdul[1].data[1][1],'Canopys')
        self.assertEqual(hdul[1].data.field(2).all(),
                         num.array([-1.45,-0.73],dtype=num.float32).all())
        self.assertEqual(hdul[1].data[0][3],'A1V')
        self.assertEqual(hdul[1].data[1][3],'F0Ib')

        hdul.close()
        os.remove('toto.fits')
        hdu=pyfits.new_table(bright,nrows=2)
        tmp=pyfits.rec.array([(1,'Serius',-1.45,'A1V'),\
                              (2,'Canopys',-0.73,'F0Ib')],\
                             formats='int16,a20,float32,a10',\
                             names='order,name,mag,Sp')
        self.assertEqual(comparerecords(hdu.data,tmp),True)
        hdu.writeto('toto.fits', clobber=True)
        hdul = pyfits.open('toto.fits')
        self.assertEqual(comparerecords(hdu.data,hdul[1].data),True)
        hdul.close()
        os.remove('toto.fits')

    def testAppendingAColumn(self):
        counts = num.array([312,334,308,317])
        names = num.array(['NGC1','NGC2','NGC3','NCG4'])
        c1=pyfits.Column(name='target',format='10A',array=names)
        c2=pyfits.Column(name='counts',format='J',unit='DN',array=counts)
        c3=pyfits.Column(name='notes',format='A10')
        c4=pyfits.Column(name='spectrum',format='5E')
        c5=pyfits.Column(name='flag',format='L',array=[1,0,1,1])
        coldefs=pyfits.ColDefs([c1,c2,c3,c4,c5])
        tbhdu=pyfits.new_table(coldefs)
        tbhdu.writeto('table1.fits')

        counts = num.array([412,434,408,417])
        names = num.array(['NGC5','NGC6','NGC7','NCG8'])
        c1=pyfits.Column(name='target',format='10A',array=names)
        c2=pyfits.Column(name='counts',format='J',unit='DN',array=counts)
        c3=pyfits.Column(name='notes',format='A10')
        c4=pyfits.Column(name='spectrum',format='5E')
        c5=pyfits.Column(name='flag',format='L',array=[0,1,0,0])
        coldefs=pyfits.ColDefs([c1,c2,c3,c4,c5])
        tbhdu=pyfits.new_table(coldefs)
        tbhdu.writeto('table2.fits')

        # Append the rows of table 2 after the rows of table 1
        # The column definitions are assumed to be the same

        # Open the two files we want to append
        t1=pyfits.open('table1.fits')
        t2=pyfits.open('table2.fits')

        # Get the number of rows in the table from the first file
        nrows1=t1[1].data.shape[0]

        # Get the total number of rows in the resulting appended table
        nrows=t1[1].data.shape[0]+t2[1].data.shape[0]

        self.assertEqual(t1[1].columns._arrays[1] is t1[1].columns.data[1].array, True)

        # Create a new table that consists of the data from the first table
        # but has enough space in the ndarray to hold the data from both tables
        hdu=pyfits.new_table(t1[1].columns,nrows=nrows)

        # For each column in the tables append the data from table 2 after the
        # data from table 1.
        for i in range(len(t1[1].columns)):
            hdu.data.field(i)[nrows1:]=t2[1].data.field(i)

        hdu.writeto('newtable.fits')

        tmpfile = open(jfile,'w')
        sys.stdout = tmpfile
        pyfits.info('newtable.fits')
        sys.stdout = sys.__stdout__
        tmpfile.close()
        tmpfile = open(jfile,'r')
        output = tmpfile.readlines()
        tmpfile.close()
        os.remove(jfile)
        self.assertEqual(output,['Filename: newtable.fits\n', 'No.    Name         Type      Cards   Dimensions   Format\n', '0    PRIMARY     PrimaryHDU       4  ()            uint8\n', '1                BinTableHDU     19  8R x 5C       [10A, J, 10A, 5E, L]\n'])

        tmpfile = open(jfile,'w')
        sys.stdout = tmpfile
        print hdu.data
        sys.stdout = sys.__stdout__
        tmpfile.close()
        tmpfile = open(jfile,'r')
        output = tmpfile.readlines()
        tmpfile.close()
        os.remove(jfile)
        self.assertEqual(output,["[ ('NGC1', 312, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), True)\n", " ('NGC2', 334, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), False)\n", " ('NGC3', 308, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), True)\n", " ('NCG4', 317, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), True)\n", " ('NGC5', 412, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), False)\n", " ('NGC6', 434, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), True)\n", " ('NGC7', 408, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), False)\n", " ('NCG8', 417, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), False)]\n"])

        # Verify that all of the references to the data point to the same
        # numarray
        hdu.data[0][1] = 300
        self.assertEqual(hdu.data._coldefs._arrays[1][0], 300)
        self.assertEqual(hdu.data._coldefs.data[1].array[0], 300)
        self.assertEqual(hdu.columns._arrays[1][0], 300)
        self.assertEqual(hdu.columns.data[1].array[0], 300)
        self.assertEqual(hdu.data[0][1], 300)

        hdu.data._coldefs._arrays[1][0] = 200
        self.assertEqual(hdu.data._coldefs._arrays[1][0], 200)
        self.assertEqual(hdu.data._coldefs.data[1].array[0], 200)
        self.assertEqual(hdu.columns._arrays[1][0], 200)
        self.assertEqual(hdu.columns.data[1].array[0], 200)
        self.assertEqual(hdu.data[0][1], 200)

        hdu.data._coldefs.data[1].array[0] = 100
        self.assertEqual(hdu.data._coldefs._arrays[1][0], 100)
        self.assertEqual(hdu.data._coldefs.data[1].array[0], 100)
        self.assertEqual(hdu.columns._arrays[1][0], 100)
        self.assertEqual(hdu.columns.data[1].array[0], 100)
        self.assertEqual(hdu.data[0][1], 100)

        hdu.columns._arrays[1][0] = 90
        self.assertEqual(hdu.data._coldefs._arrays[1][0], 90)
        self.assertEqual(hdu.data._coldefs.data[1].array[0], 90)
        self.assertEqual(hdu.columns._arrays[1][0], 90)
        self.assertEqual(hdu.columns.data[1].array[0], 90)
        self.assertEqual(hdu.data[0][1], 90)

        hdu.columns.data[1].array[0] = 80
        self.assertEqual(hdu.data._coldefs._arrays[1][0], 80)
        self.assertEqual(hdu.data._coldefs.data[1].array[0], 80)
        self.assertEqual(hdu.columns._arrays[1][0], 80)
        self.assertEqual(hdu.columns.data[1].array[0], 80)
        self.assertEqual(hdu.data[0][1], 80)

        # Same verification from the file
        hdul = pyfits.open('newtable.fits')
        hdu = hdul[1]
        hdu.data[0][1] = 300
        self.assertEqual(hdu.data._coldefs._arrays[1][0], 300)
        self.assertEqual(hdu.data._coldefs.data[1].array[0], 300)
        self.assertEqual(hdu.columns._arrays[1][0], 300)
        self.assertEqual(hdu.columns.data[1].array[0], 300)
        self.assertEqual(hdu.data[0][1], 300)

        hdu.data._coldefs._arrays[1][0] = 200
        self.assertEqual(hdu.data._coldefs._arrays[1][0], 200)
        self.assertEqual(hdu.data._coldefs.data[1].array[0], 200)
        self.assertEqual(hdu.columns._arrays[1][0], 200)
        self.assertEqual(hdu.columns.data[1].array[0], 200)
        self.assertEqual(hdu.data[0][1], 200)

        hdu.data._coldefs.data[1].array[0] = 100
        self.assertEqual(hdu.data._coldefs._arrays[1][0], 100)
        self.assertEqual(hdu.data._coldefs.data[1].array[0], 100)
        self.assertEqual(hdu.columns._arrays[1][0], 100)
        self.assertEqual(hdu.columns.data[1].array[0], 100)
        self.assertEqual(hdu.data[0][1], 100)

        hdu.columns._arrays[1][0] = 90
        self.assertEqual(hdu.data._coldefs._arrays[1][0], 90)
        self.assertEqual(hdu.data._coldefs.data[1].array[0], 90)
        self.assertEqual(hdu.columns._arrays[1][0], 90)
        self.assertEqual(hdu.columns.data[1].array[0], 90)
        self.assertEqual(hdu.data[0][1], 90)

        hdu.columns.data[1].array[0] = 80
        self.assertEqual(hdu.data._coldefs._arrays[1][0], 80)
        self.assertEqual(hdu.data._coldefs.data[1].array[0], 80)
        self.assertEqual(hdu.columns._arrays[1][0], 80)
        self.assertEqual(hdu.columns.data[1].array[0], 80)
        self.assertEqual(hdu.data[0][1], 80)

        os.remove('newtable.fits')
        os.remove('table1.fits')
        os.remove('table2.fits')

    def testAddingAColumn(self):
        # Tests adding a column to a table.
        counts = num.array([312,334,308,317])
        names = num.array(['NGC1','NGC2','NGC3','NCG4'])
        c1=pyfits.Column(name='target',format='10A',array=names)
        c2=pyfits.Column(name='counts',format='J',unit='DN',array=counts)
        c3=pyfits.Column(name='notes',format='A10')
        c4=pyfits.Column(name='spectrum',format='5E')
        c5=pyfits.Column(name='flag',format='L',array=[1,0,1,1])
        coldefs=pyfits.ColDefs([c1,c2,c3,c4])
        tbhdu=pyfits.new_table(coldefs)

        self.assertEqual(tbhdu.columns.names,['target', 'counts', 'notes', 'spectrum'])
        coldefs1 = coldefs + c5

        tbhdu1=pyfits.new_table(coldefs1)
        self.assertEqual(tbhdu1.columns.names,['target', 'counts', 'notes', 'spectrum', 'flag'])

        tmpfile = open(jfile, 'w')
        sys.stdout = tmpfile
        print tbhdu1.data
        sys.stdout = sys.__stdout__
        tmpfile.close()

        tmpfile = open(jfile,'r')
        output = tmpfile.readlines()
        tmpfile.close()
        os.remove(jfile)
        self.assertEqual(output,["[ ('NGC1', 312, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), True)\n", " ('NGC2', 334, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), False)\n", " ('NGC3', 308, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), True)\n", " ('NCG4', 317, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), True)]\n"])

    def testMergeTables(self):
        counts = num.array([312,334,308,317])
        names = num.array(['NGC1','NGC2','NGC3','NCG4'])
        c1=pyfits.Column(name='target',format='10A',array=names)
        c2=pyfits.Column(name='counts',format='J',unit='DN',array=counts)
        c3=pyfits.Column(name='notes',format='A10')
        c4=pyfits.Column(name='spectrum',format='5E')
        c5=pyfits.Column(name='flag',format='L',array=[1,0,1,1])
        coldefs=pyfits.ColDefs([c1,c2,c3,c4,c5])
        tbhdu=pyfits.new_table(coldefs)
        tbhdu.writeto('table1.fits')

        counts = num.array([412,434,408,417])
        names = num.array(['NGC5','NGC6','NGC7','NCG8'])
        c1=pyfits.Column(name='target1',format='10A',array=names)
        c2=pyfits.Column(name='counts1',format='J',unit='DN',array=counts)
        c3=pyfits.Column(name='notes1',format='A10')
        c4=pyfits.Column(name='spectrum1',format='5E')
        c5=pyfits.Column(name='flag1',format='L',array=[0,1,0,0])
        coldefs=pyfits.ColDefs([c1,c2,c3,c4,c5])
        tbhdu=pyfits.new_table(coldefs)
        tbhdu.writeto('table2.fits')

        # Merge the columns of table 2 after the columns of table 1
        # The column names are assumed to be different

        # Open the two files we want to append
        t1=pyfits.open('table1.fits')
        t2=pyfits.open('table2.fits')

        hdu =pyfits.new_table(t1[1].columns+t2[1].columns)

        tmpfile = open(jfile,'w')
        sys.stdout = tmpfile
        print hdu.data
        sys.stdout = sys.__stdout__
        tmpfile.close()
        tmpfile = open(jfile,'r')
        output = tmpfile.readlines()
        tmpfile.close()
        os.remove(jfile)
        self.assertEqual(output,["[ ('NGC1', 312, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), True, 'NGC5', 412, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), False)\n", " ('NGC2', 334, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), False, 'NGC6', 434, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), True)\n", " ('NGC3', 308, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), True, 'NGC7', 408, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), False)\n", " ('NCG4', 317, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), True, 'NCG8', 417, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), False)]\n"])

        hdu.writeto('newtable.fits')

        # Verify that all of the references to the data point to the same
        # numarray
        hdu.data[0][1] = 300
        self.assertEqual(hdu.data._coldefs._arrays[1][0], 300)
        self.assertEqual(hdu.data._coldefs.data[1].array[0], 300)
        self.assertEqual(hdu.columns._arrays[1][0], 300)
        self.assertEqual(hdu.columns.data[1].array[0], 300)
        self.assertEqual(hdu.data[0][1], 300)

        hdu.data._coldefs._arrays[1][0] = 200
        self.assertEqual(hdu.data._coldefs._arrays[1][0], 200)
        self.assertEqual(hdu.data._coldefs.data[1].array[0], 200)
        self.assertEqual(hdu.columns._arrays[1][0], 200)
        self.assertEqual(hdu.columns.data[1].array[0], 200)
        self.assertEqual(hdu.data[0][1], 200)

        hdu.data._coldefs.data[1].array[0] = 100
        self.assertEqual(hdu.data._coldefs._arrays[1][0], 100)
        self.assertEqual(hdu.data._coldefs.data[1].array[0], 100)
        self.assertEqual(hdu.columns._arrays[1][0], 100)
        self.assertEqual(hdu.columns.data[1].array[0], 100)
        self.assertEqual(hdu.data[0][1], 100)

        hdu.columns._arrays[1][0] = 90
        self.assertEqual(hdu.data._coldefs._arrays[1][0], 90)
        self.assertEqual(hdu.data._coldefs.data[1].array[0], 90)
        self.assertEqual(hdu.columns._arrays[1][0], 90)
        self.assertEqual(hdu.columns.data[1].array[0], 90)
        self.assertEqual(hdu.data[0][1], 90)

        hdu.columns.data[1].array[0] = 80
        self.assertEqual(hdu.data._coldefs._arrays[1][0], 80)
        self.assertEqual(hdu.data._coldefs.data[1].array[0], 80)
        self.assertEqual(hdu.columns._arrays[1][0], 80)
        self.assertEqual(hdu.columns.data[1].array[0], 80)
        self.assertEqual(hdu.data[0][1], 80)

        tmpfile = open(jfile,'w')
        sys.stdout = tmpfile
        pyfits.info('newtable.fits')
        sys.stdout = sys.__stdout__
        tmpfile.close()
        tmpfile = open(jfile,'r')
        output = tmpfile.readlines()
        tmpfile.close()
        os.remove(jfile)
        self.assertEqual(output,['Filename: newtable.fits\n', 'No.    Name         Type      Cards   Dimensions   Format\n', '0    PRIMARY     PrimaryHDU       4  ()            uint8\n', '1                BinTableHDU     30  4R x 10C      [10A, J, 10A, 5E, L, 10A, J, 10A, 5E, L]\n'])

        hdul = pyfits.open('newtable.fits')
        hdu = hdul[1]

        self.assertEqual(hdu.columns.names,['target', 'counts', 'notes', 'spectrum', 'flag', 'target1', 'counts1', 'notes1', 'spectrum1', 'flag1'])

        tmpfile = open(jfile,'w')
        sys.stdout = tmpfile
        print hdu.data
        sys.stdout = sys.__stdout__
        tmpfile.close()
        tmpfile = open(jfile,'r')
        output = tmpfile.readlines()
        tmpfile.close()
        os.remove(jfile)
        self.assertEqual(output,["[ ('NGC1', 312, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), True, 'NGC5', 412, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), False)\n", " ('NGC2', 334, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), False, 'NGC6', 434, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), True)\n", " ('NGC3', 308, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), True, 'NGC7', 408, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), False)\n", " ('NCG4', 317, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), True, 'NCG8', 417, '0.0', array([ 0.,  0.,  0.,  0.,  0.], dtype=float32), False)]\n"])

        # Same verification from the file
        hdu.data[0][1] = 300
        self.assertEqual(hdu.data._coldefs._arrays[1][0], 300)
        self.assertEqual(hdu.data._coldefs.data[1].array[0], 300)
        self.assertEqual(hdu.columns._arrays[1][0], 300)
        self.assertEqual(hdu.columns.data[1].array[0], 300)
        self.assertEqual(hdu.data[0][1], 300)

        hdu.data._coldefs._arrays[1][0] = 200
        self.assertEqual(hdu.data._coldefs._arrays[1][0], 200)
        self.assertEqual(hdu.data._coldefs.data[1].array[0], 200)
        self.assertEqual(hdu.columns._arrays[1][0], 200)
        self.assertEqual(hdu.columns.data[1].array[0], 200)
        self.assertEqual(hdu.data[0][1], 200)

        hdu.data._coldefs.data[1].array[0] = 100
        self.assertEqual(hdu.data._coldefs._arrays[1][0], 100)
        self.assertEqual(hdu.data._coldefs.data[1].array[0], 100)
        self.assertEqual(hdu.columns._arrays[1][0], 100)
        self.assertEqual(hdu.columns.data[1].array[0], 100)
        self.assertEqual(hdu.data[0][1], 100)

        hdu.columns._arrays[1][0] = 90
        self.assertEqual(hdu.data._coldefs._arrays[1][0], 90)
        self.assertEqual(hdu.data._coldefs.data[1].array[0], 90)
        self.assertEqual(hdu.columns._arrays[1][0], 90)
        self.assertEqual(hdu.columns.data[1].array[0], 90)
        self.assertEqual(hdu.data[0][1], 90)

        hdu.columns.data[1].array[0] = 80
        self.assertEqual(hdu.data._coldefs._arrays[1][0], 80)
        self.assertEqual(hdu.data._coldefs.data[1].array[0], 80)
        self.assertEqual(hdu.columns._arrays[1][0], 80)
        self.assertEqual(hdu.columns.data[1].array[0], 80)
        self.assertEqual(hdu.data[0][1], 80)

        os.remove('table1.fits')
        os.remove('table2.fits')
        os.remove('newtable.fits')

    def testMaskArray(self):
        t=pyfits.open('table.fits')
        tbdata = t[1].data
        mask = tbdata.field('V_mag') > 12
        newtbdata = tbdata[mask]
        hdu = pyfits.BinTableHDU(newtbdata)
        hdu.writeto('newtable.fits')

        hdul = pyfits.open('newtable.fits')

        tmpfile = open(jfile,'w')
        sys.stdout = tmpfile
        print hdu.data
        sys.stdout = sys.__stdout__
        tmpfile.close()
        tmpfile = open(jfile,'r')
        output = tmpfile.readlines()
        tmpfile.close()
        os.remove(jfile)
        self.assertEqual(output,["[('NGC1002', 12.3) ('NGC1003', 15.2)]\n"])

        tmpfile = open(jfile,'w')
        sys.stdout = tmpfile
        print hdul[1].data
        sys.stdout = sys.__stdout__
        tmpfile.close()
        tmpfile = open(jfile,'r')
        output = tmpfile.readlines()
        tmpfile.close()
        os.remove(jfile)
        self.assertEqual(output,["[('NGC1002', 12.3) ('NGC1003', 15.2)]\n"])

        os.remove('newtable.fits')


if __name__ == '__main__':
    unittest.main()

