#!/usr/bin/python
# -*- coding: utf-8 -*-
# rdiffweb, A web interface to rdiff-backup repositories
# Copyright (C) 2015 Patrik Dufresne Service Logiciel
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
Created on Dec 29, 2015

@author: Patrik Dufresne
"""

from __future__ import unicode_literals

import unittest

from rdiffweb.test import MockRdiffwebApp


class HistoryPageTest(unittest.TestCase):

    def setUp(self):
        self.app = MockRdiffwebApp(enabled_plugins=['SQLite'])
        self.app.reset()
        self.app.reset_testcases()
        self.app.login()

    def tearDown(self):
        # Stop patching ldap.initialize and reset state.
        self.app.clear()

    def test_index(self):
        """Make sure the browse page can be rendered without error."""
        page = self.app.root.history.index(path=b'testcases/')
        self.assertNotIn('Access denied.', page)
        self.assertNotIn('Error', page)
        self.assertIn('testcases', page)

if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
