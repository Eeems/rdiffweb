#!/usr/bin/python
# -*- coding: utf-8 -*-
# rdiffweb, A web interface to rdiff-backup repositories
# Copyright (C) 2018 Patrik Dufresne Service Logiciel
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

import logging
import unittest

from rdiffweb.test import WebCase


class HistoryPageTest(WebCase):

    login = True

    reset_app = True

    reset_testcases = True

    def _history(self, user, repo, limit=None):
        url = "/history/" + user + "/" + repo + "/"
        if limit:
            url += "?limit=%s" % limit
        return self.getPage(url)

    def test_history(self):
        self._history(self.USERNAME, self.REPO)
        # New
        self.assertInBody("2016-02-02 16:30")
        # Old
        self.assertInBody("2014-11-02 09:50")
        self.assertInBody("Show more")

    def test_history_with_limit(self):
        self._history(self.USERNAME, self.REPO, 10)
        self.assertInBody("Show more")
        self._history(self.USERNAME, self.REPO, 50)
        self.assertNotInBody("Show more")

    def test_as_another_user(self):
        # Create a nother user with admin right
        user_obj = self.app.store.add_user('anotheruser', 'password')
        user_obj.user_root = self.app.testcases
        user_obj.add_repo('testcases')

        self.getPage("/history/anotheruser/testcases")
        self.assertStatus('200 OK')

        # Remove admin right
        admin = self.app.store.get_user('admin')
        admin.is_admin = 0

        # Browse admin's repos
        self.getPage("/history/anotheruser/testcases")
        self.assertStatus('403 Forbidden')


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
