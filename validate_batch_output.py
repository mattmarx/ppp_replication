#!/usr/bin/env python3
"""
Validate batch output CSV to ensure:
1. magid values are correct (numeric, not hallucinated)
2. assessments are valid (A, B, C, or D)
3. No unwanted fields (original_response, error, etc.)
"""
import pandas as pd
import json
import sys

def validate_batch_csv(csv_path):
    """Validate batch output CSV"""
    print(f"Loading {csv_path}...")
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"ERROR: Failed to load CSV: {e}")
        return False
    
    print(f"✓ CSV loaded: {len(df)} rows, {len(df.columns)} columns")
    print(f"  Columns: {df.columns.tolist()}")
    
    # Check for expected columns
    expected_cols = {'magid', 'patent_id', 'assessment'}
    actual_cols = set(df.columns)
    
    if not expected_cols.issubset(actual_cols):
        missing = expected_cols - actual_cols
        print(f"ERROR: Missing expected columns: {missing}")
        return False
    
    print(f"✓ All expected columns present: {expected_cols}")
    
    # Check for unwanted columns
    unwanted_cols = {'original_response', 'error'}
    found_unwanted = unwanted_cols & actual_cols
    if found_unwanted:
        print(f"WARNING: Found unwanted columns: {found_unwanted}")
    else:
        print(f"✓ No unwanted columns found")
    
    # Validate magid values
    print("\nValidating magid column...")
    magid_issues = []
    for idx, val in enumerate(df['magid']):
        try:
            magid_int = int(val)
            if magid_int < 0:
                magid_issues.append(f"  Row {idx}: negative magid ({magid_int})")
        except (ValueError, TypeError):
            magid_issues.append(f"  Row {idx}: non-numeric magid ({val})")
    
    if magid_issues:
        print(f"WARNING: {len(magid_issues)} magid issues found:")
        for issue in magid_issues[:10]:  # Show first 10
            print(issue)
    else:
        print(f"✓ All magid values are valid numeric")
    
    # Validate assessment values
    print("\nValidating assessment column...")
    valid_assessments = {'A', 'B', 'C', 'D'}
    assessment_issues = []
    
    for idx, val in enumerate(df['assessment']):
        assessment_str = str(val).strip().upper()
        if assessment_str not in valid_assessments:
            assessment_issues.append(f"  Row {idx}: invalid assessment ({val})")
    
    if assessment_issues:
        print(f"ERROR: {len(assessment_issues)} invalid assessment values:")
        for issue in assessment_issues[:10]:  # Show first 10
            print(issue)
        return False
    else:
        print(f"✓ All assessments are valid (A, B, C, or D)")
        print(f"  Distribution:\n{df['assessment'].value_counts().sort_index()}")
    
    # Sample a few rows
    print("\nSample rows (first 5):")
    print(df[['magid', 'patent_id', 'assessment']].head(5).to_string(index=False))
    
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_batch_output.py <csv_path>")
        sys.exit(1)
    
    csv_path = sys.argv[1]
    success = validate_batch_csv(csv_path)
    sys.exit(0 if success else 1)
