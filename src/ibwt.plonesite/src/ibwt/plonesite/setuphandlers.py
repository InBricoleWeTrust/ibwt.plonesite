import logging
import transaction
from Products.CMFCore.utils import getToolByName

from ibwt.plonesite import PRODUCT_DEPENDENCIES

logger = logging.getLogger('ibwt.plonesite / setuphandler')

INDEXES = {
    'FieldIndex': [
    ],
    'KeywordIndex': [
    ],
    'ZCTextIndex': [
    ],
    'DateIndex': [
    ],
}

METADATAS = [
]


def full_reindex(portal):
    logger.info('Reindex content')
    cat = getToolByName(portal, 'portal_catalog')
    cat.refreshCatalog()
    logger.info('Reindexed content')


# Define custom indexes
class ZCTextIndex_extra:
    lexicon_id = 'plone_lexicon'
    index_type = 'Okapi BM25 Rank'


ZCTextIndex_extra = ZCTextIndex_extra()
SelectedTextIndex_type = 'ZCTextIndex'
SelectedTextIndex_extra = ZCTextIndex_extra


def setup_catalog(portal,
                  indexes=None, metadatas=None,
                  remove_indexes=None, remove_metadatas=None,
                  reindex=True):
    if indexes is None:
        indexes = INDEXES
    if metadatas is None:
        metadatas = METADATAS
    if remove_indexes is None:
        remove_indexes = []
    if remove_metadatas is None:
        remove_metadatas = []
    portal_catalog = getToolByName(portal, 'portal_catalog')
    reindex_indexes = []
    reindex_columns = []
    for typ in indexes:
        for idx in indexes[typ]:
            e = None
            if typ == 'ZCTextIndex':
                e = SelectedTextIndex_extra
            if not idx in portal_catalog.indexes():
                logger.info('Adding index: %s' % idx)
                portal_catalog.manage_addIndex(idx, typ, e)
                reindex_indexes.append(idx)

    for column in metadatas:
        if not column in portal_catalog.schema():
            logger.info('Adding metadata: %s' % column)
            portal_catalog.manage_addColumn(column)
            reindex_columns.append(column)

    for idx in remove_indexes:
        if idx in portal_catalog.indexes():
            logger.info('Removing index: %s' % idx)
            portal_catalog.manage_delIndex(idx)
            if idx in reindex_indexes:
                reindex_indexes.pop(reindex_indexes.index(idx))

    for idx in remove_metadatas:
        if idx in portal_catalog.schema():
            logger.info('Removing metadata: %s' % idx)
            portal_catalog.manage_delColumn(column)
            if idx in reindex_columns:
                reindex_columns.pop(reindex_indexes.index(idx))

    if reindex:
        if reindex_columns:
            logger.info('Regenerating metadatas: %s' % reindex_columns)
            logger.info('Reindexing: %s' % reindex_indexes)
            portal_catalog.refreshCatalog(clear=0)
        elif reindex_indexes:
            logger.info('Reindexing: %s' % reindex_indexes)
            portal_catalog.manage_reindexIndex(reindex_indexes)


def setupVarious(context):
    """Miscellanous steps import handle.
    """

    # Ordinarily, GenericSetup handlers check for the existence of XML files.
    # Here, we are not parsing an XML file, but we use this text file as a
    # flag to check that we actually meant for this import step to be run.
    # The file is found in profiles/default.

    if context.readDataFile('ibwt.plonesite_various.txt') is None:
        return

    portal = context.getSite()
    setup_catalog(portal)
    full_reindex(portal)


def setupQi(context):
    """Miscellanous steps import handle.
    """
    # Ordinarily, GenericSetup handlers check for the existence of XML files.
    # Here, we are not parsing an XML file, but we use this text file as a
    # flag to check that we actually meant for this import step to be run.
    # The file is found in profiles/default.

    if context.readDataFile('ibwt.plonesite_qi.txt') is None:
        return

    portal = context.getSite()
    portal_quickinstaller = getToolByName(portal, 'portal_quickinstaller')
    #portal_setup = getToolByName(portal, 'portal_setup')
    logger = logging.getLogger('ibwt.plonesite.Install')

    for product in PRODUCT_DEPENDENCIES:
        logger.info('(RE)Installing %s.' % product)
        if not portal_quickinstaller.isProductInstalled(product):
            portal_quickinstaller.installProduct(product)
            transaction.savepoint()
