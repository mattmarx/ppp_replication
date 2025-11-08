import pandas as pd
import os
import sys
import argparse

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Merge PPP data with paper and patent information from embeddings TSV files'
    )
    parser.add_argument('input', nargs='?', help='Input CSV file to merge (or use default paths)')
    parser.add_argument('--output', '-o', help='Output filename (default: finalpppsplusabstract[score].csv)')
    parser.add_argument('--second-input', help='Second CSV file to merge (optional)')
    parser.add_argument('--ppp-score', type=int, help='Filter to keep only rows with this ppp_score value (applied before merge)')

    args = parser.parse_args()

    # Define base paths
    base_dir = "/mnt/d/Marx Dropbox/Matt Marx/research/anticommonsrevisited/handcheck/llmcheck/"
    data_int_dir = "/mnt/d/Marx Dropbox/Matt Marx/bigdata/ppp/mattrewriteofemma/data/int/"
    paper_tsv_path = os.path.join(data_int_dir, "papertoembed.tsv")
    patent_tsv_path = os.path.join(data_int_dir, "patenttoembed.tsv")

    # Set output path in data/int/
    output_dir = "/mnt/d/Marx Dropbox/Matt Marx/bigdata/ppp/mattrewriteofemma/data/int/"

    # Generate default output filename based on ppp_score if provided
    if args.output:
        output_filename = args.output
    elif args.ppp_score is not None:
        output_filename = f"finalpppsplusabstract{args.ppp_score}.csv"
    else:
        output_filename = "finalpppsplusabstract.csv"

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

    # Load the TSV files with paper and patent data
    print("Loading TSV files...")

    print(f"  Loading paper data from {paper_tsv_path}...")
    paper_data = pd.read_csv(paper_tsv_path, sep='\t', low_memory=False)
    # Extract paper information: id, abstract, and title
    paper_cols = [col for col in ['id', 'abstract', 'title'] if col in paper_data.columns]
    paper_data = paper_data[paper_cols].copy()
    paper_data.rename(columns={'id': 'magid', 'abstract': 'paper_abstract', 'title': 'papertitle'}, inplace=True)
    print(f"    Paper data columns: {paper_data.columns.tolist()}")

    print(f"  Loading patent data from {patent_tsv_path}...")
    patent_data = pd.read_csv(patent_tsv_path, sep='\t', low_memory=False)
    # Extract patent information: id, title, abstract
    patent_cols = [col for col in ['id', 'title', 'abstract'] if col in patent_data.columns]
    patent_data = patent_data[patent_cols].copy()
    patent_data.rename(columns={'id': 'patent_id', 'title': 'patent_title', 'abstract': 'patent_abstract'}, inplace=True)
    print(f"    Patent data columns: {patent_data.columns.tolist()}")

    # Process File 1
    print("\nProcessing File 1...")
    df1_merged = df1.merge(paper_data, on='magid', how='left')
    df1_merged = df1_merged.merge(patent_data, on='patent_id', how='left')
    print(f"File 1 rows: {len(df1_merged)}")

    # Process File 2 if provided
    if df2 is not None:
        print("Processing File 2...")
        df2_merged = df2.merge(paper_data, on='magid', how='left')
        df2_merged = df2_merged.merge(patent_data, on='patent_id', how='left')
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
