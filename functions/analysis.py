import pandas as pd
import networkx as nx
import plotly.graph_objects as go


def get_parent_author_username(df:pd.DataFrame):
    "parent comment author username"
    id_to_author = df.set_index('id')['author'].to_dict()
    df['parent_author'] = df['parent_id'].str.split('_').str[1].map(id_to_author)


def extract_interaction_graph(comment_df:pd.DataFrame):
    "Creates a user interaction DiGraph from a reddit "
    user_interactions = comment_df.groupby(['author','parent_author']).agg(**{'count':('id','count')}).reset_index()
    G=nx.DiGraph()
    G.add_edges_from([a for a in zip(user_interactions['author'],user_interactions['parent_author'],[{'weight': c} for c in user_interactions['count'] ])])

    return G

def create_nx_graph(df:pd.DataFrame):
    G=nx.DiGraph()
    G.add_nodes_from(df['id'])
    G.add_nodes_from(df['link_id'].drop_duplicates().str.split('_').str[1])
    G.add_edges_from([a for a in zip(df['id'],df['parent_id'].drop_duplicates().str.split('_').str[1])])
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