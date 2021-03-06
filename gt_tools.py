from __future__ import division
from sys import platform as _platform
import matplotlib
import matplotlib.cm as colormap

if _platform == "linux" or _platform == "linux2":
    matplotlib.use('Agg')
import matplotlib.pylab as plt
from graph_tool.all import *
import os
import matplotlib.cm as colormap
from matplotlib.colors import ColorConverter as color_converter
import pandas as pd
import Image
import ImageDraw
import ImageFont
import subprocess
import printing
import random
import datetime
import copy
import shutil
import numpy as np
import operator
import math
from scipy.sparse.linalg.eigen.arpack import eigsh as largest_eigsh
import sys
from scipy.stats import powerlaw, poisson
from collections import defaultdict
import traceback
from basics import create_folder_structure


def print_f(*args, **kwargs):
    if 'class_name' not in kwargs:
        kwargs.update({'class_name': 'gt_tools'})
    printing.print_f(*args, **kwargs)

# Generator Class works with GraphTool generators, as they provide more functionality than NetworkX Generators
class GraphGenerator():
    # init generator
    def __init__(self, num_nodes=5000, directed=False):
        self.directed = directed
        self.num_nodes = num_nodes
        self.graph = None
        self.node_id_map = None
        self.return_and_reset()

    def return_and_reset(self):
        result = self.graph
        self.graph = Graph(directed=self.directed)
        self.node_id_map = defaultdict(lambda x: self.graph.add_vertex())
        return result

    # start creating blockmodel graph
    def create_blockmodel_graph(self, blocks=7, connectivity=10, model="blockmodel-traditional"):
        def corr(a, b):
            if a == b:
                return 0.999
            else:
                return 0.001

        self.print_f("Starting to create Blockmodel Graph with {} nodes and {} blocks".format(self.num_nodes, blocks))

        self.graph, vertex_colors = random_graph(self.num_nodes, lambda: poisson(connectivity), directed=False, model=model, block_membership=lambda: random.randint(1, blocks),
                                                 vertex_corr=corr)
        self.graph.vertex_properties["colorsComm"] = vertex_colors
        return self.return_and_reset()

    def create_fully_connected_graph(self, size=1000, directed=False, self_edges=False):
        return self.create_stochastic_blockmodel_graph(blocks=1, size=size, directed=directed, self_edges=self_edges, self_block_connectivity=1.0, other_block_connectivity=1.0)

    @staticmethod
    def create_sbm_lined_up_matrix(blocks=10, self_block_connectivity=None, other_block_connectivity=None):
        if self_block_connectivity is None:
            self_block_connectivity = [0.9]
        elif isinstance(self_block_connectivity, (int, float)):
            self_block_connectivity = [self_block_connectivity]
        if other_block_connectivity is None:
            other_block_connectivity = [0.1]
        elif isinstance(other_block_connectivity, (int, float)):
            other_block_connectivity = [other_block_connectivity]
        connectivity_matrix = []
        blocks_range = range(blocks)
        for idx in blocks_range:
            row = []
            outer_prob = other_block_connectivity[idx % len(other_block_connectivity)]
            inner_prob = self_block_connectivity[idx % len(self_block_connectivity)]
            for jdx in blocks_range:
                if idx != jdx:
                    row.append(outer_prob / pow(abs(idx - jdx), 2))
                else:
                    row.append(inner_prob)
            connectivity_matrix.append(row)
        return connectivity_matrix

    # scale = None
    # scale = relative
    # scale = absolute
    def create_stochastic_blockmodel_graph(self, blocks=10, size=100, self_block_connectivity=0.9, other_block_connectivity=0.1, connectivity_matrix=None, directed=False,
                                           self_edges=False, power_exp=None, scale=None, plot_stat=False):
        size = size if isinstance(size, list) else [size]
        self_block_connectivity = self_block_connectivity if isinstance(self_block_connectivity, list) else [self_block_connectivity]
        other_block_connectivity = other_block_connectivity if isinstance(other_block_connectivity, list) else [other_block_connectivity]

        num_nodes = sum([size[i % len(size)] for i in xrange(blocks)])
        if power_exp is None:
            self.print_f("Starting to create Stochastic Blockmodel Graph with {} nodes and {} blocks".format(num_nodes, blocks))
        else:
            self.print_f("Starting to create degree-corrected (alpha=" + str(power_exp) + ") Stochastic Blockmodel Graph with {} nodes and {} blocks".format(num_nodes, blocks))
        self.print_f('convert/transform probabilities')
        blocks_range = range(blocks)
        block_sizes = np.array([size[i % len(size)] for i in blocks_range])

        # create connectivity matrix of self- and other-block-connectivity
        if connectivity_matrix is None:
            connectivity_matrix = []
            self.print_f('inner conn: ' + str(self_block_connectivity) + '\tother conn: ' + str(other_block_connectivity))
            for idx in blocks_range:
                row = []
                for jdx in blocks_range:
                    if idx == jdx:
                        row.append(self_block_connectivity[idx % len(self_block_connectivity)])
                    else:
                        if scale is not None:
                            prob = other_block_connectivity[idx % len(other_block_connectivity)] / (num_nodes - block_sizes[idx]) * block_sizes[jdx]
                            if directed:
                                row.append(prob)
                            else:
                                row.append(prob / 2)
                        else:
                            row.append(other_block_connectivity[idx % len(other_block_connectivity)])
                connectivity_matrix.append(row)

        # convert con-matrix to np.array
        if connectivity_matrix is not None and isinstance(connectivity_matrix, np.matrix):
            connectivity_matrix = np.asarray(connectivity_matrix)

        # convert con-matrix to np.array
        if connectivity_matrix is not None and not isinstance(connectivity_matrix, np.ndarray):
            connectivity_matrix = np.array(connectivity_matrix)

        self.print_f('conn mat')
        printing.print_matrix(connectivity_matrix)

        if scale == 'relative' or scale == 'absolute':
            new_connectivity_matrix = []
            for i in blocks_range:
                connectivity_row = connectivity_matrix[i, :] if connectivity_matrix is not None else None
                nodes_in_src_block = block_sizes[i]
                multp = 1 if scale == 'absolute' else (nodes_in_src_block * (nodes_in_src_block - 1))
                row_prob = [(connectivity_row[idx] * multp) / (nodes_in_src_block * (nodes_in_block - 1)) for idx, nodes_in_block in enumerate(block_sizes)]
                new_connectivity_matrix.append(np.array(row_prob))
            connectivity_matrix = np.array(new_connectivity_matrix)
            self.print_f(scale + ' scaled conn mat:')
            printing.print_matrix(connectivity_matrix)

        # create nodes and store corresponding block-id
        self.print_f('insert nodes')
        vertex_to_block = []
        appender = vertex_to_block.append
        colors = self.graph.new_vertex_property("float")
        for i in xrange(blocks):
            block_size = size[i % len(size)]
            for j in xrange(block_size):
                appender((self.graph.add_vertex(), i))
                node = vertex_to_block[-1][0]
                colors[node] = i

        # create edges
        get_rand = np.random.random
        add_edge = self.graph.add_edge

        self.print_f('create edge probs')
        degree_probs = defaultdict(lambda: dict())
        for vertex, block_id in vertex_to_block:
            if power_exp is None:
                degree_probs[block_id][vertex] = 1
            else:
                degree_probs[block_id][vertex] = math.exp(power_exp * np.random.random())

        tmp = dict()
        self.print_f('normalize edge probs')
        all_prop = []
        for block_id, node_to_prop in degree_probs.iteritems():
            sum_of_block_norm = 1 / sum(node_to_prop.values())
            tmp[block_id] = {key: val * sum_of_block_norm for key, val in node_to_prop.iteritems()}
            all_prop.append(tmp[block_id].values())
        degree_probs = tmp
        if plot_stat:
            plt.clf()
            plt.hist(all_prop, bins=15)
            plt.savefig("prop_dist.png")
            plt.close('all')

        self.print_f('count edges between blocks')
        edges_between_blocks = defaultdict(lambda: defaultdict(int))
        for idx, (src_node, src_block) in enumerate(vertex_to_block):
            conn_mat_row = connectivity_matrix[src_block, :]
            for dest_node, dest_block in vertex_to_block:
                if get_rand() < conn_mat_row[dest_block]:
                    edges_between_blocks[src_block][dest_block] += 1

        self.print_f('create edges')
        for src_block, dest_dict in edges_between_blocks.iteritems():
            self.print_f(' -- Processing Block {}. Creating links to: {}'.format(src_block, dest_dict))
            for dest_block, num_edges in dest_dict.iteritems():
                self.print_f('   ++ adding {} edges to {}'.format(num_edges, dest_block))
                for i in xrange(num_edges):
                    # find src node
                    prob = np.random.random()
                    prob_sum = 0
                    src_node = None
                    for vertex, v_prob in degree_probs[src_block].iteritems():
                        prob_sum += v_prob
                        if prob_sum >= prob:
                            src_node = vertex
                            break
                    # find dest node
                    prob = np.random.random()
                    prob_sum = 0
                    dest_node = None
                    for vertex, v_prob in degree_probs[dest_block].iteritems():
                        prob_sum += v_prob
                        if prob_sum >= prob:
                            dest_node = vertex
                            break
                    if src_node is None or dest_node is None:
                        print 'Error selecting node:', src_node, dest_node
                    if self.graph.edge(src_node, dest_node) is None:
                        if self_edges or not src_node == dest_node:
                            add_edge(src_node, dest_node)
        self.graph.vertex_properties["colorsComm"] = colors
        return self.return_and_reset()

    def create_preferential_attachment(self, communities=10):
        self.graph = price_network(self.num_nodes, directed=False, c=0, gamma=1, m=1)
        self.graph.vertex_properties['colorsComm'] = community_structure(self.graph, 1000, communities)
        return self.return_and_reset()

    # add node to graph and check if node is in node_dict
    def add_node(self, node_id, further_mappings=None):
        v = self.node_id_map[node_id]
        self.graph.vp['NodeId'][v] = node_id
        if further_mappings is not None:
            assert isinstance(further_mappings, dict)
            for key, val in further_mappings.iteritems():
                self.graph.vp[key][v] = val
        return v

    def load_smw_collab_network(self, filename, communities=10):
        self.print_f("Creating Graph")
        id_prop = self.graph.new_vertex_property("int")
        self.graph.vp["label"] = self.graph.new_vertex_property("string")

        f = open(filename, "rb")
        for idx, line in enumerate(f):
            if idx % 1000 == 0:
                self.print_f("--> parsing line %d" % idx)
            split_line = line.strip("\n").split("\t")
            source_v = self.add_node(split_line[0], id_prop)
            if split_line[1] != "":
                target_v = self.add_node(split_line[1], id_prop)
                self.graph.add_edge(source_v, target_v)

        self.print_f("Detecting Communities")
        self.graph.vp['colorsComm'] = community_structure(self.graph, 1000, communities)
        remove_self_loops(self.graph)
        remove_parallel_edges(self.graph)
        return self.return_and_reset()

    @staticmethod
    def increment_neighbours(vertices, b):
        for n in vertices:
            b[int(n)] += 1

    # start creating random graph
    # NOTE:
    # If min_degree is too small, graph will be disconnected and consist of many smaller graphs!
    # This could make diffusion problematic!
    def create_random_graph(self, min_degree=2, max_degree=40, model="probabilistic", communities=10):
        # Function to sample edges between nodes!
        self.print_f('create random graph')

        def sample_k(min_val, max_val, k=None):
            accept = False
            while not accept:
                k = random.randint(min_val, max_val + 1)
                accept = random.random() < 1.0 / k
            return k

        self.graph = random_graph(self.num_nodes, lambda: sample_k(min_degree, max_degree), model=model, vertex_corr=lambda i, k: 1.0 / (1 + abs(i - k)), directed=self.directed,
                                  n_iter=100)
        self.graph.vp['colorsComm'] = community_structure(self.graph, 10000, max_degree / communities)
        return self.return_and_reset()

    # start loading  graph
    def create_karate_graph(self):
        self.graph = collection.data["karate"]
        # Removing descriptions and readme, as they screw with the GML parser of networkx!
        self.graph.gp['description'] = ''
        self.graph.gp['readme'] = ''
        # Calculating Colors and updating members
        self.graph.vp['colorsComm'] = community_structure(self.graph, 10000, 2)
        self.directed = self.graph.is_directed()
        self.num_nodes = self.graph.num_vertices()
        return self.return_and_reset()

    def loaded_post_action(self):
        self.directed = self.graph.is_directed()
        self.num_nodes = self.graph.num_vertices()
        self.print_f("Graph loaded with {} nodes and {} edges".format(self.graph.num_vertices(), self.graph.num_edges()))

    # load graph from gml
    def load_gml(self, fn):
        self.print_f("Loading GML")
        self.graph = load_graph(fn)
        self.loaded_post_action()
        return self.return_and_reset()

    # load graph from file
    def load_gt(self, fn):
        self.print_f("Loading GT")
        self.graph = load_graph(fn)
        self.loaded_post_action()
        return self.return_and_reset()

    @staticmethod
    def print_f(*args, **kwargs):
        kwargs.update({'class_name': 'GraphGenerator'})
        print_f(*args, **kwargs)


def calc_eigenvalues(graph, num_ev=100):
    num_ev = min(100, num_ev)
    print_f("Extracting adjacency matrix!")
    adj_mat = adjacency(graph, weight=None)
    print_f("Starting calculation of {} Eigenvalues".format(num_ev))
    evals_large_sparse, evecs_large_sparse = largest_eigsh(adj_mat, num_ev * 2, which='LM')
    print_f("Finished calculating Eigenvalues")
    weights = sorted([float(x) for x in evals_large_sparse], reverse=True)[:num_ev]
    graph.gp["top_eigenvalues"] = graph.new_graph_property("vector<float>", weights)
    return graph


def cleanup_graph(graph, largest_comp=True, parallel_edges=False, self_loops=False):
    if largest_comp:
        reduce_to_largest_component(graph)
    if not parallel_edges:
        remove_parallel_edges(graph)
    if not self_loops:
        remove_self_loops(graph)
    return graph


def reduce_to_largest_component(graph):
    print_f("Reducing graph to largest connected component!")
    l = label_largest_component(graph)
    graph = GraphView(graph, vfilt=l)
    graph.purge_vertices(in_place=True)
    return graph


def calc_vertex_properties(graph, max_iter_ev=1000, max_iter_hits=1000):
    print_f("Calculating PageRank")
    graph.vp["pagerank"] = pagerank(graph)

    print_f("Calculating Clustering Coefficient")
    graph.vp["clustercoeff"] = local_clustering(graph)

    print_f("Calculating Eigenvector Centrality")
    ev, ev_centrality = eigenvector(graph, weight=None, max_iter=max_iter_ev)
    graph.vp["evcentrality"] = ev_centrality

    print_f("Calculating HITS")
    eig, authorities, hubs = hits(graph, weight=None, max_iter=max_iter_hits)
    graph.vp["authorities"] = authorities
    graph.vp["hubs"] = hubs

    print_f("Calculating Degree Property Map")
    graph.vertex_properties["degree"] = graph.degree_property_map("total")
    return graph

# plot graph to file
# TODO: check if code of GraphAnimator can be used
'''
def draw_graph(run=0, min_nsize=None, max_nsize=None, size_property=None, file_format="png", output_size=4000, appendix="", label_color="orange", draw_labels=False):
    if size_property == "degree":
        size_map = self.graph.new_vertex_property('float')
        for v in self.graph.vertices():
            size_map[v] = v.out_degree() + v.in_degree()

    if not (isinstance(size_property, int) or isinstance(size_property, float), isinstance(size_property, str)):
        size_map = size_property

    if min_nsize is None or max_nsize is None:
        val = math.sqrt(self.graph.num_vertices()) / self.graph.num_vertices() * (output_size / 4)
        mi = val if min_nsize is None else min_nsize
        ma = val * 2 if max_nsize is None else max_nsize

    if draw_labels:
        try:
            labels = self.graph.vertex_properties["label"]
        except:
            ls = self.graph.new_vertex_property("int")
            for ndx, n in enumerate(self.graph.vertices()):
                ls[n] = str(ndx)
            self.graph.vertex_properties["label"] = ls
            labels = self.graph.vertex_properties["label"]
    else:
        labels = self.graph.new_vertex_property("string")

    if size_property is not None:
        try:
            self.draw_specific_graph(self.graph.vertex_properties["colorsComm"], "communities", output_size, label_color, "black", mi, ma, labels, run, appendix, file_format, label_pos=0, v_size_prop_map=size_map)
        except Exception as e:
            self.debug_msg("\x1b[31m" + str(e) + "\x1b[00m")
    else:
        try:
            self.draw_specific_graph(self.graph.vertex_properties["colorsComm"], "communities", output_size, label_color, "black", mi, ma, labels, run, appendix, file_format, label_pos=0)
        except Exception as e:
            self.debug_msg("\x1b[31m" + str(e) + "\x1b[00m")

        try:
            self.draw_specific_graph(self.graph.vertex_properties["colorsMapping"], "mapping", output_size, label_color, "black", mi, ma, labels, run, appendix, file_format, label_pos=0)
        except Exception as e:
            self.debug_msg("\x1b[31m" + str(e) + "\x1b[00m")

        try:
            self.draw_specific_graph(self.graph.vertex_properties["colorsActivity"], "activity", output_size, label_color, "black", mi, ma, labels, run, appendix, file_format, label_pos=0)
        except Exception as e:
            self.debug_msg("\x1b[31m" + str(e) + "\x1b[00m")
'''

'''
def draw_specific_graph(self, colors, color_type_in_outfname, output_size, label_color, edge_color, mi, ma, labels, run, appendix, file_format, label_pos=0, pos=None, v_size_prop_map=None):
    if pos is None:
        try:
            pos = self.graph.vertex_properties["pos"]
        except KeyError:
            self.debug_msg("  --> Calculating SFDP layout positions!")
            pos = sfdp_layout(self.graph)
            self.graph.vertex_properties["pos"] = pos
            self.debug_msg("  --> Done!")

    if v_size_prop_map is None:
        try:
            v_size_prop_map = self.graph.vertex_properties["activity"]
        except KeyError:
            self.add_node_weights(0.0, 0.1)
            v_size_prop_map = self.graph.vertex_properties["activity"]

    graph_draw(self.graph, vertex_fill_color=colors, edge_color=edge_color, output_size=(output_size, output_size), vertex_text_color=label_color, pos=pos, vertex_size=(prop_to_size(v_size_prop_map, mi=mi, ma=ma)), vertex_text=labels, vertex_text_position=label_pos,
               output=config.graph_dir + "{}_{}_run_{}{}.{}".format(self.graph_name, color_type_in_outfname, run, appendix, file_format))
'''

'''
    def collect_colors(self, alpha=0.75):
        self.debug_msg("Collecting Colors for Graphs")
        norm = matplotlib.colors.Normalize(vmin=0, vmax=self.graph.num_vertices())
        cmap = plt.get_cmap('gist_rainbow')
        norma = matplotlib.colors.Normalize(vmin=0.0, vmax=1.0)
        camap = plt.get_cmap("Blues")
        m = matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap)
        ma = matplotlib.cm.ScalarMappable(norm=norma, cmap=camap)

        clist = self.graph.new_vertex_property("vector<float>")
        calist = self.graph.new_vertex_property("vector<float>")
        for x in xrange(self.graph.num_vertices()):
            # color for node id
            l = list(m.to_rgba(x))
            l[3] = alpha
            node = self.graph.vertex(x)
            clist[node] = l

            # color for activity / weight of node
            weight = self.graph.vp["activity"][node]
            la = list(ma.to_rgba(weight))
            la[3] = alpha
            calist[node] = la
        self.graph.vp["colorsMapping"] = clist
        self.graph.vp["colorsActivity"] = calist
        self.graph.vp['colorsComm'] = community_structure(self.graph, 1000, 10)
'''
