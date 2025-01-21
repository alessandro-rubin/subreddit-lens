import pandas as pd
import networkx as nx
import plotly.graph_objects as go

def create_nx_graph(df:pd.DataFrame):
    G=nx.DiGraph()
    G.add_nodes_from(df['id'])
    G.add_nodes_from(df['link_id'].drop_duplicates().str.split('_').str[1])
    G.add_edges_from([a for a in zip(df['id'],df['parent_id'].drop_duplicates().str.split('_').str[1])])
    return G

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
    node_trace = go.Scatter(
        x=[pos[n][0] for n in G.nodes()],
        y=[pos[n][1] for n in G.nodes()],
        text=[f'Node {n}' for n in G.nodes()],
        mode='markers+text',
        hovertext=hovertext,
        hoverinfo='text',
        marker=dict(size=10, color='blue')
    )
    
    # Return the figure
    return go.Figure(data=edge_trace + [node_trace],
                    layout=go.Layout(
                        showlegend=False,
                        hovermode='closest',
                        margin=dict(b=0, l=0, r=0, t=0),
                        xaxis=dict(showgrid=False, zeroline=False),
                        yaxis=dict(showgrid=False, zeroline=False)))