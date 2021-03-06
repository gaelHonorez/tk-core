# Copyright (c) 2013 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
Base class for engine and app testing
"""

import os
import time
import shutil
import tempfile

from mock import Mock
import unittest2 as unittest

import sgtk
import tank
from tank_vendor import yaml

TANK_TEMP = None
TANK_SOURCE_PATH = None

__all__ = ['setUpModule', 'TankTestBase', 'tank']

def setUpModule():
    """
    Creates studio level directories in temporary location for tests.
    """
    global TANK_TEMP
    global TANK_SOURCE_PATH

    


    # determine tests root location 
    temp_dir = tempfile.gettempdir()
    # make a unique test dir for each file
    temp_dir_name = "tankTemporaryTestData"
    # Append time to the temp directory name
    temp_dir_name += "_%f" % time.time()

    TANK_TEMP = os.path.join(temp_dir, temp_dir_name)
    # print out the temp data location
    msg = "Tank test data location: %s" % TANK_TEMP
    print "\n" + "="*len(msg)
    print msg
    print "="*len(msg) + "\n"

    # move tank directory if left by previous tests
    _move_data(TANK_TEMP)
    os.makedirs(TANK_TEMP)

    # create studio level tank directories
    studio_tank = os.path.join(TANK_TEMP, "tank")

    # make studio level subdirectories
    os.makedirs(os.path.join(studio_tank, "config", "core"))
    os.mkdir(os.path.join(studio_tank, "doc"))
    install_dir = os.path.join(studio_tank, "install")

    # copy tank engine code into place
    TANK_SOURCE_PATH = os.path.abspath(os.path.join( os.path.dirname(__file__), "..", "..", ".."))
    os.makedirs(os.path.join(install_dir, "engines"))



def _move_data(path):
    """
    Rename directory to backup name, if backup currently exists replace it.
    """
    if path and os.path.exists(path):
        dirname, basename = os.path.split(path)
        new_basename = "%s.old" % basename
        backup_path = os.path.join(dirname, new_basename)
        if os.path.exists(backup_path):
            shutil.rmtree(backup_path)

        try: 
            os.rename(path, backup_path)
        except WindowsError:
            # On windows intermittent problems with sqlite db file occur
            pc = sgtk.pipelineconfig.from_path(path)
            db_path = pc.get_path_cache_location()
            if os.path.exists(db_path):
                print 'Removing db %s' % db_path
                # Importing pdb allows the deletion of the sqlite db sometimes...
                import pdb
                # try multiple times, waiting longer in between
                for count in range(5):
                    try:
                        os.remove(db_path)
                        break
                    except WindowsError:
                        time.sleep(count*2) 
            os.rename(path, backup_path)


class TankTestBase(unittest.TestCase):
    """Test base class which manages fixtures for tank related tests."""
    def __init__(self, *args, **kws):
        super(TankTestBase, self).__init__(*args, **kws)
        # simple mocked shotgun
        self.sg_mock = self._setup_sg_mock()

        # Below are attributes which will be set during setUp

        # Path to temp directory
        self.tank_temp = None
        # fake project enity dictionary
        self.project = None
        self.project_root = None
        # alternate project roots for multi-root tests
        self.alt_root_1 = None
        self.alt_root_2 = None
        # path to tank source code
        self.tank_source_path = None
        # project level config directories
        self.project_config = None

    def setUp(self, project_tank_name = "project_code"):
        """Creates and registers test project."""
        self.tank_temp = TANK_TEMP
        self.tank_source_path = TANK_SOURCE_PATH

        # mocking shotgun data (see add_to_sg_mock)
        self._sg_mock_db = {}

        # define entity for test project
        self.project = {"type": "Project",
                        "id": 1,
                        "tank_name": project_tank_name,
                        "name": "project_name"}

        self.project_root = os.path.join(self.tank_temp, self.project["tank_name"].replace("/", os.path.sep) )
          
        # create project directory
        self._move_project_data()
        
        os.makedirs(self.project_root)
        
        project_tank = os.path.join(self.project_root, "tank")
        os.mkdir(project_tank)

        # project level config directories
        self.project_config = os.path.join(project_tank, "config")

        # create project cache directory
        project_cache_dir = os.path.join(project_tank, "cache")
        os.mkdir(project_cache_dir)

        # create back-link file from project storage
        data = "- {darwin: '%s', linux2: '%s', win32: '%s'}" % (project_tank, project_tank, project_tank) 
        self.create_file(os.path.join(project_tank, "config", "tank_configs.yml"), data)

        # add files needed by the pipeline config
        
        pc_yml = os.path.join(project_tank, "config", "core", "pipeline_configuration.yml")
        pc_yml_data = "{ project_name: %s, pc_id: 123, project_id: 12345, pc_name: Primary}\n\n" % self.project["tank_name"]        
        self.create_file(pc_yml, pc_yml_data)
        
        loc_yml = os.path.join(project_tank, "config", "core", "install_location.yml")
        loc_yml_data = "Windows: '%s'\nDarwin: '%s'\nLinux: '%s'" % (project_tank, project_tank, project_tank)
        self.create_file(loc_yml, loc_yml_data)
        
        roots = {"primary": {}}
        for os_name in ["windows_path", "linux_path", "mac_path"]:
            #TODO make os specific roots
            roots["primary"][os_name] = self.tank_temp        
        roots_path = os.path.join(project_tank, "config", "core", "roots.yml")
        roots_file = open(roots_path, "w") 
        roots_file.write(yaml.dump(roots))
        roots_file.close()        
        
        self.pipeline_configuration = sgtk.pipelineconfig.from_path(project_tank)        

        # add project to mock sg and path cache db
        self.add_production_path(self.project_root, self.project)
        
        # change to return our shotgun object
        def return_sg(*args, **kws):
            return self.sg_mock

        sgtk.util.shotgun.create_sg_connection = return_sg


    def tearDown(self):
        """Cleans up after tests."""
        self._move_project_data()

        
    def setup_fixtures(self, core_config="default_core"):
        test_data_path = os.path.join(self.tank_source_path, "tests", "data")
        core_source = os.path.join(test_data_path, core_config)
        core_target = os.path.join(self.project_config, "core")
        self._copy_folder(core_source, core_target)

        for config_dir in ["env", "hooks", "test_app", "test_engine"]:
            config_source = os.path.join(test_data_path, config_dir)
            config_target = os.path.join(self.project_config, config_dir)
            self._copy_folder(config_source, config_target)
        
        # Edit the test environment with correct hard-coded paths to the test engine and app
        src = open(os.path.join(test_data_path, "env", "test.yml"))
        dst = open(os.path.join(self.project_config, "env", "test.yml"), "w")
        
        test_app_path = os.path.join(self.project_config, "test_app")
        test_engine_path = os.path.join(self.project_config, "test_engine")
        
        for line in src:
            tmp = line.replace("TEST_APP_LOCATION", test_app_path)
            dst.write(tmp.replace("TEST_ENGINE_LOCATION", test_engine_path))
        
        src.close()
        dst.close()
    
    def setup_multi_root_fixtures(self):
        self.setup_fixtures(core_config="multi_root_core")
        # Add multiple project roots
        project_name = os.path.basename(self.project_root)
        self.alt_root_1 = os.path.join(self.tank_temp, "alternate_1", project_name)
        self.alt_root_2 = os.path.join(self.tank_temp, "alternate_2", project_name)
        
        # add backlink files to storage
        tank_code = os.path.join(self.project_root, "tank")
        data = "- {darwin: '%s', linux2: '%s', win32: '%s'}" % (tank_code, tank_code, tank_code) 
        self.create_file(os.path.join(self.alt_root_1, "tank", "config", "tank_configs.yml"), data)
        self.create_file(os.path.join(self.alt_root_2, "tank", "config", "tank_configs.yml"), data)


        # Write roots file
        roots = {"primary": {}, "alternate_1": {}, "alternate_2": {}}
        for os_name in ["windows_path", "linux_path", "mac_path"]:
            #TODO make os specific roots
            roots["primary"][os_name]     = os.path.dirname(self.project_root)
            roots["alternate_1"][os_name] = os.path.dirname(self.alt_root_1)
            roots["alternate_2"][os_name] = os.path.dirname(self.alt_root_2)
        roots_path = os.path.join(self.project_root, "tank", "config", "core", "roots.yml")     
        roots_file = open(roots_path, "w") 
        roots_file.write(yaml.dump(roots))
        roots_file.close()
        
        # need a new PC object that is using the new roots def file we just created
        self.pipeline_configuration = sgtk.pipelineconfig.from_path(os.path.join(self.project_root, "tank"))
        
        # add project root folders
        # primary path was already added in base setUp
        self.add_production_path(self.alt_root_1, self.project)
        self.add_production_path(self.alt_root_2, self.project)
        # use Tank object to write project info
        tk = sgtk.Sgtk(self.project_root)
        tk.create_filesystem_structure("Project", self.project["id"])

        

    def add_production_path(self, path, entity=None):
        """
        Creates project directories, populates path cache and mocked shotgun from a
        path an entity.
        
        :param path: Path of directory to create, relative to it's project.
        :param entity: Entity to add to path cache, mocked shotgun and for which
                       to write an entity file. Should be dictionary with 'type',
                       'name', and 'id' keys.
        """
        full_path = os.path.join(self.project_root, path)
        if not os.path.exists(full_path):
            # create directories
            os.makedirs(full_path)
        if entity:
            # add to path cache
            self.add_to_path_cache(path, entity)
            # populate mock sg
            self.add_to_sg_mock_db(entity)

    def add_to_path_cache(self, path, entity):
        """Adds a path and entity to the path cache sqlite db. Can also be done by useing
        sgtk.path_cache.PathCache.

        :param path: Absolute path to add.
        :param entity: Entity dictionary with values for keys 'id', 'name', and 'type'
        """
        path_cache = sgtk.path_cache.PathCache(self.pipeline_configuration)
        path_cache.add_mapping(entity["type"],
                                    entity["id"],
                                    entity["name"],
                                    path)
        # On windows path cache has persisted, interfering with teardowns, so get rid of it.
        path_cache.close()
        del(path_cache)
                                    

    def add_to_sg_mock_db(self, entities):
        """Adds an entity or entities to the mocked shotgun database.

        :param entities: A shotgun style dictionary with keys for id, type, and name
                         defined. A list of such dictionaries is also valid.
        """
        # make sure it's a list
        if isinstance(entities, dict):
            entities = [entities] 
        for entity in entities:
            # (type, id): {"id": 2, "type":"Shot", "name":...}
            self._sg_mock_db[(entity["type"], entity["id"])] = entity

    def add_to_sg_schema_db(self, entity_type, field_name, data):
        """Adds a schema info dictionary to the mocked up database.
        This will be returned when a a call to 
        schema_field_read(entity_type, field_name) is made.
        
        :param entity_type: The Shotgun Entity type that the field is associated with
        :param field_name: The field name to associate the schema data with
        :param data: schema data that schema_field_read should return
        """
        self._sg_mock_db[("schema_field_read", entity_type, field_name)] = data

    def create_file(self, file_path, data=""):
        """Creates a file on disk with specified data. First the file's directory path will be 
        created, and then a file with contents matching input data.

        :param file_path: Absolute path to the file.
        :param data: (Optional)Data to be written in the file. 
        """
        if not file_path.startswith(self.tank_temp):
            raise Exception("Only files in the test data area should be created with this method.")

        dir_path = os.path.dirname(file_path)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

        open_file = open(file_path, "w") 
        open_file.write(data)
        open_file.close()
            

    def _setup_sg_mock(self):
        """Primitive mocking of shotgun api. Should be used only when
        queries being mocked are limited(see implementations below for restrictions).
        """

        def find_one(entity_type, filters, fields=None, *args, **kws):
            """
            Version of find_one which only returns values when filtered by id.
            """
            for item in self._sg_mock_db.values():
                
                # first make sure that this record is right type
                if item.get("type") != entity_type:
                    continue
                
                # now check filters
                
                # complex style
                # {'conditions': [{'path': 'id', 'relation': 'is', 'values': [1]}], 'logical_operator': 'and'}
                
                # turn these into simple style
                new_filters = []
                if isinstance(filters, dict):
                    if filters.get("logical_operator") != "and":
                        raise Exception("unsupported sg mock find_one filter %s" % filters)
                    for c in filters.get("conditions"):
                        if c["relation"] != "is":
                            raise Exception("Unsupported sg mock find one filter %s" % filters)
                        field = c["path"]
                        value = c["values"][0]
                        if len(c["values"]) > 1:
                            raise Exception("Unsupported sg mock find one filter %s" % filters)
                        new_filters.append( [field, "is", value])
                    filters = new_filters
                

                found = True
                for f in filters:

                    # assume operator is equals: e.g
                    # filter = ["field", "is", "value"]
                    field = f[0]
                    if f[1] != "is":
                        raise Exception("Unsupported sg mock find one filter %s" % filters)
                    value = f[2]

                    # now search through item to see if we got it
                    if field in item and item[field] == value:
                        # it is a match! Keep going...
                        pass
                    else:
                        # no match!
                        found = False
                        break
                    
                # did we find it?
                if found:
                    return item
            
            # no match
            return None            

        def find(entity_type, filters, *args, **kws):
            """
            Returns all entries for specified type. 
            Filters are ignored in many cases, check code.
            """
            results = [self._sg_mock_db[key] for key in self._sg_mock_db if key[0] == entity_type]
            
            # support [['id', 'in', 23, 34]]
            if isinstance(filters, list) and len(filters) ==1:
                # we have a [[something]] structure
                inner_filter = filters[0]
                if isinstance(inner_filter, list) and len(inner_filter) > 2 and inner_filter[0] == "id" and inner_filter[1] == "in":
                    all_items_of_type = [self._sg_mock_db[key] for key in self._sg_mock_db if key[0] == entity_type]
                    ids_to_find = inner_filter[2:]
                    matches = []
                    for i in all_items_of_type:
                        if i["id"] in ids_to_find:
                            matches.append(i)
                    
                    # assign to final matches structure
                    results = matches
                
            # support dict style with 'is' relation
            if isinstance(filters, dict):
                for sg_filter in filters.get("conditions", []):
                    if sg_filter["relation"] == "is":
                        
                        if sg_filter["values"] == [None] and sg_filter["path"] == "id":
                            # always return empty for this
                            results = [] 
                        
                        if isinstance(sg_filter["values"][0], (int, str)):
                            # only handling simple string and number relations
                            field_name = sg_filter["path"]
                            # filter only if value exists in mocked data (if field not there don't skip)
                            results = [result for result in results if result.get(field_name, sg_filter["values"][0]) in sg_filter["values"]]
                        #TODO add entity filtering?

            return results
        
        def schema_field_read(entity_type, field_name):
            """
            Returns the schema info dictionary for a field
            """
            key = ("schema_field_read", entity_type, field_name)
            data = self._sg_mock_db.get(key, {})
            # wrap the returned data with a field name key
            # see https://github.com/shotgunsoftware/python-api/wiki/Reference%3A-Methods#wiki-schema_field_read
            return {field_name: data}
        
        def upload_thumbnail(entity_type, entity_id, path):
            """
            Nop thumb uploader
            """
            # do nothing
        
        mock_find_one = Mock(side_effect=find_one)
        mock_find = Mock(side_effect=find)
        mock_schema_field_read = Mock(side_effect=schema_field_read)
        sg = Mock()
        sg.base_url = "http://unit_test_mock_sg"
        sg.find_one = mock_find_one
        sg.find = mock_find
        sg.upload_thumbnail = upload_thumbnail
        sg.schema_field_read = mock_schema_field_read
        return sg

    def check_error_message(self, Error, message, func, *args, **kws):
        """
        Check that the correct exception is raised with the correct message.

        :param Error: The exception that is expected.
        :param message: The expected message on the exception.
        :param func: The function to call.
        :param args: Arguments to be passed to the function.
        :param kws: Keyword arguments passed to the function.

        :rasies: Exception if correct exception is not raised, or the message on the exception
                 does not match that specified.
        """
        self.assertRaises(Error, func, *args, **kws)

        try:
            func(*args, **kws)
        except Error, e:
            self.assertEquals(message, e.message)

    def _move_project_data(self):
        """
        Calls _move_data for all project roots.
        """
        _move_data(self.project_root)
        _move_data(self.alt_root_1)
        _move_data(self.alt_root_2)

    def _copy_folder(self, src, dst): 
        """
        Alternative implementation to shutil.copytree
        Copies recursively with very open permissions.
        Creates folders if they don't already exist.
        """
        files = []
        
        if not os.path.exists(dst):
            os.mkdir(dst, 0777)
    
        names = os.listdir(src) 
        for name in names:
    
            srcname = os.path.join(src, name) 
            dstname = os.path.join(dst, name) 
                    
            if os.path.isdir(srcname): 
                files.extend( self._copy_folder(srcname, dstname) )             
            else: 
                shutil.copy(srcname, dstname)
                files.append(srcname)
                # if the file extension is sh, set executable permissions
                if dstname.endswith(".sh") or dstname.endswith(".bat"):
                    # make it readable and executable for everybody
                    os.chmod(dstname, 0777)        
        
        return files
    
