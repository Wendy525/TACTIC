###########################################################
#
# Copyright (c) 2005, Southpaw Technology
#                     All Rights Reserved
#
# PROPRIETARY INFORMATION.  This software is proprietary to
# Southpaw Technology, and is not to be reproduced, transmitted,
# or disclosed in any way without written permission.
#
#
#

__all__ = ['FileNaming', 'BaseFileNaming']


import re, os

from pyasm.common import Config, Container, Common, TacticException
from pyasm.search import SearchType, Search, SObject
from file import File
from project import Repo, Project
from naming import NamingUtil, Naming
from snapshot import Snapshot


class BaseFileNaming(object):
    def __init__(my, **kwargs):
        my.kwargs = kwargs

    def get_file(my):
        return ""

    def get_dir(my):
        return ""

    def get_sandbox_dir(my):
        return ""




class FileNaming(object):

    def __init__(my, sobject=None, snapshot=None, file_object=None, ext='', naming_expr=None):
        my.sobject = sobject
        my.snapshot = snapshot
        my.file_object = file_object

        my.set_ext(ext)

        my.naming_expr = naming_expr


    def add_default_ending(my, parts, auto_version=True, is_sequence=True):

        context = my.snapshot.get_value("context")
        filename = my.file_object.get_full_file_name()


        # make sure that the version in the file name does not yet exist
        version = my.get_version_from_file_name(filename)
        if not auto_version and version:

            # if the file version is not the same as the snapshot version
            # then check to see if the snapshot already exists
            if version != my.snapshot.get_value("version"):
                existing_snap = Snapshot.get_by_version(my.snapshot.get_value("search_type"),\
                    my.snapshot.get_value("search_id"), context, version)
                if existing_snap:
                    raise TacticException('A snapshot with context "%s" and version "%s" already exists.' % (context, version) )


            my.snapshot.set_value("version", version)
            my.snapshot.commit()
        else:
            version = my.snapshot.get_value("version")


        if version == 0:
            version = "CURRENT"
        elif version == -1:
            version = "LATEST"
        else:
            # pad the version by by the global setting
            padding = Config.get_value("checkin", "version_padding")
            if not padding:
                padding = 3
            else:
                padding = int(padding)
            expr = "v%%0.%sd" % padding

            version = expr % version

        revision = my.snapshot.get_value("revision", no_exception=True)
        if revision:
            revision = "r%0.2d" % revision

        ext = my.get_ext()

        # by default publish is not put into the file name
        if context != "publish":
            parts.append(context.replace("/", "_"))


        # add the server location
        #value = ProdSetting.get_value_by_key("naming/add_server")
        server = Config.get_value("install", "server")
        if server:
            parts.append(server)


        if my.is_tactic_repo():
            parts.append(version)
            if revision:
                parts.append(revision)

        from pyasm.prod.biz import ProdSetting
        value = ProdSetting.get_value_by_key("naming/add_initials")
        if value == "false":
            project = Project.get()
            initials = Project.get().get_initials()
            parts.append(initials)

        filename = "_".join(parts)
        if is_sequence:
            filename = "%s.####.%s" % (filename, ext)
        elif ext: # dir don't need extension
            filename = "%s%s" % (filename, ext)


        
        return filename


    def get_version_from_file_name(my, file_name):
        '''utility function to extract version information from a file'''

        # get current file name of maya session and extract version.
        # ? is needed in case it's a folder which does not have the 
        # . or _ after the v###
        pattern = re.compile( r'v(\d+)[\.|_]?', re.IGNORECASE)
        matches = pattern.findall(file_name)
        if not matches:
            version = 0
        else:
            version = int(matches[0])

        return version


    def get_file_type(my):
        if not my.file_object:
            file_type = ''
        else:
            # old file object may not have this filled in
            file_type = my.file_object.get_type()
            if not file_type:
                file_code = my.file_object.get_code()
                file_type = my.snapshot.get_type_by_file_code(file_code)
        return file_type


    def get_ext(my):
        if my.ext:
            return my.ext

        base_type = my.file_object.get_value('base_type')
        if base_type == 'directory':
            return None

        base, ext = os.path.splitext( my.file_object.get_full_file_name() )
        
        return ext


    def is_tactic_repo(my):
        '''returns whether the current state is a tactic repo'''
        repo_handler = my.sobject.get_repo_handler(my.snapshot)
        return repo_handler.is_tactic_repo()



    def get_padding(my):
        '''returns the padding of the file code, should the project use this
        feature'''
        return 10



    # set the various objects needed to build a directory
    def set_sobject(my, sobject):
        my.sobject = sobject

    def set_snapshot(my, snapshot):
        my.snapshot = snapshot

    def set_naming(my, naming_expr):
        my.naming_expr = naming_expr

 
    def set_file_object(my, file_object):
        my.file_object = file_object

    def set_ext(my, ext):
        if not ext:
            my.ext = ''
            return

        if not ext.startswith("."):
            ext = ".%s" % ext
        my.ext = ext


    def get_file_name(my):
        assert my.sobject != None
        assert my.snapshot != None
        # File object can be none
        #assert my.file_object != None

        # determine whether naming is used
        file_type = my.get_file_type()
        if file_type and my.snapshot:
            # if there is a snapshot check the file to see if naming conventions
            # are even used
            if not my.snapshot.get_use_naming_by_type(file_type):
                file_name = my.file_object.get_value("file_name")
                if file_name:
                    return file_name


        if my.naming_expr:
            file_name = my.get_from_expression(my.naming_expr)
            return file_name


        search_type = my.sobject.get_base_search_type()

        # first check the db
        file_name = my.get_from_db_naming(search_type)
        if file_name:
            file_type = my.get_file_type()
            if file_type in ['web','icon']:
                basename, ext = os.path.splitext(file_name)
                file_name = '%s_%s%s' %(basename, file_type, ext)
            return file_name


        func_name = search_type.replace("/", "_")

        try:
            file_name = eval( "my.%s()" % func_name)
            
        except Exception, e:
            if e[0].find("object has no attribute '%s'"%func_name) != -1:
                file_name = my.get_default()
            else:
                raise
        # ensure that the filename has no illegal characters
        file_name = Common.get_filesystem_name(file_name)

        return file_name



    def get_from_expression(my, naming_expr):
        naming_util = NamingUtil()
        file_type = my.get_file_type()

        return naming_util.naming_to_file(naming_expr, my.sobject,my.snapshot,my.file_object,ext=my.get_ext(),file_type=file_type)



    def get_from_db_naming(my, search_type):
        project_code = Project.get_project_code()
        if project_code in ["admin", "sthpw"]:
            return ""

        file_type = my.get_file_type()
        filename = my.file_object.get_full_file_name()

        naming = Naming.get(my.sobject, my.snapshot, file_path=filename)

        #naming = Naming.get_by_search_type(search_type)
        if not naming:
            return None
        naming_util = NamingUtil()

        # Provide a mechanism for a custom class
        naming_class = naming.get_value("class_name", no_exception=True)
        if naming_class:
            kwargs = {
                'sobject': my.sobject,
                'snapshot': my.snapshot,
                'file_object': my.file_object,
                'ext': my.get_ext(),
                'mode': 'file'
            }
            naming = Common.create_from_class_path(naming_class, kwargs)
            filename = naming.get_file()
            if filename:
                return filename


        # provide a mechanism for a custom client side script
        script_path = naming.get_value("script_path", no_exception=True)
        if script_path:
            input = {
                'sobject': my.sobject,
                'snapshot': my.snapshot,
                'file_object': my.file_object,
                'ext': my.get_ext(),
                'mode': 'file'
            }
            from tactic.command import PythonCmd

            cmd = PythonCmd(script_path=script_path, input=input)
            results = cmd.execute()
            if results:
                return results




        naming_value = naming.get_value("file_naming")
        #if my.snapshot.get_value("version") == -1:
        #    naming_value = "{basefile}.{ext}"

        if not naming_value:
            return ""
        
        # check for manual_version
        manual_version = naming.get_value('manual_version')
        if manual_version == True:
	    # if the file version is not the same as the snapshot version
            # then check to see if the snapshot already exists
            filename = my.file_object.get_full_file_name()
            version = my.get_version_from_file_name(filename)
            context = my.snapshot.get_context()
            if version > 0 and version != my.snapshot.get_value("version"):
                existing_snap = Snapshot.get_snapshot(\
                    my.snapshot.get_value("search_type"),\
                    my.snapshot.get_value("search_id"), context=context, \
                    version=version, show_retired=True)
                if existing_snap:
                    raise TacticException('You have chosen manual version in Naming for this SObject. A snapshot with context "%s" and version "%s" already exists.' % (context, version) )


                my.snapshot.set_value("version", version)
                my.snapshot.commit()
        
       
        file_type = my.get_file_type()

        return naming_util.naming_to_file(naming_value, my.sobject,my.snapshot,my.file_object,ext=my.get_ext(),file_type=file_type)



    def get_default(my):
        '''functions that all assets go through.  This can be used as a catchall
        for sobjects that do not have a specific handler.
        '''
        parts = []


        # remove _v001.
        name = my.file_object.get_value("file_name")
        name = re.sub(r"_v\d+\.", ".", name)

        name, ext = os.path.splitext(name)

        # put the number signs at the end if there is one in the original name
        # This is a failsafe to check in sequences even if no naming is
        # specified
        if name.endswith("#"):
            name = name.replace('#','')
            is_sequence = True
        else:
            is_sequence = False

        parts.append(name)


        file_name = my.add_default_ending(parts=parts, is_sequence=is_sequence)
        #code = my.file_object.get_code()
        #file_name = File.add_file_code(name,code)
        return file_name

    def get_sandbox_file_name(my, current_file_name, context, sandbox_dir=None):
        '''function that determines the file name to be saved in the sandbox'''

        # get current file name of app session and extract version.
        pattern = re.compile( r'v(\d+)[\.|_]')
        matches = pattern.findall(current_file_name)
        if not matches:
            version = 0

            # add a version to the name
            base, ext = os.path.splitext(current_file_name)
            file_name = "%s_%s_v%0.3d%s" % (base, context, version+1, ext)
        else:
            # add 1 to the version
            version = int(matches[0])
            padding = len(matches[0])

            old = "v%s" % str(version).zfill(padding)
            new = "v%s" % str(version+1).zfill(padding)
            file_name = current_file_name.replace(old, new )

        return file_name


    # examples ('_' is extra here and is not present in real implementation)
    def _prod_asset(my):
        orig = my.file_object.get_value("file_name")
        name = os.path.basename(orig)
        name, ext = os.path.splitext(name)
 
        file_name = "%s_jojojo%s" % (name,ext)
        return file_name


    def _prod_art_reference(my):

        orig = my.file_object.get_value("file_name")
        name = os.path.basename(orig)
        name, ext = os.path.splitext(name)
        context = my.snapshot.get_value("context")
        #file_code = my.file_object.get_value("code")

        file_name = "%s_%s_gaga%s" % (name, context, ext)
        return file_name



