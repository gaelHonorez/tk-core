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
Various helper methods relating to user interaction via the shell.
"""

import textwrap

from ... import pipelineconfig
from ...platform import validation
from ...platform import constants
from ...errors import TankError
from ...util import shotgun
from ..app_store_descriptor import TankAppStoreDescriptor
from ..descriptor import AppDescriptor
from .. import util


##########################################################################################
# user prompts

g_ask_questions = True

def ask_question(question, force_promt=False):
    """
    Ask a yes-no-always question
    returns true if user pressed yes (or previously always)
    false if no
    
    if force_prompt is True, it always ask, regardless of if the user
    has previously pressed [a]lways
    
    """
    global g_ask_questions
    if g_ask_questions == False and force_promt == False:
        # auto-press YES
        return True

    answer = raw_input("%s [Yna?]" % question)
    answer = answer.lower()
    if answer != "n" and answer != "a" and answer != "y" and answer != "":
        print("Press ENTER or y for YES, n for NO and a for ALWAYS.")
        answer = raw_input("%s [Yna?]" % question)

    if answer == "a":
        g_ask_questions = False
        return True

    if answer == "y" or answer == "":
        return True

    return False

def ask_yn_question(question):
    """
    Ask a yes-no question
    returns true if user pressed yes (or previously always)
    false if no
    """
    
    answer = raw_input("%s [yn]" % question )
    answer = answer.lower()
    if answer != "n" and answer != "y":
        print("Press y for YES, n for NO")
        answer = raw_input("%s [yn]" % question )
    
    if answer == "y":
        return True

    return False   


##########################################################################################
# displaying of info in the terminal, ascii-graphcics style

def format_bundle_info(log, descriptor):
    """
    Formats a release notes summary output for an app, engine or core
    """
    
    # yay we can install! - get release notes
    (summary, url) = descriptor.get_changelog()
    if summary is None:
        summary = "No details provided."
    
    
    log.info("/%s" % ("-" * 70))
    log.info("| Item:        %s" % descriptor)
    log.info("|")
    
    str_to_wrap = "Description: %s" % descriptor.get_description()
    for x in textwrap.wrap(str_to_wrap, width=68, initial_indent="| ", subsequent_indent="|              "):
        log.info(x)
    log.info("|")
    
    str_to_wrap = "Change Log:  %s" % summary
    for x in textwrap.wrap(str_to_wrap, width=68, initial_indent="| ", subsequent_indent="|              "):
        log.info(x)
    
    log.info("\%s" % ("-" * 70))




##########################################################################################
# displaying of info in the terminal, ascii-graphcics style



def get_configuration(log, tank_api_instance, new_ver_descriptor, old_ver_descriptor):
    """
    Retrieves all the parameters needed for an app, engine or framework.
    May prompt the user for information.
    """
    
    # first get data for all new settings values in the config
    param_diff = _generate_settings_diff(new_ver_descriptor, old_ver_descriptor)

    if len(param_diff) > 0:
        log.info("Several new settings are associated with %s." % new_ver_descriptor)
        log.info("You will now be prompted to input values for all settings")
        log.info("that do not have default values defined.")
        log.info("")

    params = {}
    for (name, data) in param_diff.items():

        ######
        # output info about the setting
        log.info("")
        log.info("/%s" % ("-" * 70))
        log.info("| Item:    %s" % name)
        log.info("| Type:    %s" % data["type"])
        str_to_wrap = "Summary: %s" % data["description"]
        for x in textwrap.wrap(str_to_wrap, width=68, initial_indent="| ", subsequent_indent="|          "):
            log.info(x)
        log.info("\%s" % ("-" * 70))
        

        # don't ask user to input anything for default values
        if data["value"] is not None:
            
            if data["type"] == "hook":
                # for hooks, instead set the value to "default"
                # this means that the app will use its local hooks
                # rather than the ones provided.
                value = constants.TANK_BUNDLE_DEFAULT_HOOK_SETTING
            else:
                # just copy the default value into the environment
                value = data["value"]
            params[name] = value

            # note that value can be a tuple so need to cast to str
            log.info("Auto-populated with default value '%s'" % str(value))

        else:

            # get value from user
            # loop around until happy
            input_valid = False
            while not input_valid:
                # ask user
                answer = raw_input("Please enter value (enter to skip): ")
                if answer == "":
                    # user chose to skip
                    log.warning("You skipped this value! Please update the environment by hand later!")
                    params[name] = None
                    input_valid = True
                else:
                    # validate value
                    try:
                        obj_value = _validate_parameter(tank_api_instance, new_ver_descriptor, name, answer)
                    except Exception, e:
                        log.error("Validation failed: %s" % e)
                    else:
                        input_valid = True
                        params[name] = obj_value
    

    return params







def ensure_frameworks_installed(log, tank_api_instance, file_location, descriptor, environment):
    """
    Recursively check that all required frameworks are installed.
    Anything not installed will be downloaded from the app store.
    """
    missing_fws = validation.get_missing_frameworks(descriptor, environment)
    # (this returns dictionaries with name and version keys)
    
    for fw_dict in missing_fws:
        
        # see if we can get this from the app store...
        fw_descriptor = TankAppStoreDescriptor.find_item(tank_api_instance.pipeline_configuration, 
                                                         AppDescriptor.FRAMEWORK, 
                                                         fw_dict["name"], 
                                                         fw_dict["version"])
        
        
        # and now process this framework
        log.info("Installing required framework %s..." % fw_descriptor)
        if not fw_descriptor.exists_local():
            fw_descriptor.download_local()
        
        # now assume a convention where we will name the fw_instance that we create in the environment
        # on the form name_version
        fw_instance_name = "%s_%s" % (fw_descriptor.get_system_name(), fw_descriptor.get_version())
    
        # check so that there is not an fw with that name already!
        if fw_instance_name in environment.get_frameworks():
            raise TankError("The environment already has a framework instance named %s! "
                            "Please contact support." % fw_instance_name)
    
        # now make sure all constraints are okay
        try:
            check_constraints_for_item(fw_descriptor, environment)
        except TankError, e:
            raise TankError("Cannot install framework: %s" % e)
    
        # okay to install!
    
        # create required shotgun fields
        fw_descriptor.ensure_shotgun_fields_exist()

        # run post install hook
        fw_descriptor.run_post_install()
    
        # now get data for all new settings values in the config
        params = get_configuration(log, tank_api_instance, fw_descriptor, None)
    
        # next step is to add the new configuration values to the environment
        environment.create_framework_settings(file_location, fw_instance_name, params, fw_descriptor.get_location())
        
        # now make sure these guys have all their required frameworks installed
        ensure_frameworks_installed(log, tank_api_instance, file_location, fw_descriptor, environment)
        
    
    
def check_constraints_for_item(descriptor, environment_obj, engine_instance_name=None):
    """
    Validates the constraints for a single item. This will check that requirements for 
    minimum versions for shotgun, core API etc are fulfilled.
    
    Raises a TankError if one or more constraints are blocking. The exception message
    will contain details. 
    """
    
    # get the parent engine descriptor, if we are checking an app
    if engine_instance_name:
        # we are checking an engine object (it has no parent engine)
        parent_engine_descriptor = environment_obj.get_engine_descriptor(engine_instance_name)
    else:
        parent_engine_descriptor = None
        
    # check constraints (minimum versions etc)
    (can_update, reasons) = _check_constraints(descriptor, parent_engine_descriptor)
    
    if can_update == False:
        reasons.insert(0, "%s requires an upgrade to one or more "
                          "of your installed components." % descriptor)
        details = " ".join(reasons)
        raise TankError(details)

    
##########################################################################################
# helpers


def _generate_settings_diff(new_descriptor, old_descriptor=None):
    """
    Returns a list of settings which are needed if we were to upgrade
    an environment based on old_descriptor to the one based on new_descriptor.
    
    Settings in the config which have default values will have their values
    populated in the return data structures.
    
    By omitting old_descriptor you will effectively diff against nothing, meaning
    that all the settings for the new version of the item (except default ones)
    will be part of the listing.
    
    Returns dict keyed by setting names. Each value is a dict with keys description and type:
    
    {
        "param1": {"description" : "a required param (no default)", "type": "str", value: None }
        "param1": {"description" : "an optional param (has default)", "type": "int", value: 123 }
    }
    
    """
    # get the new metadata (this will download the app potentially)
    schema = new_descriptor.get_configuration_schema()
    new_config_items = schema.keys()
    
    if old_descriptor is None:
        old_config_items = []
    else:
        try:
            old_schema = old_descriptor.get_configuration_schema()
            old_config_items = old_schema.keys()
        except TankError:
            # download to local failed? Assume that the old version is 
            # not valid. This is an edge case. 
            old_config_items = []
        
    
    new_parameters = set(new_config_items) - set(old_config_items)
    
    # add descriptions and types - skip default values!!!
    data = {}
    for x in new_parameters:        
        desc = schema[x].get("description", "No description.")
        schema_type = schema[x].get("type", "Unknown")
        default_val = schema[x].get("default_value")
        # check if allows_empty == True, in that case set default value to []
        if schema[x].get("allows_empty") == True:
            if default_val is None:
                default_val = []
        
        data[x] = {"description": desc, "type": schema_type, "value": default_val}
    return data
    
    


g_sg_studio_version = None
def __get_sg_version():
    """
    Returns the version of the studio shotgun server.
    
    :returns: a string on the form "X.Y.Z"
    """
    global g_sg_studio_version
    if g_sg_studio_version is None:
        try:
            studio_sg = shotgun.create_sg_connection()
            g_sg_studio_version = ".".join([ str(x) for x in studio_sg.server_info["version"]])        
        except Exception, e:
            raise TankError("Could not extract version number for studio shotgun: %s" % e)
        
    return g_sg_studio_version

def _check_constraints(descriptor_obj, parent_engine_descriptor = None):
    """
    Checks if there are constraints blocking an upgrade or install
    
    :returns: a tuple: (can_upgrade, list_of_reasons)
    """
    
    constraints = descriptor_obj.get_version_constraints()
    
    can_update = True
    reasons = []
    
    if "min_sg" in constraints:
        # ensure shotgun version is ok
        studio_sg_version = __get_sg_version()
        minimum_sg_version = constraints["min_sg"]
        if util.is_version_older(studio_sg_version, minimum_sg_version):
            can_update = False
            reasons.append("Requires at least Shotgun v%s but currently "
                           "installed version is v%s." % (minimum_sg_version, studio_sg_version))
        
    if "min_core" in constraints:
        # ensure core API is ok
        core_api_version = pipelineconfig.get_core_api_version_based_on_current_code()
        minimum_core_version = constraints["min_core"]
        if util.is_version_older(core_api_version, minimum_core_version):
            can_update = False
            reasons.append("Requires at least Core API %s but currently "
                           "installed version is %s." % (minimum_core_version, core_api_version))
    
    if "min_engine" in constraints:
        curr_engine_version = parent_engine_descriptor.get_version()
        minimum_engine_version = constraints["min_engine"]
        if util.is_version_older(curr_engine_version, minimum_engine_version):
            can_update = False
            reasons.append("Requires at least Engine %s %s but currently "
                           "installed version is %s." % (parent_engine_descriptor.get_display_name(),
                                                        minimum_engine_version, 
                                                        curr_engine_version))
            
    # for multi engine apps, validate the supported_engines list
    supported_engines  = descriptor_obj.get_supported_engines()
    if supported_engines is not None:
        # this is a multi engine app!
        engine_name = parent_engine_descriptor.get_system_name()
        if engine_name not in supported_engines:
            can_update = False
            reasons.append("Not compatible with engine %s. "
                           "Supported engines are %s" % (engine_name, ", ".join(supported_engines)))
    
    return (can_update, reasons)


def _validate_parameter(tank_api_instance, descriptor, parameter, str_value):
    """
    Convenience wrapper. Validates a single parameter.
    Will raise exceptions if validation fails.
    Returns the object-ified value on success.
    """
    
    schema = descriptor.get_configuration_schema()
    # get the type for the param we are dealing with
    schema_type = schema.get(parameter, {}).get("type", "unknown")
    # now convert string value input to objet (int, string, dict etc)
    obj_value = validation.convert_string_to_type(str_value, schema_type)
    # finally validate this object against the schema
    validation.validate_single_setting(descriptor.get_display_name(), tank_api_instance, schema, parameter, obj_value)
    
    # we are here, must mean we are good to go!
    return obj_value
