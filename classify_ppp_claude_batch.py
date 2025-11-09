#!/usr/bin/env python3
"""
Comprehensive script to classify patent-paper pairs using Claude.
Supports batch submission, batch retrieval, and streaming modes (sequential and concurrent).

Requires ANTHROPIC_API_KEY environment variable to be set.

Usage:
    # Submit a batch (fastest for large datasets, but asynchronous)
    python classify_ppp_claude_batch.py --mode batch-submit --input input.csv --prompt prompt.txt

    # Retrieve batch results
    python classify_ppp_claude_batch.py --mode batch-retrieve --batch-id <batch_id>

    # Stream results sequentially (slower)
    python classify_ppp_claude_batch.py --mode stream --input input.csv --prompt prompt.txt

    # Stream results concurrently (fast and immediate feedback, recommended)
    python classify_ppp_claude_batch.py --mode stream-concurrent --input input.csv --prompt prompt.txt --max-concurrent 10

    # List all tracked batches
    python classify_ppp_claude_batch.py --mode list-batches
"""

import csv
import json
import os
import sys
import argparse
import time
import asyncio
from datetime import datetime
from pathlib import Path
import pandas as pd
from anthropic import Anthropic, AsyncAnthropic
import logging
from dotenv import load_dotenv

# Load environment variables from ~/.env file
home_env_path = Path.home() / '.env'
load_dotenv(str(home_env_path))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BATCH_TRACKING_FILE = 'batch_tracking.json'
PROMPT_FILE = 'ppp_prompt.txt'

# Pricing per million tokens (update as needed)
MODEL_PRICING = {
    "claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0},
    "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
}

class PPPBatchClassifier:
    def __init__(self, model="claude-sonnet-4-5-20250929"):
        """Initialize the classifier with specified model."""
        if not os.getenv('ANTHROPIC_API_KEY'):
            raise ValueError(
                "ANTHROPIC_API_KEY not found. Please add it to ~/.env file with:\n"
                "  ANTHROPIC_API_KEY=your_api_key_here\n"
                "Or set it as an environment variable."
            )

        self.client = Anthropic()
        self.model = model
        self.batch_tracking = self._load_batch_tracking()

    def _calculate_cost(self, input_tokens, output_tokens):
        """Calculate cost in USD for given token usage."""
        pricing = MODEL_PRICING.get(self.model, {"input": 3.0, "output": 15.0})
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost

    def _load_batch_tracking(self):
        """Load existing batch tracking data."""
        if os.path.exists(BATCH_TRACKING_FILE):
            with open(BATCH_TRACKING_FILE, 'r') as f:
                return json.load(f)
        return {'batches': []}

    def _save_batch_tracking(self):
        """Save batch tracking data."""
        with open(BATCH_TRACKING_FILE, 'w') as f:
            json.dump(self.batch_tracking, f, indent=2)

    def load_prompt(self, prompt_file):
        """Load the classification prompt from file."""
        if not os.path.exists(prompt_file):
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
        with open(prompt_file, 'r', encoding='utf-8') as f:
            return f.read().strip()

    def _build_message_content(self, prompt, magid, patent_id, papertitle,
                              patent_title, paper_abstract, patent_abstract, original_response):
        """Build the message content for classification."""
        return f"""{prompt}

Paper Information:
- Title: {papertitle}
- Abstract: {paper_abstract}

Patent Information:
- Patent ID: {patent_id}
- Title: {patent_title}
- Abstract: {patent_abstract}

Original Response: {original_response}
Paper ID (magid): {magid}
Patent ID: {patent_id}"""

    def _parse_response(self, response_text, magid, patent_id, original_response):
        """Parse JSON response from Claude."""
        try:
            # Try to extract JSON from the response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                result = json.loads(json_str)
                return result
            else:
                # Fallback: try to extract just the assessment (A/B/C/D)
                for line in response_text.split('\n'):
                    if 'assessment' in line.lower() and any(grade in line for grade in ['A', 'B', 'C', 'D']):
                        for grade in ['A', 'B', 'C', 'D']:
                            if grade in line:
                                return {
                                    "magid": magid,
                                    "patent_id": patent_id,
                                    "original_response": original_response,
                                    "assessment": grade
                                }

                logger.warning(f"No JSON found in response for magid {magid}")
                return {
                    "magid": magid,
                    "patent_id": patent_id,
                    "original_response": original_response,
                    "assessment": None,
                    "error": "No JSON found in response"
                }
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON for magid {magid}: {str(e)}")
            return {
                "magid": magid,
                "patent_id": patent_id,
                "original_response": original_response,
                "assessment": None,
                "error": f"JSON parsing error: {str(e)}"
            }

    def create_batch_messages(self, input_file, prompt_file, start_row=0, limit=None):
        """
        Create batch messages from input CSV file.
        Returns list of request dicts for batch API.
        """
        logger.info(f"Loading data from {input_file}...")
        df = pd.read_csv(input_file)
        prompt = self.load_prompt(prompt_file)

        if limit:
            df = df.iloc[:limit]

        messages = []
        row_mapping = {}  # Map request custom_id to row data

        for idx, row in df.iterrows():
            if idx < start_row:
                continue

            try:
                magid = int(row['magid'])
                # Handle both numeric and non-numeric patent IDs (e.g., reissue patents like 'RE47740')
                try:
                    patent_id = int(row['patent_id'])
                except (ValueError, TypeError):
                    patent_id = row['patent_id']
                papertitle = str(row['papertitle'])
                patent_title = str(row['patent_title'])
                paper_abstract = str(row['paper_abstract'])
                patent_abstract = str(row['patent_abstract'])
                original_response = str(row.get('response', ''))

                message_content = self._build_message_content(
                    prompt, magid, patent_id, papertitle, patent_title,
                    paper_abstract, patent_abstract, original_response
                )

                custom_id = f"pair_{magid}_{patent_id}_{idx}"

                message = {
                    "custom_id": custom_id,
                    "params": {
                        "model": self.model,
                        "max_tokens": 500,
                        "messages": [
                            {"role": "user", "content": message_content}
                        ]
                    }
                }

                messages.append(message)
                row_mapping[custom_id] = {
                    'magid': magid,
                    'patent_id': patent_id,
                    'original_response': original_response,
                    'row_idx': idx
                }

            except Exception as e:
                logger.error(f"Error preparing row {idx}: {str(e)}")
                continue

        logger.info(f"Prepared {len(messages)} messages for batch submission")
        return messages, row_mapping

    def submit_batch(self, input_file, prompt_file, start_row=0, limit=None, output_file=None):
        """
        Submit batch job to Anthropic Batch API.
        Returns batch ID.
        """
        messages, row_mapping = self.create_batch_messages(input_file, prompt_file, start_row, limit)

        if not messages:
            logger.error("No messages to submit")
            return None

        logger.info(f"Submitting batch with {len(messages)} requests...")

        # Submit batch
        batch = self.client.beta.messages.batches.create(
            requests=messages
        )

        batch_id = batch.id
        logger.info(f"Batch submitted successfully. Batch ID: {batch_id}")

        # Track this batch
        batch_info = {
            "batch_id": batch_id,
            "submitted_at": datetime.now().isoformat(),
            "input_file": input_file,
            "output_file": output_file or f"ppp_claude_assessments_{batch_id}.csv",
            "num_requests": len(messages),
            "model": self.model,
            "status": "submitted",
            "row_mapping": row_mapping
        }

        self.batch_tracking['batches'].append(batch_info)
        self._save_batch_tracking()

        logger.info(f"Batch info saved to {BATCH_TRACKING_FILE}")
        print(f"\n✓ Batch submitted: {batch_id}")
        print(f"  Requests: {len(messages)}")
        print(f"  Check status with: python classify_ppp_claude_batch.py --mode list-batches")

        return batch_id

    def check_batch_status(self, batch_id):
        """Check the status of a batch job."""
        batch = self.client.beta.messages.batches.retrieve(
            batch_id
        )
        return batch

    def retrieve_batch_results(self, batch_id, output_file=None):
        """
        Retrieve results from completed batch.
        Saves results to CSV file.
        """
        logger.info(f"Retrieving batch {batch_id}...")

        # Get batch info
        batch_info = None
        for b in self.batch_tracking['batches']:
            if b['batch_id'] == batch_id:
                batch_info = b
                break

        if not batch_info:
            logger.error(f"Batch {batch_id} not found in tracking")
            return None

        # Check batch status
        batch = self.check_batch_status(batch_id)
        logger.info(f"Batch status: {batch.processing_status}")
        logger.info(f"Request counts: {batch.request_counts}")

        # Batch API returns "ended" when complete (not "completed")
        if batch.processing_status != "ended":
            logger.warning(f"Batch not yet complete. Current status: {batch.processing_status}")
            logger.info(f"Check again later with: python classify_ppp_claude_batch.py --mode batch-retrieve --batch-id {batch_id}")
            return None

        # Determine output file
        if not output_file:
            output_file = batch_info.get('output_file', f"ppp_claude_assessments_{batch_id}.csv")

        logger.info(f"Saving results to {output_file}...")

        row_mapping = batch_info.get('row_mapping', {})
        results = []

        # Stream results from batch
        results_iter = self.client.beta.messages.batches.results(batch_id)
        for result in results_iter:
            try:
                custom_id = result.custom_id
                row_data = row_mapping.get(custom_id, {})

                if result.result.type == "succeeded":
                    response_text = result.result.message.content[0].text
                    parsed = self._parse_response(
                        response_text,
                        row_data.get('magid'),
                        row_data.get('patent_id'),
                        row_data.get('original_response')
                    )
                    results.append(parsed)
                elif result.result.type == "errored":
                    error_msg = result.result.error.message if result.result.error else "Unknown error"
                    results.append({
                        "magid": row_data.get('magid'),
                        "patent_id": row_data.get('patent_id'),
                        "original_response": row_data.get('original_response'),
                        "assessment": None,
                        "error": f"API error: {error_msg}"
                    })
                elif result.result.type == "expired":
                    results.append({
                        "magid": row_data.get('magid'),
                        "patent_id": row_data.get('patent_id'),
                        "original_response": row_data.get('original_response'),
                        "assessment": None,
                        "error": "Request expired"
                    })
            except Exception as e:
                logger.error(f"Error processing result {result.custom_id}: {str(e)}")

        # Write results to CSV
        if results:
            df_results = pd.DataFrame(results)
            df_results.to_csv(output_file, index=False)
            logger.info(f"Results saved to {output_file}")
            logger.info(f"Total results: {len(results)}")

            # Update batch tracking
            batch_info['status'] = 'completed'
            batch_info['output_file'] = output_file
            batch_info['completed_at'] = datetime.now().isoformat()
            batch_info['results_count'] = len(results)
            self._save_batch_tracking()

            print(f"\n✓ Results retrieved: {output_file}")
            print(f"  Total results: {len(results)}")
            return output_file
        else:
            logger.warning("No results found in batch")
            return None

    def stream_classify(self, input_file, prompt_file, output_file=None, start_row=0, limit=None):
        """
        Classify pairs using streaming mode (one at a time).
        Slower but provides immediate feedback and lower latency.
        """
        start_time = time.time()
        logger.info(f"Loading data from {input_file}...")
        df = pd.read_csv(input_file)

        if limit:
            df = df.iloc[:limit]

        if not output_file:
            output_file = 'ppp_claude_assessments.csv'

        prompt = self.load_prompt(prompt_file)

        # Check if output file exists
        start_idx = 0
        if os.path.exists(output_file) and not start_row:
            with open(output_file, 'r') as f:
                start_idx = sum(1 for _ in f) - 1  # Exclude header
            logger.info(f"Resuming from row {start_idx + 1}")

        processed = 0
        input_tokens = 0
        output_tokens = 0

        with open(output_file, 'w' if start_idx == 0 else 'a', newline='', encoding='utf-8') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=['magid', 'patent_id', 'original_response', 'assessment', 'error'])

            if start_idx == 0:
                writer.writeheader()

            for idx, row in df.iterrows():
                if idx < start_row + start_idx:
                    continue

                try:
                    magid = int(row['magid'])
                    # Handle both numeric and non-numeric patent IDs (e.g., reissue patents like 'RE47740')
                    try:
                        patent_id = int(row['patent_id'])
                    except (ValueError, TypeError):
                        patent_id = row['patent_id']
                    papertitle = str(row['papertitle'])
                    patent_title = str(row['patent_title'])
                    paper_abstract = str(row['paper_abstract'])
                    patent_abstract = str(row['patent_abstract'])
                    original_response = str(row.get('response', ''))

                    row_number = idx + 2  # Account for header
                    logger.info(f"Processing row {row_number}/{len(df)} (magid: {magid}, patent_id: {patent_id})")

                    message_content = self._build_message_content(
                        prompt, magid, patent_id, papertitle, patent_title,
                        paper_abstract, patent_abstract, original_response
                    )

                    # Call Claude API
                    response = self.client.messages.create(
                        model=self.model,
                        max_tokens=500,
                        messages=[
                            {"role": "user", "content": message_content}
                        ]
                    )

                    # Track token usage
                    input_tokens += response.usage.input_tokens
                    output_tokens += response.usage.output_tokens

                    response_text = response.content[0].text.strip()
                    result = self._parse_response(response_text, magid, patent_id, original_response)

                    # Write result
                    output_row = {
                        'magid': result.get('magid', magid),
                        'patent_id': result.get('patent_id', patent_id),
                        'original_response': result.get('original_response', original_response),
                        'assessment': result.get('assessment', ''),
                        'error': result.get('error', '')
                    }
                    writer.writerow(output_row)
                    outfile.flush()

                    processed += 1
                    if processed % 10 == 0:
                        logger.info(f"Processed {processed} pairs...")

                except Exception as e:
                    logger.error(f"Error processing row {idx}: {str(e)}")
                    output_row = {
                        'magid': row.get('magid', ''),
                        'patent_id': row.get('patent_id', ''),
                        'original_response': row.get('response', ''),
                        'assessment': '',
                        'error': str(e)
                    }
                    writer.writerow(output_row)

        # Calculate and report costs
        total_cost = self._calculate_cost(input_tokens, output_tokens)
        elapsed_time = time.time() - start_time

        logger.info(f"Done! Processed {processed} pairs. Results saved to {output_file}")
        print(f"\n✓ Classification complete: {output_file}")
        print(f"  Total results: {processed}")
        print(f"  Input tokens: {input_tokens:,}")
        print(f"  Output tokens: {output_tokens:,}")
        print(f"  Total cost: ${total_cost:.4f}")
        print(f"  Processing time: {elapsed_time:.2f}s")
        return output_file

    def stream_classify_concurrent(self, input_file, prompt_file, output_file=None, start_row=0, limit=None, max_concurrent=5):
        """
        Classify pairs using concurrent streaming mode.
        Processes multiple requests in parallel for faster throughput.
        """
        start_time = time.time()
        logger.info(f"Loading data from {input_file}...")
        df = pd.read_csv(input_file)

        if limit:
            df = df.iloc[:limit]

        if not output_file:
            output_file = 'ppp_claude_assessments.csv'

        prompt = self.load_prompt(prompt_file)

        # Run async processing
        results, token_usage = asyncio.run(self._async_process_concurrent(df, prompt, start_row, max_concurrent))

        # Write results to CSV
        if results:
            with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
                writer = csv.DictWriter(outfile, fieldnames=['magid', 'patent_id', 'original_response', 'assessment', 'error'])
                writer.writeheader()
                for result in results:
                    writer.writerow(result)

            # Calculate and report costs
            total_cost = self._calculate_cost(token_usage['input'], token_usage['output'])
            elapsed_time = time.time() - start_time

            logger.info(f"Done! Processed {len(results)} pairs. Results saved to {output_file}")
            print(f"\n✓ Classification complete: {output_file}")
            print(f"  Total results: {len(results)}")
            print(f"  Input tokens: {token_usage['input']:,}")
            print(f"  Output tokens: {token_usage['output']:,}")
            print(f"  Total cost: ${total_cost:.4f}")
            print(f"  Processing time: {elapsed_time:.2f}s")
            return output_file
        else:
            logger.warning("No results processed")
            return None

    async def _async_process_concurrent(self, df, prompt, start_row, max_concurrent):
        """Process rows concurrently with asyncio."""
        async_client = AsyncAnthropic()
        semaphore = asyncio.Semaphore(max_concurrent)
        results = []
        tasks = []

        # Track token usage across all requests
        token_usage = {'input': 0, 'output': 0}

        logger.info(f"Starting concurrent processing with {max_concurrent} workers...")

        async def process_row(idx, row):
            """Process a single row with semaphore limiting."""
            async with semaphore:
                try:
                    magid = int(row['magid'])
                    # Handle both numeric and non-numeric patent IDs (e.g., reissue patents like 'RE47740')
                    try:
                        patent_id = int(row['patent_id'])
                    except (ValueError, TypeError):
                        patent_id = row['patent_id']
                    papertitle = str(row['papertitle'])
                    patent_title = str(row['patent_title'])
                    paper_abstract = str(row['paper_abstract'])
                    patent_abstract = str(row['patent_abstract'])
                    original_response = str(row.get('response', ''))

                    message_content = self._build_message_content(
                        prompt, magid, patent_id, papertitle, patent_title,
                        paper_abstract, patent_abstract, original_response
                    )

                    # Call Claude API asynchronously
                    response = await async_client.messages.create(
                        model=self.model,
                        max_tokens=500,
                        messages=[
                            {"role": "user", "content": message_content}
                        ]
                    )

                    # Track token usage
                    token_usage['input'] += response.usage.input_tokens
                    token_usage['output'] += response.usage.output_tokens

                    response_text = response.content[0].text.strip()
                    result = self._parse_response(response_text, magid, patent_id, original_response)

                    row_number = idx + 2  # Account for header
                    logger.info(f"Completed row {row_number}/{len(df)} (magid: {magid}, patent_id: {patent_id})")

                    return {
                        'magid': result.get('magid', magid),
                        'patent_id': result.get('patent_id', patent_id),
                        'original_response': result.get('original_response', original_response),
                        'assessment': result.get('assessment', ''),
                        'error': result.get('error', '')
                    }
                except Exception as e:
                    logger.error(f"Error processing row {idx}: {str(e)}")
                    return {
                        'magid': row.get('magid', ''),
                        'patent_id': row.get('patent_id', ''),
                        'original_response': row.get('response', ''),
                        'assessment': '',
                        'error': str(e)
                    }

        # Create tasks for all rows
        for idx, row in df.iterrows():
            if idx < start_row:
                continue
            tasks.append(process_row(idx, row))

        logger.info(f"Processing {len(tasks)} pairs concurrently...")

        # Execute all tasks and collect results
        results = await asyncio.gather(*tasks)

        return results, token_usage

    def list_batches(self):
        """List all tracked batches."""
        if not self.batch_tracking['batches']:
            print("No batches tracked yet.")
            return

        print("\n=== BATCH TRACKING ===\n")
        for i, batch in enumerate(self.batch_tracking['batches'], 1):
            print(f"Batch {i}:")
            print(f"  ID: {batch['batch_id']}")
            print(f"  Status: {batch.get('status', 'unknown')}")
            print(f"  Submitted: {batch.get('submitted_at', 'unknown')}")
            print(f"  Requests: {batch.get('num_requests', 'unknown')}")
            print(f"  Output: {batch.get('output_file', 'unknown')}")

            # Check current status from API
            try:
                api_batch = self.check_batch_status(batch['batch_id'])
                print(f"  API Status: {api_batch.processing_status}")
                print(f"  Request Counts: {api_batch.request_counts}")
            except Exception as e:
                print(f"  API Status: Error - {str(e)}")

            print()

def main():
    parser = argparse.ArgumentParser(
        description='Classify patent-paper pairs using Claude with batch/stream modes'
    )
    parser.add_argument('--mode', choices=['batch-submit', 'batch-retrieve', 'stream', 'stream-concurrent', 'list-batches'],
                       default='batch-submit', help='Mode of operation')
    parser.add_argument('--input', help='Input CSV file')
    parser.add_argument('--prompt', default='ppp_prompt.txt', help='Prompt file')
    parser.add_argument('--output', help='Output CSV file')
    parser.add_argument('--batch-id', help='Batch ID for retrieval')
    parser.add_argument('--model', default='claude-sonnet-4-5-20250929', help='Claude model to use')
    parser.add_argument('--start-row', type=int, default=0, help='Start from this row (0-indexed)')
    parser.add_argument('--limit', type=int, help='Limit number of rows to process')
    parser.add_argument('--max-concurrent', type=int, default=5, help='Maximum concurrent requests (default: 5)')

    args = parser.parse_args()

    try:
        classifier = PPPBatchClassifier(model=args.model)

        if args.mode == 'batch-submit':
            if not args.input:
                print("Error: --input required for batch-submit mode", file=sys.stderr)
                sys.exit(1)
            classifier.submit_batch(args.input, args.prompt, args.start_row, args.limit, args.output)

        elif args.mode == 'batch-retrieve':
            if not args.batch_id:
                print("Error: --batch-id required for batch-retrieve mode", file=sys.stderr)
                sys.exit(1)
            classifier.retrieve_batch_results(args.batch_id, args.output)

        elif args.mode == 'stream':
            if not args.input:
                print("Error: --input required for stream mode", file=sys.stderr)
                sys.exit(1)
            classifier.stream_classify(args.input, args.prompt, args.output, args.start_row, args.limit)

        elif args.mode == 'stream-concurrent':
            if not args.input:
                print("Error: --input required for stream-concurrent mode", file=sys.stderr)
                sys.exit(1)
            classifier.stream_classify_concurrent(args.input, args.prompt, args.output, args.start_row, args.limit, args.max_concurrent)

        elif args.mode == 'list-batches':
            classifier.list_batches()

    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
