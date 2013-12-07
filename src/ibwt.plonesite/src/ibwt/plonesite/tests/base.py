import unittest2 as unittest

from ibwt.plonesite.testing import (
    PLONE_MANAGER_NAME,
    TEST_USER_NAME,
    IBWT_PLONESITE_SIMPLE as SIMPLE,
    IBWT_PLONESITE_FIXTURE as UNIT_TESTING,
    IBWT_PLONESITE_INTEGRATION_TESTING as INTEGRATION_TESTING,
    IBWT_PLONESITE_FUNCTIONAL_TESTING as FUNCTIONAL_TESTING,
    IBWT_PLONESITE_SELENIUM_TESTING as SELENIUM_TESTING,
)


class TestCase(unittest.TestCase):
    """We use this base class for all the tests in this package.
    If necessary, we can put common utility or setup code in here.
    """
    layer = UNIT_TESTING

    def setUp(self):
        super(TestCase, self).setUp()
        self.app = self.layer['app']
        self.portal = self.layer['portal']
        self.folder = self.layer['test-folder']

    def add_user(self, id, username, password, roles=None):
        self.layer.add_user(id, username, password, roles=None)

    def logout(self):
        self.layer.logout()

    def login(self, user=None):
        if not user:
            user = TEST_USER_NAME
        self.layer.login(self.portal, user)

    def loginAsPortalOwner(self):
        self.layer.loginAsPortalOwner()

    def loginAsManager(self):
        self.login(PLONE_MANAGER_NAME)

    def setRoles(self, roles=None, id=None):
        self.layer.setRoles(roles, id)


class IntegrationTestCase(TestCase):
    """Integration base TestCase."""
    layer = INTEGRATION_TESTING


class FunctionalTestCase(TestCase):
    """Functionnal base TestCase."""
    layer = FUNCTIONAL_TESTING


class SeleniumTestCase(TestCase):
    """Functionnal base TestCase."""
    layer = SELENIUM_TESTING


class SimpleTestCase(unittest.TestCase):
    layer = SIMPLE

# vim:set ft=python:
