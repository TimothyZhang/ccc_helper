# coding=utf-8
# Copyright 2014 Timothy Zhang(zt@live.cn).
#
# This file is part of Structer.
#
# Structer is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Structer is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Structer.  If not, see <http://www.gnu.org/licenses/>.

from unittest import TestCase
from ccc import Project, SceneAsset, CompareContext, Prefab


class TestCCC(TestCase):
    def setUp(self):
        self.project = Project('test_project')
        self.project.load()

    def synchronize_asset_instances(self, asset):
        """
        :param Asset asset:
        """
        ctx = CompareContext()

        for node in asset.root.iterate_instance_roots(False):
            uuid_ = node.get_prefab_uuid()
            prefab = self.project.get_asset_by_uuid(uuid_)
            if not prefab:
                ctx.remove('miss prefab for %s' % node.path)
                continue

            assert isinstance(prefab, Prefab)
            node.synchronize(prefab.root, ctx, True)

        return ctx

    def assertContextEqual(self, ctx1, ctx2):
        """
        :param CompareContext ctx1:
        :param CompareContext ctx2:
        """
        if cmp(ctx1, ctx2) != 0:
            print 'ctx1:', ctx1
            print 'ctx2:', ctx2
        self.assertEqual(ctx1, ctx2)

    def test_ss1(self):
        s1 = self.project.get_asset_by_path('testcases/ss1/s1.fire')
        self.assertIsInstance(s1, SceneAsset)
        ctx1 = self.synchronize_asset_instances(s1)
        ctx2 = CompareContext()
        ctx2.push('i1').push('_color').change('g').change('b').pop().pop().ignore('i2').ignore('i3').ignore('i4')
        self.assertContextEqual(ctx1, ctx2)

    def test_ss2(self):
        s1 = self.project.get_asset_by_path('testcases/ss2/s1.fire')
        self.assertIsInstance(s1, SceneAsset)
        ctx1 = self.synchronize_asset_instances(s1)
        ctx2 = CompareContext()
        ctx2.push('i1').change('_opacity').push('_color').change('g').change('b').pop().push('_contentSize').\
            change('width').change('height').pop().pop()
        self.assertContextEqual(ctx1, ctx2)

    def test_ss3(self):
        s1 = self.project.get_asset_by_path('testcases/ss3/s1.fire')
        self.assertIsInstance(s1, SceneAsset)
        ctx1 = self.synchronize_asset_instances(s1)
        ctx2 = CompareContext()
        ctx2.push('i1').push('(components)').add('cc.Widget').pop().pop()
        self.assertContextEqual(ctx1, ctx2)

    def test_ss4(self):
        s1 = self.project.get_asset_by_path('testcases/ss4/s1.fire')
        ctx1 = self.synchronize_asset_instances(s1)
        ctx2 = CompareContext()
        self.assertContextEqual(ctx1, ctx2)

    def test_ss5(self):
        s1 = self.project.get_asset_by_path('testcases/ss5/s1.fire')
        ctx1 = self.synchronize_asset_instances(s1)
        self.assert_(not ctx1.has_changed())

    def test_nested(self):
        s1 = self.project.get_asset_by_path('testcases/nested/p1.prefab')
        self.assertEqual(s1.depth, 1)
        s1 = self.project.get_asset_by_path('testcases/nested/p2.prefab')
        self.assertEqual(s1.depth, 2)
        s1 = self.project.get_asset_by_path('testcases/nested/s1.fire')
        self.assertEqual(s1.depth, 0)

    def clear_setting(self):
        self.project.ignore_components.clear()
        self.project.ignore_component_properties.clear()
        self.project.ignore_component_properties_if_empty.clear()

    def test_cr1_cr2_cr3(self):
        # cr1
        self.clear_setting()
        self.project.ignore_components.add('cc.Button')
        # print self.project.ignore_components
        s1 = self.project.get_asset_by_path('testcases/cr1_cr2_cr3/s1.fire')
        ctx1 = self.synchronize_asset_instances(s1)
        ctx2 = CompareContext()
        self.assertContextEqual(ctx1, ctx2)

        # cr2
        self.clear_setting()
        self.project.ignore_component_properties['cc.Button'] = {'clickEvents'}

        s2 = self.project.get_asset_by_path('testcases/cr1_cr2_cr3/s2.fire')
        ctx1 = self.synchronize_asset_instances(s2)
        ctx2 = CompareContext()
        self.assertContextEqual(ctx1, ctx2)

        # cr3
        self.clear_setting()
        self.project.ignore_component_properties_if_empty['cc.Button'] = {'clickEvents'}

        s3 = self.project.get_asset_by_path('testcases/cr1_cr2_cr3/s3.fire')
        ctx1 = self.synchronize_asset_instances(s3)
        ctx2 = CompareContext()
        self.assertContextEqual(ctx1, ctx2)

        s4 = self.project.get_asset_by_path('testcases/cr1_cr2_cr3/s4.fire')
        ctx1 = self.synchronize_asset_instances(s4)
        self.assert_(ctx1.has_changed())
