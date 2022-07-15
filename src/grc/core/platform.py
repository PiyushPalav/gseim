# Copyright 2008-2016 Free Software Foundation, Inc.
# This file is part of GNU Radio
#
# GNU Radio Companion is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# GNU Radio Companion is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA

from __future__ import absolute_import, print_function

from codecs import open
from collections import namedtuple
import os
import logging
from itertools import chain
import re

from . import (
    Messages, Constants,
    blocks, params, ports, errors, utils, schema_checker
)
from .utils import backports
from .utils import descriptors

from .utils import gutils as gu

from .Config import Config
from .base import Element
from .io import yaml
from .generator import Generator
from .FlowGraph import FlowGraph
from .Connection import Connection

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class Platform(Element):

    def __init__(self, *args, **kwargs):
        """ Make a platform for GNU Radio """
        Element.__init__(self, parent=None)

        self.config = self.Config(*args, **kwargs)

        self.blocks = self.block_classes
        self.domains = {}

        self.dict_outvars = {}

        self.d_slvparms = {}
        filename = Config.gseim_exec_dir + '/gseim_slvparms.in'
        gu.get_parms(filename, self.d_slvparms)
        self.d_slvparms['block_index'] = {'options': ['none'], 'default': '0', 'category': 'none'}

        self.d_slv_categories = {} 

        gu.prepare_dict_1(self.d_slvparms, self.d_slv_categories)

        self.d_outparms = {}
        filename = Config.gseim_exec_dir + '/gseim_outparms.in'
        gu.get_parms(filename, self.d_outparms)

        self._block_categories = {}
        self._auto_hier_block_generate_chain = set()

        if not yaml.__with_libyaml__:
            logger.warning("Slow YAML loading (libyaml not available)")

    def __str__(self):
        return 'Platform - {}'.format(self.config.name)

    @staticmethod
    def find_file_in_paths(filename, paths, cwd):
        """Checks the provided paths relative to cwd for a certain filename"""
        if not os.path.isdir(cwd):
            cwd = os.path.dirname(cwd)
        if isinstance(paths, str):
            paths = (p for p in paths.split(':') if p)

        for path in paths:
            path = os.path.expanduser(path)
            if not os.path.isabs(path):
                path = os.path.normpath(os.path.join(cwd, path))
            file_path = os.path.join(path, filename)
            if os.path.exists(os.path.normpath(file_path)):
                return file_path

    def load_and_generate_flow_graph(self, file_path, out_path=None, hier_only=False):
        """Loads a flow graph from file and generates it"""
        Messages.set_indent(len(self._auto_hier_block_generate_chain))
        Messages.send('>>> Loading: {}\n'.format(file_path))
        if file_path in self._auto_hier_block_generate_chain:
            Messages.send('    >>> Warning: cyclic hier_block dependency\n')
            return None, None

        self._auto_hier_block_generate_chain.add(file_path)
        try:
            flow_graph = self.make_flow_graph()
            flow_graph.grc_file_path = file_path
            # Other, nested hier_blocks might be auto-loaded here

            flow_graph.import_data(self.parse_flow_graph(file_path))

            flow_graph.rewrite()
            flow_graph.validate()
            if not flow_graph.is_valid():
                raise Exception('Flowgraph invalid')
            if hier_only and not flow_graph.get_option('generate_options').startswith('hb'):
                raise Exception('Not a hier block')
        except Exception as e:
            Messages.send('>>> Load Error: {}: {}\n'.format(file_path, str(e)))
            return None, None
        finally:
            self._auto_hier_block_generate_chain.discard(file_path)
            Messages.set_indent(len(self._auto_hier_block_generate_chain))

        try:
            print('grc/core/platform.py: out_path =', out_path, ' file_path =', file_path)
            generator = self.Generator(flow_graph, out_path or file_path)
            Messages.send('>>> Generating: {}\n'.format(generator.file_path))
            generator.write()
        except Exception as e:
            Messages.send('>>> platform.py: Generate Error: {}: {}\n'.format(file_path, str(e)))
            return None, None

        if flow_graph.get_option('generate_options').startswith('hb'):
            # self.load_block_xml(generator.file_path_xml)
            # TODO: implement yml output for hier blocks
            pass

        return flow_graph, 'dummy_string'

    def build_library(self, path=None):
        """load the blocks and block tree from the search paths

        path: a list of paths/files to search in or load (defaults to config)
        """

        # Reset
        self.blocks.clear()
        self.domains.clear()
        self._block_categories.clear()

        for file_path in self._iter_files_in_block_path(path):

            if file_path.endswith('block.yml'):
                loader = self.load_block_description
                scheme = schema_checker.BLOCK_SCHEME
            elif file_path.endswith('.tree.yml'):
                loader = self.load_category_tree_description
                scheme = None
            else:
                continue

            try:
                checker = schema_checker.Validator(scheme)
                with open(os.path.expanduser(file_path), encoding='utf-8') as fp:
                    data = yaml.safe_load(fp)
                passed = checker.run(data)
                for msg in checker.messages:
                    logger.warning('{:<40s} {}'.format(os.path.basename(file_path), msg))
                if not passed:
                    logger.info('YAML schema check failed for: ' + file_path)

                loader(data, file_path)
            except Exception as error:
                logger.exception('Error while loading %s', file_path)
                logger.exception(error)
                Messages.flowgraph_error = error
                Messages.flowgraph_error_file = file_path
                continue

        for key, block in iter(self.blocks.items()):
            category = self._block_categories.get(key, block.category)
            if not category:
                continue
            root = category[0]
            if root.startswith('[') and root.endswith(']'):
                category[0] = root[1:-1]
            else:
                category.insert(0, Constants.DEFAULT_BLOCK_MODULE_NAME)
            block.category = category

    def _iter_files_in_block_path(self, path=None, ext='yml'):
        """Iterator for block descriptions and category trees"""
        for entry in (path or self.config.block_paths):
            if os.path.isfile(entry):
                yield entry
            elif os.path.isdir(entry):
                for dirpath, dirnames, filenames in os.walk(entry):
                    for filename in sorted(filter(lambda f: f.endswith('.' + ext), filenames)):
                        yield os.path.join(dirpath, filename)
            else:
                logger.debug('Ignoring invalid path entry %r', entry)

    # Description File Loaders
    # region loaders
    def load_block_description(self, data, file_path):
        log = logger.getChild('block_loader')

        # don't load future block format versions

        block_id = data['id'] = data['id'].rstrip('_')
        print('load_block_description:', file_path)
        if 'outvars' in data.keys():
            block_name = file_path.split('/')[-1].split('.')[0]
            self.dict_outvars[block_name] = data['outvars']

        if block_id in self.block_classes_build_in:
            log.warning('Not overwriting build-in block %s with %s', block_id, file_path)
            return
        if block_id in self.blocks:
            log.warning('Block with id "%s" loaded from\n  %s\noverwritten by\n  %s',
                        block_id, self.blocks[block_id].loaded_from, file_path)

        try:
            block_cls = self.blocks[block_id] = self.new_block_class(**data)
            block_cls.loaded_from = file_path
        except errors.BlockLoadError as error:
            log.error('Unable to load block %s', block_id)
            log.exception(error)
            return

    def load_domain_description(self, data, file_path):
        log = logger.getChild('domain_loader')
        domain_id = data['id']
        if domain_id in self.domains:  # test against repeated keys
            log.debug('Domain "{}" already exists. Ignoring: %s', file_path)
            return

        color = data.get('color', '')
        if color.startswith('#'):
            try:
                tuple(int(color[o:o + 2], 16) / 255.0 for o in (1, 3, 5))
            except ValueError:
                log.warning('Cannot parse color code "%s" in %s', color, file_path)
                return

# todo
# check for e nodes
    def load_category_tree_description(self, data, file_path):
        """Parse category tree file and add it to list"""
        log = logger.getChild('tree_loader')
        log.debug('### Loading %s', file_path)
        path = []

        def load_category(name, elements):
            if not isinstance(name, str):
                log.debug('Invalid name %r', name)
                return
            path.append(name)
            for element in utils.to_list(elements):
                if isinstance(element, str):
                    block_id = element
                    self._block_categories[block_id] = list(path)
                elif isinstance(element, dict):
                    load_category(*next(iter(element.items())))
                else:
                    log.debug('Ignoring some elements of %s', name)
            path.pop()

        try:
            module_name, categories = next(iter(data.items()))
        except (AttributeError, StopIteration):
            log.warning('no valid data found')
        else:
            load_category(module_name, categories)

    # Access
    def parse_flow_graph(self, filename):
        """
        Parse a saved flow graph file.
        Ensure that the file exists, and passes the dtd check.

        Args:
            filename: the flow graph file

        Returns:
            nested data
        @throws exception if the validation fails
        """
        filename = filename or self.config.default_flow_graph
        with open(os.path.expanduser(filename), encoding='utf-8') as fp:

            fp.seek(0)

            data = yaml.safe_load(fp)
            validator = schema_checker.Validator(schema_checker.FLOW_GRAPH_SCHEME)
            validator.run(data)

        return data

    def save_flow_graph(self, filename, flow_graph):
        data = flow_graph.export_data()

        try:
            data['connections'] = [yaml.ListFlowing(i) for i in data['connections']]
        except KeyError:
            pass

        if flow_graph.get_option('generate_options').startswith('hb'):
            if 'drawing_scheme' not in data['gparms'].keys():
                data['gparms']['drawing_scheme'] = 'name'
            if 'rotate_strict' not in data['gparms'].keys():
                data['gparms']['rotate_strict'] = 'no'
            if 'mirror' not in data['gparms'].keys():
                data['gparms']['mirror'] = 'none'
            if 'port_sep_x' not in data['gparms'].keys():
                data['gparms']['port_sep_x'] = '4'
            if 'port_sep_y' not in data['gparms'].keys():
                data['gparms']['port_sep_y'] = '4'
            if 'port_block_x' not in data['gparms'].keys():
                data['gparms']['port_block_x'] = '4'
            if 'port_block_y' not in data['gparms'].keys():
                data['gparms']['port_block_y'] = '4'
            if 'port_offset_l' not in data['gparms'].keys():
                data['gparms']['port_offset_l'] = '0'
            if 'port_offset_r' not in data['gparms'].keys():
                data['gparms']['port_offset_r'] = '0'
            if 'port_offset_t' not in data['gparms'].keys():
                data['gparms']['port_offset_t'] = '0'
            if 'port_offset_b' not in data['gparms'].keys():
                data['gparms']['port_offset_b'] = '0'

        try:
            for d in chain([data['options']], data['blocks']):
                d['states']['coordinate'] = yaml.ListFlowing(d['states']['coordinate'])
        except KeyError:
            pass

        out = yaml.dump(data, indent=2)

        with open(os.path.expanduser(filename), 'w', encoding='utf-8') as fp:
            fp.write(out)

    def get_generate_options(self):
        for param in self.block_classes['options'].parameters_data:
            if param.get('id') == 'generate_options':
                break
        else:
            return []
        generate_mode_default = param.get('default')
        return [(value, name, value == generate_mode_default)
                for value, name in zip(param['options'], param['option_labels'])]

    # Factories
    Config = Config
    Domain = namedtuple('Domain', 'name multi_in multi_out color')
    Generator = Generator
    FlowGraph = FlowGraph
    Connection = Connection

    block_classes_build_in = blocks.build_ins
    block_classes = utils.backports.ChainMap({}, block_classes_build_in)  # separates build-in from loaded blocks)

    port_classes = {
        None: ports.Port,  # default
    }
    param_classes = {
        None: params.Param,  # default
    }

    def make_flow_graph(self, from_filename=None):
        fg = self.FlowGraph(parent=self)
        if from_filename:
            data = self.parse_flow_graph(from_filename)
            fg.grc_file_path = from_filename
            fg.import_data(data)
        return fg

    def new_block_class(self, **data):
        return blocks.build(**data)

    def make_block(self, parent, block_id, **kwargs):
        cls = self.block_classes[block_id]
        return cls(parent, **kwargs)

    def make_param(self, parent, **kwargs):
        cls = self.param_classes[kwargs.pop('cls_key', None)]
        return cls(parent, **kwargs)

    def make_port(self, parent, **kwargs):
        cls = self.port_classes[kwargs.pop('cls_key', None)]
        return cls(parent, **kwargs)
