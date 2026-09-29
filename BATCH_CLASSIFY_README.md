# Patent-Paper Pair Classification with Batching

`classify_ppp_claude_batch.py` is a comprehensive tool for classifying patent-paper pairs using Claude's API. It supports three modes of operation:

1. **Batch Submission** - Submit large jobs asynchronously (recommended for large files)
2. **Batch Retrieval** - Retrieve results from submitted batches
3. **Streaming** - Real-time classification (slower, immediate feedback)
4. **Batch Tracking** - Monitor the status of all submitted batches

## Requirements

```bash
pip install anthropic pandas
```

Set the environment variable:
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

## Quick Start

### 1. Batch Mode (Recommended for Large Files)

**Submit a batch:**
```bash
python classify_ppp_claude_batch.py --mode batch-submit \
  --input your_data.csv \
  --prompt ppp_prompt.txt \
  --output results.csv
```

This will:
- Read your CSV file
- Prepare all requests
- Submit them to the Anthropic Batch API
- Return a **Batch ID**
- Track the batch locally in `batch_tracking.json`

**Example output:**
```
✓ Batch submitted: batch_67890abcdef
  Requests: 5000
  Check status with: python classify_ppp_claude_batch.py --mode list-batches
```

**Check batch status:**
```bash
python classify_ppp_claude_batch.py --mode list-batches
```

**Retrieve results when complete:**
```bash
python classify_ppp_claude_batch.py --mode batch-retrieve --batch-id batch_67890abcdef
```

Results will be saved to the specified output file (or `ppp_claude_assessments_{batch_id}.csv` by default).

### 2. Streaming Mode (Real-time Results)

For smaller datasets or when you need immediate feedback:
```bash
python classify_ppp_claude_batch.py --mode stream \
  --input your_data.csv \
  --prompt ppp_prompt.txt \
  --output results.csv
```

**Resume from a specific row:**
```bash
python classify_ppp_claude_batch.py --mode stream \
  --input your_data.csv \
  --prompt ppp_prompt.txt \
  --start-row 100
```

**Process only first N rows:**
```bash
python classify_ppp_claude_batch.py --mode stream \
  --input your_data.csv \
  --prompt ppp_prompt.txt \
  --limit 1000
```

### 3. List All Batches

```bash
python classify_ppp_claude_batch.py --mode list-batches
```

Shows:
- Batch IDs
- Status (submitted/completed)
- Number of requests
- Output file locations
- Current API status and progress

## Input CSV Requirements

Your input CSV must have these columns:
- `magid` - Paper ID
- `patent_id` - Patent ID
- `papertitle` - Title of the paper
- `patent_title` - Title of the patent
- `paper_abstract` - Abstract of the paper
- `patent_abstract` - Abstract of the patent
- `response` - Original classification response

## Output Format

Results are saved as CSV with columns:
- `magid` - Paper ID
- `patent_id` - Patent ID
- `original_response` - Original response text
- `assessment` - Classification grade (A/B/C/D)
- `error` - Any error encountered (empty if successful)

## Batch Tracking

All submitted batches are tracked in `batch_tracking.json`:

```json
{
  "batches": [
    {
      "batch_id": "batch_67890abcdef",
      "submitted_at": "2024-11-07T15:30:45.123456",
      "input_file": "your_data.csv",
      "output_file": "results.csv",
      "num_requests": 5000,
      "model": "claude-3-5-sonnet-20241022",
      "status": "submitted"
    }
  ]
}
```

## Advanced Options

### Use Different Model

```bash
python classify_ppp_claude_batch.py --mode batch-submit \
  --input your_data.csv \
  --prompt ppp_prompt.txt \
  --model claude-opus-4-1-20250805
```

### Process Large File in Chunks

Submit multiple batches for a large file:

```bash
# Batch 1: Rows 0-50000
python classify_ppp_claude_batch.py --mode batch-submit \
  --input large_file.csv \
  --prompt ppp_prompt.txt \
  --start-row 0 \
  --limit 50000 \
  --output results_part1.csv

# Batch 2: Rows 50000-100000
python classify_ppp_claude_batch.py --mode batch-submit \
  --input large_file.csv \
  --prompt ppp_prompt.txt \
  --start-row 50000 \
  --limit 50000 \
  --output results_part2.csv
```

## Batch API Benefits

- **Cost Effective**: Batch API offers 50% discount compared to synchronous API
- **Asynchronous**: Submit and check back later (batches usually complete within hours)
- **Scalable**: Can process thousands of requests efficiently
- **Reliable**: Built-in retry logic and error handling
- **Trackable**: Full audit trail of all submissions

## Typical Batch Processing Timeline

1. **Submit** (< 1 minute)
   - Prepare requests, submit to API
   - Receive batch ID

2. **Processing** (minutes to hours)
   - Depends on batch size and current load
   - You can close the terminal and come back later

3. **Retrieve** (< 1 minute)
   - Download results and save to CSV
   - Update tracking file

## Troubleshooting

### Batch not completing
Check the API status:
```bash
python classify_ppp_claude_batch.py --mode list-batches
```

### API Key not found
Ensure environment variable is set:
```bash
echo $ANTHROPIC_API_KEY
```

### CSV column mismatch
Verify your CSV has all required columns. Check with:
```bash
python -c "import pandas as pd; print(pd.read_csv('your_data.csv').columns.tolist())"
```

### Resume streaming from specific row
If a streaming job was interrupted:
```bash
python classify_ppp_claude_batch.py --mode stream \
  --input your_data.csv \
  --prompt ppp_prompt.txt \
  --start-row 250
```

## Example Workflow

### Scenario: Process 500,000 patent-paper pairs

```bash
# 1. Submit batch (takes ~1 minute)
python classify_ppp_claude_batch.py --mode batch-submit \
  --input all_pairs.csv \
  --prompt ppp_prompt.txt \
  --output all_results.csv
# Output: Batch ID: batch_xyz123abc

# 2. Wait for processing (typically 2-4 hours for 500k pairs)

# 3. Check status periodically
python classify_ppp_claude_batch.py --mode list-batches

# 4. Once complete, retrieve results
python classify_ppp_claude_batch.py --mode batch-retrieve --batch-id batch_xyz123abc

# Results saved to: all_results.csv
```

## Comparing Batch vs Streaming

| Feature | Batch | Streaming |
|---------|-------|-----------|
| Speed | Asynchronous (hours) | Synchronous (seconds/pair) |
| Cost | 50% discount | Full price |
| Best for | Large datasets (1000+) | Small datasets (<100) |
| Latency | High initial, low per-request | Low latency throughout |
| Monitoring | Check periodically | Real-time progress |
| Resumability | Auto-tracked | Manual (--start-row) |

## API Rate Limits

- **Batch API**: No rate limits (asynchronous)
- **Streaming API**: Standard rate limits apply (50,000 requests/minute for Sonnet)

## Support

For issues or questions, check:
- `batch_tracking.json` - Track all submissions
- Anthropic API documentation: https://docs.anthropic.com/
- Error messages in logs for debugging
