import os
import sys
import subprocess
import numpy as np

# Auto-resolve deep learning packages
required_packages = ["tensorflow", "scikit-learn"]
for package in required_packages:
    import_name = "sklearn" if package == "scikit-learn" else package
    try:
        __import__(import_name)
    except ImportError:
        print(f"[!] Installing missing dependency: {package}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Bidirectional, Dropout, Input
from tensorflow.keras.utils import to_categorical
from sklearn.model_selection import train_test_split

# Resolve directories dynamically depending on whether script is run from root or python_server
DATA_DIR = "data_sequences"
if not os.path.exists(DATA_DIR) and os.path.exists(os.path.join("python_server", DATA_DIR)):
    DATA_DIR = os.path.join("python_server", DATA_DIR)

MODEL_PATH = "asl_sentence_model.h5"
if os.path.exists("python_server") and os.path.isdir("python_server"):
    MODEL_PATH = os.path.join("python_server", MODEL_PATH)

def train():
    if not os.path.exists(DATA_DIR):
        print(f"[-] Error: '{DATA_DIR}' directory not found. Please collect some sequential data first.")
        return
        
    words = sorted([d for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d))])
    if not words:
        print(f"[-] Error: No word subfolders found inside '{DATA_DIR}'.")
        return
        
    print(f"[*] Found {len(words)} classes in database: {words}")
    
    # Pre-scan classes for sample counts
    has_empty_class = False
    class_counts = {}
    for word in words:
        word_dir = os.path.join(DATA_DIR, word)
        samples = [f for f in os.listdir(word_dir) if f.endswith(".npy")]
        class_counts[word] = len(samples)
        if len(samples) == 0:
            print(f"[-] ERROR: Class '{word}' has 0 training samples!")
            has_empty_class = True
        elif len(samples) < 15:
            print(f"[!] WARNING: Class '{word}' has only {len(samples)} samples. We recommend at least 15-20 samples for robust sequence classification.")
            
    if has_empty_class:
        print("\n[-] Error: One or more target classes have 0 samples. Training cannot proceed.")
        print("[-] Please run collect_sequence_data.py to record webcam samples for the empty classes.")
        return
        
    word_to_label = {word: i for i, word in enumerate(words)}
    
    X = []
    y = []
    
    print("\n[*] Loading dataset files...")
    for word in words:
        word_dir = os.path.join(DATA_DIR, word)
        samples = [f for f in os.listdir(word_dir) if f.endswith(".npy")]
        print(f"  Loading {len(samples)} samples for '{word}'...")
        
        for sample in samples:
            data = np.load(os.path.join(word_dir, sample))
            if data.shape == (45, 138):
                X.append(data)
                y.append(word_to_label[word])
                
    X = np.array(X, dtype=np.float32)
    y = np.array(y, dtype=np.int32)
    
    if len(X) == 0:
        print("[-] Error: No valid sequences of shape (45, 138) could be loaded.")
        return
        
    print(f"\n[OK] Loaded {len(X)} total sequence blocks.")
    
    # One-hot encode targets
    y_one_hot = to_categorical(y, num_classes=len(words))
    
    # Train test split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    y_train_one_hot = to_categorical(y_train, num_classes=len(words))
    y_test_one_hot = to_categorical(y_test, num_classes=len(words))
    
    # Build simplified, robust BiLSTM model
    print("[*] Building Bidirectional LSTM sequence classifier model...")
    model = Sequential([
        Input(shape=(45, 138)),
        Bidirectional(LSTM(64)),
        Dropout(0.3),
        Dense(len(words), activation='softmax')
    ])
    
    # Use Adam with custom learning rate for stable convergence
    opt = tf.keras.optimizers.Adam(learning_rate=0.001)
    model.compile(optimizer=opt, loss='categorical_crossentropy', metrics=['accuracy'])
    model.summary()
    
    print("\n[*] Training model...")
    model.fit(X_train, y_train_one_hot, epochs=200, batch_size=8, validation_data=(X_test, y_test_one_hot))
    
    loss, accuracy = model.evaluate(X_test, y_test_one_hot)
    print(f"\n[OK] Training completed. Test Set Accuracy: {accuracy * 100:.2f}%")
    
    # Retrain on full dataset
    print(f"[*] Retraining on full dataset ({len(X)} sequences)...")
    model.fit(X, y_one_hot, epochs=150, batch_size=8, verbose=0)
    
    # Save model as H5
    print(f"[*] Serializing sequential classifier model to '{MODEL_PATH}'...")
    model.save(MODEL_PATH)
    print("[OK] Model saved successfully!")

if __name__ == "__main__":
    train()
