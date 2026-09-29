#!/usr/bin/env python3
"""
Comprehensive script to classify patent-paper pairs using multiple LLM providers.
Supports Claude (Anthropic), Grok (xAI), and Kimi K2 (Moonshot) with batch submission, retrieval, and streaming modes.

Environment variables:
    ANTHROPIC_API_KEY - For Claude models
    GROK_API_KEY - For Grok models (from xAI)
    MOONSHOT_API_KEY - For Kimi K2 models (from Moonshot)

Usage:
    # Submit a batch with Claude (default)
    python classify_ppp_claude_batch.py --mode batch-submit --input input.csv --prompt prompt.txt

    # Submit a batch with Grok
    python classify_ppp_claude_batch.py --mode batch-submit --input input.csv --prompt prompt.txt --provider grok

    # Submit a batch with Kimi K2
    python classify_ppp_claude_batch.py --mode batch-submit --input input.csv --prompt prompt.txt --provider kimi --model kimi-k2

    # Retrieve batch results
    python classify_ppp_claude_batch.py --mode batch-retrieve --batch-id <batch_id>

    # Stream results concurrently (fast and immediate feedback, recommended)
    python classify_ppp_claude_batch.py --mode stream-concurrent --input input.csv --prompt prompt.txt --max-concurrent 10

    # Use specific model
    python classify_ppp_claude_batch.py --mode stream-concurrent --input input.csv --prompt prompt.txt --provider kimi --model kimi-k2

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
    # Anthropic Claude models
    "claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0},
    "claude-opus-4-1": {"input": 15.0, "output": 75.0},
    "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
    # xAI Grok models (2M token context window)
    "grok-4": {"input": 3.0, "output": 9.0},
    "grok-4-fast-reasoning": {"input": 5.0, "output": 15.0},
    "grok-4-fast-non-reasoning": {"input": 5.0, "output": 15.0},
    # Moonshot Kimi K2 models
    "kimi-k2": {"input": 0.15, "output": 0.45},
}

class PPPBatchClassifier:
    def __init__(self, model="claude-sonnet-4-5-20250929", provider="claude"):
        """Initialize the classifier with specified model and provider.

        Args:
            model: Model name (e.g., 'claude-sonnet-4-5-20250929' or 'grok-3')
            provider: LLM provider ('claude' or 'grok')
        """
        self.provider = provider
        self.model = model

        if provider == "claude":
            if not os.getenv('ANTHROPIC_API_KEY'):
                raise ValueError(
                    "ANTHROPIC_API_KEY not found. Please add it to ~/.env file with:\n"
                    "  ANTHROPIC_API_KEY=your_api_key_here\n"
                    "Or set it as an environment variable."
                )
            self.client = Anthropic()

        elif provider == "grok":
            if not os.getenv('GROK_API_KEY'):
                raise ValueError(
                    "GROK_API_KEY not found. Please add it to ~/.env file with:\n"
                    "  GROK_API_KEY=your_grok_api_key_here\n"
                    "Or set it as an environment variable.\n"
                    "Get your key from https://console.x.ai"
                )
            try:
                from openai import OpenAI
                self.client = OpenAI(
                    api_key=os.getenv('GROK_API_KEY'),
                    base_url="https://api.x.ai/v1"
                )
            except ImportError:
                raise ImportError(
                    "OpenAI SDK required for Grok support. Install with:\n"
                    "  pip install openai"
                )
        elif provider == "kimi":
            if not os.getenv('MOONSHOT_API_KEY'):
                raise ValueError(
                    "MOONSHOT_API_KEY not found. Please add it to ~/.env file with:\n"
                    "  MOONSHOT_API_KEY=your_moonshot_api_key_here\n"
                    "Or set it as an environment variable.\n"
                    "Get your key from https://platform.moonshot.ai"
                )
            try:
                from openai import OpenAI
                self.client = OpenAI(
                    api_key=os.getenv('MOONSHOT_API_KEY'),
                    base_url="https://api.moonshot.ai/v1"
                )
            except ImportError:
                raise ImportError(
                    "OpenAI SDK required for Kimi K2 support. Install with:\n"
                    "  pip install openai"
                )
        else:
            raise ValueError(f"Unsupported provider: {provider}. Use 'claude', 'grok', or 'kimi'")

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
        message = f"""{prompt}

Paper Information:
- Title: {papertitle}
- Abstract: {paper_abstract}

Patent Information:
- Patent ID: {patent_id}
- Title: {patent_title}
- Abstract: {patent_abstract}"""

        # Only include original response if it's not empty
        if original_response and original_response.strip():
            message += f"\n\nOriginal Response: {original_response}"

        return message

    def _parse_response(self, response_text, magid, patent_id, original_response):
        """Parse JSON response from Claude."""
        try:
            # Try to extract JSON from the response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                parsed_json = json.loads(json_str)
                # Always include magid and patent_id in the result
                result = {
                    "magid": magid,
                    "patent_id": patent_id,
                }
                # Add the parsed assessment and any other fields from Claude
                result.update(parsed_json)
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
        df = pd.read_csv(input_file, low_memory=False)
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
        start_time = time.time()
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
        input_tokens = 0
        output_tokens = 0

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
                    # Track token usage
                    if hasattr(result.result, 'message') and hasattr(result.result.message, 'usage'):
                        input_tokens += result.result.message.usage.input_tokens
                        output_tokens += result.result.message.usage.output_tokens
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
            # Only keep the columns we need
            columns_to_keep = ['magid', 'patent_id', 'assessment']
            df_results = df_results[[col for col in columns_to_keep if col in df_results.columns]]
            df_results.to_csv(output_file, index=False)
            logger.info(f"Results saved to {output_file}")
            logger.info(f"Total results: {len(results)}")

            # Calculate cost and elapsed time
            total_cost = self._calculate_cost(input_tokens, output_tokens)
            elapsed_time = time.time() - start_time

            # Update batch tracking
            batch_info['status'] = 'completed'
            batch_info['output_file'] = output_file
            batch_info['completed_at'] = datetime.now().isoformat()
            batch_info['results_count'] = len(results)
            batch_info['input_tokens'] = input_tokens
            batch_info['output_tokens'] = output_tokens
            batch_info['total_cost'] = total_cost
            self._save_batch_tracking()

            print(f"\n✓ Results retrieved: {output_file}")
            print(f"  Total results: {len(results)}")
            print(f"  Input tokens: {input_tokens:,}")
            print(f"  Output tokens: {output_tokens:,}")
            print(f"  Total cost: ${total_cost:.4f}")
            print(f"  Processing time: {elapsed_time:.2f}s")
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
        df = pd.read_csv(input_file, low_memory=False)

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
            writer = csv.DictWriter(outfile, fieldnames=['magid', 'patent_id', 'assessment'])

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

                    # Call API (provider-specific)
                    if self.provider == "claude":
                        response = self.client.messages.create(
                            model=self.model,
                            max_tokens=500,
                            messages=[
                                {"role": "user", "content": message_content}
                            ]
                        )
                        input_tokens += response.usage.input_tokens
                        output_tokens += response.usage.output_tokens
                        response_text = response.content[0].text.strip()
                    else:  # grok or kimi (both use OpenAI-compatible API)
                        response = self.client.chat.completions.create(
                            model=self.model,
                            max_tokens=500,
                            messages=[
                                {"role": "user", "content": message_content}
                            ]
                        )
                        if response.usage:
                            input_tokens += response.usage.prompt_tokens
                            output_tokens += response.usage.completion_tokens
                        response_text = response.choices[0].message.content.strip()
                    result = self._parse_response(response_text, magid, patent_id, original_response)

                    # Write result (only 3 columns)
                    output_row = {
                        'magid': result.get('magid', magid),
                        'patent_id': result.get('patent_id', patent_id),
                        'assessment': result.get('assessment', '')
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
                        'assessment': ''
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

    def stream_classify_concurrent(self, input_file, prompt_file, output_file=None, start_row=0, limit=None, max_concurrent=5, checkpoint_interval=1000):
        """
        Classify pairs using concurrent streaming mode with incremental checkpointing.
        Processes multiple requests in parallel and saves results every checkpoint_interval pairs.
        """
        start_time = time.time()
        logger.info(f"Loading data from {input_file}...")
        df = pd.read_csv(input_file, low_memory=False)

        if limit:
            df = df.iloc[:limit]

        if not output_file:
            output_file = 'ppp_claude_assessments.csv'

        prompt = self.load_prompt(prompt_file)

        logger.info(f"Starting concurrent processing with checkpoints every {checkpoint_interval} pairs...")

        # Run async processing with checkpoint callback
        results, token_usage = asyncio.run(self._async_process_concurrent_with_checkpoints(
            df, prompt, start_row, max_concurrent, output_file, checkpoint_interval
        ))

        # Final summary report
        if results is not None:
            total_cost = self._calculate_cost(token_usage['input'], token_usage['output'])
            elapsed_time = time.time() - start_time

            logger.info(f"Done! Processed {results} pairs. Results saved to {output_file}")
            print(f"\n✓ Classification complete: {output_file}")
            print(f"  Total results: {results}")
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
        # Create async client based on provider
        if self.provider == "claude":
            async_client = AsyncAnthropic()
        elif self.provider == "grok":
            from openai import AsyncOpenAI
            async_client = AsyncOpenAI(
                api_key=os.getenv('GROK_API_KEY'),
                base_url="https://api.x.ai/v1"
            )
        elif self.provider == "kimi":
            from openai import AsyncOpenAI
            async_client = AsyncOpenAI(
                api_key=os.getenv('MOONSHOT_API_KEY'),
                base_url="https://api.moonshot.ai/v1"
            )
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

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

                    # Call API asynchronously (provider-specific)
                    if self.provider == "claude":
                        response = await async_client.messages.create(
                            model=self.model,
                            max_tokens=500,
                            messages=[
                                {"role": "user", "content": message_content}
                            ]
                        )
                        token_usage['input'] += response.usage.input_tokens
                        token_usage['output'] += response.usage.output_tokens
                        response_text = response.content[0].text.strip()
                    else:  # grok or kimi (both use OpenAI-compatible API)
                        response = await async_client.chat.completions.create(
                            model=self.model,
                            max_tokens=500,
                            messages=[
                                {"role": "user", "content": message_content}
                            ]
                        )
                        if response.usage:
                            token_usage['input'] += response.usage.prompt_tokens
                            token_usage['output'] += response.usage.completion_tokens
                        response_text = response.choices[0].message.content.strip()
                    result = self._parse_response(response_text, magid, patent_id, original_response)

                    row_number = idx + 2  # Account for header
                    logger.info(f"Completed row {row_number}/{len(df)} (magid: {magid}, patent_id: {patent_id})")

                    return {
                        'magid': result.get('magid', magid),
                        'patent_id': result.get('patent_id', patent_id),
                        'assessment': result.get('assessment', '')
                    }
                except Exception as e:
                    logger.error(f"Error processing row {idx}: {str(e)}")
                    return {
                        'magid': row.get('magid', ''),
                        'patent_id': row.get('patent_id', ''),
                        'assessment': ''
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

    async def _async_process_concurrent_with_checkpoints(self, df, prompt, start_row, max_concurrent, output_file, checkpoint_interval):
        """Process rows concurrently with incremental checkpointing."""
        # Create async client based on provider
        if self.provider == "claude":
            async_client = AsyncAnthropic()
        elif self.provider == "grok":
            from openai import AsyncOpenAI
            async_client = AsyncOpenAI(
                api_key=os.getenv('GROK_API_KEY'),
                base_url="https://api.x.ai/v1"
            )
        elif self.provider == "kimi":
            from openai import AsyncOpenAI
            async_client = AsyncOpenAI(
                api_key=os.getenv('MOONSHOT_API_KEY'),
                base_url="https://api.moonshot.ai/v1"
            )
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

        semaphore = asyncio.Semaphore(max_concurrent)
        token_usage = {'input': 0, 'output': 0}
        processed_count = 0

        # Initialize output file with header
        with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=['magid', 'patent_id', 'assessment'])
            writer.writeheader()

        logger.info(f"Starting concurrent processing with checkpoints every {checkpoint_interval} pairs...")

        async def process_row(idx, row):
            """Process a single row with semaphore limiting."""
            async with semaphore:
                try:
                    magid = int(row['magid'])
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

                    # Call API asynchronously (provider-specific)
                    if self.provider == "claude":
                        response = await async_client.messages.create(
                            model=self.model,
                            max_tokens=500,
                            messages=[
                                {"role": "user", "content": message_content}
                            ]
                        )
                        token_usage['input'] += response.usage.input_tokens
                        token_usage['output'] += response.usage.output_tokens
                        response_text = response.content[0].text.strip()
                    else:  # grok or kimi (both use OpenAI-compatible API)
                        response = await async_client.chat.completions.create(
                            model=self.model,
                            max_tokens=500,
                            messages=[
                                {"role": "user", "content": message_content}
                            ]
                        )
                        if response.usage:
                            token_usage['input'] += response.usage.prompt_tokens
                            token_usage['output'] += response.usage.completion_tokens
                        response_text = response.choices[0].message.content.strip()

                    result = self._parse_response(response_text, magid, patent_id, original_response)
                    row_number = idx + 2  # Account for header
                    logger.info(f"Completed row {row_number}/{len(df)} (magid: {magid}, patent_id: {patent_id})")

                    return {
                        'magid': result.get('magid', magid),
                        'patent_id': result.get('patent_id', patent_id),
                        'assessment': result.get('assessment', '')
                    }
                except Exception as e:
                    logger.error(f"Error processing row {idx}: {str(e)}")
                    return {
                        'magid': row.get('magid', ''),
                        'patent_id': row.get('patent_id', ''),
                        'assessment': ''
                    }

        # Process rows in batches
        batch_results = []
        for idx, row in df.iterrows():
            if idx < start_row:
                continue

            # Create task for this row
            task = process_row(idx, row)
            batch_results.append(asyncio.create_task(task))

            # If batch is full or we're at the end, process the batch and save checkpoint
            if len(batch_results) >= checkpoint_interval or idx == len(df) - 1:
                logger.info(f"Processing batch with {len(batch_results)} results...")
                results = await asyncio.gather(*batch_results)

                # Write batch results to CSV (append mode)
                with open(output_file, 'a', newline='', encoding='utf-8') as outfile:
                    writer = csv.DictWriter(outfile, fieldnames=['magid', 'patent_id', 'assessment'])
                    for result in results:
                        output_row = {
                            'magid': result.get('magid', ''),
                            'patent_id': result.get('patent_id', ''),
                            'assessment': result.get('assessment', '')
                        }
                        writer.writerow(output_row)

                processed_count += len(results)
                checkpoint_num = processed_count // checkpoint_interval
                logger.info(f"✓ Checkpoint {checkpoint_num}: Saved {processed_count} total results to {output_file}")
                print(f"✓ Checkpoint: Processed {processed_count} pairs so far")

                batch_results = []

        return processed_count, token_usage

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
        description='Classify patent-paper pairs using Claude, Grok, or Kimi K2 with batch/stream modes'
    )
    parser.add_argument('--mode', choices=['batch-submit', 'batch-retrieve', 'stream', 'stream-concurrent', 'list-batches'],
                       default='batch-submit', help='Mode of operation')
    parser.add_argument('--provider', choices=['claude', 'grok', 'kimi'], default='claude',
                       help='LLM provider (claude, grok, or kimi, default: claude)')
    parser.add_argument('--input', help='Input CSV file')
    parser.add_argument('--prompt', default='ppp_prompt.txt', help='Prompt file')
    parser.add_argument('--output', help='Output CSV file')
    parser.add_argument('--batch-id', help='Batch ID for retrieval')
    parser.add_argument('--model', default='claude-sonnet-4-5-20250929',
                       help='Model to use (default: claude-sonnet-4-5-20250929 for Claude, grok-4-fast-non-reasoning for Grok)')
    parser.add_argument('--start-row', type=int, default=0, help='Start from this row (0-indexed)')
    parser.add_argument('--limit', type=int, help='Limit number of rows to process')
    parser.add_argument('--max-concurrent', type=int, default=5, help='Maximum concurrent requests (default: 5)')
    parser.add_argument('--checkpoint-interval', type=int, default=1000, help='Save checkpoint every N pairs (default: 1000)')

    args = parser.parse_args()

    # Set default model based on provider if not overridden
    if args.model == 'claude-sonnet-4-5-20250929':
        if args.provider == 'grok':
            args.model = 'grok-4-fast-non-reasoning'
        elif args.provider == 'kimi':
            args.model = 'kimi-k2'

    try:
        classifier = PPPBatchClassifier(model=args.model, provider=args.provider)

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
            classifier.stream_classify_concurrent(args.input, args.prompt, args.output, args.start_row, args.limit, args.max_concurrent, args.checkpoint_interval)

        elif args.mode == 'list-batches':
            classifier.list_batches()

    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
