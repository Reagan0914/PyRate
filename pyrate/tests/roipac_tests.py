'''
Tests for ROIPAC header translation module.

Created on 12/09/2012
@author: Ben Davies, NCI
         ben.davies@anu.edu.au
'''

import os, sys
from os.path import abspath, exists, join
import unittest, datetime

from numpy import amin, zeros
from numpy.testing import assert_array_equal

from pyrate import roipac
from common import SYD_TEST_DEM_HDR, SYD_TEST_OBS
from common import SINGLE_TEST_DIR, HEADERS_TEST_DIR

from gdal import Open, UseExceptions
UseExceptions()


#  sanity checking
if not exists(HEADERS_TEST_DIR):
	sys.exit("ERROR: Missing the 'headers' data for unittests\n")

# constants
SHORT_HEADER_PATH = join(SYD_TEST_OBS, 'geo_060619-061002.unw.rsc')
FULL_HEADER_PATH  = join(HEADERS_TEST_DIR, "geo_060619-060828.unw.rsc")
FULL_HEADER_PATH2 = join(SINGLE_TEST_DIR, 'geo_060619-061002.unw.rsc')



class DateParsingTests(unittest.TestCase):

	def test_parse_short_date_pre2000(self):
		dstr = "980416"
		self.assertEqual(datetime.date(1998, 4, 16), roipac.parse_date(dstr))

	def test_parse_short_date_post2000(self):
		dstr = "081006"
		self.assertEqual(datetime.date(2008, 10, 6), roipac.parse_date(dstr))

	def test_parse_date_range(self):
		dstr = "980416-081006"
		exp = (datetime.date(1998, 4, 16), datetime.date(2008, 10, 6))
		self.assertEqual(exp, roipac.parse_date(dstr))


class HeaderParsingTests(unittest.TestCase):
	'''Verifies conversion of ROIPAC files to EHdr format.'''
	
	# low level convenience function tests
	def test_filename_pair(self):
		base = "project/run/geo_070709-080310.unw"
		exp_hdr = "project/run/geo_070709-080310.unw.rsc"
		result = roipac.filename_pair(base)
		self.assertEqual((base, exp_hdr), result)

	# short format header tests 

	def test_parse_short_roipac_header(self):
		hdrs = roipac.parse_header(SHORT_HEADER_PATH)
		self.assertEqual(hdrs[roipac.WIDTH], 47)
		self.assertEqual(hdrs[roipac.FILE_LENGTH], 72)
		self.assertAlmostEqual(hdrs[roipac.X_FIRST], 150.910)
		self.assertEqual(hdrs[roipac.X_STEP], 0.000833333)
		self.assertEqual(hdrs[roipac.Y_FIRST], -34.170000000)
		self.assertEqual(hdrs[roipac.Y_STEP], -0.000833333)
		self.assertEqual(hdrs[roipac.WAVELENGTH], 0.0562356424)

	def test_parse_short_header_has_timespan(self):
		# Ensures TIME_SPAN_YEAR field is added during parsing
		hdrs = roipac.parse_header(SHORT_HEADER_PATH)
		self.assertTrue(hdrs.has_key(roipac.TIME_SPAN_YEAR))

		# check time span calc
		master = datetime.date(2006, 06, 19)
		slave = datetime.date(2006, 10, 02)
		diff = (slave - master).days / 365.25
		self.assertEqual(diff, hdrs[roipac.TIME_SPAN_YEAR])


	# long format header tests

	def test_parse_full_roipac_header(self):
		# Ensures "long style" original header can be parsed correctly
		hdrs = roipac.parse_header(FULL_HEADER_PATH)
		
		# check some other headers
		self.assertTrue(hdrs[roipac.XMIN] == hdrs[roipac.YMIN] == 0)
		self.assertTrue(hdrs[roipac.XMAX] == 5450)
		self.assertTrue(hdrs[roipac.YMAX] == 4365)

		# check DATE/ DATE12 fields are parsed correctly
		date0 = datetime.date(2006, 6, 19) # from  "DATE 060619" header
		date12 = (date0, datetime.date(2006, 8, 28)) # from DATE12 060619-060828
		self.assertEqual(hdrs[roipac.DATE], date0)
		self.assertEqual(hdrs[roipac.DATE12], date12)

	def test_read_full_roipac_header2(self):
		# Tests header from cropped original dataset is parsed correctly
		hdrs = roipac.parse_header(FULL_HEADER_PATH)
		self.assertTrue(len(hdrs) is not None)

	def test_xylast(self):
		# Test the X_LAST and Y_LAST header elements are calculated
		hdrs = roipac.parse_header(FULL_HEADER_PATH)
		self.assertAlmostEqual(hdrs[roipac.X_LAST], 151.8519444445)
		self.assertAlmostEqual(hdrs[roipac.Y_LAST], -34.625)

	def test_date_alias(self):
		# Test header has MASTER and SLAVE dates as keys
		hdrs = roipac.parse_header(FULL_HEADER_PATH)
		self.assertTrue(hdrs.has_key(roipac.MASTER))
		self.assertTrue(hdrs.has_key(roipac.SLAVE))
		self.assertEqual(hdrs[roipac.DATE], hdrs[roipac.MASTER])
		self.assertEqual(hdrs[roipac.DATE12][-1], hdrs[roipac.SLAVE])


class TranslationFunctionTests(unittest.TestCase):
	'Tests translate_header() with data files and a DEM'

	def test_translate_header(self):
		dest = "/tmp/ehdr.hdr"
		hdr = join(HEADERS_TEST_DIR, "geo_060619-060828.unw.rsc")
		roipac.translate_header(hdr, dest)

		with open(dest) as f:
			text = f.read()
			self.assertTrue("ncols 5451" in text)
			self.assertTrue("nrows 4366" in text)
			self.assertTrue("cellsize 0.0002777" in text) # compare to 7 places
			self.assertTrue("xllcorner 150.3377777" in text) # compare to 7 places
			exp_yll = "yllcorner " + str(round(-33.4122222 - (4366 * 0.0002777), 3))
			self.assertTrue(exp_yll in text, "Got " + exp_yll)

		os.remove(dest)

	def test_translate_header_defaults(self):
		# test default header filename
		base_hdr = abspath(join(SINGLE_TEST_DIR, "geo_060619-061002.unw.rsc"))
		hdr = "/tmp/geo_060619-061002.unw.rsc"
		if os.path.exists(hdr):
			os.unlink(hdr)

		os.symlink(base_hdr, hdr)
		exp_hdr = "/tmp/geo_060619-061002.hdr"

		if os.path.exists(exp_hdr): os.remove(exp_hdr)
		roipac.translate_header(hdr)
		self.assertTrue(os.path.exists(exp_hdr))

		# add data to /tmp for GDAL test
		base_data = abspath(join(SINGLE_TEST_DIR, "geo_060619-061002.unw"))
		exp_data = "/tmp/geo_060619-061002.unw"
		os.symlink(base_data, exp_data)

		# test GDAL can open the data with the new header & cleanup
		ds = Open(exp_data)
		self.assertTrue(ds is not None)
		bands = ds.GetRasterBand(1), ds.GetRasterBand(1)
		self.assertTrue(all(bands)) # both bands exist?

		del bands, ds
		os.unlink(exp_data)
		os.remove(exp_hdr)
		os.unlink(hdr)

	def test_translate_header_fail_wrong_input(self):
		# ensure giving the data file breaks translate_header()
		src = join(SYD_TEST_OBS, "geo_060619-061002.unw")
		try:
			roipac.translate_header(src)
			self.fail("Should not be able to accept .unw data file")
		except:
			pass

	def test_translate_header_fail_missing_input(self):
		# ensure giving the data file breaks translate_header()
		src = join(SYD_TEST_OBS, "fake.unw.rsc")
		self.assertRaises(IOError, roipac.translate_header, src)

	def test_translate_header_fail_with_dir_input(self):
		# ensure giving the data file breaks translate_header()
		self.assertRaises(IOError, roipac.translate_header, SYD_TEST_OBS)


	def test_translate_header_with_dem(self):
		# ensure the DEM header can be translated
		act = roipac.translate_header(SYD_TEST_DEM_HDR)
		self.assertEqual(act, SYD_TEST_DEM_HDR[:-7] + "hdr")

		with open(act) as f:
			lines = [line.strip() for line in f.readlines()]
			values = [line.split() for line in lines]

		self.assertTrue(['ncols', '47'] in values)
		self.assertTrue(['nrows', '72'] in values)

		# verify content has been converted
		self.assertTrue(['cellsize', '0.000833333'] in values)
		self.assertFalse(['nodata', '0'] in values)
		self.assertFalse(['nbands', '1'] in values)
		self.assertTrue(['byteorder', 'lsb'] in values)
		self.assertFalse(['layout', 'bil'] in values)
		self.assertTrue(['nbits', '16'] in values)
		self.assertTrue(['pixeltype', 'signedint'] in values)
		os.remove(act)

	def test_gdal_interop(self):
		# test GDAL can open and read data with new generated header
		hdr = join(SYD_TEST_OBS, "geo_060619-061002.unw.rsc")
		ehdr = join(SYD_TEST_OBS, "geo_060619-061002.hdr")
		if os.path.exists(ehdr):
			os.remove(ehdr) # can be left behind if the test fails

		roipac.translate_header(hdr)
		self.assertTrue(os.path.exists(ehdr))

		# open with GDAL and ensure there is data
		src = join(SYD_TEST_OBS, "geo_060619-061002.unw")
		ds = Open(src)
		self.assertTrue(ds is not None)

		# check faked amplitude band 1 for 0s
		band = ds.GetRasterBand(1)
		data = band.ReadAsArray()
		shape = data.shape
		assert_array_equal(data, zeros(shape))

		# check phase (band 2) for data
		band = ds.GetRasterBand(2)
		nodata = band.GetNoDataValue()
		self.assertEqual(nodata, 0) # check default ROIPAC NODATA

		# ensure decent data is retrieved
		data = band.ReadAsArray()
		self.assertTrue(amin(data) != 0) # ignore max as NODATA is 0
		self.assertTrue(data.ptp() != 0)

		# cleanup
		os.remove(ehdr)
