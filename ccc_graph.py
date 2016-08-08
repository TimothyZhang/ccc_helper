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

import optparse
import os
from ccc import Project, Prefab
import networkx as nx


plt = graphviz_layout = pygraphviz = None
# noinspection PyBroadException
try:
    import matplotlib.pyplot as plt
except:
    print 'matplotlib not found'

# noinspection PyBroadException
try:
    from networkx.drawing.nx_pydot import graphviz_layout
except:
    print 'graphviz_layout not found'


try:
    import pygraphviz
except:
    print 'pygraphviz not found'


option = None


def create_project_graph(project):
    """
    :param Project project:
    :rtype: nx.MultiDiGraph
    """
    g = nx.MultiDiGraph()
    assets = list(project.iterate_assets())
    add_assets_to_graph(g, assets)
    return g


def create_asset_graph(asset):
    """
    :param Asset asset:
    :rtype nx.DiGraph:
    """
    g = nx.DiGraph()
    assets = [asset]
    assets += asset.search_referents()
    if isinstance(asset, Prefab):
        assets += asset.search_referers()

    add_assets_to_graph(g, assets)
    return g


def add_assets_to_graph(g, assets):
    """
    :param nx.Graph g:
    :param Sequence[Asset] assets:
    """
    for asset in assets:
        if not asset.referers and not asset.referents:
            continue

        add_node(g, asset)

    for asset in assets:
        if not asset.referers and not asset.referents:
            continue

        for ref in asset.referers:
            g.add_edge(ref.relative_path, asset.relative_path)


def add_node(g, asset):
    """
    :param nx.Graph g:
    :param Asset asset:
    """
    if isinstance(asset, Prefab):
        if not asset.referents:
            color = 'green'
        else:
            color = 'blue'
    else:
        color = 'red'

    if option.long:
        label = asset.relative_path
    else:
        label = asset.file.name
    g.add_node(asset.relative_path, label=label, color=color)


def create_image(g, path):
    path = os.path.relpath(path)

    if pygraphviz:
        a = nx.nx_agraph.to_agraph(g)
        # ['neato'|'dot'|'twopi'|'circo'|'fdp'|'nop']
        a.layout(prog='neato', args="-Goverlap=false -Gsplines=true")  # splines=true
        a.draw(path)
    elif plt:
        nodes = g.nodes(True)
        colors = [attrs['color'] for n, attrs in nodes]
        labels = {n: attrs['label'] for n, attrs in nodes}

        if graphviz_layout:
            pos = graphviz_layout(g)
        else:
            pos = nx.spring_layout(g)
        nx.draw_networkx_nodes(g, pos, node_shape='o', node_color=colors, alpha=0.3)
        nx.draw_networkx_edges(g, pos, style='solid', alpha=0.2)
        nx.draw_networkx_labels(g, pos, labels, alpha=0.5)
        # plt.show()
        plt.imsave(path)  # todo: this is not tested!

    print 'Image saved to', path


def main():
    parser = optparse.OptionParser()
    parser.add_option('-p', '--project', dest='project', help='project path')
    # parser.add_option('-a', '--asset', dest='asset', help='asset path (relative to assets)')
    parser.add_option('-o', '--output', dest='output', help='output file name')
    parser.add_option('-l', '--long', dest='long', default=False, action='store_true',
                      help='show long label (relative path to assets)')

    usage = """
python ccc_graph.py [options] [asset]
e.g.:
    # visualize entire project (to ccc.png)
    python ccc_graph.py -p .
    # visualize one prefab (and its referer and referents)
    python ccc_graph.py -p . -o prefab_a.png path/relative/to/assets/xxx.prefab
"""

    parser.set_usage(usage)
    global option
    option, args = parser.parse_args()

    if not option.project:
        parser.print_help()
        return

    project = Project(option.project)
    project.load()

    output = option.output
    if not output:
        output = '%s.jpg' % project.name

    if len(args) > 0:
        asset = project.get_asset_by_path(args[1])
        create_image(create_asset_graph(asset), output)
    else:
        create_image(create_project_graph(project), output)

if __name__ == '__main__':
    main()
