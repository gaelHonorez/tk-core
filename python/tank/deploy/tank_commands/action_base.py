# Copyright (c) 2013 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.


class Action(object):
    """
    Describes an executable action. Base class that all tank command actions derive from.
    """
    
    # GLOBAL - works everywhere, requires self.code_install_root only
    # PC_LOCAL - works when a PC exists. requires GLOBAL + self.pipeline_config_root + self.tk
    # CTX - works when a context exists. requires PC_LOCAL + self.context
    # ENGINE - works when an engine exists. requires CTX + self.engine 
    GLOBAL, PC_LOCAL, CTX, ENGINE = range(4)
    
    def __init__(self, name, mode, description, category):
        self.name = name
        self.mode = mode
        self.description = description
        self.category = category
        
        # special flag for commands that run in multiple contexts where an engine
        # is optional, but beneficial. This is so that the system can determine
        # whether it is worth starting the engine or not. 
        self.wants_running_shell_engine = False
        if self.mode == Action.ENGINE:
            self.wants_running_shell_engine = True
        
        # these need to be filled in by calling code prior to execution
        self.tk = None
        self.context = None
        self.engine = None
        self.code_install_root = None
        self.pipeline_config_root = None
        
    def __repr__(self):
        
        mode_str = "UNKNOWN"
        if self.mode == Action.GLOBAL:
            mode_str = "GLOBAL"
        elif self.mode == Action.PC_LOCAL:
            mode_str = "PC_LOCAL"
        elif self.mode == Action.CTX:
            mode_str = "CTX"
        elif self.mode == Action.ENGINE:
            mode_str = "ENGINE"
        
        return "<Action Cmd: '%s' Category: '%s' MODE:%s>" % (self.name, self.category, mode_str)
            
    def __str__(self):
        
        return "Command %s (Category %s)" % (self.name, self.category)
        
    def run(self, log, args):
        raise Exception("Need to implement this")
             
