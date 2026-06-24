import csv
import os
import shutil

def build_hybrid():
    input_path = 'dataset.csv'
    
    if not os.path.exists(input_path):
        print(f"[-] Error: '{input_path}' not found.")
        return
        
    with open(input_path, 'r') as f:
        reader = list(csv.reader(f))
        
    print(f"Current rows in dataset.csv: {len(reader)}")
    if len(reader) < 4000:
        print("[-] Error: dataset.csv has not been reverted yet. It has only {} rows.".format(len(reader)))
        print("[-] Please revert the file in your editor (e.g. Local History or Undo) to restore the ~4860 lines.")
        return
        
    # Backup original reverted dataset just in case
    shutil.copy(input_path, 'dataset_backup.csv')
    print("[OK] Created backup of original dataset at 'dataset_backup.csv'")
    
    static_rows = reader[:2484]
    user_rows = reader[2484:]
    
    modified_letters = {'E', 'G', 'H', 'I', 'K', 'M', 'N', 'O', 'Q', 'R', 'T', 'U', 'V', 'Y'}
    
    clean_rows = []
    
    # Process static rows: exclude modified letters
    excluded_count = 0
    for r in static_rows:
        label = r[-1]
        if label in modified_letters:
            excluded_count += 1
        else:
            clean_rows.append(r)
            
    print("Excluded {} static rows for modified letters.".format(excluded_count))
    print("Kept {} static rows for other letters.".format(len(clean_rows)))
    
    # Add all user rows
    clean_rows.extend(user_rows)
    print("Added {} user recorded rows.".format(len(user_rows)))
    print("Total rows in final hybrid dataset: {}".format(len(clean_rows)))
    
    # Write to a temporary file first
    temp_path = 'dataset_temp.csv'
    with open(temp_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(clean_rows)
        
    # Safely swap files
    if os.path.exists(input_path):
        os.remove(input_path)
    os.rename(temp_path, input_path)
    print("[OK] Hybrid dataset successfully written to dataset.csv.")

if __name__ == '__main__':
    build_hybrid()
