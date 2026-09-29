import pandas as pd
from diff_match_patch import diff_match_patch
import numpy as np

# Initialize diff_match_patch
dmp = diff_match_patch()

# Helper function to process diff_main output for a single row
def compute_plagiarism_metrics(row):
    text1 = row['text1']
    #[:1000]
    text2 = row['text2']
    #[:1000]
    
    # Compute diff
    plagiarism = dmp.diff_main(text1, text2, True)
    # Filter for matches (operation == 0)
    plagiarism = [elem for elem in plagiarism if elem[0] == 0]
    # Sort by length, descending, and take top 5
    plagiarism = sorted(plagiarism, key=lambda val: len(val[1]), reverse=True)[:5]
    
    # Extract common strings
    common_strings = [elem[1] for elem in plagiarism]
    
    # Compute word counts for top 1, 3, and 5 matches
    word_counts = [len(elem[1].split()) for elem in plagiarism]
    plagiarism_words_1 = sum(word_counts[:1]) if word_counts else 0
    plagiarism_words_3 = sum(word_counts[:3]) if word_counts else 0
    plagiarism_words_5 = sum(word_counts) if word_counts else 0
    
    # Compute plagiarism percentage
    total_words = len(text1.split()) + len(text2.split())
    if total_words > plagiarism_words_5 and plagiarism_words_5 > 0:
        plagiarism_percentage = 100 * plagiarism_words_5 / (total_words - plagiarism_words_5)
    else:
        plagiarism_percentage = 0.0
    
    return pd.Series({
        'common_strings': common_strings,
        'plagiarism_group_words_1': plagiarism_words_1,
        'plagiarism_group_words_3': plagiarism_words_3,
        'plagiarism_group_words_5': plagiarism_words_5,
        'plagiarism_percentage': plagiarism_percentage
    })

