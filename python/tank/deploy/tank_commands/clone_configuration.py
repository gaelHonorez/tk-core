# Copyright (c) 2013 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

from .. import util
from ... import pipelineconfig
from ...errors import TankError

from tank_vendor import yaml

import sys
import os
import shutil


def clone_pipeline_configuration_html(log, tk, source_pc_id, user_id, new_name, target_linux, target_mac, target_win, is_localized):
    """
    Clones a pipeline configuration, not necessarily the one associated with the current tk handle.
    
    This script is called from the tank command directly and is what gets executed if someone
    tries to run the clone command from inside of Shotgun by right clicking on a Pipeline 
    Configuration entry and go select the clone action.
    """

    (source_folder, target_folder) = _do_clone(log, tk, source_pc_id, user_id, new_name, target_linux, target_mac, target_win)

    log.info("<b>Clone Complete!</b>")
    log.info("")
    log.info("Your configuration has been copied from <code>%s</code> "
             "to <code>%s</code>." % (source_folder, target_folder))

    # if this new clone is using a shared core API, tell people how to localize.
    if not(is_localized):
        log.info("")
        log.info("")
        log.info("Note: You are running a shared version of the Toolkit Core API for this new clone. "
                 "This means that when you make an upgrade to that shared API, all "
                 "the different projects that share it will be upgraded. This makes the upgrade "
                 "process quick and easy. However, sometimes you also want to break out of a shared "
                 "environment, for example if you want to test a new version of the Shotgun Pipeline Toolkit. ")
        log.info("")
        log.info("In order to change this pipeline configuration to use its own independent version "
                 "of the Toolkit API, you can execute the following command: ")
    
        if sys.platform == "win32":
            tank_cmd = os.path.join(target_folder, "tank.bat")
        else:
            tank_cmd = os.path.join(target_folder, "tank")
        
        log.info("")
        code_css_block = "display: block; padding: 0.5em 1em; border: 1px solid #bebab0; background: #faf8f0;"
        log.info("<code style='%s'>%s localize</code>" % (code_css_block, tank_cmd))


###################################################################################################
# private methods


def _do_clone(log, tk, source_pc_id, user_id, new_name, target_linux, target_mac, target_win):
    """
    Clones the current configuration
    """

    curr_os = {"linux2":"linux_path", "win32":"windows_path", "darwin":"mac_path" }[sys.platform]    
    source_pc = tk.shotgun.find_one("PipelineConfiguration", 
                                    [["id", "is", source_pc_id]], 
                                    ["code", "project", "linux_path", "windows_path", "mac_path"])
    source_folder = source_pc.get(curr_os)
    
    target_folder = {"linux2":target_linux, "win32":target_win, "darwin":target_mac }[sys.platform] 
    
    log.debug("Cloning %s -> %s" % (source_folder, target_folder))
    
    if not os.path.exists(source_folder):
        raise TankError("Cannot clone! Source folder '%s' does not exist!" % source_folder)
    
    if os.path.exists(target_folder):
        raise TankError("Cannot clone! Target folder '%s' already exists!" % target_folder)
    
    # copy files and folders across
    old_umask = os.umask(0)
    try:
        os.mkdir(target_folder, 0777)
        os.mkdir(os.path.join(target_folder, "cache"), 0777)
        util._copy_folder(log, os.path.join(source_folder, "config"), os.path.join(target_folder, "config"))
        util._copy_folder(log, os.path.join(source_folder, "install"), os.path.join(target_folder, "install"))
        shutil.copy(os.path.join(source_folder, "tank"), os.path.join(target_folder, "tank"))
        shutil.copy(os.path.join(source_folder, "tank.bat"), os.path.join(target_folder, "tank.bat"))
        os.chmod(os.path.join(target_folder, "tank.bat"), 0777)
        os.chmod(os.path.join(target_folder, "tank"), 0777)

        sg_code_location = os.path.join(target_folder, "config", "core", "install_location.yml")
        if os.path.exists(sg_code_location):
            os.chmod(sg_code_location, 0666)
            os.remove(sg_code_location)
        fh = open(sg_code_location, "wt")
        fh.write("# Shotgun Pipeline Toolkit configuration file\n")
        fh.write("# This file was automatically created by tank clone\n")
        fh.write("# This file reflects the paths in the pipeline configuration\n")
        fh.write("# entity which is associated with this location (%s).\n" % new_name)
        fh.write("\n")
        fh.write("Windows: '%s'\n" % target_win)
        fh.write("Darwin: '%s'\n" % target_mac)    
        fh.write("Linux: '%s'\n" % target_linux)                    
        fh.write("\n")
        fh.write("# End of file.\n")
        fh.close()
    
    except Exception, e:
        raise TankError("Could not create file system structure: %s" % e)
    finally:
        os.umask(old_umask)

    # now register this with the cache file for each storage
    for dr in tk.pipeline_configuration.get_data_roots().values():
        scm = pipelineconfig.StorageConfigurationMapping(dr)
        scm.add_pipeline_configuration(target_mac, target_win, target_linux)
    
    # finally register with shotgun
    data = {"linux_path": target_linux,
            "windows_path":target_win,
            "mac_path": target_mac,
            "code": new_name,
            "project": source_pc["project"],
            "users": [ {"type": "HumanUser", "id": user_id} ] 
            }
    log.debug("Create sg: %s" % str(data))
    pc_entity = tk.shotgun.create("PipelineConfiguration", data)
    log.debug("Created in SG: %s" % str(pc_entity))

    # lastly, update the pipeline_configuration.yml file
    old_umask = os.umask(0)
    try:
        
        sg_pc_location = os.path.join(target_folder, "config", "core", "pipeline_configuration.yml")
        
        # read the file first
        fh = open(sg_pc_location, "rt")
        try:
            data = yaml.load(fh)
        finally:
            fh.close()

        # now delete it        
        if os.path.exists(sg_pc_location):
            os.chmod(sg_pc_location, 0666)
            os.remove(sg_pc_location)

        # now update some fields            
        data["pc_id"] = pc_entity["id"]
        data["pc_name"] = new_name 
        
        # and write the new file
        fh = open(sg_pc_location, "wt")
        yaml.dump(data, fh)
        fh.close()

    except Exception, e:
        raise TankError("Could not update pipeline_configuration.yml file: %s" % e)
    
    finally:
        os.umask(old_umask)
        
    return (source_folder, target_folder)



    