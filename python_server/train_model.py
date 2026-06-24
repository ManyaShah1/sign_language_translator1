import os
import csv
import pickle
import numpy as np
from sklearn.neural_network import MLPClassifier
from sklearn.model_selection import train_test_split

def train():
    dataset_path = 'dataset.csv'
    pickle_path = 'isl_model_advanced.pkl'
    
    if not os.path.exists(dataset_path):
        print(f"[-] Error: '{dataset_path}' not found. Please run collect_data.py first to log some coordinate frames.")
        return
        
    print(f"[*] Loading training frames from '{dataset_path}'...")
    X = []
    y = []
    
    with open(dataset_path, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) == 131:  # 130 coordinates + 1 label
                X.append([float(val) for val in row[:-1]])
                y.append(row[-1])
                
    X = np.array(X, dtype=np.float32)
    y = np.array(y)
    
    total_samples = len(X)
    print(f"[OK] Loaded {total_samples} frames.")
    
    classes, counts = np.unique(y, return_counts=True)
    print("\nClass Distribution:")
    for cls, count in zip(classes, counts):
        print(f"  Class '{cls}': {count} frames")
    print("")
    
    if len(classes) < 2:
        print("[-] Error: You need at least 2 different classes in your dataset to train a model.")
        return
        
    if total_samples < 10:
        print("[-] Error: Insufficient data. Please collect more frames for model training.")
        return
        
    # Split dataset for validation scoring
    print("[*] Splitting dataset into 80% train and 20% test...")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    print("[*] Training Multi-Layer Perceptron classifier...")
    # Hidden layer sizes: 128 inputs -> Dense(128) -> Dense(64) -> Output
    clf = MLPClassifier(hidden_layer_sizes=(128, 64), max_iter=500, random_state=42, verbose=True)
    clf.fit(X_train, y_train)
    
    accuracy = clf.score(X_test, y_test)
    print(f"\n[OK] Training completed.")
    print(f"[*] Test Set Accuracy: {accuracy * 100:.2f}%")
    
    print(f"[*] Retraining on full dataset ({total_samples} samples)...")
    clf.fit(X, y)
    
    print(f"[*] Serializing model to '{pickle_path}'...")
    with open(pickle_path, 'wb') as f:
        pickle.dump(clf, f)
        
    print(f"[OK] Model saved successfully! When you start/restart your server.py, it will automatically load this model.")

if __name__ == "__main__":
    train()
