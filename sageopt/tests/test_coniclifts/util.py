"""
   Copyright 2019 Riley John Murray

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""
import unittest
from sageopt.coniclifts.utilities import array_index_iterator


class BaseTest(unittest.TestCase):

    def assertArraysAlmostEqual(self, a, b, places=4):
        self.assertEqual(a.shape, b.shape)
        for tup in array_index_iterator(a.shape):
            self.assertAlmostEqual(a[tup], b[tup], places)
