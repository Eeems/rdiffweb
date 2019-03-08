#!/usr/bin/python
# -*- coding: utf-8 -*-
# rdiffweb, A web interface to rdiff-backup repositories
# Copyright (C) 2019 rdiffweb contributors
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

from __future__ import unicode_literals

import logging
from rdiffweb.core import InvalidUserError, RdiffError
from rdiffweb.core.i18n import ugettext as _
from rdiffweb.core.user_ldap_auth import LdapPasswordStore
from rdiffweb.core.user_sqlite import SQLiteUserDB

from builtins import str, bytes
from future.utils import python_2_unicode_compatible
from future.utils.surrogateescape import encodefilename
from rdiffweb.core.librdiff import RdiffRepo
from rdiffweb.core.config import BoolOption

# Define the logger
logger = logging.getLogger(__name__)

SEP = b'/'


def normpath(val):
    "Normalize path value"
    if not val.endswith(SEP):
        val += SEP
    if val.startswith(SEP):
        val = val[1:]
    return val


class IUserChangeListener():
    """
    A listener to receive user changes event.
    """

    def __init__(self, app):
        self.app = app
        self.app.userdb.add_change_listener(self)

    def user_added(self, user, password):
        """New user (account) created."""

    def user_attr_changed(self, user, attrs={}):
        """User attribute changed."""

    def user_deleted(self, user):
        """User and related account information have been deleted."""

    def user_logined(self, user, password):
        """User successfully logged into rdiffweb."""

    def user_password_changed(self, user, password):
        """Password changed."""


@python_2_unicode_compatible
class UserObject(object):
    """Represent an instance of user."""

    def __init__(self, userdb, db, username):
        assert userdb
        assert db
        assert username
        self._userdb = userdb
        self._db = db
        self._username = username

    def __eq__(self, other):
        return (isinstance(other, UserObject) and
                self._username == other._username and
                self._db == other._db)

    def __str__(self):
        return 'UserObject[%s]' % self._username

    @property
    def username(self):
        return self._username

    def get_repo(self, name):
        """
        Return the repository identified as `name`.
        `name` may be a bytes string or unicode string.
        """
        assert isinstance(name, str) or isinstance(name, bytes)
        if isinstance(name, str):
            name = encodefilename(name)
        name = normpath(name)
        for r in self._db.get_repos(self._username):
            if name == normpath(encodefilename(r)):
                return RepoObject(self._db, self._username, r)
        raise KeyError(name)
    
    def get_repo_path(self, path):
        """
        Return a the repository identified by the given `path`.
        """
        assert isinstance(path, str) or isinstance(path, bytes)
        if isinstance(path, str):
            path = encodefilename(path)
        path = normpath(path)
        user_root = encodefilename(self.user_root)
        for r in self._db.get_repos(self._username):
            repo = normpath(encodefilename(r))
            if path.startswith(repo):                
                repo_obj = RdiffRepo(user_root, repo)
                path_obj = repo_obj.get_path(path[len(repo):])
                return (repo_obj, path_obj)
        raise KeyError(path)

    def set_attr(self, key, value, notify=True):
        """Used to define an attribute"""
        self.set_attrs(**{key: value, 'notify': notify})

    def set_attrs(self, **kwargs):
        """Used to define multiple attributes at once."""
        for key, value in kwargs.items():
            if key in ['is_admin', 'email', 'user_root', 'repos']:
                setter = getattr(self._db, 'set_%s' % key)
                setter(self._username, value)
        # Call notification listener
        if kwargs.get('notify', True):
            del kwargs['notify']
            self._userdb._notify('attr_changed', self._username, kwargs)

    # Declare properties
    is_admin = property(fget=lambda x: x._db.is_admin(x._username), fset=lambda x, y: x.set_attr('is_admin', y))
    email = property(fget=lambda x: x._db.get_email(x._username), fset=lambda x, y: x.set_attr('email', y))
    user_root = property(fget=lambda x: x._db.get_user_root(x._username), fset=lambda x, y: x.set_attr('user_root', y))
    repos = property(fget=lambda x: x._db.get_repos(x._username), fset=lambda x, y: x.set_attr('repos', y))
    repo_list = property(fget=lambda x: [RepoObject(x._db, x._username, r)
                                         for r in x._db.get_repos(x._username)])


@python_2_unicode_compatible
class RepoObject(object):
    """Represent a repository."""

    def __init__(self, db, username, repo):
        self._db = db
        self._username = username
        self._repo = repo

    def __eq__(self, other):
        return (isinstance(other, RepoObject) and
                self._username == other._username and
                self._repo == other._repo and
                self._db == other._db)

    def __str__(self):
        return 'RepoObject[%s]' % self._username

    def __repr__(self):
        return 'RepoObject(db, %r, %r)' % (self._username, self._repo)

    def set_attr(self, key, value):
        """Used to define an attribute to the repository."""
        self.set_attrs(**{key: value})

    def set_attrs(self, **kwargs):
        """Used to define multiple attribute to a repository"""
        for key, value in kwargs.items():
            assert isinstance(key, str) and key.isalpha() and key.islower()
            self._db.set_repo_attr(self._username, self._repo, key, value)

    def get_attr(self, key, default=None):
        assert isinstance(key, str)
        return self._db.get_repo_attr(self._username, self._repo, key, default)

    @property
    def name(self):
        return self._repo

    maxage = property(fget=lambda x: x._db.get_repo_maxage(x._username, x._repo), fset=lambda x, y: x._db.set_repo_maxage(x._username, x._repo, y))
    keepdays = property(fget=lambda x: int(x.get_attr('keepdays', default='-1')), fset=lambda x, y: x.set_attr('keepdays', int(y)))


class UserManager():
    """
    This class handle all user operation. This class is greatly inspired from
    TRAC account manager class.
    """
    
    _allow_add_user = BoolOption("AddMissingUser", False)

    def __init__(self, app):
        self.app = app
        self._database = SQLiteUserDB(app) 
        self._password_stores = [self._database, LdapPasswordStore(app)]
        self._change_listeners = []

    def add_change_listener(self, listener):
        self._change_listeners.append(listener)

    def remove_change_listener(self, listener):
        self._change_listeners.remove(listener)

    def add_user(self, user, password=None):
        """
        Used to add a new user with an optional password.
        """
        assert password is None or isinstance(password, str)
        # Check if user already exists.
        if self._database.exists(user):
            raise RdiffError(_("User %s already exists." % (user,)))
        # Find a database where to add the user
        logger.debug("adding new user [%s]", user)
        self._database.add_user(user)
        self._notify('added', user, password)
        # Find a password store where to set password
        if password:
            self._database.set_password(user, password)

        # Return user object
        return UserObject(self, self._database, user)

    def delete_user(self, user):
        """
        Delete the given user from password store.

        Return True if the user was deleted. Return False if the user didn't
        exists.
        """
        if hasattr(user, 'username'):
            user = user.username
        result = False
        # Delete user from database (required).
        if self._database.exists(user):
            logger.info("deleting user [%s] from database", user)
            result |= self._database.delete_user(user)
        if not result:
            return result
        # Delete credentials from password store (optional).
        store = self.find_user_store(user)
        if hasattr(store, 'delete_user'):
            logger.info("deleting user [%s] from password store [%s]", user, store)
            result |= store.delete_user(user)
        self._notify('deleted', user)
        return True

    def exists(self, user):
        """
        Verify if the given user exists in our database.

        Return True if the user exists. False otherwise.
        """
        return self._database.exists(user)

    def find_user_store(self, user):
        """
        Locates which store contains the user specified.

        If the user isn't found in any IPasswordStore in the chain, None is
        returned.
        """
        assert isinstance(user, str)
        for store in self._password_stores:
            try:
                if store.has_password(user):
                    return store
            except:
                pass
        return None

    def get_user(self, user):
        """Return a user object."""
        if not self.exists(user):
            raise InvalidUserError(user)
        return UserObject(self, self._database, user)

    def _get_supporting_store(self, operation):
        """
        Returns the IPasswordStore that implements the specified operation.

        None is returned if no supporting store can be found.
        """
        for store in self._password_stores:
            if store.supports(operation):
                return store
        return None

    def list(self):
        """Search users database. Return a generator of user object."""
        # TODO Add criteria as required.
        for username in self._database.list():
            yield UserObject(self, self._database, username)

    def login(self, user, password):
        """
        Called to authenticate the given user.

        Check if the credentials are valid. Then may actually add the user
        in database if allowed.

        If valid, return the username. Return False if the user exists but the
        password doesn't matches. Return None if the user was not found in any
        password store.
        The return user object. The username may not be equals to the given username.
        """
        assert isinstance(user, str)
        assert password is None or isinstance(user, str)
        # Validate the credentials
        logger.debug("validating user [%s] credentials", user)
        if not self._password_stores:
            logger.warn("not password store available to validate user credentials")
        real_user = False
        for store in self._password_stores:
            real_user = store.are_valid_credentials(user, password)
            if real_user:
                break
        if not real_user:
            return None
        # Check if user exists in database
        try:
            userobj = self.get_user(real_user)
            self._notify('logined', real_user, password)
            return userobj
        except InvalidUserError:
            # Check if user may be added.
            if not self._allow_add_user:
                logger.info("user [%s] not found in database", real_user)
                return None
            # Create user
            userobj = self.add_user(real_user)
            self._notify('logined', real_user, password)
            return userobj

    def set_password(self, user, password, old_password=None):
        # Check if user exists in database
        if not self.exists(user):
            raise InvalidUserError(user)
        # Try to update the user password.
        store = self.find_user_store(user)
        if store and not store.supports('set_password'):
            logger.warn("authentication backend for user [%s] does not support changing the password", user)
            raise RdiffError(_("You cannot change the user's password."))
        elif not store:
            store = self._get_supporting_store('set_password')
        if not store:
            logger.warn("none of the IPasswordStore supports setting the password")
            raise RdiffError(_("You cannot change the user's password."))
        store.set_password(user, password, old_password)
        self._notify('password_changed', user, password)

    def supports(self, operation, user=None):
        """
        Check if the users password store or user database supports the given operation.
        """
        assert isinstance(operation, str)
        assert user is None or isinstance(user, str)

        if user:
            if operation in ['set_password']:
                store = self.find_user_store(user)
                return store is not None and store.supports(operation)
            else:
                return self._database.supports(operation)
        else:
            if operation in ['set_password']:
                return self._get_supporting_store(operation) is not None
            else:
                return self._database.supports(operation)

    def _notify(self, mod, *args):
        mod = '_'.join(['user', mod])
        for listener in self._change_listeners:
            # Support divergent account change listener implementations too.
            try:
                logger.debug('call [%s] [%s]', listener.__class__.__name__, mod)
                getattr(listener, mod)(*args)
            except:
                logger.warning(
                    'IUserChangeListener [%s] fail to run [%s]',
                    listener.__class__.__name__, mod, exc_info=1)
