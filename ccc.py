# coding=utf-8
import base64
import copy
import optparse
import os
import json
import yaml
import re
import shutil
import traceback
import uuid
from collections import OrderedDict

import datetime

import sys

ASSETS_PATH = 'assets'
INDENT = '  '


NODE_IGNORE_PROPERTIES = {'_active'}
INSTANCE_ROOT_IGNORE_PROPERTIES = {'_position', '_rotationX', '_rotationY', '_scaleX', '_scaleY', '_anchorPoint',
                                   '_skewX', '_skewY', '_name', '_localZOrder', '_globalZOrder',
                                   '_tag', '_active'}

IGNORE_COMPONENT_PROPERTIES = {
    'cc.Layout': ['_layoutSize']
}


class KdPrefabStrategy(object):
    ALL = 0
    NEVER = 1


class LayoutType(object):
    NONE = 0
    HORIZONTAL = 1
    VERTICAL = 2
    GRID = 3


class LayoutStartAxis(object):
    HORIZONTAL = 0
    VERTICAL = 1


class LayoutResizeMode(object):
    NONE = 0
    CONTAINER = 1
    CHILDREN = 2


class WidgetAlignFlag(object):
    TOP = 1
    VERTICAL_CENTER = 2
    BOTTOM = 4
    LEFT = 8
    HORIZONTAL_CENTER = 16
    RIGHT = 32


class File(object):
    def __init__(self, project, relative_path):
        """
        :param Project project:
        :param str relative_path: relative to assets
        """
        self.project = project
        self.relative_path = relative_path.replace('\\', '/')
        self.path = os.path.normpath(os.path.join(project.path, 'assets', relative_path)).replace('\\', '/')
        self.name, self.ext = os.path.splitext(os.path.split(relative_path)[-1])


class FileInput(File):
    def __init__(self, project, relative_path):
        File.__init__(self, project, relative_path)
        self.meta = json.load(open(self.path + '.meta'), object_pairs_hook=OrderedDict)
        self.data = json.load(open(self.path), object_pairs_hook=OrderedDict)
        """:type: list[dict[str, *]]"""
        self.elements = [[] for _ in xrange(len(self.data))]
        """:type: list[list[Element]]"""

    @property
    def uuid(self):
        return self.meta['uuid']

    def __str__(self):
        return '<%s name=%s uuid=%s path=%s/>' % (self.__class__.__name__, self.name, self.meta['uuid'], self.path)

    def load(self, root_class):
        """
        :param class root_class:
        :rtype Element:
        """
        root = root_class(self.project)
        """:type: Element"""
        root.load(self, 0)

        # fix node references
        for i, elements in enumerate(self.elements):
            for element in elements:
                element.post_load(self)

        for i, elements in enumerate(self.elements):
            if len(elements) <= 0:
                raise Exception('Element %s not loaded in "%s"' % (i, self.path))

        return root

    def dump_elements(self, indent=0):
        for i, elements in enumerate(self.elements):
            for element in elements:
                print '%s% 3d %s' % (INDENT * indent, i, element)


class FileOutput(File):
    def __init__(self, project, relative_path):
        File.__init__(self, project, relative_path)

        self.elements = []
        """:type: list[dict]"""

    def save(self, asset):
        """
        :param Asset asset:
        """
        asset.save(self)
        content = json.dumps(self.elements, indent=2)
        content = '\n'.join(line.rstrip() for line in content.split('\n'))  # 去掉行尾的空格，和ccc保持一致
        open(self.path, 'wb').write(content)


class Element(object):
    def __init__(self, project):
        self.project = project
        self._keys = None
        """:type list[str]"""
        self._data = OrderedDict()
        """:type: dict[str, *]"""
        # the index in original file
        self._loaded_index = -1
        # todo: 如果需要多次保存，要先清空
        self._saved_index = -1
        # 同步时，需要忽略的属性
        self._ignore_properties = set()
        """:type: set[str]"""

    @property
    def type(self):
        return '%s' % self._data['__type__']

    def get_property(self, name, default=None):
        return self._data.get(name, default)

    @property
    def loaded_index(self):
        """
        The index of current element in source file.
        :rtype: int
        """
        return self._loaded_index

    @property
    def saved_index(self):
        """
        :rtype: int
        """
        return self._saved_index

    def pop_data(self, key, default=None):
        """
        从_data中pop数据。为了保留顺序，不会真正的pop掉，而是置为None
        :param str key:
        :param * default:
        :rtype: *
        """
        val = self._data.get(key, default)
        if key in self._data:
            self._data[key] = None
        return val

    def load(self, file_, index):
        """
        :param FileInput file_:
        :param int index:
        """
        self._data = copy.deepcopy(file_.data[index])
        self._keys = self._data.keys()
        self._loaded_index = index
        assert self.type == self._data['__type__'], '%s %s' % (self.type, self._data['__type__'])
        if len(file_.elements[index]):
            # Components might be reused
            assert isinstance(self, Component)
            assert isinstance(file_.elements[index][0], Component)

        file_.elements[index].append(self)

    def post_load(self, file_):
        """
        fix references
        :param FileInput file_:
        """
        self._data = load_dict(file_, self, self._data)

    def save(self, file_):
        """
        :param FileOutput file_:
        :rtype: dict
        """
        if self._saved_index >= 0:
            return self._saved_index

        self._saved_index = len(file_.elements)
        file_.elements.append({})

        file_.elements[self._saved_index] = data = save_dict(file_, self, self._data)
        self._save(file_, data)

        return self._saved_index

    def _save(self, file_, data):
        """
        :param FileOutput file_:
        :param data:
        :return:
        """
        _ = self, file_, data

    # def compare(self, other, ctx):
    #     """
    #     :param Element other:
    #     :param CompareResult ctx:
    #     """
    #     compare_dict(self, other, self._data, other._data, ctx)

    def synchronize(self, other, ctx):
        """
        :param Element other:
        :param CompareContext ctx:
        """
        # CR4: 忽略特定的prefab中的特定Node的特定组件的特定属性
        synchronize_dict(self, other, self._data, other._data, ctx, ignores=other._ignore_properties)

    def ignore(self, properties):
        self._ignore_properties = set(properties)

    def __str__(self):
        return '<%s type=%s/>' % (self.__class__.__name__, self.type)


class Asset(Element):
    """
    Root Element of assets.
    """

    file = None
    """:type: File"""
    root = None
    """:type: Node"""

    # 是否需要同步（可能是部分文件需要同步）
    need_synchronize = False
    # 是否同步过了（仅用于校验）
    synchronized = False

    def __init__(self, project):
        Element.__init__(self, project)

        # 用于解析Asset之间的依赖关系
        # 我引用到的
        self.references = set()
        """:type: set[Prefab]"""
        # 引用到我的
        self.referents = set()
        """:type: set[Asset]"""
        # 在森林中的深度(从根开始的最长路径)
        self.depth = 0

    @property
    def path(self):
        return self.file.path

    @property
    def relative_path(self):
        return self.file.relative_path

    def load(self, file_, index):
        """
        :param FileInput file_:
        :param int index:
        """
        Element.load(self, file_, index)
        self.file = file_

    # def compare_all_instances(self, ctx):
    #     """
    #     :param CompareResult ctx:
    #     """
    #     for node in self.root.iterate_instance_roots(False):  # 避免自己跟自己比较
    #         uuid_ = node.get_prefab_uuid()
    #         asset = self.project.get_asset_by_uuid(uuid_)
    #         if not asset:
    #             ctx.remove('miss prefab for %s' % node.path)
    #             continue
    #         assert isinstance(asset, Prefab)
    #         node.compare(asset.root, ctx, True)

    def synchronize_all_instances(self, ctx):
        """
        :param CompareContext ctx:
        """
        print 'synchronize', self.relative_path
        assert not self.synchronized

        for node in self.root.iterate_instance_roots(False):
            uuid_ = node.get_prefab_uuid()
            asset = self.project.get_asset_by_uuid(uuid_)
            if not asset:
                ctx.remove('miss prefab for %s' % node.path)
                continue

            assert isinstance(asset, Prefab)

            if not asset.need_synchronize:
                continue

            assert asset.synchronized

            node.synchronize(asset.root, ctx, True)

        self.synchronized = True

    def get_element_by_path(self, path):
        """
        :param str path:
        :rtype: Element
        """
        current = self.root
        for item in path.split('/'):
            assert isinstance(current, Node)
            if item[0] == '#':
                current = current.get_component(item[1:])
            else:
                current = current.get_child_by_name(item)
        return current

    def search_referents(self):
        """
        查找引用到prefab的所有asset(prefab/scene)，包含直接/间接引用的。按照依赖关系排序(前面的不依赖后面的)。
        :rtype: list[Asset]
        """
        assets, result = {self}, set()
        while assets:
            referents = set(sum([list(asset.referents) for asset in assets], []))
            result.update(referents)
            assets = referents

        result = list(result)
        result.sort(key=lambda x: x.depth, reverse=True)  # depth大的在前
        return result


class Prefab(Asset):
    def load(self, file_, index):
        Asset.load(self, file_, index)

        node_ref = self.pop_data('data')
        self.root = Node(self.project, None, self)
        self.root.load(file_, get_element_ref(node_ref), True)

    def _save(self, file_, data):
        data['data'] = create_element_ref(self.root.save(file_))

    def get_file_id(self):
        return self.root.prefab_info.file_id

    def __str__(self):
        return '<Prefab path=%s/>' % self.relative_path


class SceneAsset(Asset):
    root = None
    """:type: Scene"""

    def load(self, file_, index):
        Asset.load(self, file_, index)

        scene_ref = self.pop_data('scene')
        self.root = Scene(self.project, None, self)
        self.root.load(file_, get_element_ref(scene_ref), True)

    def _save(self, file_, data):
        data['scene'] = create_element_ref(self.root.save(file_))

    def search_references(self):
        """
        查找所有被引用asset(prefab/scene)，包含直接/间接引用的。按照依赖关系排序(前面的不依赖后面的)。
        :rtype: list[Asset]
        """
        assets, result = {self}, set()
        while assets:
            refs = set(sum([list(asset.references) for asset in assets], []))
            result.update(refs)
            assets = refs

        result = list(result)
        result.sort(key=lambda x: x.depth, reverse=True)  # depth大的在前
        return result

    def __str__(self):
        return '<SceneAsset path=%s/>' % self.relative_path


class Node(Element):

    def __init__(self, project, parent, root_element=None):
        """
        :param Project project:
        :param Node|None parent:
        :param Asset root_element:
        """
        Element.__init__(self, project)
        self.root_element = root_element
        self.parent = parent
        self.children = []
        """:type: list[Node]"""
        self.components = []
        """:type: list[Component]"""
        self.prefab_info = None
        """:type: PrefabInfo"""
        self._id = ""   # Scene中的"_id"
        """:type: str"""
        self.position = None
        """:type: Position"""
        self.size = None
        """:type: Size"""

    @property
    def root(self):
        """
        :rtype: Node
        """
        if self.parent:
            return self.parent.root
        return self

    @property
    def name(self):
        return self._data.get('_name')

    @property
    def path(self):
        if not self.parent:
            assert self.root_element
            return self.root_element.path
        return '%s/%s' % (self.parent.path, self.name)

    @property
    def relative_path(self):
        if not self.parent:
            assert self.root_element
            return self.root_element.relative_path
        return '%s/%s' % (self.parent.relative_path, self.name)

    @property
    def relative_path_to_asset(self):
        return os.path.relpath(self.relative_path, self.root.relative_path).replace('\\', '/')

    @property
    def instance_root(self):
        """
        :rtype: Node
        """
        node = self
        root = None
        while node:
            if node.get_prefab_uuid() is not None:
                root = node
            node = node.parent
        return root

    def is_prefab_root(self):
        return self.root_element and isinstance(self.root_element, Prefab)

    def is_instance_root(self):
        return not self.is_prefab_root() and self.instance_root is self

    def get_relative_path_to(self, node):
        """
        返回当前节点相对于node的相对路径
        :param Node node:
        :rtype: str
        """
        rel_path = os.path.relpath(self.path, node.path)
        return rel_path.replace('\\', '/')

    def get_relative_node(self, relative_path):
        """
        根据相对路径，返回相应节点
        :param str relative_path:
        :rtype: Node
        """
        relative_path = os.path.normpath(relative_path).replace('\\', '/')
        node = self

        for item in relative_path.split('/'):
            if item == '..':
                node = node.parent
            else:
                node = node.get_child_by_name(item)
        return node

    def get_child_by_name(self, name):
        """
        :param str name:
        :rtype: Node
        """
        for child in self.children:
            if child.name == name:
                return child

    def get_component(self, name):
        """
        :param str name:
        :rtype: Component
        """
        for component in self.components:
            if component.name == name:
                return component

    def get_components(self, name):
        """
        :param str name:
        :rtype: Component
        """
        return [c for c in self.components if c.name == name]

    def walk(self):
        yield self

        for child in self.children:
            for x in child.walk():
                yield x

    def iterate_instance_roots(self, including_self):
        """
        遍历所有的Prefab实例。注意，如果Prefab嵌套，其内部的Prefab不会被遍历！
        :param bool including_self:
        :rtype: Iterator[Node]
        """
        if including_self and self.get_prefab_uuid() is not None:
            yield self
            return

        for child in self.children:
            for x in child.iterate_instance_roots(True):
                yield x

    def load(self, file_, index, might_be_instance_root=None):
        Element.load(self, file_, index)

        # _id只要唯一即可，无需比较（Prefab中的Node的_id都为空）
        self._id = self.pop_data('_id')

        # verify parent if presents
        parent_ref = self.pop_data('_parent', None)
        # noinspection PyTypeChecker
        assert (self.parent is None and parent_ref is None) or (self.parent.loaded_index == get_element_ref(parent_ref))

        names = set()
        for component_ref in self.pop_data('_components', {}):
            component = Component(self.project, self)
            component.load(file_, component_ref['__id__'])
            self.components.append(component)

            # R2: 每一个Node的Component不可重复
            if component.name in names:
                raise Exception('duplicated component type "%s" in "%s"' % (component.name, self.path))
            names.add(component.name)

        prefab_ref = self.pop_data('_prefab', None)
        """:type: dict[str, int]"""
        kd_prefab = self.get_component('KdPrefab')

        is_instance_root = False
        if might_be_instance_root:
            # R3: 每一个Prefab的根节点，必须有KdPrefab组件；反之亦然。
            if prefab_ref and kd_prefab is None:
                raise Exception('Missing KdPrefab in: %s' % self.relative_path)

            if kd_prefab:
                # R3: 每一个Prefab的根节点，必须有KdPrefab组件；反之亦然。
                if prefab_ref is None:
                    raise Exception('%s is not prefab, but contains KdPrefab' % self.relative_path)

                # R3-1: 其中的prefab属性指向Prefab自身
                kd_prefab_ref = kd_prefab.get_property('prefab')
                if not kd_prefab_ref:
                    raise Exception('KdPrefab.prefab is None: %s' % self.relative_path)
                # R3-1: 其中的prefab属性指向Prefab自身
                uuid_ = kd_prefab_ref.get('__uuid__')
                if uuid_ is None:
                    raise Exception('Invalid Format, KdPrefab.prefab contains no uuid: %s' % self.relative_path)

                self.prefab_info = PrefabInfo(self.project, self)
                self.prefab_info.load(file_, get_element_ref(prefab_ref))

                # PrefabRoot的KdPrefab的prefab，应该和文件的uuid一致
                if self.is_prefab_root() and uuid_ != self.root_element.file.uuid:
                    raise Exception('KdPrefab.prefab does not match Prefab file: %s' % self.relative_path)

                if self.is_instance_root() and self.prefab_info.uuid != uuid_:
                    raise Exception('Prefab uuid not match in %s: %s != %s' % (self.relative_path,
                                                                               self.prefab_info.uuid, uuid_))

                is_instance_root = True
        else:
            self.prefab_info = PrefabInfo(self.project, self)
            self.prefab_info.load(file_, get_element_ref(prefab_ref))

        names = set()
        for child_ref in self.pop_data('_children'):
            child = Node(self.project, self)
            child.load(file_, child_ref['__id__'], might_be_instance_root and not is_instance_root)
            self.children.append(child)

            # R1: 每一个Node的Children不可重名
            if child.name in names:
                raise Exception('duplicated child name "%s" in "%s"' % (child.name, self.path))
            names.add(child.name)

        # position和size特殊处理
        self.position = self.pop_data('_position')
        self.size = self.pop_data('_contentSize')

    def _save(self, file_, data):
        # Scene中每一个Node都有唯一的id.
        _id = self._id
        if self.root.is_prefab_root():
            _id = ''
        elif not _id:
            _id = base64.b64encode(uuid.uuid4().bytes).rstrip('=')
        data['_id'] = _id

        data['_parent'] = create_element_ref(self.parent.saved_index if self.parent else None)

        # 注意保持顺序，尽量和ccc的一致: _children, _components, _prefab
        data['_children'] = _children = []
        for child in self.children:
            _children.append(create_element_ref(child.save(file_)))

        data['_components'] = _components = []
        for component in self.components:
            _components.append(create_element_ref(component.save(file_)))

        if self.prefab_info:
            data['_prefab'] = create_element_ref(self.prefab_info.save(file_))

        data['_position'] = self.position
        data['_contentSize'] = self.size

    def get_prefab_uuid(self):
        kd_prefab = self.get_component('KdPrefab')
        if kd_prefab:
            prefab = kd_prefab.get_property('prefab')
            if not prefab:
                raise Exception('KdPrefab.prefab is None: %s' % self.relative_path)
            return prefab['__uuid__']

    def synchronize(self, other, ctx, is_instance_root=False):
        """
        :param Node other:
        :param CompareContext ctx:
        :param bool is_instance_root:
        """
        assert self is not other

        if is_instance_root:
            # SS1: 只有当prefab root和instance root的KdPrefab.strategy都为DEFAULT(0)，才会同步
            my_kd_prefab, other_kd_prefab = self.get_component('KdPrefab'), other.get_component('KdPrefab')
            my_strategy = my_kd_prefab.get_property('strategy')
            other_strategy = other_kd_prefab.get_property('strategy')
            if my_strategy == KdPrefabStrategy.NEVER or other_strategy == KdPrefabStrategy.NEVER:
                ctx.ignore(self.name)
                return

        if is_instance_root:
            ctx.push(self.relative_path_to_asset, '-> %s' % other.relative_path)
        else:
            ctx.push(self.name)

        self.synchronize_without_children(other, ctx, is_instance_root)

        to_remove = []
        for i, my_child in enumerate(self.children):
            other_child = other.get_child_by_name(my_child.name)
            if other_child:  # 修改
                my_child.synchronize(other_child, ctx, False)
            else:  # 删掉多余的子节点
                # todo: 小心误删
                to_remove.append(i)
                ctx.remove(my_child.name)

        for i in reversed(to_remove):
            self.children.pop(i)

        # 新增
        for other_child in other.children:
            my_child = self.get_child_by_name(other_child.name)
            if not my_child:
                ctx.add(other_child.name)
                new_child = Node(self.project, self)
                self.children.append(new_child)
                new_child.synchronize(other_child, CompareContext(), False)  # 不需要diff

        # 确保顺序一致
        my_order = {child.name: i for i, child in enumerate(self.children)}
        other_order = {child.name: i for i, child in enumerate(other.children)}
        if my_order != other_order:
            self.children.sort(cmp=lambda x, y: cmp(other_order[x.name], other_order[y.name]))
            ctx.change('(children order)', my_order, other_order)
        ctx.pop()

    def synchronize_without_children(self, other, ctx, is_instance_root):
        """
        :param Node other:
        :param CompareContext ctx:
        :param bool is_instance_root:
        """
        if is_instance_root:
            ignores = INSTANCE_ROOT_IGNORE_PROPERTIES
        else:
            ignores = NODE_IGNORE_PROPERTIES

        # CR4: 忽略特定的prefab中的特定Node的特定组件的特定属性
        if other._ignore_properties:
            ignores = ignores.union(other._ignore_properties)

        # SS2: instance root忽略: position, rotation, scale, anchor, size, skew, name
        synchronize_dict(self, other, self._data, other._data, ctx, ignores)

        if is_instance_root:
            assert isinstance(other.root_element, Prefab)
            self.prefab_info.file_id = other.prefab_info.file_id
            self.prefab_info.uuid = other.root_element.file.uuid
        else:
            if not self.prefab_info:
                self.prefab_info = PrefabInfo(self.project, self)
            self.prefab_info.file_id = other.prefab_info.file_id
            self.prefab_info.uuid = other.root.root_element.file.uuid

        # components
        ctx.push('(components)')
        to_remove = []
        for i, component in enumerate(self.components):
            # SS3: instance root忽略: Widget
            if is_instance_root and component.name == 'cc.Widget':
                continue

            # CR1: 完全忽略组件(ignore_components)
            if component.name in self.project.ignore_components:
                continue

            other_component = other.get_component(component.name)
            if other_component:
                component.synchronize(other_component, ctx)
            else:
                # todo: 防止误删
                to_remove.append(i)
                ctx.remove(component.name)

        for i in reversed(to_remove):
            self.components.pop(i)

        # 新增
        for other_component in other.components:
            # CR1: 完全忽略组件(ignore_components)
            if other_component.name in self.project.ignore_components:
                continue

            my_component = self.get_component(other_component.name)
            if not my_component:
                # print '+ component', other_component.name
                ctx.add(other_component.name)
                new_component = Component(self.project, self)
                self.components.append(new_component)
                new_component.synchronize(other_component, CompareContext())  # 不需要diff

        # 确保顺序一致。组件数量可能不一样，比children稍微复杂
        my_names = [component.name for component in self.components]
        other_names = [component.name for component in other.components]
        if my_names != other_names:
            intersection = set(my_names).intersection(set(other_names))
            for i in xrange(len(other_names)-1, -1, -1):
                if other_names[i] not in intersection:
                    other_names.pop(i)
            for name in my_names:
                if name not in intersection:
                    other_names.append(name)
            if my_names != other_names:  # 如果Node只是增加了组件，结果有可能是一样的
                order = {name: i for i, name in enumerate(other_names)}
                self.components.sort(key=lambda x: order[x.name])
                ctx.change('(component order)', my_names, other_names)
        ctx.pop()  # components

        # SS5: Node的size/position受Layout/Widget影响时，不同步相应的x/y/w/h(包括KdLayout/KdWidget)
        # 必须在组件同步完之后处理!
        self.synchronize_position_and_size(other, ctx, is_instance_root, ignores)

    def synchronize_position_and_size(self, other, ctx, is_instance_root, ignores):
        """
        SS5: Node的size/position受Layout/Widget影响时，不同步相应的x/y/w/h(包括KdLayout/KdWidget)
        :param Node other:
        :param CompareContext ctx:
        :param bool is_instance_root:
        :param set[str] ignores:
        """
        _ = is_instance_root

        position_ignores = set()
        size_ignores = set()

        # 本身有Layout，且ResizeMode为CONTAINER
        layout = self.get_component('cc.Layout')
        if layout:
            resize_mode = layout.get_property('_resize')
            if resize_mode == LayoutResizeMode.CONTAINER:
                type_ = layout.get_property('_N$layoutType')
                if type_ == LayoutType.HORIZONTAL:
                    size_ignores.add('width')
                elif type_ == LayoutType.VERTICAL:
                    size_ignores.add('height')
                elif type_ == LayoutType.GRID:  # GRID需要判断startAxis
                    start_axis = layout.get_property('_N$startAxis')
                    if start_axis == LayoutStartAxis.HORIZONTAL:
                        size_ignores.add('width')
                    else:
                        size_ignores.add('height')
                elif type_ == LayoutType.NONE:
                    size_ignores.add('height')
                    size_ignores.add('width')

        widget = self.get_component('cc.Widget')
        if widget:
            flag = widget.get_property('_alignFlags')
            if flag & (WidgetAlignFlag.LEFT | WidgetAlignFlag.RIGHT | WidgetAlignFlag.HORIZONTAL_CENTER):
                position_ignores.add('x')
            if flag & WidgetAlignFlag.LEFT and flag & WidgetAlignFlag.RIGHT:
                size_ignores.add('width')
            if flag & (WidgetAlignFlag.TOP | WidgetAlignFlag.BOTTOM | WidgetAlignFlag.VERTICAL_CENTER):
                position_ignores.add('y')
            if flag & WidgetAlignFlag.TOP and flag & WidgetAlignFlag.BOTTOM:
                size_ignores.add('height')

        if self.parent:
            layout = self.parent.get_component('cc.Layout')
            if layout:
                type_ = layout.get_property('_N$layoutType')
                if type_ == LayoutType.HORIZONTAL:
                    position_ignores.add('x')
                elif type_ == LayoutType.VERTICAL:
                    position_ignores.add('y')
                elif type_ == LayoutType.GRID:
                    position_ignores.add('x')
                    position_ignores.add('y')

                resize_mode = layout.get_property('_resize')
                if resize_mode == LayoutResizeMode.CHILDREN:
                    if type_ == LayoutType.HORIZONTAL:
                        size_ignores.add('width')
                    elif type_ == LayoutType.VERTICAL:
                        size_ignores.add('height')
                    elif type_ == LayoutType.GRID:
                        size_ignores.add('width')
                        size_ignores.add('height')

                kd_layout = self.parent.get_component('KdLayout')
                if kd_layout:
                    assert resize_mode == LayoutResizeMode.NONE
                    kd_widget = self.get_component('KdWidget')
                    if kd_widget:
                        proportion = kd_widget.get_property('proportion', 0)
                        if proportion != 0:
                            if type_ == LayoutType.HORIZONTAL:
                                size_ignores.add('width')
                            elif type_ == LayoutType.VERTICAL:
                                size_ignores.add('height')

        if self.position is None:
            assert self.loaded_index == -1
            self.position = copy.deepcopy(other.position)
        else:
            if '_position' not in ignores:
                ctx.push('_position')
                synchronize_dict(self, other, self.position, other.position, ctx, position_ignores)
                ctx.pop()

        if self.size is None:
            assert self.loaded_index == -1
            self.size = copy.deepcopy(other.size)
        else:
            if '_contentSize' not in ignores:
                ctx.push('_contentSize')
                synchronize_dict(self, other, self.size, other.size, ctx, size_ignores)
                ctx.pop()

    def __str__(self):
        return '<%s name=%s/>' % (self.__class__.__name__, self.name)


class Scene(Node):
    # def clone(self):
    #     raise Exception('could not clone a scene')
    def _save(self, file_, data):
        Node._save(self, file_, data)

        # Scene的component为空时，ccc会去掉这个属性。（然而Node并不会）
        _components = data.get('_components')
        if _components is not None and not _components:
            data.pop('_components')

        data.pop('_position', None)
        # data.pop('_parent', None)


class Component(Element):
    def __init__(self, project, node):
        """
        :param Project project:
        :param Node node:
        """
        Element.__init__(self, project)
        self.node = node

    def root(self):
        """
        :rtype: Node
        """
        return self.node.root

    @property
    def path(self):
        return '%s/#%s' % (self.node.path, self.type)

    # @property
    # def type(self):
    #     if self.__class__.__name__ == 'Component':
    #         return self._data['__type__']
    #     return 'cc.%s' % self.__class__.__name__

    @property
    def name(self):
        return self.project.get_component_name(self.type)

    def load(self, file_, index):
        Element.load(self, file_, index)

        node_ref = self.pop_data('node', None)
        _ = node_ref
        if node_ref is not None:
            if node_ref['__id__'] != self.node.loaded_index:
                # A component could be shared by multiple Node
                print 'Reused component:', self.path

        # R4: Button的clickEvents最多只能有一个元素
        if self.type == 'cc.Button':
            if len(self.get_property('clickEvents')) > 1:
                raise Exception('Button have too many clickEvents: %s' % self.node.relative_path)

        if self.type == 'cc.Layout':
            type_ = self.get_property('_N$layoutType')
            resize_mode = self.get_property('_resize')
            # R6: 只能包含已知的Type和ResizeMode
            if type_ not in {LayoutType.NONE, LayoutType.HORIZONTAL, LayoutType.VERTICAL, LayoutType.GRID}:
                raise Exception('Unknown layout type %s: %s' % (type_, self.node.relative_path))

            if resize_mode not in {LayoutResizeMode.NONE, LayoutResizeMode.CONTAINER, LayoutResizeMode.CHILDREN}:
                raise Exception('Unknown layout resize mode %s: %s' % (resize_mode, self.node.relative_path))

            # # R7: Layout的Type为NONE时，Resize Mode也必须为None(应该不会有这种需求?防止编辑失误而作的检查)
            # if type_ == LayoutType.NONE and resize_mode != LayoutResizeMode.NONE:
            #         raise Exception('Layout of type NONE should have resize mode NONE: %s' % self.node.relative_path)

        if self.type == 'KdLayout':
            layout = self.node.get_component('Layout')
            if not layout:
                raise Exception('KdLayout without Layout: %s' % self.node.relative_path)
            type_ = layout.get_property('_N$layoutType')
            if type_ not in {LayoutType.HORIZONTAL, LayoutType.VERTICAL}:
                raise Exception('KdLayout must be HORIZONTAL or VERTICAL: %s' % self.node.relative_path)
            resize_mode = layout.get_property('_resize')
            if resize_mode != LayoutResizeMode.NONE:
                raise Exception('KdLayout must be ResizeModeNone: %s' % self.node.relative_path)

    def _save(self, file_, data):
        data['node'] = create_element_ref(self.node.saved_index)

    def synchronize(self, other, ctx):
        """
        :param Component other:
        :param CompareContext ctx:
        """
        assert isinstance(other, Component)
        # 否则没有self.name
        self._data['__type__'] = other._data['__type__']

        # CR2: 忽略组件的指定属性(ignore_component_properties)
        ignores = self.project.ignore_component_properties.get(self.name, set())
        """:type: set[str]"""

        # CR3: 忽略组件的空属性(ignore_component_properties_if_empty)，空指0, "", [], null等，或不存在
        for property_name in self.project.ignore_component_properties_if_empty.get(self.name, set()):
            if not other._data.get(property_name):
                ignores = ignores.union(property_name)

        # CR4: 忽略特定的prefab中的特定Node的特定组件的特定属性
        if other._ignore_properties:
            ignores = ignores.union(other._ignore_properties)

        ctx.push(self.name)
        synchronize_dict(self, other, self._data, other._data, ctx, ignores=ignores)
        ctx.pop()

    def __str__(self):
        return '<%s name=%s node=%s/>' % (self.__class__.__name__, self.name, self.node.relative_path)


def check_value(val):
    if isinstance(val, (int, float, str, unicode)):
        return

    if val is None:
        return

    if isinstance(val, (dict, OrderedDict)):
        if len(val) == 1 and '__uuid__' in val:
            return

        if len(val) == 1 and 'uuid' in val:  # "_N$horizontalScrollBar": { "uuid": null },
            return

        if val.get('__type__') in {'cc.Vec2', 'cc.Color', 'cc.Size'}:
            return

    raise Exception('invalid value: %s' % val)


# class Button(Component):
#     def __init__(self, project, node):
#         Component.__init__(self, project, node)
#         self.click_events = []
#         """:type: list[ClickEvent]"""
#         self.target = None
#         """:type: Node"""
#
#     def load(self, file_, index):
#         Component.load(self, file_, index)
#
#         node_ref = self._data.pop('node')
#         assert node_ref['__id__'] == self.node.loaded_index
#
#         for ref in self._data.pop('clickEvents'):
#             click_event = ClickEvent(self.project)
#             click_event.load(file_, ref['__id__'])
#             self.click_events.append(click_event)
#
#     def post_load(self, file_):
#         target_ref = self._data.pop('_N$target')
#         if target_ref:
#             self.target = file_.elements[self.loaded_index]
#             assert isinstance(self.target, Node)
#
#
# class ClickEvent(Element):
#     pass


# class ArgumentMeta(Element):
#     @property
#     def type(self):
#         return 'ArgumentMeta'


class Value(object):
    def save(self, file_):
        """
        :param FileOutput file_:
        :return: *
        """
        raise NotImplementedError()

    def synchronize(self, other, ctx):
        """
        :param Value other:
        :param CompareContext ctx:
        """
        raise NotImplementedError()

    def clone(self, element):
        """
        :param Element element:
        :rtype: Value
        """
        raise NotImplementedError()

    def __cmp__(self, other):
        raise NotImplementedError()


class NodeReference(Value):
    def __init__(self, node, referenced_node=None):
        """
        :param Node node:
        :param Node referenced_node:
        """
        self._node = node
        self._relative_path = ''
        if referenced_node:
            self._relative_path = referenced_node.get_relative_path_to(node)

    def __cmp__(self, other):
        """
        :param NodeReference|None other:
        :return: int
        """
        if other is None:
            return 1
        assert isinstance(other, NodeReference)
        return cmp(self._relative_path, other._relative_path)

    def clone(self, element):
        r = NodeReference(element.node)
        r._relative_path = self._relative_path
        return r

    def synchronize(self, other, ctx):
        """
        :param NodeReference|None other:
        :param CompareContext ctx:
        """
        assert isinstance(other, NodeReference)
        # ctx.change('<ref>', self._relative_path, other._relative_path)
        self._relative_path = other._relative_path
        # self._referenced_node =._node.get_relative_node(other._relative_path)

    def save(self, file_):
        referenced_node = self._node.get_relative_node(self._relative_path)
        if referenced_node:
            if referenced_node.saved_index == -1:
                referenced_node.save(file_)
            return create_element_ref(referenced_node.saved_index)
        else:
            return create_element_ref(None)

    def __str__(self):
        return '<Reference path=%s/>' % self._relative_path


class ComponentReference(Value):
    def __init__(self, node, referenced_component=None):
        """
        :param Node node:
        :param Component referenced_component:
        """
        self._node = node
        self._relative_path = ''
        self._component_name = ''

        if referenced_component:
            self._relative_path = referenced_component.node.get_relative_path_to(node)
            self._component_name = referenced_component.name

    def __cmp__(self, other):
        """
        :param ComponentReference|None other:
        :return: int
        """
        if other is None:
            return 1
        assert isinstance(other, ComponentReference)
        r = cmp(self._relative_path, other._relative_path)
        if r == 0:
            r = cmp(self._component_name, other._component_name)
        return r

    def clone(self, element):
        r = ComponentReference(element.node)
        r._relative_path = self._relative_path
        r._component_name = self._component_name
        return r

    def synchronize(self, other, ctx):
        """
        :param ComponentReference|None other:
        :param CompareContext ctx:
        """
        assert isinstance(other, ComponentReference)
        # ctx.change('<ref>', self._relative_path, other._relative_path)
        self._relative_path = other._relative_path
        self._component_name = other._component_name
        # self._referenced_node =._node.get_relative_node(other._relative_path)

    def save(self, file_):
        referenced_node = self._node.get_relative_node(self._relative_path)
        if referenced_node:
            if referenced_node.saved_index == -1:
                referenced_node.save(file_)
            component = referenced_node.get_component(self._component_name)
            if component:
                assert component.saved_index != -1
                return create_element_ref(referenced_node.saved_index)

        return create_element_ref(None)

    def __str__(self):
        return '<Reference path=%s/>' % self._relative_path


# class Color(Value):
#     def __init__(self, data):
#         self._data = data
#
#     def __str__(self):
#         return '<Color r=%s g=%s b=%s a=%s/>' % (self._data['r'], self._data['g'], self._data['b'], self._data['a'])
#
#     def save(self, file_):
#         return copy.deepcopy(self._data)
#
#
# class Size(Value):
#     def __init__(self, data):
#         self._data = data
#
#     @property
#     def width(self):
#         return self._data['width']
#
#     @property
#     def height(self):
#         return self._data['height']
#
#     def __str__(self):
#         return '<Size w=%s h=%s/>' % (self.width, self.height)
#
#     def save(self, file_):
#         return copy.deepcopy(self._data)


class Argument(Element):
    def __init__(self, project, component):
        Element.__init__(self, project)
        self.component = component

    @property
    def node(self):
        return self.component.node

    @property
    def type(self):
        return self._data['__type__']


class PrefabInfo(Element):
    def __init__(self, project, node):
        """
        :param Project project:
        :param Node node:
        """
        Element.__init__(self, project)
        self.node = node

    def post_load(self, file_):
        root_ref = self.pop_data('root')
        if get_element_ref(root_ref) != self.node.instance_root.loaded_index:
            raise Exception('Instance root not match: %s' % self.node.relative_path)

    @property
    def file_id(self):
        return self._data.get('fileId')

    @file_id.setter
    def file_id(self, val):
        self._data['fileId'] = val

    @property
    def uuid(self):
        asset = self._data.get('asset')
        if asset:
            return asset.get('__uuid__')

    @uuid.setter
    def uuid(self, val):
        self._data['asset'] = {'__uuid__': val} if val else None

    def _save(self, file_, data):
        data['root'] = create_element_ref(self.node.instance_root.save(file_))


class Project(object):
    def __init__(self, path):
        self.ignore_components = set()
        """:type: set[str]"""
        self.ignore_component_properties = {}
        """:type: dict[str, set[str]]"""
        self.ignore_component_properties_if_empty = {}
        """:type: dict[str, set[str]]"""
        self.ignore_prefabs = {}
        """:type: dict[str, dict[str, list[str]]]"""

        self.path = os.path.realpath(path)

        self._uuid_to_assets = {}
        """:type: dict[str, Asset]"""
        
        self._path_to_assets = {}
        """:type: dict[str, Asset]"""
        
        self._component_id_to_names = {}
        """:type: dict[str, str]"""

    def load(self):
        self._load_setting()

        cwd = os.getcwd()
        os.chdir(self.path)
        errors = 0
        try:
            self._load_components()
            errors += self._load_assets()
            self._sort_assets()
        finally:
            os.chdir(cwd)

        errors += self._ignore_prefabs()

        if errors > 0:
            raise Exception('Load failed.')

    def _ignore_prefabs(self):
        errors = 0

        for path, elements in self.ignore_prefabs.iteritems():
            asset = self.get_asset_by_path(path)
            if not asset:
                print 'Asset not found: ', path
                errors += 1
                continue

            for element_path, properties in elements.iteritems():
                element = asset.get_element_by_path(element_path)
                if not element:
                    print 'Element not found:', element_path
                    errors += 1
                    continue
                element.ignore(properties)
        return errors

    def _load_setting(self):
        setting = yaml.load(open(os.path.join(self.path, 'ccchelper.yaml')))
        self.ignore_components = set(setting.get('ignore_components', []))

        ignore_component_properties = setting.get('ignore_component_properties', {})
        for key in ignore_component_properties.keys() + IGNORE_COMPONENT_PROPERTIES.keys():
            v = ignore_component_properties.get(key, []) + IGNORE_COMPONENT_PROPERTIES.get(key, [])
            self.ignore_component_properties[key] = set(v)

        self.ignore_component_properties_if_empty = setting.get('ignore_component_properties_if_empty', {})
        for k, v in self.ignore_component_properties_if_empty.iteritems():
            self.ignore_component_properties_if_empty[k] = set(v)

        self.ignore_prefabs = setting.get('ignore_prefabs', {})

    # noinspection SpellCheckingInspection
    def _load_components(self):
        bundle_js = os.path.join('library', 'bundle.project.js')
        bundle = open(bundle_js).read()
        # cc._RFpush(module, '4c3c5p1IVNIn7SN0Moet2KO', 'KdPrefab');
        pairs = re.findall('cc\._RFpush\(module,\s+\'([a-zA-Z0-9]+)\',\s+\'([a-zA-Z0-9_]+)\'\);', bundle, re.M)
        # noinspection PyTypeChecker
        self._component_id_to_names = dict(pairs)

    def _load_assets(self):
        errors = 0
        for p, ds, fs in os.walk('assets'):
            for f in fs:
                if f.endswith('.meta'):
                    continue
                fp = os.path.join(p, f)
                assert fp.startswith('assets/') or fp.startswith('assets\\')
                fp = fp[7:]  # remove 'assets/'
                try:
                    self.load_one_asset(fp)
                except Exception, e:
                    traceback.print_exc()
                    print 'Load Error:', fp, str(e)
                    errors += 1
        return errors

    def load_one_asset(self, relative_path):
        """
        :param str relative_path: relative to assets
        :rtype: Asset|None
        """
        _, fullname = os.path.split(relative_path)
        name, ext = os.path.splitext(fullname)
        asset = None
        """:type: Asset"""

        if ext == '.prefab':
            print 'loading', relative_path
            asset = FileInput(self, relative_path).load(Prefab)
        elif ext == '.fire':
            print 'loading', relative_path
            asset = FileInput(self, relative_path).load(SceneAsset)

        if asset:
            self._uuid_to_assets[asset.file.uuid] = asset
            self._path_to_assets[asset.file.relative_path] = asset
        return asset

    def get_component_name(self, id_):
        return self._component_id_to_names.get(id_, id_)

    def iterate_assets(self):
        """
        :rtype: collections.Iterable[Asset]
        """
        return self._uuid_to_assets.itervalues()

    def synchronize_all_instances(self, dry_run):
        # 按照依赖关系排序
        assets = self._uuid_to_assets.values()
        assets.sort(key=lambda x: x.depth, reverse=True)
        self._synchronized_assets(assets, dry_run, 'synchronize_all_instances')

    def synchronize_prefab(self, prefab, dry_run):
        """
        将prefab递归同步到引用到它的scene/prefab中
        :param Prefab prefab:
        :param bool dry_run:
        :return:
        """
        assets = prefab.search_referents()
        assets.insert(0, prefab)
        self._synchronized_assets(assets, dry_run, 'synchronize %s' % prefab.relative_path)

    def _synchronized_assets(self, assets, dry_run, message):
        """
        :param list[Asset] assets: 必须排好序
        :param bool dry_run:
        """
        for asset in self.iterate_assets():
            asset.synchronized = asset.need_synchronize = False
        for asset in assets:
            asset.need_synchronize = True

        # 备份
        backup = Backup(self)
        backup.log.write('%s\n' % message)

        files = 0
        for asset in assets:
            ctx = CompareContext()
            ctx.push(asset.relative_path)
            asset.synchronize_all_instances(ctx)
            ctx.pop()
            ctx.dump(backup.log)

            if not dry_run and ctx.has_changed():
                backup.backup_asset(asset)
                FileOutput(self, asset.file.relative_path).save(asset)
                files += 1

        print 'Modified %s files. For more information, check "%s"' % (files, backup.path)

    def get_prefab_by_file_id(self, file_id):
        """
        :param str file_id:
        :rtype:
        """
        for asset in self.iterate_assets():
            if isinstance(asset, Prefab):
                if asset.get_file_id() == file_id:
                    return asset

    def get_asset_by_uuid(self, uuid_):
        """
        :param str uuid_:
        :rtype: Prefab|SceneAsset|None
        """
        return self._uuid_to_assets.get(uuid_)

    def get_asset_by_path(self, path):
        """
        :param str path: relative to assets
        :rtype: Asset
        """
        return self._path_to_assets.get(path)

    def get_prefab_by_path(self, path):
        """
        :param str path: relative to assets
        :rtype: Prefab
        """
        asset = self.get_asset_by_path(path)
        assert isinstance(asset, Prefab)
        return asset

    def _sort_assets(self):
        """
        对所有Asset按照依赖关系排序。如果A依赖B，B.order < A.order
        """
        # # 初始化
        # for asset in self.iterate_assets():
        #     asset.references = []
        #     asset.referents = []
        #     asset.depth = 0

        # 查找每个Asset引用到的其他Asset，形成森林
        for asset in self.iterate_assets():
            for node in asset.root.iterate_instance_roots(False):
                prefab = self.get_asset_by_uuid(node.get_prefab_uuid())
                asset.references.add(prefab)
                prefab.referents.add(asset)

        # BFS遍历，计算每个asset的depth
        # 所有的树根，depth都为0
        assets = {asset for asset in self.iterate_assets() if not asset.referents}
        depth = 1
        while assets:
            references = set(sum([list(asset.references) for asset in assets], []))  # 被引用的
            for child in references:
                child.depth = depth

            depth += 1
            assets = references

    def dump_references(self):
        for asset in self.iterate_assets():
            print asset.relative_path
            for ref in asset.references:
                print '   ', ref.relative_path

    def dump_referents(self):
        for asset in self.iterate_assets():
            print asset.relative_path
            for ref in asset.referents:
                print '   ', ref.relative_path


class Backup(object):
    def __init__(self, project):
        self.project = project
        # noinspection SpellCheckingInspection
        self.path = os.path.join(project.path, 'ccchelper_backup',
                                 datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S'))
        os.makedirs(self.path)
        self.log = open(os.path.join(self.path, 'logs.txt'), 'w')

    def backup_asset(self, asset):
        """
        :param Asset asset:
        """
        dst_path = os.path.join(self.path, asset.file.relative_path)
        dst_folder = os.path.split(dst_path)[0]
        if not os.path.exists(dst_folder):
            os.makedirs(dst_folder)
        shutil.copy(asset.path, dst_path)


def create_element_ref(index):
    if index is None:
        return None
    return {'__id__': index}


def is_element_ref(value):
    return isinstance(value, dict) and len(value) == 1 and '__id__' in value


def get_element_ref(value):
    """
    :param dict [str, int] value:
    :rtype: int
    """
    assert is_element_ref(value)
    return value['__id__']


def is_primitive(value):
    if isinstance(value, (int, float, str, unicode)):
        return True


def is_dict(v):
    return isinstance(v, (dict, OrderedDict))


def is_same_type(v1, v2):
    if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
        return True

    if is_dict(v1) and is_dict(v2):
        return True

    return type(v1) == type(v2)


def synchronize_dict(element1, element2, dict1, dict2, ctx, ignores=set()):
    """
    :param Element element1:
    :param Element element2:
    :param dict dict1:
    :param dict dict2: prefab里的
    :param CompareContext ctx:
    :param set[str] ignores:
    """
    if dict1 is None:
        dict1 = OrderedDict()
    assert is_dict(dict1)
    assert is_dict(dict2)

    to_remove = []
    for k, v in dict1.iteritems():
        if k in ignores:
            continue

        if k not in dict2:
            to_remove.append(k)
            ctx.remove(k, v)

    for k in to_remove:
        dict1.pop(k)

    for k, v in dict2.iteritems():
        if k in ignores:
            continue

        dict1[k] = synchronize_value(k, element1, element2, dict1.get(k), v, ctx)
    return dict1


def synchronize_list(element1, element2, list1, list2, ctx):
    """
    :param Element element1:
    :param Element element2:
    :param list list1:
    :param list list2:
    :param CompareContext ctx:
    """
    if list1 is None:
        list1 = []
    assert isinstance(list1, list)
    assert isinstance(list2, list)

    # list同步比较复杂。这里只能简单的覆盖
    for i in xrange(min(len(list1), len(list2))):
        list1[i] = synchronize_value('%s' % i, element1, element2, list1[i], list2[i], ctx)

    if len(list1) < len(list2):
        for i in xrange(len(list1), len(list2)):
            v = synchronize_value('%s' % i, element1, element2, None, list2[i], CompareContext())  # 完全复制
            list1.append(v)
            ctx.add('%s' % i)
    elif len(list1) > len(list2):
        for i in xrange(len(list2), len(list1)):
            list1.pop()
            ctx.remove('%s' % i)
    return list1


def synchronize_value(name, element1, element2, v1, v2, ctx):
    """
    :param str name:
    :param Element element1:
    :param Element element2:
    :param * v1:
    :param * v2:
    :param CompareContext ctx:
    """
    if v1 is None and v2 is None:
        return None

    if v2 is None:
        ctx.change(name, v1, v2)
        return None

    if v1 is not None and v2 is not None:
        assert is_same_type(v1, v2), '%s %s' % (type(v1), type(v2))

    # if is_element_ref(v1) or is_element_ref(v2):  # 必须在dict前面！
    #     compare_element_ref(name, element1, element2, v1, v2, ctx)
    if isinstance(v1, Element) or isinstance(v2, Element):
        # assert isinstance(v1, Element) and isinstance(v2, Element)
        if v1 is None:
            if isinstance(v2, Argument):
                v1 = Argument(v2.project, element1)
        v1.synchronize(v2, ctx)
        return v1
    elif isinstance(v1, dict) or isinstance(v2, dict):
        ctx.push(name)
        v1 = synchronize_dict(element1, element2, v1, v2, ctx)
        ctx.pop()
        return v1
    elif isinstance(v1, list) or isinstance(v2, list):
        ctx.push(name)
        v1 = synchronize_list(element1, element2, v1, v2, ctx)
        ctx.pop()
        return v1
    elif isinstance(v1, Value) or isinstance(v2, Value):
        if v1 != v2:
            ctx.change(name, v1, v2)
        if v2 is None:
            return None
        if v1 is None:
            return v2.clone(element1)
        v1.synchronize(v2, ctx)
        return v1
    else:
        if v1 != v2:
            ctx.change(name, v1, v2)
        assert is_primitive(v2)
        return copy.deepcopy(v2)


def load_dict(file_, element, dict_):
    for key, val in dict_.iteritems():
        dict_[key] = load_value(file_, element, val)
    return dict_


def load_list(file_, element, list_):
    for i, val in enumerate(list_):
        list_[i] = load_value(file_, element, val)
    return list_


def load_value(file_, element, val):
    if is_element_ref(val):
        return load_ref(file_, element, val)
    elif isinstance(val, list):
        return load_list(file_, element, val)
    elif isinstance(val, dict):
        return load_dict(file_, element, val)
    else:
        check_value(val)
        return val


def load_ref(file_, element, val):
    """
    :param FileInput file_:
    :param Element element:
    :param * val:
    :rtype: Value|Element
    """
    id_ = get_element_ref(val)
    if len(file_.elements[id_]) > 1:
        raise Exception('Could not reference more than one target: %s' % id_)

    if len(file_.elements[id_]) == 1:
        assert isinstance(element, (Component, Argument)), type(element)
        referenced = file_.elements[id_][0]
        if referenced:
            if isinstance(referenced, Node):
                return NodeReference(element.node, referenced)
            elif isinstance(referenced, Component):
                return ComponentReference(element.node, referenced)
            else:
                raise Exception('unknown reference: %s' % referenced)

    class_ = Argument
    assert isinstance(element, Component)
    element = class_(element.project, element)
    element.load(file_, id_)
    return element


def save_dict(file_, element, data):
    """
    :param FileOutput file_:
    :param Element element:
    :param dict data:
    """
    assert isinstance(data, dict)
    r = OrderedDict()
    for k, v in data.iteritems():
        r[k] = save_value(file_, element, v)
    return r


def save_list(file_, element, data):
    """
    :param FileOutput file_:
    :param Element element:
    :param list data:
    """
    assert isinstance(data, list)
    r = []
    for v in data:
        r.append(save_value(file_, element, v))
    return r


def save_value(file_, element, v):
    """
    :param FileOutput file_:
    :param Element element:
    :param * v:
    """
    if v is None:
        return None

    if isinstance(v, Element):
        assert isinstance(v, Argument)
        v.save(file_)
        return create_element_ref(v.saved_index)
    elif isinstance(v, Value):
        return v.save(file_)
    elif isinstance(v, dict):
        return save_dict(file_, element, v)
    elif isinstance(v, list):
        return save_list(file_, element, v)
    else:
        assert is_primitive(v), v
        return copy.copy(v)


class CompareContext(object):
    def __init__(self):
        self._diff = []

    def push(self, name, comment=''):
        self._diff.append(('push', name, comment))
        return self

    def pop(self):
        if self._diff and self._diff[-1][0] == 'push':
            self._diff.pop()
            return

        self._diff.append(('pop',))
        return self

    def add(self, name, comment=''):
        self._diff.append(('+', name, comment))
        return self

    def remove(self, name, value=''):
        self._diff.append(('-', name, value))
        return self

    def change(self, name, old=None, new=None):
        self._diff.append(('*', name, old, new))
        return self

    def ignore(self, name):
        self._diff.append(('!', name))
        return self

    def has_changed(self):
        for item in self._diff:
            if item[0] in '+-*':
                return True

        return False

    def dump(self, stream=None):
        level = 0

        if stream is None:
            stream = sys.stdout

        def print_(*s):
            stream.write('  ' * level)
            stream.write(' '.join(map(str, s)))
            stream.write('\n')

        for item in self._diff:
            if item[0] == 'push':
                print_(*item[1:])
                level += 1
            elif item[0] == 'pop':
                level -= 1
            else:
                print_(*item)
        stream.flush()

    def __eq__(self, other):
        if not isinstance(other, CompareContext):
            return False

        if len(self._diff) != len(other._diff):
            return False

        for i in xrange(len(self._diff)):
            # 只需要比较前两个
            if self._diff[i][:2] != other._diff[i][:2]:
                return False

        return True

    def __str__(self):
        return '%s' % self._diff


def test2():
    p = Project('../kingdom')
    p.load()
    p.dump_references()


def main():
    parser = optparse.OptionParser()
    parser.add_option('-p', '--project', dest='project', help='project path')
    usage = """
python ccc.py [options] action
e.g.:
    # synchronize all prefabs in project
    python ccc.py -p . sync
    # synchronize one prefab (to prefabs/scenes which has referenced to it)
    python ccc.py -p . sync a.prefab
    # verify entire project, won't modify any file
    python ccc.py -p . verify
    # verify one prefab (and its referents)
    python ccc.py -p . verify a.prefab
"""

    parser.set_usage(usage)

    option, args = parser.parse_args()
    action = args[0] if args else None
    if action not in ('sync', 'verify'):
        parser.print_help()
        return

    project = Project(option.project)
    project.load()

    asset = None
    if len(args) > 1:
        asset = project.get_asset_by_path(args[1])
    
    if action == 'sync':
        if asset:
            assert isinstance(asset, Prefab)
            project.synchronize_prefab(asset, False)
        else:
            project.synchronize_all_instances(False)
    elif action == 'verify':
        if asset:
            assert isinstance(asset, Prefab)
            project.synchronize_prefab(asset, True)
        else:
            project.synchronize_all_instances(True)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
