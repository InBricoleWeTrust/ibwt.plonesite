from zope.interface import implements
from Products.CMFQuickInstallerTool.interfaces import (
    INonInstallable as INonInstallableProducts
)
from Products.CMFPlone.interfaces import (
    INonInstallable as INonInstallableProfiles
)
import logging
from zope.i18nmessageid import MessageFactory

MessageFactory = ibwtplonesiteMessageFactory = MessageFactory('ibwt.plonesite')
logger = logging.getLogger('ibwt.plonesite')
EXTENSION_PROFILES = ('ibwt.plonesite:default',)
SKIN = 'ibwt.skin'
HIDDEN_PRODUCTS = [u'plone.app.openid', u'NuPlone']
HIDDEN_PROFILES = [u'plone.app.openid', u'NuPlone']

PRODUCT_DEPENDENCIES = (
)


class HiddenProducts(object):
    implements(INonInstallableProducts)

    def getNonInstallableProducts(self):
        return HIDDEN_PRODUCTS


class HiddenProfiles(object):
    implements(INonInstallableProfiles)

    def getNonInstallableProfiles(self):
        return [u'plone.app.openid', u'NuPlone']


def initialize(context):
    """Initializer called when used as a Zope 2 product."""


GLOBALS = globals()
