"""
Checking specifics portal settings.
"""

import unittest2 as unittest

from base import IntegrationTestCase


class TestSetup(IntegrationTestCase):
    """Check Policy."""

    def test_Noop(self):
        self.assertEquals(True, True)


def test_suite():
    """."""
    suite = unittest.TestSuite()
    suite.addTests(
        unittest.defaultTestLoader.loadTestsFromName(
            __name__))
    return suite
