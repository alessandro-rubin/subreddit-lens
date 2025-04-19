import pandas as pd
import networkx as nx
import plotly.graph_objects as go
import numpy as np
from scipy.stats import gaussian_kde
from scipy.spatial.distance import jensenshannon


def get_parent_author_username(df:pd.DataFrame):
    """parent comment author username"""
    id_to_author = df.set_index('id')['author'].to_dict()
    df['parent_author'] = df['parent_id'].str.split('_').str[1].map(id_to_author)


def extract_interaction_graph(comment_df:pd.DataFrame):
    """Creates a user interaction DiGraph from a reddit dataframe, where each node is a user
    and the weight of the edge ('user_a', 'user_b') is the number of replies by user_a to comments of user_b"""

    user_interactions = comment_df.groupby(['author','parent_author']).agg(**{'count':('id','count')}).reset_index()
    G=nx.DiGraph()
    G.add_edges_from([a for a in zip(user_interactions['author'],user_interactions['parent_author'],[{'weight': c} for c in user_interactions['count'] ])])

    return G

def create_nx_graph(df:pd.DataFrame):
    G=nx.DiGraph()
    G.add_nodes_from(df['id'])
    G.add_nodes_from(df['link_id'].drop_duplicates().str.split('_').str[1])
    G.add_edges_from([a for a in zip(df['id'],df['parent_id'].str.split('_').str[1])])
    return G

def symmetrize_graph(G:nx.DiGraph):
    G_sym = nx.Graph()
    for u, v, data in G.edges(data=True):
        weight = data.get('weight', 1)  # Default weight = 1 if missing

        # Add edge with combined weights if it exists in the reverse direction
        if G.has_edge(v, u):
            reverse_weight = G[v][u].get('weight', 1)
            total_weight = weight + reverse_weight
            delta = weight - reverse_weight
        else:
            total_weight = weight
            delta = weight

        G_sym.add_edge(u, v, weight=total_weight,delta=delta)
    return G_sym

def js_similarity(densities:dict):
    item_list =densities.keys()
    dim = len(densities.keys())
    similarity_matrix = np.zeros((dim, dim))

    for i, i1 in enumerate(item_list):
        for j, j1 in enumerate(item_list):
            # Compute Jensen-Shannon divergence (symmetric and bounded)
            js_divergence = jensenshannon(densities[i1], densities[j1])
            # Convert to similarity (higher values mean more similar)
            similarity_matrix[i, j] = 1 - js_divergence
    return similarity_matrix

def compute_posting_habists_pdf(df:pd.DataFrame,author_list,x_grid):
    df['created_dt']=pd.to_datetime(df['created_utc'], unit='s')
    df['creaed_hour']=df['created_dt'].dt.hour
    author_densities={}
    for author in author_list:
        # Extract hours for current author
        author_hours = pd.to_datetime(df[df['author'] == author]['created_utc'], unit='s').dt.hour
        
        # Create mirrored data for periodic boundary conditions
        mirrored_hours = np.concatenate([author_hours - 24, author_hours, author_hours + 24])
        
        # Calculate KDE with mirrored data
        kde = gaussian_kde(mirrored_hours,bw_method=.05)
        density = kde.evaluate(x_grid) * 3  # Multiply by 3 to account for mirrored data
        author_densities[author] = density
    return author_densities

def generate_graph_figure(G:nx.DiGraph):
    pos=nx.get_node_attributes(G, "pos")
    
    # Edge traces
    edge_trace = []
    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_trace.append(go.Scatter(
            x=[x0, x1, None],
            y=[y0, y1, None],
            mode='lines',
            line=dict(width=2, color='black'),
            hoverinfo='none'
        ))
    hovertext=[f'Node {n}\nNeighbor={str(list(G.neighbors(n)))}' for n in G.nodes()]
    # Node trace
    connectivity=([len([x for x in G.neighbors(n)] )for n in G.nodes])
    node_trace = go.Scatter(
        x=[pos[n][0] for n in G.nodes()],
        y=[pos[n][1] for n in G.nodes()],
        #text=[f'{n}' for n in G.nodes()],
        mode='markers+text',
        hovertext=hovertext,
        hoverinfo='text',
        marker=dict(size=10, color=connectivity)
    )
    
    # Return the figure
    return go.Figure(data=edge_trace + [node_trace],
                    layout=go.Layout(
                        showlegend=False,
                        hovermode='closest',
                        margin=dict(b=0, l=0, r=0, t=0),
                        xaxis=dict(showgrid=False, zeroline=False),
                        yaxis=dict(showgrid=False, zeroline=False)))