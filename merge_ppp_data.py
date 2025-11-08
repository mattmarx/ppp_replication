import pandas as pd
import os
import sys
import argparse

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Merge PPP data with paper abstracts'
    )
    parser.add_argument('input', nargs='?', help='Input CSV file to merge (or use default paths)')
    parser.add_argument('--output', '-o', help='Output filename (default: merged_ppp_data.csv)')
    parser.add_argument('--second-input', help='Second CSV file to merge (optional)')
    parser.add_argument('--ppp-score', type=int, help='Filter to keep only rows with this ppp_score value (applied before merge)')

    args = parser.parse_args()

    # Define base paths
    base_dir = "/mnt/d/Marx Dropbox/Matt Marx/research/anticommonsrevisited/handcheck/llmcheck/"
    tsv_path = "/mnt/d/Marx Dropbox/Matt Marx/bigdata/ppp/mattrewriteofemma/data/int/papertoembed.tsv"

    # Set output path in data/int/
    output_dir = "/mnt/d/Marx Dropbox/Matt Marx/bigdata/ppp/mattrewriteofemma/data/int/"
    output_filename = args.output or "merged_ppp_data.csv"
    output_path = os.path.join(output_dir, output_filename)

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Load CSV files
    print("Loading CSV files...")
    if args.input:
        # User provided input file(s)
        csv1_path = args.input
        csv2_path = args.second_input

        print(f"Loading {csv1_path}...")
        df1 = pd.read_csv(csv1_path, low_memory=False)

        if csv2_path:
            print(f"Loading {csv2_path}...")
            df2 = pd.read_csv(csv2_path, low_memory=False)
        else:
            df2 = None
    else:
        # Use default paths
        csv1_path = os.path.join(base_dir, "PPP_Round2 - Responded.csv")
        csv2_path = os.path.join(base_dir, "PPP_Working Sheet - Responded (2).csv")

        print(f"Using default paths:")
        print(f"  {csv1_path}")
        print(f"  {csv2_path}")

        df1 = pd.read_csv(csv1_path, low_memory=False)
        df2 = pd.read_csv(csv2_path, low_memory=False)

    print(f"CSV1 shape: {df1.shape}")
    if df2 is not None:
        print(f"CSV2 shape: {df2.shape}")

    # Filter by ppp_score if specified (do this before merge to save time)
    if args.ppp_score is not None:
        print(f"\nFiltering by ppp_score = {args.ppp_score}...")
        if 'ppp_score' in df1.columns:
            df1 = df1[df1['ppp_score'] == args.ppp_score].copy()
            print(f"  CSV1 after filter: {df1.shape[0]} rows")
        else:
            print("  Warning: ppp_score column not found in CSV1")

        if df2 is not None and 'ppp_score' in df2.columns:
            df2 = df2[df2['ppp_score'] == args.ppp_score].copy()
            print(f"  CSV2 after filter: {df2.shape[0]} rows")
        elif df2 is not None:
            print("  Warning: ppp_score column not found in CSV2")

    # Load the TSV file with paper abstracts
    print("Loading TSV file with paper abstracts...")
    paper_abstracts = pd.read_csv(tsv_path, sep='\t')
    paper_abstracts = paper_abstracts[['id', 'abstract']].copy()
    paper_abstracts.rename(columns={'id': 'magid', 'abstract': 'paper_abstract'}, inplace=True)

    # Process File 1
    print("\nProcessing File 1...")
    df1_merged = df1.merge(paper_abstracts, on='magid', how='left')
    print(f"File 1 rows: {len(df1_merged)}")

    # Process File 2 if provided
    if df2 is not None:
        print("Processing File 2...")
        df2_merged = df2.merge(paper_abstracts, on='magid', how='left')
        print(f"File 2 rows: {len(df2_merged)}")

        # Combine both files
        print("\nCombining both files...")
        combined_df = pd.concat([df1_merged, df2_merged], ignore_index=True)
        print(f"Combined shape: {combined_df.shape}")
    else:
        combined_df = df1_merged

    # Convert IDs to integers (removing .0) if they exist and are numeric
    if 'magid' in combined_df.columns:
        try:
            combined_df['magid'] = combined_df['magid'].astype(int)
        except (ValueError, TypeError):
            print("Warning: magid contains non-numeric values, keeping as-is")

    if 'patent_id' in combined_df.columns:
        try:
            combined_df['patent_id'] = combined_df['patent_id'].astype(int)
        except (ValueError, TypeError):
            print("Warning: patent_id contains non-numeric values (e.g., reissue patents like 'RE37100'), keeping as-is")
            # Try to convert numeric strings to int, leave others as-is
            combined_df['patent_id'] = pd.to_numeric(combined_df['patent_id'], errors='ignore')

    # Keep all columns from the merged dataframe
    final_df = combined_df.copy()

    print(f"Final shape: {final_df.shape}")
    print(f"Final columns: {final_df.columns.tolist()}")

    # Write output
    print(f"\nWriting output to {output_path}...")
    final_df.to_csv(output_path, index=False)
    print("Done!")

    # Print response distribution if response column exists
    if 'response' in final_df.columns:
        print(f"\nResponse distribution in final file:\n{final_df['response'].value_counts()}")

if __name__ == "__main__":
    main()
