# Copyright (c) 2013 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

from ...errors import TankError
from . import console_utils
from .action_base import Action

from ..descriptor import AppDescriptor
from ..descriptor import get_from_location
from ..app_store_descriptor import TankAppStoreDescriptor 


class InstallAppAction(Action):
    """
    Action for installing an app
    """
    def __init__(self):
        Action.__init__(self, 
                        "install_app", 
                        Action.PC_LOCAL, 
                        "Adds a new app to your configuration.", 
                        "Configuration")
    
    def run(self, log, args):

        if len(args) != 3:
            
            log.info("This command adds an app to an existing environment and engine. "
                     "You can either add apps from the Toolkit App Store or from git "
                     "source control.")
            log.info("")
            log.info("Adding an app from the Toolkit App Store")
            log.info("----------------------------------------")
            log.info("")
            log.info("The standard mechanism through which apps and engines are distributed "
                     "is the Toolkit App Store. Items in the App Store are part of the official "
                     "toolkit distribution and have gone through our quality control process. "
                     "To see all apps and engines in the Toolkit App Store, navigate here:")
            log.info("https://toolkit.shotgunsoftware.com/entries/23874562")
            log.info("")
            log.info("To install an app store app, use the following syntax:")
            log.info("> tank install_app environment_name engine_name app_name")
            log.info("")
            log.info("For example, to install the loader app into the shell engine in the "
                     "Asset environment:")
            log.info("> tank install_app Asset tk-shell tk-multi-loader")
            log.info("")
            log.info("")
            log.info("")
            log.info("Adding an app from git or github")
            log.info("----------------------------------------")
            log.info("")
            log.info("You can also install apps directly from git or github. Toolkit will "
                     "read a git repository's list of tags, try to interpret them as version numbers, and "
                     "install the tag with the highest version number. Later on, when you run "
                     "the 'tank updates' command, it will automatically detect if there are tags "
                     "with higher version number than the currently installed and prompt you to "
                     "update.")
            log.info("")
            log.info("We strongly recommend that your tags following the Semantic Version "
                     "numbering scheme when working with Toolkit. You can read more about it "
                     "here: http://semver.org")
            log.info("")
            log.info("To install an app from git, use the following syntax:")
            log.info("> tank install_app environment_name engine_name git-repo")
            log.info("")
            log.info("The git_repo part is a repository location that can be understood by git. "
                     "Examples include: ")
            log.info(" - /path/to/repo.git")
            log.info(" - user@remotehost:/path_to/repo.git")
            log.info(" - git://github.com/manneohrstrom/tk-hiero-publish.git")
            log.info(" - https://github.com/manneohrstrom/tk-hiero-publish.git")
            log.info("")
            log.info("")
            log.info("Handy tip: For a list of existing environments, engines and apps, "
                     "run the 'tank app_info' command.")
            log.info("")
            
            return
            

        env_name = args[0]
        engine_instance_name = args[1]
        app_name = args[2]
        
        log.info("")
        log.info("Welcome to the Shotgun Pipeline Toolkit App installer!")
        log.info("Installing into environment %s and engine %s." % (env_name, engine_instance_name))
    
        try:
            env = self.tk.pipeline_configuration.get_environment(env_name)
        except Exception, e:
            raise TankError("Environment '%s' could not be loaded! Error reported: %s" % (env_name, e))
    
        # make sure the engine exists in the environment
        if engine_instance_name not in env.get_engines():
            raise TankError("Environment %s has no engine named %s!" % (env_name, engine_instance_name))
    
        
        if app_name.endswith(".git"):
            # this is a git location!
            # run descriptor factory method
            log.info("Connecting to git...")
            location = {"type": "git", "path": app_name, "version": "v0.0.0"}
            tmp_descriptor = get_from_location(AppDescriptor.APP, 
                                               self.tk.pipeline_configuration, 
                                               location)
            # now find latest
            app_descriptor = tmp_descriptor.find_latest_version()
            log.info("Latest version in repository '%s' is %s." % (app_name, 
                                                                   app_descriptor.get_version()))
            
        else:
            # this is an app store app!
            log.info("Connecting to the Toolkit App Store...")
            app_descriptor = TankAppStoreDescriptor.find_item(self.tk.pipeline_configuration, AppDescriptor.APP, app_name)
            log.info("Latest approved App Store Version is %s." % app_descriptor.get_version())
        
        # note! Some of these methods further down are likely to pull the apps local
        # in order to do deep introspection. In order to provide better error reporting,
        # pull the apps local before we start
        if not app_descriptor.exists_local():
            log.info("Downloading, hold on...")
            app_descriptor.download_local()
    
        # now assume a convention where we will name the app instance that we create in the environment
        # the same as the short name of the app
        app_instance_name = app_descriptor.get_system_name()
    
        # check so that there is not an app with that name already!
        if app_instance_name in env.get_apps(engine_instance_name):
            raise TankError("Engine %s already has an app named %s!" % (engine_instance_name, app_instance_name))
    
        # now make sure all constraints are okay
        try:
            console_utils.check_constraints_for_item(app_descriptor, env, engine_instance_name)
        except TankError, e:
            raise TankError("Cannot install: %s" % e)
    
        # okay to install!
        
        # ensure that all required frameworks have been installed
        
        # find the file where our app is being installed
        # when adding new items, we always add them to the root env file
        fw_location = env.disk_location
        console_utils.ensure_frameworks_installed(log, self.tk, fw_location, app_descriptor, env)
    
        # create required shotgun fields
        app_descriptor.ensure_shotgun_fields_exist()
    
        # run post install hook
        app_descriptor.run_post_install()
    
        # now get data for all new settings values in the config
        params = console_utils.get_configuration(log, self.tk, app_descriptor, None)
    
        # next step is to add the new configuration values to the environment
        env.create_app_settings(engine_instance_name, app_instance_name)
        env.update_app_settings(engine_instance_name, app_instance_name, params, app_descriptor.get_location())
    
        log.info("App Installation Complete!")
        if app_descriptor.get_doc_url():
            log.info("For documentation, see %s" % app_descriptor.get_doc_url())
        log.info("")
        log.info("")
        


class InstallEngineAction(Action):
    """
    Action for installing an engine.
    """
    def __init__(self):
        Action.__init__(self, 
                        "install_engine", 
                        Action.PC_LOCAL, 
                        "Adds a new engine to your configuration.", 
                        "Configuration")
    
    def run(self, log, args):

        if len(args) != 2:
            
            log.info("This command adds an engine to an existing environment. ")
            log.info("")
            log.info("The standard mechanism through which apps and engines are distributed "
                     "is the Toolkit App Store. Items in the App Store are part of the official "
                     "toolkit distribution and have gone through our quality control process. "
                     "To see all apps and engines in the Toolkit App Store, navigate here:")
            log.info("https://toolkit.shotgunsoftware.com/entries/23874562")
            log.info("")
            log.info("To install an app store engine, use the following syntax:")
            log.info("> tank install_engine environment_name engine_name")
            log.info("")
            log.info("For example, to install the tk-houdini engine into Asset environment:")
            log.info("> tank install_engine Asset tk-houdini")
            log.info("")
            log.info("")
            log.info("Handy tip: For a list of existing environments, engines and apps, "
                     "run the 'tank app_info' command.")
            log.info("")
            
            return


                    
        env_name = args[0]
        engine_name = args[1]   

        log.info("")
        log.info("")
        log.info("Welcome to the Shotgun Pipeline Toolkit Engine installer!")
        log.info("")
    
        try:
            env = self.tk.pipeline_configuration.get_environment(env_name)
        except Exception, e:
            raise TankError("Environment '%s' could not be loaded! Error reported: %s" % (env_name, e))
    
        # find engine
        engine_descriptor = TankAppStoreDescriptor.find_item(self.tk.pipeline_configuration, AppDescriptor.ENGINE, engine_name)
        log.info("Successfully located %s..." % engine_descriptor)
        log.info("")
    
        # now assume a convention where we will name the engine instance that we create in the environment
        # the same as the short name of the engine
        engine_instance_name = engine_descriptor.get_system_name()
    
        # check so that there is not an app with that name already!
        if engine_instance_name in env.get_engines():
            raise TankError("Engine %s already exists in environment %s!" % (engine_instance_name, env))
    
        # now make sure all constraints are okay
        try:
            console_utils.check_constraints_for_item(engine_descriptor, env)
        except TankError, e:
            raise TankError("Cannot install: %s" % e)
    
    
        # okay to install!
    
        # ensure that all required frameworks have been installed
        # find the file where our app is being installed
        # when adding new items, we always add them to the root env file
        fw_location = env.disk_location    
        console_utils.ensure_frameworks_installed(log, self.tk, fw_location, engine_descriptor, env)
    
        # note! Some of these methods further down are likely to pull the apps local
        # in order to do deep introspection. In order to provide better error reporting,
        # pull the apps local before we start
        if not engine_descriptor.exists_local():
            log.info("Downloading from App Store, hold on...")
            engine_descriptor.download_local()
            log.info("")
    
        # create required shotgun fields
        engine_descriptor.ensure_shotgun_fields_exist()
    
        # run post install hook
        engine_descriptor.run_post_install()
    
        # now get data for all new settings values in the config
        params = console_utils.get_configuration(log, self.tk, engine_descriptor, None)
        
        # next step is to add the new configuration values to the environment
        env.create_engine_settings(engine_instance_name)
        env.update_engine_settings(engine_instance_name, params, engine_descriptor.get_location())
    
        log.info("")
        log.info("")
        log.info("Engine Installation Complete!")
        log.info("")
        if engine_descriptor.get_doc_url():
            log.info("For documentation, see %s" % engine_descriptor.get_doc_url())
        log.info("")
        log.info("")
    
