# Quick Start: Batch Classification

## 1. Install Dependencies

```bash
pip install -r requirements_batch.txt
```

## 2. Set API Key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

## 3. Prepare Input

Make sure your CSV has these columns:
- `magid`, `patent_id`, `papertitle`, `patent_title`, `paper_abstract`, `patent_abstract`, `response`

## 4. Create/Update Prompt

Ensure `ppp_prompt.txt` exists with your classification prompt.

## 5. Submit Batch

For a large file (recommended):
```bash
python classify_ppp_claude_batch.py --mode batch-submit \
  --input your_data.csv \
  --prompt ppp_prompt.txt
```

Or for real-time results on smaller files:
```bash
python classify_ppp_claude_batch.py --mode stream \
  --input your_data.csv \
  --prompt ppp_prompt.txt
```

## 6. Check Status

```bash
python classify_ppp_claude_batch.py --mode list-batches
```

## 7. Retrieve Results

Once batch processing is complete:
```bash
python classify_ppp_claude_batch.py --mode batch-retrieve --batch-id <batch_id>
```

Results will be saved to CSV automatically!

---

For detailed documentation, see: **BATCH_CLASSIFY_README.md**
