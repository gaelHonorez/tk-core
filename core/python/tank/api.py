"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------

Classes for the main Tank API.

"""
import os
import glob

from tank_vendor import yaml

from . import hook
from . import folder
from . import constants
from . import context
from . import root
from .util import shotgun
from .errors import TankError
from .path_cache import PathCache
from .template import read_templates, TemplatePath

class Tank(object):
    """
    Object with presenting interface to tank.
    """
    def __init__(self, project_path):
        """
        :param project_path: Path to root of project containing tank configuration.
        """
        # TODO: validate this really is a valid project path
        self.__project_path = os.path.abspath(project_path)
        self.__sg = None
        self.roots = root.get_project_roots(self.project_path)
        self.templates = read_templates(project_path, self.roots)
        

    ################################################################################################
    # properties
    
    @property
    def project_path(self):
        """
        Path to the primary root directory for a project.
        """
        return self.__project_path
    
    @property
    def shotgun(self):
        """
        Lazily create a Shotgun API handle
        """
        if self.__sg is None:
            self.__sg = shotgun.create_sg_connection(self.project_path)
        
        return self.__sg
        
    @property
    def version(self):
        """
        The version of the tank Core API (e.g. v0.2.3)

        :returns: string representing the version
        """
        # read this from info.yml
        info_yml_path = os.path.abspath(os.path.join( os.path.dirname(__file__), "..", "..", "info.yml"))
        try:
            with open(info_yml_path, "r") as info_fh:
                data = yaml.load(info_fh)
            data = str(data.get("version", "unknown"))
        # NOTE! REALLY WANT THIS TO BEHAVE NICELY WHEN AN ERROR OCCURS
        # PLEASE DO NOT LIMIT THIS CATCH-ALL EXCEPTION
        except:
            data = "unknown"

        return data

    @property
    def documentation_url(self):
        """
        Return the relevant documentation url for this app.

        :returns: url string, None if no documentation was found
        """
        # read this from info.yml
        info_yml_path = os.path.abspath(os.path.join( os.path.dirname(__file__), "..", "..", "info.yml"))
        try:
            with open(info_yml_path, "r") as info_fh:
                data = yaml.load(info_fh)
            data = str(data.get("documentation_url"))
            if data == "":
                data = None
        # NOTE! REALLY WANT THIS TO BEHAVE NICELY WHEN AN ERROR OCCURS
        # PLEASE DO NOT LIMIT THIS CATCH-ALL EXCEPTION
        except:
            data = None

        return data
    
    ##########################################################################################
    # public methods
    
    def template_from_path(self, path):
        """Finds a template that matches the input path.

        :param input_path: path against which to match a template. 
        :type  input_path: string representation of a path
        
        :returns: Template matching this path
        :rtype: Template instance or None
        """
        matched = []
        for key, template in self.templates.items():
            if template.validate(path):
                matched.append(template)

        if len(matched) == 0:
            return None
        elif len(matched) == 1:
            return matched[0]
        else:
            # ambiguity!
            msg = "%d Tank templates are matching the path '%s'.\n" % (len(matched), path)
            msg += "The overlapping templates are:\n"
            msg += "\n".join([str(x) for x in matched])         
            raise TankError(msg)        
    
    def paths_from_template(self, template, fields, skip_keys=None):
        """
        Finds paths that match a template using field values passed.

        :param template: Template against whom to match.
        :type  template: Tank.Template instance.
        :param fields: Fields and values to use.
        :type  fields: Dictionary.
        :param skip_keys: Keys whose values should be ignored from the fields parameter.
        :type  skip_keys: List of key names.

        :returns: Matching file paths
        :rtype: List of strings.
        """
        skip_keys = skip_keys or []
        if isinstance(skip_keys, basestring):
            skip_keys = [skip_keys]
        local_fields = fields.copy()
        # Add wildcard for each key to skip
        for skip_key in skip_keys:
            local_fields[skip_key] = "*"
        # Add wildcard for each field missing from the input fields
        for missing_key in template.missing_keys(local_fields):
            local_fields[missing_key] = "*"
            skip_keys.append(missing_key)
        glob_str = template._apply_fields(local_fields, ignore_types=skip_keys)
        # Return all files which are valid for this template
        found_files = glob.iglob(glob_str)
        return [found_file for found_file in found_files if template.validate(found_file)]

    def abstract_paths_from_template(self, template, fields):
        """Returns an abstract path based on a template.

        If the leaf level of the path contains only abstract keys, or only a combination
        of abstract keys with keys which appear higher up in the path, the method does
        not check that this level actually exists, only that the structure above it exists.

        :param template: Template with which to search.
        :param fields: Mapping of keys to values with which to assemble the abstract path.

        :returns: A list of paths whose abstract keys use their abstract(default) value unless
                  a value is specified for them in the fields parameter.
        """
        search_template = template
        search_fields = fields.copy()
        # If the leaf only includes abstract keys, leave it out of glob
        leaf_keys = set(template.keys.keys()) - set(template.parent.keys.keys())
        abstract_keys = template.abstract_keys()
        # we don't want values for abstract keys when searching
        for abstract_key in abstract_keys:
            search_fields[abstract_key] = None
        
        if all([k in abstract_keys for k in leaf_keys]):
            search_template = template.parent

        found_files = self.paths_from_template(search_template, search_fields)
        abstract_paths = set()
        for found_file in found_files:
            cur_fields = search_template.get_fields(found_file)
            for abstract_key in abstract_keys:
                # Abstract keys may have formatting values supplied
                cur_fields[abstract_key] = fields.get(abstract_key)
                abstract_paths.add(template.apply_fields(cur_fields))
        return list(abstract_paths)


    def paths_from_entity(self, entity_type, entity_id):
        """
        Finds paths associated with an entity.
        
        :param entity_type: a Shotgun entity type
        :params entity_id: a Shotgun entity id
        
        :returns: Matching file paths
        :rtype: List of strings.
        """

        # Use the path cache to look up all paths associated with this entity
        path_cache = PathCache(self.project_path)
        paths = path_cache.get_paths(entity_type, entity_id)
        path_cache.connection.close()
        
        return paths

    def entity_from_path(self, path):
        """
        Returns the shotgun entity associated with a path
        
        :param path: A path to a folder or file
        
        :returns: Shotgun dictionary containing name, type and id or None 
                  if no path was associated.
        """
        # Use the path cache to look up all paths associated with this entity
        path_cache = PathCache(self.project_path)
        entity = path_cache.get_entity(path)
        path_cache.connection.close()
        
        return entity

    def context_empty(self):
        """
        Create empty context.

        :returns: Context object.
        """
        return context.create_empty(self)
    
    def context_from_path(self, path, previous_context=None):
        """
        Derive a context from a path.

        :param path: a file system path
        :param previous_context: a context object to use to try to automatically extend the generated
                                 context if it is incomplete when extracted from the path. For example,
                                 the Task may be carried across from the previous context if it is 
                                 suitable and if the task wasn't already expressed in the file system
                                 path passed in via the path argument.
        :returns: Context object.
        """
        return context.from_path(self, path, previous_context)
    
    def context_from_entity(self, entity_type, entity_id):
        """
        Derive context from entity.

        :param entity_type: The name of the entity type.
        :type  entity_type: String.
        :param entity_id: Shotgun id of the entity upon which to base the context.
        :type  entity_id: Integer.

        :returns: Context object.
        """
        return context.from_entity(self, entity_type, entity_id)
    
    def create_filesystem_structure(self, entity_type, entity_id):
        """
        Create folders and associated data on disk to reflect branches in the project tree
        related to a specific entity.

    
        :param entity_type: The name of the entity type.
        :type  entity_type: String.
        :param entity_id: Shotgun id of the entity 
        :type  entity_id: Integer.

        :returns: The number of entity folders were processed
        """
        num_processed, _ = folder.process_filesystem_structure(self, entity_type, entity_id, preview=False)
        return num_processed
        
    def preview_filesystem_structure(self, entity_type, entity_id):
        """
        Previews folders that would be created by create_filesystem_structure.

        :param entity_type: The name of the entity type.
        :type  entity_type: String.
        :param entity_id: Shotgun id of the entity 
        :type  entity_id: Integer.

        :returns: List of items processed.
        """
        _, processed_items = folder.process_filesystem_structure(self, entity_type, entity_id, preview=True)
        return processed_items

    def execute_hook(self, hook_name, **kwargs):
        """
        Executes a core level hook, passing it any keyword arguments supplied. 

        :param hook_name: Name of hook to execute.

        :returns: Return value of the hook.
        """
        hook_path = _get_hook_path(hook_name, self.project_path)
        return hook.execute_hook(hook_path, self, **kwargs)

    

##########################################################################################
# module methods

def tank_from_path(path):
    """
    Create a Tank API instance based on a path inside a project.
    """
    project_path = root.get_primary_root(path)
    return Tank(project_path)

def _get_hook_path(hook_name, project_path):
    hook_folder = constants.get_core_hooks_folder(project_path)
    file_name = "%s.py" % hook_name
    # use project level hook if available
    hook_path = os.path.join(hook_folder, file_name)
    if not os.path.exists(hook_path):
        # construct install hooks path if no project(override) hook
        hooks_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "hooks"))
        hook_path = os.path.join(hooks_path, file_name)
    return hook_path