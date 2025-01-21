import pandas as pd
import networkx as nx

def create_nx_graph(df:pd.DataFrame):
    G=nx.DiGraph()
    G.add_nodes_from(df['id'])
    G.add_nodes_from(df['link_id'].drop_duplicates().str.split('_').str[1])
    G.add_edges_from([a for a in zip(df['id'],df['parent_id'].drop_duplicates().str.split('_').str[1])])
    return G