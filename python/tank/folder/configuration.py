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
Handles the creation of a configuration object structure based on the folder configuration on disk.

"""

import os
import fnmatch

from .folder_types import Static, ListField, Entity, Project, UserWorkspace, ShotgunStep, ShotgunTask

from ..errors import TankError
from ..platform import constants

from tank_vendor import yaml


def read_ignore_files(schema_config_path):
    """
    Reads ignore_files from root of schema if it exists.
    Returns a list of patterns to ignore.
    """
    ignore_files = []
    file_path = os.path.join(schema_config_path, "ignore_files")
    if os.path.exists(file_path):
        open_file = open(file_path, "r")
        try:
            for line in open_file.readlines():
                # skip comments
                if "#" in line:
                    line = line[:line.index("#")]
                line = line.strip()
                if line:
                    ignore_files.append(line)
        finally:
            open_file.close()
    return ignore_files

class FolderConfiguration(object):
    """
    Class that loads the schema from disk and constructs folder objects.
    """

    def __init__(self, tk, schema_config_path):
        """
        Constructor
        """
        self._tk = tk
        
        # access shotgun nodes by their entity_type
        self._entity_nodes_by_type = {}
        
        # maintain a list of all Step nodes for special introspection
        self._step_fields = []
        
        # read skip files config
        self._ignore_files = read_ignore_files(schema_config_path)
        
        # load schema
        self._load_schema(schema_config_path)


    ##########################################################################################
    # public methods

    def get_folder_objs_for_entity_type(self, entity_type):
        """
        Returns all the nodes representing a particular sg entity type
        """
        return self._entity_nodes_by_type.get(entity_type, [])

    def get_task_step_nodes(self):
        """
        Returns all step nodes in the configuration
        """
        return self._step_fields

    ####################################################################################
    # utility methods

    def _get_sub_directories(self, parent_path):
        """
        Returns all the directories for a given path
        """
        directory_paths = []
        for file_name in os.listdir(parent_path):
            full_path = os.path.join(parent_path, file_name)
            # ignore files
            if os.path.isdir(full_path) and not file_name.startswith("."):
                directory_paths.append(full_path)
        return directory_paths

    def _get_files_in_folder(self, parent_path):
        """
        Returns all the files for a given path except yml files
        Also ignores any files mentioned in the ignore files list
        """
        file_paths = []
        items_in_folder = os.listdir(parent_path)

        folders = [f for f in items_in_folder if os.path.isdir(os.path.join(parent_path, f))]

        for file_name in items_in_folder:

            full_path = os.path.join(parent_path, file_name)

            if not os.path.isfile(full_path):
                # not a file path!
                continue

            if any(fnmatch.fnmatch(file_name, p) for p in self._ignore_files):
                # don't process files matching ignore pattern(s)
                continue

            if file_name.endswith(".yml") and os.path.splitext(file_name)[0] in folders:
                # this is a foo.yml and we have a folder called foo
                # this means that this is a config file!
                continue

            # this is a file path and it
            file_paths.append(full_path)


        return file_paths

    def _read_metadata(self, full_path):
        """
        Reads metadata file.

        :param full_path: Absolute path without extension
        :returns: Dictionary of file contents or None
        """
        metadata = None
        # check if there is a yml file with the same name
        yml_file = "%s.yml" % full_path
        if os.path.exists(yml_file):
            # try to parse it
            try:
                open_file = open(yml_file)
                try:
                    metadata = yaml.load(open_file)
                finally:
                    open_file.close()
            except Exception, error:
                raise TankError("Cannot load config file '%s'. Error: %s" % (yml_file, error))
        return metadata

    ##########################################################################################
    # internal stuff


    def _load_schema(self, schema_config_path):
        """
        Scan the config and build objects structure
        """

        project_folders = self._get_sub_directories(schema_config_path)

        # make some space in our obj/entity type mapping
        self._entity_nodes_by_type["Project"] = []

        for project_folder in project_folders:

            # read metadata to determine root path
            metadata = self._read_metadata(project_folder)

            if metadata is None:
                if os.path.basename(project_folder) == "project":
                    # this is a project folder with no project.yml file specified
                    # in this case, just assume it is the primary storage 
                    metadata = {"type": "project", "root_name": constants.PRIMARY_STORAGE_NAME}
                else:
                    raise TankError("Project directory missing required yml file: %s.yml" % project_folder)

            if metadata.get("type") != "project":
                raise TankError("Only items of type 'project' are allowed at the root level: %s" % project_folder)

            project_obj = Project.create(self._tk, project_folder, metadata)

            # store it in our lookup tables
            self._entity_nodes_by_type["Project"].append(project_obj)

            # recursively process the rest
            self._process_config_r(project_obj, project_folder)


    def _process_config_r(self, parent_node, parent_path):
        """
        Recursively scan the file system and construct an object
        hierarchy.

        Factory method for Folder objects.
        """
        for full_path in self._get_sub_directories(parent_path):
            # check for metadata (non-static folder)
            metadata = self._read_metadata(full_path)
            if metadata:
                node_type = metadata.get("type", "undefined")

                if node_type == "shotgun_entity":
                    cur_node = Entity.create(self._tk, parent_node, full_path, metadata)

                    # put it into our list where we group entity nodes by entity type
                    et = cur_node.get_entity_type()
                    if et not in self._entity_nodes_by_type:
                        self._entity_nodes_by_type[et] = []
                    self._entity_nodes_by_type[et].append(cur_node)

                elif node_type == "shotgun_list_field":
                    cur_node = ListField.create(self._tk, parent_node, full_path, metadata)

                elif node_type == "static":
                    cur_node = Static.create(self._tk, parent_node, full_path, metadata)

                elif node_type == "user_workspace":
                    cur_node = UserWorkspace.create(self._tk, parent_node, full_path, metadata)

                elif node_type == "shotgun_step":
                    cur_node = ShotgunStep.create(self._tk, parent_node, full_path, metadata)
                    self._step_fields.append(cur_node)

                elif node_type == "shotgun_task":
                    cur_node = ShotgunTask.create(self._tk, parent_node, full_path, metadata)

                else:
                    # don't know this metadata
                    raise TankError("Error in %s. Unknown metadata type '%s'" % (full_path, node_type))
            else:
                # no metadata - so this is just a static folder!
                # specify the type in the metadata chunk for completeness
                # since we are passing this into the hook later
                cur_node = Static.create(self._tk, parent_node, full_path, {"type": "static"})

            # and process children
            self._process_config_r(cur_node, full_path)

        # now process all files and add them to the parent_node token
        for f in self._get_files_in_folder(parent_path):
            parent_node.add_file(f)












