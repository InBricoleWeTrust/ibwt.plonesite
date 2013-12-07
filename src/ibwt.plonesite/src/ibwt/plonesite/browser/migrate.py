#!/usr/bin/env python
# -*- coding: utf-8 -*-
__docformat__ = 'restructuredtext en'

import datetime
import re
import json
import traceback
import hashlib
import time
import subprocess
import threading

from zope.interface import alsoProvides
from zope import interface
from zope.annotation.interfaces import IAnnotations

#from Acquisition import aq_parent
from persistent.mapping import PersistentMapping

from Products.CMFCore.utils import getToolByName
from Products.contentmigration.walker import CustomQueryWalker
from Products.CMFDefault.upgrade.to22 import upgrade_dcmi_metadata

from Products.contentmigration.migrator import BaseInlineMigrator
#from Products.SimpleAttachment.migration import migrations as sa_migrations
from Products.CMFCore.CachingPolicyManager import manage_addCachingPolicyManager
from Products.CMFPlone.setuphandlers import addCacheHandlers
from Products.CMFPlone.setuphandlers import addCacheForResourceRegistry


from plone.app.upgrade.v40 import alphas
#from plone.registry.interfaces import IRegistry
from plone.indexer.interfaces import IIndexableObject
from plone.app.folder.migration import BTreeMigrationView as Bv

from plone.app.blob.migrations import (
    ATFileToBlobFileMigrator,
    ATImageToBlobImageMigrator,
)

from five import grok

from ibwt.plonesite.setuphandlers import setup_catalog
from ibwt.plonesite import upgrades


ENABLED = 1
PRODUCT = 'ibwt.plonesite'
log = upgrades.log
move = upgrades.move
re_flags = re.U | re.M | re.S | re.X


class FMigrator(ATFileToBlobFileMigrator):
    def migrate_data(self):
        f = self.old.getFile()
        self.new.getField('file').getMutator(self.new)(f)


class ImgMigrator(ATImageToBlobImageMigrator):
    def migrate_data(self):
        f = self.old.getImage()
        self.new.getField('image').getMutator(self.new)(f)


class BlobMigrator(BaseInlineMigrator):
    src_portal_type = 'File'
    src_meta_type = 'File'
    dst_portal_type = 'File'
    dst_meta_type = 'File'
    fields_map = {'file': None}
    reindex_indexes = tuple()

    def migrate_data(self):
        ppath = '/'.join(self.obj.getPhysicalPath())
        filename = ''
        for f in self.fields_map.keys():
            _marker = []
            oldfield = self.obj.schema[f]
            field = self.obj.getPrimaryField()
            try:
                # already migrated
                if (
                    'blob' in
                    oldfield.storage.get(
                        oldfield.__name__, self.obj
                    ).__class__.__name__.lower()
                ):
                    continue
                try:
                    filename = oldfield.get(self.obj).filename
                except:
                    pass
                data = oldfield.get(self.obj).data
                if (
                    not isinstance(data, basestring)
                    and hasattr(data, 'data')
                ):
                    data, odata = '', data
                    while odata is not None:
                        data += odata.data
                        odata = odata.next
                if (
                    not data
                    and not isinstance(data, basestring)
                ):
                    raise Exception('Invalid blob')
            except Exception:
                upgrades.log(
                    'Migration to blob failed for %s:\n'
                    '%s' % (ppath, traceback.format_exc()))
                data = _marker
            #upgrades.log(
            #        '%s %s;%s;%s' %(
            #            self.dst_portal_type.upper(),
            #            ppath,
            #            len(data),
            #            hashlib.sha224(data).hexdigest(),
            #        ))
            if not data:
                upgrades.log('VOID ' + ppath)
            resps = self.obj.getResponsables()
            self.obj.getField('responsables').set(self.obj, resps)
            title = self.obj.Title() or self.obj.title
            if not title:
                try:
                    title = self.obj.title_or_id()
                except:
                    pass
            if not title:
                try:
                    title = self.obj.getId()
                except:
                    pass
            if not title:
                try:
                    title = self.obj.id
                except:
                    pass
            self.obj.setTitle(title)
            self.obj.title = title
            # regarder si ts les idx existent
            self.obj.reindexObject(['Title', 'sortable_title'])
            self.obj.setDescription(
                self.obj.getDescription()
                or self.obj.Description())
            if data is not _marker:
                fset = field.getMutator(self.obj)
                fset(data)
                if filename:
                    field.get(self.obj).setFilename(filename)

    def last_migrate_reindex(self):
        try:
            self.obj.reindexObject(list(self.reindex_indexes))
        except Exception:
            upgrades.log(
                '%s failed reindex during blob migration:\n'
                '%s' % (
                    '/'.join(
                        self.obj.getPhysicalPath()),
                    traceback.format_exc()))


def is_migrated(context, step_id):
    value = migration_infos(context)
    return value.get(step_id, False)


def mark_migrated(context, step_id):
    value = migration_infos(context)
    value[step_id] = True
    upgrades.commit(context)


def migration_infos(context):
    path = '/'.join(context.getPhysicalPath())
    purl = getToolByName(context, 'portal_url')
    pobj = purl.getPortalObject()
    annotations = IAnnotations(pobj)
    if not PRODUCT in annotations:
        annotations[PRODUCT] = PersistentMapping()
    if not path in annotations[PRODUCT]:
        annotations[PRODUCT][path] = PersistentMapping()
    return annotations[PRODUCT][path]


def onlyonce(callback):
    step = callback.func_name

    def wrap(self, *args, **kwargs):
        context = self.context
        path = '/'.join(context.getPhysicalPath())
        try:
            if not is_migrated(context, step):
                callback(self, *args, **kwargs)
            else:
                upgrades.log('%s already done for %s' % (step, path))
            mark_migrated(context, step)
        except Exception:
            raise
    return wrap


class BTreeMigrationView(Bv):
    def mklog(self):
        """ helper to prepend a time stamp to the output """
        def log(msg, timestamp=True, cr=True):
            upgrades.log(msg)
        return log


class FileIbwtPlonesiteMigrator(BlobMigrator):
    src_portal_type = 'FileIbwtPlonesite'
    src_meta_type = 'FileIbwtPlonesite'
    dst_portal_type = 'FileIbwtPlonesite'
    dst_meta_type = 'FileIbwtPlonesite'


class IbwtPlonesite_migrate(grok.View):
    """Helper to migrate from older plone versions"""

    grok.context(interface.Interface)
    grok.require("cmf.ManagePortal")

    def __init__(self, *a, **kw):
        self.products = []
        self.upproducts = []
        self.view_maps = {}
        grok.View.__init__(self, *a, **kw)

    def monkeypatch(self):
        # commit on each suceeded step
        from Products.GenericSetup import upgrade as gs_u
        #context = self.context

        def doStep(self, tool):
            ctx = getToolByName(tool, 'portal_url').getPortalObject()
            ret = getattr(self, '_oldm_doStep')(tool)
            upgrades.commit(ctx)
            return ret
        if not hasattr(gs_u.UpgradeStep, '_oldm_doStep'):
            setattr(gs_u.UpgradeStep, '_oldm_doStep',
                    getattr(gs_u.UpgradeStep, 'doStep'))
            setattr(gs_u.UpgradeStep, 'doStep', doStep)

    def restore_monkeypatch(self):
        from Products.GenericSetup import upgrade as gs_u
        if hasattr(gs_u.UpgradeStep, '_oldm_doStep'):
            setattr(gs_u.UpgradeStep, 'doStep',
                    getattr(gs_u.UpgradeStep, '_oldm_doStep'))
            delattr(gs_u.UpgradeStep, '_oldm_doStep')

    def render(self):
        #mt = getToolByName(self.context, 'portal_membership')
        if not ENABLED:
            return
        try:
            self.monkeypatch()
            data = self.migrate()
        except Exception:
            trace = traceback.format_exc()
            log(trace, 'error')
            data = {'migrated': False, 'error': trace}
        finally:
            self.restore_monkeypatch()
        sdata = json.dumps(data)
        self.request.RESPONSE.setHeader("Content-Transfer-Encoding", "binary")
        self.request.RESPONSE.setHeader("Content-Length", len(sdata))
        self.request.RESPONSE.setHeader("Expires", "0")
        self.request.RESPONSE.setHeader(
            "Cache-Control", "no-cache, must-revalidate")
        self.request.RESPONSE.setHeader("Pragma", "no-cache")
        self.request.RESPONSE.setHeader('Content-Type', 'application/json')
        self.request.RESPONSE.addHeader(
            'Content-Disposition', "attachment; filename=file.json")
        self.request.RESPONSE.write(sdata)

    def migrate(self):
        migration_data = {}
        context = self.context
        # launch wvhtml controller thread to avoid dangling wv processes
        self.controlrun = True
        control_wv_t = threading.Thread(target=control_wv, args=(self,))
        control_wv_t.start()
        pt = self.context.restrictedTraverse('@@plone_portal_state')
        #portal_setup = getToolByName(context, 'portal_setup')
        context = self.context
        portal = pt.portal()
        #root = pt.navigation_root()
        annotations = IAnnotations(portal)
        if not PRODUCT in annotations:
            annotations[PRODUCT] = PersistentMapping()
        migration_data = annotations[PRODUCT]
        migration_data.setdefault('migrated', False)
        #qi = portal.portal_quickinstaller
        self.custom_hook_migrationbegin()
        self.migrate_btrees()
        #not_deleted = []
        # notneeded: self.delete_manual_broken(not_deleted)
        # notneeded: self.delete_broken(not_deleted)
        upgrades.cleanup_portal_setup_registries(context)
        # notneeded: self.migrate_actions()
        # notneeded: self.reimplement()
        self.to_blob()
        self.custom_hook_blob()
        self.to_blob_f()
        self.to_blob_i()
        self.migrate_object_provides()
        self.blob_pack()
        self.custom_hook_afterblob()
        self.remove_products()
        upgrades.cleanup_portal_setup_registries(context)
        self.custom_hook_before_plone_upgrade()
        self.upgrade_plone()
        self.custom_hook_after_plone_upgrade()
        self.totinymce()
        self.move_custom()
        self.update_view_maps()
        self.remap_views()
        self.remove_ttw()
        self.update_products_sets()
        self.custom_hook_before_postupgrade()
        self.postupgrade()
        self.custom_hook_after_postupgrade()
        self.cleanup_profile()
        # notneeded: self.rebuild_catalog()
        upgrades.cleanup_portal_setup_registries(context)
        upgrades.remove_persistent_utilities(
            context, [re.compile('CacheSetup', re_flags)])
        self.custom_hook_aftermigration()
        self.final_pack()
        self.custom_hook_finished()
        migration_data['migrated'] = True
        upgrades.log('Migration done')
        self.controlrun = False
        control_wv_t.join(1)
        ret = dict(migration_data.items())
        ret[self.path] = dict(migration_data[self.path].items())
        return ret

    @property
    def path(self):
        return '/'.join(self.context.getPhysicalPath())

    def delete_path(self, path):
        parts = path.split('/')
        parent = '/'.join(parts[:-1])
        id = parts[-1]
        ret = False
        try:
            parento = self.context.restrictedTraverse(parent)
            try:
                if parento is None:
                    raise
                parento.manage_delObjects([id])
                ret = True
                upgrades.log('Deleted %s' % path)
            except:
                upgrades.log("cannot delete %s" % path)
        except:
            upgrades.log("Cannot delete %s because parent does not exist anymore" % path)
        return ret

    def pack(self):
        upgrades.log('Packing database')
        upgrades.commit(self.context)
        self.context._p_jar._db.pack()

    def get_allobjs(self):
        catalog = getToolByName(self.context, 'portal_catalog')
        brains = catalog.search({})
        objects, brokens = {}, {}
        for i in brains:
            try:
                p = i.getPath()
                obj = i.getObject()
                if (
                    repr(obj).startswith(
                        '<persistent broken ')
                ):
                    brokens[p] = (i, obj)
                else:
                    objects[p] = (i, obj)
            except:
                brokens[p] = (i, None)
        return objects, brokens

    @onlyonce
    def migrate_btrees(self):
        """
        https://dev.plone.org/ticket/9912
        """
        upgrades.log('Migrating to BTrees')
        ret = BTreeMigrationView(self.context, self.request)()
        upgrades.commit(self.context)
        return ret

    @onlyonce
    def delete_manual_broken(self, not_deleted=None):
        """Delete well known (by path) objects"""
        if not_deleted is None:
            not_deleted = []
        knowns = [
            #self.path + '/CacheSetup_OFSCache',
        ]
        for path in knowns:
            if (
                not self.delete_path(path)
                and (not path in not_deleted)
            ):
                not_deleted.append(path)
        return not_deleted

    @onlyonce
    def delete_broken(self, not_deleted=None):
        if not_deleted is None:
            not_deleted = []
        catalog = getToolByName(self.context, 'portal_catalog')
        uid_catalog = getToolByName(self.context, 'uid_catalog')
        ref_catalog = getToolByName(self.context, 'reference_catalog')
        not_deleted = []
        notstop = True
        while notstop:
            objects, brokens = self.get_allobjs()
            for path in brokens:
                if (
                    not self.delete_path(path)
                    and (not path in not_deleted)
                ):
                    not_deleted.append(path)
            objects2, broken2 = self.get_allobjs()
            if not len(broken2) < len(brokens):
                notstop = False
            else:
                upgrades.log('Another pass to delete items')
        if len(broken2):
            catalog.refreshCatalog(clear=1)
            uid_catalog.refreshCatalog(clear=1)
            ref_catalog.refreshCatalog(clear=1)
        upgrades.commit(self.context)

    @onlyonce
    def migrate_actions(self):
        self.delete_path(self.path + '/portal_actions/object/relations')
        self.delete_path(self.path + '/portal_actions/user/fsdmystuff')

    @onlyonce
    def reimplement(self):
        catalog = getToolByName(self.context, 'portal_catalog')
        count = 0
        for i in catalog.search({}):
            o = i.getObject()
            if not IIndexableObject.providedBy(o):
                count += 1
                alsoProvides(o, IIndexableObject)
        msg = '%s have been marked as indexable' % count
        upgrades.log(msg)

    @onlyonce
    def to_blob(self):
        portal_setup = getToolByName(self.context, 'portal_setup')
        upgrade_dcmi_metadata(portal_setup)
        portal_setup.runAllImportStepsFromProfile('profile-plone.app.registry:default')
        portal_setup.runAllImportStepsFromProfile('profile-plone.app.blob:default')
        upgrades.commit(self.context)

    @onlyonce
    def to_blob_i(self):
        """To avoir conflicts during the plonemigration loop, run the blob migration now"""
        portal = getToolByName(self.context, 'portal_url').getPortalObject()
        migrator = ImgMigrator
        walker = CustomQueryWalker(portal, migrator, full_transaction=True)
        upgrades.log('Migrating images to blob')
        walker.go()
        upgrades.commit(self.context)

    @onlyonce
    def to_blob_f(self):
        """To avoir conflicts during the plonemigration loop, run the blob migration now"""
        portal = getToolByName(self.context, 'portal_url').getPortalObject()
        migrator = FMigrator
        walker = CustomQueryWalker(portal, migrator, full_transaction=True)
        upgrades.log('Migrating files to blob')
        walker.go()
        upgrades.commit(self.context)

    @onlyonce
    def migrate_object_provides(self):
        catalog = self.context.portal_catalog
        upgrades.log('Migrating object_provides')
        catalog.manage_reindexIndex(['object_provides'])

    @onlyonce
    def blob_pack(self):
        return self.pack()

    @onlyonce
    def remove_products(self):
        context = self.context
        qi = getToolByName(context, 'portal_quickinstaller')
        if qi.isProductInstalled('kupu'):
            upgrades.quickinstall_addons(
                context, uninstall=['kupu'])
        if 'kupu_library_tool' in context.objectIds():
            self.delete_path(self.path + "/kupu_library_tool")
        self.remove_cachefu()

    def remove_cachefu(self):
        """Remove cache fu (done often  too late in plonemigration)"""
        alphas.removeBrokenCacheFu(self.context)
        knowns = [
            self.path + '/portal_cache_settings',
            self.path + '/portal_squid',
            self.path + '/CacheSetup_PageCache',
            self.path + '/caching_policy_manager',
            self.path + '/HTTPCache',
            self.path + '/CacheSetup_OFSCache',
            self.path + '/CacheSetup_ResourceRegistryCache',
        ]
        upgrades.commit(self.context)
        not_deleted = []
        for path in knowns:
            if (
                not self.delete_path(path)
                and (not path in not_deleted)
            ):
                not_deleted.append(path)
        manage_addCachingPolicyManager(self.context)
        addCacheHandlers(self.context)
        addCacheForResourceRegistry(self.context)

    @onlyonce
    def upgrade_plone(self):
        """Run the plone_migration tool upgrade loop"""
        pm = getToolByName(self.context, 'portal_migration')
        if pm.needUpgrading():
            upgrades.log(
                upgrades.upgrade_plone(self.context)
            )
            upgrades.commit(self.context)
        if pm.needUpgrading():
            raise Exception("Plone did not upgrade")
        else:
            upgrades.commit(self.context)

    @onlyonce
    def totinymce(self):
        log('Migrating to tinymce')
        context = self.context
        acl_users = getToolByName(self.context, 'acl_users')
        users = acl_users.getUserNames()
        portal_membership = getToolByName(self.context, 'portal_membership')
        for user in users + ['admin']:
            member = portal_membership.getMemberById(user)
            log('Tinymce editor for %s' % user)
            member.wysiwyg_editor = "TinyMCE"
            member.setMemberProperties({'wysiwyg_editor': 'TinyMCE'})
        upgrades.commit(context)

    @onlyonce
    def move_custom(self):
        """Wipe out the portal_skins/custom CMF layer content"""
        upgrades.move_custom(
            self.context,
            ignores=[
                'logo_intra.jpg',
                'global_logo',
                'portlet_',
                'list_emails',
                'find_by_mail',
                'list_subscriptions',
            ])
        upgrades.commit(self.context)

    @onlyonce
    def remove_ttw(self):
        context = self.context
        ttw = getToolByName(context, 'portal_view_customizations')
        [ttw.manage_delObjects(a) for a in ttw.objectIds()]
        upgrades.commit(context)

    @onlyonce
    def cleanup_profile(self):
        ps = getToolByName(self.context, 'portal_setup')
        cleanup_profile = 'profile-%s:cleanup' % PRODUCT
        if ps.profileExists(cleanup_profile):
            ps.runAllImportStepsFromProfile(cleanup_profile)
        upgrades.commit(self.context)

    @onlyonce
    def remap_views(self):
        maps = self.view_maps
        if not maps:
            return
        views_i = {"FieldIndex": ['getLayout', 'default_page']}
        context = self.context
        catalog = self.context.portal_catalog
        setup_catalog(
            self.context,
            indexes=views_i,
            metadatas=[],
        )
        upgrades.commit(context)
        try:
            for view in maps.keys():
                brains = catalog.search({'getLayout': view})

                for brain in brains:
                    log(
                        'Changing view: %s %s->%s' % (
                            brain.getPath(),
                            view,
                            maps[view]
                        ))
                    try:
                        obj = brain.getObject()
                        obj.setLayout(maps[view])
                        catalog.reindexObject(obj, ['getLayout'])
                    except Exception, e:
                        log('Cant change layout: %s (%s)' % (
                            brain.getPath(), e))
                        continue
            catalog.uniqueValuesFor('getLayout')
            upgrades.commit(context)
        finally:
            setup_catalog(
                self.context,
                indexes=[], metadatas=[],
                remove_indexes=views_i["FieldIndex"],
                remove_metadatas=views_i["FieldIndex"],
            )
        upgrades.commit(context)

    @onlyonce
    def postupgrade(self):
        """Mark products as correctly installed by the quickinstaller"""
        upgrades.log('postupgrade')
        context = self.context
        upgrades.quickinstall_addons(
            self.context, self.products, [], upgrades=self.upproducts)
        upgrades.commit(context)

    @onlyonce
    def rebuild_catalog(self):
        context = self.context
        upgrades.upgrade_plone(context)
        catalog = getToolByName(self.context, 'portal_catalog')
        upgrades.log('Recataloging items')
        brains = catalog.search({})
        lb = len(brains)
        for i, itm in enumerate(brains):
            try:
                obj = context.unrestrictedTraverse(itm.getPath())
                uid = '/'.join(obj.getPhysicalPath())
                if not uid in catalog._catalog.uids:
                    catalog.catalog_object(obj)
                    catalog.indexObject(obj)
                # let the objects be wrapped now by plone.indexer
                if IIndexableObject.providedBy(obj):
                    interface.noLongerProvides(obj, IIndexableObject)
                    catalog.reindexObject(obj, [
                        "allowedRolesAndUsers", "object_provides", "sortable_title",
                        "getObjPositionInParent", "getObjSize", "is_folderish",
                        "syndication_enabled", "is_default_page", "getIcon"]
                    )
            except Exception, e:
                upgrades.log('pb cataloging %s; %s' % (itm.getPath(), e))
            if i % 10 == 0:
                upgrades.log('Recatalog: %s on %s (%s %s)' % (
                    i, lb, (i / (1.0 * lb) * 100), '%'))
                upgrades.commit(context)
        catalog.searchResults(path='/')
        upgrades.commit(context)

    @onlyonce
    def final_pack(self):
        self.pack()
        return self.pack()

    def custom_hook_migrationbegin(self):
        pass

    @onlyonce
    def custom_hook_blob(self):
        self.migrate_fileIbwtPlonesite_to_blob()
        self.migrate_simpleattachment_to_blob()

    @onlyonce
    def custom_hook_afterblob(self):
        pass

    @onlyonce
    def custom_hook_before_plone_upgrade(self):
        return
        self.log_files1()

    @onlyonce
    def custom_hook_after_plone_upgrade(self):
        ps = getToolByName(self.context, 'portal_setup')
        ps.runImportStepFromProfile(
            'profile-IbwtPlonesite.skin:default', "skins", run_dependencies=False)
        upgrades.quickinstall_addons(self.context, uninstall=['aws.pdfbook'])
        self.migrate_description()

    @onlyonce
    def custom_hook_before_postupgrade(self):
        pass

    @onlyonce
    def custom_hook_after_postupgrade(self):
        pass

    @onlyonce
    def custom_hook_aftermigration(self):
        pass

    @onlyonce
    def custom_hook_finished(self):
        return
        self.log_files2()

    def update_view_maps(self):
        self.view_maps.update({
            'folder_listing-DRH': 'folder_listing',
            'folder_sante': 'folder_summary_view',
            'gallery': 'galleria_view',
            'folder_summary_news_view': (
                'folder_summary_view'),
            'homepage_news': 'folder_summary_view',
        })

    def update_products_sets(self):
        self.products.extend([
            'collective.dancing',
            'collective.js.jqueryui',
            'plone.app.theming',
            'plone.app.dexterity',
            'plone.resource',
            'plone.app.caching',
            'plone.app.jquerytools',
            'collective.galleria',
            'plone.app.ldap',
            'csvreplicata',
            'ATVocabularyManager',
            'Ploneboard',
            'PloneboardNotify',
            'aws.pdfbook',
        ])
        self.upproducts.extend(['ContentWellPortlets'])

    @onlyonce
    def migrate_fileIbwtPlonesite_to_blob(self):
        upgrades.log('Migrating FileIbwtPlonesite to blob')
        walker = CustomQueryWalker(self.context, FileIbwtPlonesiteMigrator, full_transaction=True)
        walker.go()
        upgrades.commit(self.context)

    @onlyonce
    def migrate_simpleattachment_to_blob(self):
        """Move simple attachments to blob"""
        #upgrades.log('SimpleAttachment -> blob')
        #upgrades.log(
        #    sa_migrations.migrate_to_blob_storage(self.context)
        #)
        #upgrades.commit(self.context)
        pass

    @onlyonce
    def log_files1(self):
        return self.log_files("1")

    @onlyonce
    def log_files2(self):
        return self.log_files("5")

    def log_files(self, idx='1'):
        ptypes = ['Image', 'FileIbwtPlonesite', 'File',
                  'FileAttachment', 'ImageAttachment']
        lsize = 0
        for ptype in ptypes:
            for i in self.context.portal_catalog.search(
                {'portal_type': ptype}
            ):
                obj = i.getObject()
                ppath = '/'.join(obj.getPhysicalPath())
                field = 'file' in ptype.lower() and 'file' or 'image'
                data = obj.getField(field).get(obj).data
                ldata = len(data)
                lsize += ldata
                upgrades.log(
                    '%s_AFTERBLOB%s %s;%s;%s;' % (
                        ptype,
                        idx, ppath, ldata,
                        hashlib.sha224(data).hexdigest(),))
        upgrades.log(
            '%s_AFTERBLOB%s %s;%s;%s;' % (
                'TOTAL SIZE', idx, '/t', lsize, 0,))

    @onlyonce
    def migrate_reindexdescription(self, catalog):
        pref = 'Migrating html description to text:'
        upgrades.log('%s reindex' % pref)
        for obj, indexes in catalog:
            obj.reindexObject(indexes)
        upgrades.log('%s reindex finished' % pref)

    @onlyonce
    def migrate_description(self):
        catalog = self.context.portal_catalog
        portal_transforms = getToolByName(self.context,
                                          'portal_transforms')
        upgrades.log('Migrating html description to text')
        reindex = []
        for itm in catalog.search({}):
            obj = itm.getObject()
            desc = obj.getField('description').getRaw(obj)
            schema = obj.Schema()
            if desc:
                indexes = []
                data = portal_transforms.convert(
                    'html_to_text', desc
                ).getData()
                if data != desc:
                    obj.getField('description').set(obj, data)
                    indexes.append('description')
                if 'text' in schema.keys():
                    text = obj.getField('text').getRaw(obj)
                    p = '<p>&nbsp;</p>'
                    if text:
                        nval = ('%s\n'
                                '%s\n'
                                '%s\n'
                                '%s\n'
                                '%s') % (
                            desc, p, p, p, text)
                    else:
                        nval = desc
                    obj.getField('text').set(obj, nval)
                    indexes.append('text')
                # postpone the index to a later step
                if indexes:

                    reindex.append((obj, indexes))
        self.migrate_reindexdescription(reindex)
        upgrades.log(
            'Migrating html description to text: finished')
        upgrades.commit(self.context)


def control_wv(view):
    upgrades.log("Wvhtml killer/watcher thread start")
    onow = None
    onow = now = datetime.datetime.now()
    while view.controlrun:
        now = datetime.datetime.now()
        if now - onow > datetime.timedelta(seconds=30):
            upgrades.log("Always running wv control thread")
            onow = now
            pl = subprocess.Popen(
                ['ps', '-aeo', 'etime,pid,command'],
                stdout=subprocess.PIPE).communicate()[0]
        for i in [a.strip() for a in pl.splitlines() if 'wv' in a.lower()]:
            etime = i.split()[0]
            pid = i.split()[1]
            if ":" in etime:
                minutes = etime.split(':')[0]
                try:
                    if int(minutes) > 1:
                        subprocess.Popen(
                            ['kilL', '-9', '%s' % pid],
                            stdout=subprocess.PIPE).communicate()[0]
                        upgrades.log("Wvhtml control: kill %s" % pid)
                except:
                    pass
        time.sleep(10)
    upgrades.log("Wvhtml killer/watcher thread end")
# vim:set et sts=4 ts=4 tw=80:
