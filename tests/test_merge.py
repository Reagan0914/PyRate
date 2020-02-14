# coding: utf-8
#   This Python module is part of the PyRate software package.
#
#   Copyright 2020 Geoscience Australia
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
"""
This Python module contains tests for mpi operations in PyRate.
Run this module as 'mpirun -n 4 pytest tests/test_mpi.py'
"""
import glob
import shutil
import numpy as np
import pytest
import os
import tempfile
import random
import string
from . import common

import core.orbital
import core.shared

import process, prepifg, merge, conv2tif
from common import small_data_setup, reconstruct_mst, reconstruct_stack_rate, SML_TEST_DEM_HDR_GAMMA, pre_prepare_ifgs
import common
from core import algorithm, ref_phs_est as rpe, mpiops, config as cf, covariance, refpixel
from merge import create_png_from_tif
import unittest

legacy_maxvar = [
    15.4156637191772,
    2.85829424858093,
    34.3486289978027,
    2.59190344810486,
    3.18510007858276,
    3.61054635047913,
    1.64398515224457,
    14.9226036071777,
    5.13451862335205,
    6.82901763916016,
    10.9644861221313,
    14.5026779174805,
    29.3710079193115,
    8.00364685058594,
    2.06328082084656,
    5.66661834716797,
    5.62802362442017,
]


class MergingTest(unittest.TestCase):
    """ """
    def test_png_creation(self):
        """ """

        output_folder_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "test_data", "merge")
        create_png_from_tif(output_folder_path)

        # check if color map is created
        output_color_map_path = os.path.join(output_folder_path, "colormap.txt")
        if not os.path.isfile(output_color_map_path):
            self.assertTrue(False, "Output color map file not found at: " + output_color_map_path)

        # check if png is created
        output_image_path = os.path.join(output_folder_path, "stack_rate.png")
        if not os.path.isfile(output_image_path):
            self.assertTrue(False, "Output png file not found at: " + output_image_path)

        # check if kml is created
        output_kml_path = os.path.join(output_folder_path, "stack_rate.kml")
        if not os.path.isfile(output_kml_path):
            self.assertTrue(False, "Output kml file not found at: " + output_kml_path)

        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()