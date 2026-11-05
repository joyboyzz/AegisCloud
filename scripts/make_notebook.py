#!/usr/bin/env python3
"""Build the standalone, *unexecuted* Colab sequence-model comparison notebook."""
from pathlib import Path
import nbformat as nbf

ROOT = Path(__file__).resolve().parent.parent
n = nbf.v4.new_notebook()
def md(s): n.cells.append(nbf.v4.new_markdown_cell(s))
def code(s): n.cells.append(nbf.v4.new_code_cell(s))

md('''# AegisCloud: temporal LSTM / 1D-CNN comparison

**Exploratory notebook — results are not precomputed.** Upload
`artifacts/sessions_train.csv` from the AegisCloud project when prompted.
The dataset is synthetic, and the positive class is **session success**, not an attack.

The notebook uses a chronological 70/15/15 split; per-user statistics, feature
vocabulary and scaling are fitted on the training split only. It compares sequence
models with tabular baselines on validation data and evaluates the selected model
once on the final test split. This experiment is separate from the deployed Flask
model and must be run before claiming LSTM or CNN results.''')
code('''# Colab only: install missing dependencies. Do not run this cell in a restricted runtime.
%pip -q install tensorflow scikit-learn pandas matplotlib''')
code('''import os, random
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             f1_score, roc_auc_score, confusion_matrix)
import tensorflow as tf
from tensorflow.keras import layers, models, callbacks
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)
print('TensorFlow:', tf.__version__)''')
md('''## 1. Load the synthetic corpus''')
code('''PATH = 'sessions_train.csv'
if not os.path.exists(PATH):
    try:
        from google.colab import files
        files.upload()
    except ImportError:
        raise FileNotFoundError('Put sessions_train.csv next to this notebook')
if not os.path.exists(PATH):
    raise FileNotFoundError('Please upload a file named sessions_train.csv')
df = pd.read_csv(PATH).sort_values('timestamp', kind='stable').reset_index(drop=True)
if len(df) < 100:
    raise ValueError('The experiment requires at least 100 session rows.')
print('Sessions:', len(df), 'success fraction:', (df['outcome'] == 'success').mean())
display(df.head(3))''')
md('''## 2. Split chronologically, then fit the feature preparation

Validation and test rows do **not** contribute to the user baselines, category
vocabulary or scaler. Unseen users fall back to the training-wide mean and standard
deviation.''')
code('''n = len(df)
a, b = int(.70*n), int(.85*n)
train, valid, test = df.iloc[:a].copy(), df.iloc[a:b].copy(), df.iloc[b:].copy()
y_all = (df['outcome'].str.lower() == 'success').astype(int).to_numpy()
y_tr, y_va, y_te = y_all[:a], y_all[a:b], y_all[b:]

user_stats = train.groupby('user_id')['session_duration_sec'].agg(['mean', 'std'])
global_mean = float(train['session_duration_sec'].mean())
global_std = float(train['session_duration_sec'].std())
if not np.isfinite(global_std) or global_std <= 0:
    global_std = 1.0
NUM = ['resource_sensitivity', 'session_duration_sec', 'bytes_transferred_mb',
       'failed_attempts', 'request_rate_per_min', 'is_new_device', 'geo_mismatch',
       'hour_of_day', 'anomaly_flag']
DERIVED = ['duration_z', 'duration_absdev', 'off_hours', 'velocity_score',
           'velocity_excess', 'auth_strength', 'novelty_score', 'interaction_risk']
CAT = ['cloud_provider', 'auth_method', 'session_type', 'resource_accessed']
STRENGTH = {'password': .15, 'certificate': .55, 'mfa': .75,
            'biometric': .9, 'hardware_key': 1.0}

def engineer(d):
    d = d.copy()
    mean = d['user_id'].map(user_stats['mean']).fillna(global_mean)
    std = d['user_id'].map(user_stats['std']).replace(0, np.nan).fillna(global_std)
    d['duration_z'] = ((d['session_duration_sec'] - mean) / std).clip(-4, 4)
    d['duration_absdev'] = (mean - d['session_duration_sec']).abs() / 2000
    d['off_hours'] = ((d['hour_of_day'] < 8) | (d['hour_of_day'] > 20)).astype(int)
    d['velocity_score'] = np.log1p(d['request_rate_per_min'].clip(lower=0))
    d['velocity_excess'] = (d['velocity_score'] - np.log1p(8)).clip(lower=0)
    d['auth_strength'] = d['auth_method'].map(STRENGTH).fillna(.15)
    d['novelty_score'] = d['is_new_device'] + d['geo_mismatch']
    d['interaction_risk'] = (d['novelty_score'] * (1 - d['auth_strength'])
                              + .5 * d['failed_attempts'] * d['off_hours'])
    cats = pd.get_dummies(d[CAT], columns=CAT, prefix_sep='=')
    return pd.concat([d[NUM + DERIVED], cats], axis=1).astype('float32')

Xtr = engineer(train)
Xva = engineer(valid).reindex(columns=Xtr.columns, fill_value=0)
Xte = engineer(test).reindex(columns=Xtr.columns, fill_value=0)
scaler = StandardScaler().fit(Xtr)
Xall_scaled = scaler.transform(pd.concat([Xtr, Xva, Xte], axis=0)).astype('float32')
print('Train / validation / test:', len(Xtr), len(Xva), len(Xte))
print('Training-fitted features:', len(Xtr.columns))''')
md('''## 3. Per-user sequences

Each sample contains the current event and up to four **earlier** events for the same
user. Earlier validation/test events may be observed as context, but never as labels;
no future event is used. Zero-padding corresponds to the training mean after scaling.''')
code('''from collections import defaultdict, deque
SEQ = 5
histories = defaultdict(lambda: deque(maxlen=SEQ))
seqs = np.zeros((len(df), SEQ, Xall_scaled.shape[1]), dtype='float32')
for i, uid in enumerate(df['user_id']):
    histories[uid].append(Xall_scaled[i])
    history = np.asarray(histories[uid], dtype='float32')
    seqs[i, -len(history):, :] = history
Xs_tr, Xs_va, Xs_te = seqs[:a], seqs[a:b], seqs[b:]
print('Sequence tensors:', Xs_tr.shape, Xs_va.shape, Xs_te.shape)
counts = np.bincount(y_tr, minlength=2)
if min(counts) == 0:
    raise ValueError('Both success and failure labels are required in training.')
class_weights = {i: float(len(y_tr) / (2 * counts[i])) for i in range(2)}
print('Class weights:', class_weights)''')
md('''## 4. LSTM and 1D-CNN training''')
code('''def build_lstm(shape):
    m = models.Sequential([layers.Input(shape=shape), layers.LSTM(64),
                           layers.Dropout(.3), layers.Dense(32, activation='relu'),
                           layers.Dense(1, activation='sigmoid')])
    m.compile(optimizer='adam', loss='binary_crossentropy',
              metrics=['accuracy', tf.keras.metrics.AUC(name='auc')])
    return m

def build_cnn(shape):
    m = models.Sequential([layers.Input(shape=shape),
                           layers.Conv1D(64, 3, padding='same', activation='relu'),
                           layers.Conv1D(32, 3, padding='same', activation='relu'),
                           layers.GlobalMaxPooling1D(), layers.Dropout(.3),
                           layers.Dense(32, activation='relu'),
                           layers.Dense(1, activation='sigmoid')])
    m.compile(optimizer='adam', loss='binary_crossentropy',
              metrics=['accuracy', tf.keras.metrics.AUC(name='auc')])
    return m

def early_stop():
    return callbacks.EarlyStopping(monitor='val_loss', patience=4, restore_best_weights=True)

lstm = build_lstm((SEQ, Xs_tr.shape[2]))
hist_lstm = lstm.fit(Xs_tr, y_tr, validation_data=(Xs_va, y_va), epochs=30,
                     batch_size=128, class_weight=class_weights,
                     callbacks=[early_stop()], verbose=2)
cnn = build_cnn((SEQ, Xs_tr.shape[2]))
hist_cnn = cnn.fit(Xs_tr, y_tr, validation_data=(Xs_va, y_va), epochs=30,
                   batch_size=128, class_weight=class_weights,
                   callbacks=[early_stop()], verbose=2)''')
md('''## 5. Tabular baselines

All models use training-only preprocessing. Success is the positive class.
Validation comparisons are exploratory and should not be described as real-world
attack detection performance.''')
code('''fitted = {}
for name, model in {
    'LogisticRegression': LogisticRegression(max_iter=2000, class_weight='balanced'),
    'RandomForest': RandomForestClassifier(n_estimators=300, max_depth=14,
                                          min_samples_leaf=4, class_weight='balanced_subsample',
                                          n_jobs=-1, random_state=SEED),
    'HistGradientBoosting': HistGradientBoostingClassifier(max_iter=300, learning_rate=.08,
                                                            max_depth=6, random_state=SEED)
}.items():
    model.fit(Xall_scaled[:a], y_tr)
    fitted[name] = model
print('Trained baselines:', ', '.join(fitted))''')
code('''def measures(name, y, proba):
    pred = (proba >= .5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {'model': name, 'accuracy': accuracy_score(y, pred),
            'success_precision': precision_score(y, pred, zero_division=0),
            'success_recall': recall_score(y, pred, zero_division=0),
            'success_f1': f1_score(y, pred, zero_division=0),
            'failure_recall': tn / (tn + fp) if tn + fp else np.nan,
            'roc_auc': roc_auc_score(y, proba)}

val_proba = {'LSTM': lstm.predict(Xs_va, verbose=0).ravel(),
             '1D-CNN': cnn.predict(Xs_va, verbose=0).ravel()}
for name, model in fitted.items():
    val_proba[name] = model.predict_proba(Xall_scaled[a:b])[:, 1]
validation = pd.DataFrame([measures(name, y_va, prob) for name, prob in val_proba.items()])
validation = validation.sort_values('success_f1', ascending=False).reset_index(drop=True)
display(validation.round(4))
winner = validation.loc[0, 'model']
print('Selected on validation success F1:', winner)''')
md('''## 6. Evaluate the selected model once on the later test block''')
code('''if winner == 'LSTM':
    p_test = lstm.predict(Xs_te, verbose=0).ravel()
elif winner == '1D-CNN':
    p_test = cnn.predict(Xs_te, verbose=0).ravel()
else:
    p_test = fitted[winner].predict_proba(Xall_scaled[b:])[:, 1]
holdout = pd.DataFrame([measures(winner, y_te, p_test)])
display(holdout.round(4))
cm = confusion_matrix(y_te, (p_test >= .5).astype(int), labels=[0, 1])
fig, ax = plt.subplots(figsize=(4.5, 4))
ax.imshow(cm, cmap='Blues')
ax.set_xticks([0, 1], ['Failure', 'Success'])
ax.set_yticks([0, 1], ['Failure', 'Success'])
ax.set_xlabel('Predicted'); ax.set_ylabel('Actual'); ax.set_title(winner + ' · test')
for i in range(2):
    for j in range(2):
        ax.text(j, i, int(cm[i, j]), ha='center', va='center',
                color='white' if cm[i, j] > cm.max()/2 else 'black')
plt.tight_layout(); plt.show()''')
code('''fig, ax = plt.subplots(figsize=(7, 3.5))
for label, history in [('LSTM', hist_lstm), ('1D-CNN', hist_cnn)]:
    ax.plot(history.history['val_loss'], label=label + ' validation')
ax.set_xlabel('Epoch'); ax.set_ylabel('Loss'); ax.legend(); plt.tight_layout(); plt.show()
validation.to_csv('validation_comparison.csv', index=False)
holdout.to_csv('selected_model_test.csv', index=False)
print('Saved validation_comparison.csv and selected_model_test.csv')''')
n.metadata = {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
              'language_info': {'name': 'python', 'version': '3.10'},
              'colab': {'provenance': []}}
out = ROOT / 'notebooks' / 'AegisCloud_Training_Colab.ipynb'
out.parent.mkdir(exist_ok=True)
nbf.write(n, out)
print('saved', out, len(n.cells), 'cells')
