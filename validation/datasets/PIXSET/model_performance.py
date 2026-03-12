import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.metrics import classification_report, confusion_matrix, precision_recall_fscore_support, accuracy_score

import plotly.graph_objects as go
import dash
from dash import dcc, html, Input, Output
import dash_bootstrap_components as dbc
import warnings

warnings.filterwarnings("ignore", category=RuntimeWarning)

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = "Prediction Methods Comparison"

# ✅ Adapte ici le chemin vers le dossier contenant 'adj' et 'no_adj'
BASE_PATH = Path("C:/Users/svictor/Documents/PIXSET/output")
AVAILABLE_DIRS = sorted([f.name for f in BASE_PATH.iterdir() if f.is_dir()])

# === Méthodes de calcul ===

def compute_method_1(results_root: Path):
    labels = [True, False]
    pedestrian_level_true = []
    pedestrian_level_pred = []

    csv_files = list(results_root.glob("*.csv"))

    for csv_path in csv_files:
        df = pd.read_csv(csv_path)
        if df.empty:
            continue
        if "crossing" not in df.columns or "prediction" not in df.columns or "pedestrian_id" not in df.columns:
            continue

        # Convertir en booléen
        df["crossing"] = df["crossing"].astype(str).str.lower() == "true"
        df["prediction"] = df["prediction"].astype(str).str.lower() == "true"

        # Parcours par piéton
        for pid, group in df.groupby("pedestrian_id"):
            crossing = group["crossing"]
            prediction = group["prediction"]

            # 1. TP: crossing & prediction True sur la même frame
            if ((crossing) & (prediction)).any():
                pedestrian_level_true.append(True)
                pedestrian_level_pred.append(True)

            # 2. TN: crossing == False partout & prediction == False partout
            elif not crossing.any() and not prediction.any():
                pedestrian_level_true.append(False)
                pedestrian_level_pred.append(False)

            # 3. FN: crossing == True quelque part, mais jamais de pred True en même temps
            elif crossing.any() and not ((crossing) & (prediction)).any():
                pedestrian_level_true.append(True)
                pedestrian_level_pred.append(False)

            # 4. FP: crossing == False partout, mais au moins une pred == True
            elif not crossing.any() and prediction.any():
                pedestrian_level_true.append(False)
                pedestrian_level_pred.append(True)

            # Cas anormal ?
            else:
                print(f"[WARN] Cas non couvert pour pedestrian_id {pid}")

    # Générer les métriques
    report = classification_report(pedestrian_level_true, pedestrian_level_pred, labels=labels, zero_division=0, output_dict=True)
    report['accuracy'] = accuracy_score(pedestrian_level_true, pedestrian_level_pred)
    report_str = classification_report(pedestrian_level_true, pedestrian_level_pred, labels=labels, zero_division=0)
    cm = confusion_matrix(pedestrian_level_true, pedestrian_level_pred, labels=labels)
    return report, report_str, cm






def compute_method_2(results_root: Path):
    all_true_labels = []
    all_pred_labels = []

    # Liste tous les CSV directement dans results_root (plus de set*/ !)
    csv_files = list(results_root.glob("*.csv"))
    for csv_path in csv_files:
        df = pd.read_csv(csv_path)
        if df.empty:
            continue
        if "crossing" not in df.columns or "prediction" not in df.columns:
            continue
        true = df["crossing"].astype(str).tolist()
        pred = df["prediction"].astype(str).tolist()
        all_true_labels.extend(true)
        all_pred_labels.extend(pred)

    report = classification_report(all_true_labels, all_pred_labels, labels=['True', 'False'], zero_division=0, output_dict=True)
    report['accuracy'] = accuracy_score(all_true_labels, all_pred_labels)
    report_str = classification_report(all_true_labels, all_pred_labels, labels=['True', 'False'], zero_division=0)
    cm = confusion_matrix(all_true_labels, all_pred_labels, labels=['True', 'False'])
    return report, report_str, cm


def create_confusion_figure(cm, title):
    labels = [True, False]
    cm = np.array(cm)
    if cm.shape != (2, 2):
        cm = np.zeros((2, 2), dtype=int)
    text_labels = [[str(cm[i][j]) for j in range(2)] for i in range(2)]
    fig = go.Figure(data=go.Heatmap(
        z=cm,
        x=labels,
        y=labels,
        colorscale='Blues',
        text=text_labels,
        texttemplate="%{text}",
        showscale=True,
        hovertemplate="Actual: %{y}<br>Predicted: %{x}<br>Count: %{z}<extra></extra>",
        xgap=2,
        ygap=2
    ))
    fig.update_layout(
        title=title,
        xaxis_title="Predicted",
        yaxis_title="Actual",
        yaxis=dict(autorange="reversed"),
        height=400,
        margin=dict(t=50, b=50, l=50, r=50)
    )
    return fig

def compute_metrics_distribution(df, variable):
    classes = [True, False]
    if variable == 'taille_cm':
        bin_size = 5
        df[f"{variable}_bin"] = pd.cut(df[variable], bins=np.arange(df[variable].min(), df[variable].max() + bin_size, bin_size))
        var_col = f"{variable}_bin"
    elif variable in ['ego_speed_mps', 'dist_m']:
        bin_size = 5
        df[f"{variable}_bin"] = pd.cut(df[variable], bins=np.arange(df[variable].min(), df[variable].max() + bin_size, bin_size))
        var_col = f"{variable}_bin"
    else:
        var_col = variable

    metric_values = {'precision': {c: [] for c in classes},
                     'recall': {c: [] for c in classes},
                     'f1_score': {c: [] for c in classes}}
    counts = []
    categories = []

    for name, group in df.groupby(var_col):
        if pd.isna(name):
            continue
        categories.append(str(name))
        counts.append(len(group))
        y_true = group["crossing"].astype(str)
        y_pred = group["prediction"].astype(str)
        precision, recall, f1, _ = precision_recall_fscore_support(y_true, y_pred, labels=classes, zero_division=0)
        for i, c in enumerate(classes):
            metric_values['precision'][c].append(precision[i])
            metric_values['recall'][c].append(recall[i])
            metric_values['f1_score'][c].append(f1[i])
    return categories, metric_values, counts

def create_metric_bar(metric_values, categories, metric_name, variable):
    fig = go.Figure()
    for cls in metric_values:
        fig.add_trace(go.Bar(x=categories, y=metric_values[cls], name=f"Class {cls}"))
    fig.update_layout(
        title=f"{metric_name.title()} by {variable}",
        xaxis_title=variable,
        yaxis_title=metric_name.title(),
        barmode='group',
        height=400,
        margin=dict(t=50, b=80),
        xaxis_tickangle=-45,
        xaxis_tickfont_size=10
    )
    return fig

def create_distribution_bar(categories, counts, variable):
    fig = go.Figure(data=go.Bar(x=categories, y=counts, marker_color='indianred'))
    fig.update_layout(
        title=f"Sample Count for {variable}",
        xaxis_title=variable,
        yaxis_title="Count",
        height=400,
        margin=dict(t=50, b=80),
        xaxis_tickangle=-45,
        xaxis_tickfont_size=10
    )
    return fig

def create_global_metrics_comparison(report_1, report_2):
    metrics = ['precision', 'recall', 'f1-score', 'accuracy']
    a_vals = [report_1['macro avg']['precision'], report_1['macro avg']['recall'], report_1['macro avg']['f1-score'], report_1['accuracy']]
    b_vals = [report_2['macro avg']['precision'], report_2['macro avg']['recall'], report_2['macro avg']['f1-score'], report_2['accuracy']]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=metrics, y=b_vals, name='Frame by Frame', marker_color='blue'))
    fig.add_trace(go.Bar(x=metrics, y=a_vals, name='Pedestrian Decision', marker_color='green'))
    fig.update_layout(title="Global Metrics Comparison", barmode='group', height=400, margin=dict(t=50, b=50))
    return fig

# === Layout ===

app.layout = dbc.Container([
    html.H1("Prediction Methods Comparison", className="my-4"),

    dbc.Row([
        dbc.Col([
            html.Label("Select a result folder:"),
            dcc.Dropdown(id="folder-selector",
                         options=[{"label": d, "value": d} for d in AVAILABLE_DIRS],
                         value=AVAILABLE_DIRS[0] if AVAILABLE_DIRS else None,
                         clearable=False),
        ], width=6),
    ]),

    html.Hr(),

    dbc.Card([
        dbc.CardHeader(html.H4("Global Metrics Comparison")),
        dbc.CardBody([
            dcc.Loading(id="loading-global-graphs", children=[
                html.Div(id="global-graphs-container")
            ], type="circle", color="#0d6efd")
        ])
    ], className="mb-4"),

    dbc.Tabs(
        id="tabs",
        active_tab="weather",
        children=[
            dbc.Tab(label="weather", tab_id="weather"),
            dbc.Tab(label="taille_cm", tab_id="taille_cm"),
            dbc.Tab(label="ego_speed_mps", tab_id="ego_speed_mps"),
            dbc.Tab(label="dist_m", tab_id="dist_m"),
        ],
    ),

    html.Div(id="tab-content", className="mt-3"),
], fluid=True)

# === Callbacks ===

@app.callback(
    Output("global-graphs-container", "children"),
    Input("folder-selector", "value")
)
def update_global_graphs(selected_folder):
    if not selected_folder:
        return "Please select a folder."

    folder_path = BASE_PATH / selected_folder
    report_2, report_str_2, cm_2 = compute_method_2(folder_path)
    report_1, report_str_1, cm_1 = compute_method_1(folder_path)
    fig_1 = create_confusion_figure(cm_1, "Confusion Matrix - Pedestrian Decision")
    fig_2 = create_confusion_figure(cm_2, "Confusion Matrix - Frame by Frame")
    fig_compare = create_global_metrics_comparison(report_1, report_2)

    return dbc.Container([
        dbc.Row([
            dbc.Col([dcc.Graph(figure=fig_compare)], width=12)
        ], className="mb-4"),

        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H5("Pedestrian Decision - Classification Report", className="card-title"),
                        html.Pre(report_str_1, style={"whiteSpace": "pre-wrap", "fontSize": "12px"}),
                        dcc.Graph(figure=fig_1)
                    ])
                ])
            ], width=6),

            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H5("Frame by Frame - Classification Report", className="card-title"),
                        html.Pre(report_str_2, style={"whiteSpace": "pre-wrap", "fontSize": "12px"}),
                        dcc.Graph(figure=fig_2)
                    ])
                ])
            ], width=6)
        ])
    ])

@app.callback(
    Output("tab-content", "children"),
    Input("tabs", "active_tab"),
    Input("folder-selector", "value"),
)
def render_tab_content(active_tab, selected_folder):
    if not selected_folder:
        return "Please select a folder."
    if not active_tab:
        return "Please select a tab."

    folder_path = BASE_PATH / selected_folder
    all_dfs = []
    csv_files = list(folder_path.glob("*.csv"))
    for csv_path in csv_files:
        df = pd.read_csv(csv_path)
        if not df.empty and "crossing" in df.columns and "prediction" in df.columns:
            all_dfs.append(df)
    if not all_dfs:
        return "No data found."

    full_df = pd.concat(all_dfs, ignore_index=True)
    categories, metric_values, counts = compute_metrics_distribution(full_df, active_tab)

    graphs_list = []
    for metric_name in ['precision', 'recall', 'f1_score']:
        fig = create_metric_bar(metric_values[metric_name], categories, metric_name, active_tab)
        graphs_list.append((metric_name, fig))

    accuracy_per_bin = []
    for name, group in full_df.groupby(active_tab if active_tab == 'weather' else f"{active_tab}_bin"):
        if pd.isna(name):
            continue
        y_true = group["crossing"].astype(str)
        y_pred = group["prediction"].astype(str)
        acc = (y_true == y_pred).mean()
        accuracy_per_bin.append(acc)
    fig_acc = go.Figure(data=go.Bar(x=categories, y=accuracy_per_bin, marker_color='purple'))
    fig_acc.update_layout(title=f"Accuracy by {active_tab}", xaxis_title=active_tab, yaxis_title="Accuracy", height=400,
                          margin=dict(t=50, b=80), xaxis_tickangle=-45, xaxis_tickfont_size=10)
    graphs_list.append(('accuracy', fig_acc))

    fig_dist = create_distribution_bar(categories, counts, active_tab)
    graphs_list.append(('dist', fig_dist))

    return [
        dcc.Graph(figure=fig, id=f"graph-{selected_folder}-{active_tab}-{metric_name}")
        for metric_name, fig in graphs_list
    ]

if __name__ == "__main__":
    app.run(debug=True)
