from __future__ import print_function

###########
# imports #
###########

import numpy as np
from sklearn import manifold, datasets
from sklearn.neighbors import kneighbors_graph
from scipy.spatial.distance import cdist
from scipy.cluster import hierarchy
from scipy.stats import pearsonr
import ot
import networkx as nx
from textwrap import wrap
import time
import sys
import zipfile

#############
# functions #
#############

def setup_for_OT_reconstruction(dge, locations, num_neighbors_source = 5, num_neighbors_target = 5):
    start_time = time.time()
    print ('Setting up for reconstruction ... ', end='', flush=True)

    # Shortest paths matrices at target and source spaces
    num_neighbors_target = num_neighbors_target # number of neighbors for nearest neighbors graph at target
    A_locations = kneighbors_graph(locations, num_neighbors_target, mode='connectivity', include_self=True)
    G_locations = nx.from_scipy_sparse_matrix(A_locations)
    sp_locations = nx.floyd_warshall_numpy(G_locations)
    num_neighbors_source = num_neighbors_source # number of neighbors for nearest neighbors graph at source
    A_expression = kneighbors_graph(dge, num_neighbors_source, mode='connectivity', include_self=True)
    G_expression = nx.from_scipy_sparse_matrix(A_expression)
    sp_expression = nx.floyd_warshall_numpy(G_expression)
    sp_expression_max = np.nanmax(sp_expression[sp_expression != np.inf])
    sp_expression[sp_expression > sp_expression_max] = sp_expression_max #set threshold for shortest paths

    # Set normalized cost matrices based on shortest paths matrices at target and source spaces
    cost_locations = sp_locations / sp_locations.max()
    cost_locations -= np.mean(cost_locations)
    cost_expression = sp_expression / sp_expression.max()
    cost_expression -= np.mean(cost_expression)

    print ('done (', round(time.time()-start_time, 2), 'seconds )')
    return cost_expression, cost_locations

def find_spatial_archetypes(num_clusters, sdge):
    """Clusters the expression data and finds gene archetypes. Current
    implementation is based on hierarchical clustering with the Ward method.
    Returns the archetypes, the gene sets (clusters) and the Pearson 
    correlations of every gene with respect to each archetype."""
    print ('Finding gene archetypes ... ', flush=True, end='')
    clusters = hierarchy.fcluster(hierarchy.ward(sdge),
                                  num_clusters,
                                  criterion='maxclust')
    arch_comp = lambda x : np.mean(sdge[np.where(clusters == x)[0], :], axis=0)
    archetypes = np.array([arch_comp(xi) for xi in range(1, num_clusters+1)])
    gene_corrs = np.array([])
    for gene in range(len(sdge)):
        gene_corrs = np.append(gene_corrs, pearsonr(sdge[gene, :],
                                                    archetypes[clusters[gene]-1, :])[0])
    print ('done')
    
    return archetypes, clusters, gene_corrs


def get_genes_from_spatial_archetype(sdge, gene_names, archetypes, archetype, pval_threshold=0):
    """Returns a list of genes which are the best representatives of the archetype
    archetypes       -- the archetypes output of find_spatial_archetypes
    archetype        -- a number denoting the archetype
    pvalue_threshold -- the pvalue returned from the pearsonr function"""
    # Classify all genes and return the most significant ones
    all_corrs = np.array([])
    all_corrs_p = np.array([])
    
    for g in range(len(sdge)):
        all_corrs = np.append(all_corrs, pearsonr(sdge[g, :], archetypes[archetype, :])[0])
        all_corrs_p = np.append(all_corrs_p, pearsonr(sdge[g, :], archetypes[archetype, :])[1])
    indices = np.where(all_corrs_p[all_corrs > 0] <= pval_threshold)[0]
    if len(indices) == 0:
        print ('No genes with significant correlation were found at the current p-value threshold.')
        return None
    genes = gene_names[all_corrs > 0][indices]
    
    return genes


def find_spatially_related_genes(sdge, gene_names, archetypes, gene, pval_threshold=0):
    """Given a gene, find other genes which correlate well spatially.
    gene           -- the index of the gene to be queried
    pval_threshold -- the pvalue returned from the pearsonr function"""
    # First find the archetype of the gene
    arch_corrs = np.array([])
    for archetype in range(len(archetypes)):
        arch_corrs = np.append(arch_corrs, pearsonr(sdge[gene, :], archetypes[archetype, :])[0])
    if np.max(arch_corrs) < 0.7:
        print ('No significant correlation between the gene and the spatial archetypes was found.')
        return None
    archetype = np.argmax(arch_corrs)

    return get_genes_from_spatial_archetype(sdge, gene_names, archetypes, archetype,
                                            pval_threshold=pval_threshold)
    
