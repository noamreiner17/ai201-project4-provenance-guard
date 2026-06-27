# ai201-project4-provenance-guard

## Project Overview

Provenance Guard is a backend service that helps determine whether a piece of text is likely AI-generated or human-written. Instead of making a simple yes/no decision, the system combines multiple detection signals to produce a confidence score and a transparency label. The goal is to provide useful information to readers while allowing creators to appeal decisions that may be incorrect.

Every classification is stored in a structured audit log, and creators can appeal decisions they believe are incorrect.

---

## Architecture Overview

When a creator submits text, the request is first received by the `POST /submit` API endpoint and validated. The text is then analyzed by two independent detection signals:

1. **LLM-Based Classification (Groq)** – Uses an LLM to estimate whether the writing appears AI-generated or human-written based on semantic patterns and writing style.
2. **Stylometric Analysis** – Measures statistical writing characteristics such as sentence length variation, vocabulary diversity, and punctuation usage.

The outputs from both signals are combined into a single confidence score. Based on this score, the system generates one of three transparency labels:

- **Likely AI-Generated**
- **Likely Human-Written**
- **Uncertain Result**

The final decision, confidence score, individual signal scores, and metadata are stored in the audit log before the API returns the response to the user.

If a creator disagrees with the decision, they may submit an appeal through the `POST /appeal` endpoint. The appeal is linked to the original submission, its status changes to **Under Review**, and the appeal is recorded in the audit log.

### Architecture Diagram

```text
                   POST /submit
                         |
                         v
                 Validate Request
                         |
          +--------------+--------------+
          |                             |
          v                             v
    Groq LLM Signal          Stylometric Analysis
          |                             |
          +--------------+--------------+
                         |
                         v
              Confidence Scoring
                         |
                         v
              Transparency Label
                         |
                         v
                Structured Audit Log
                         |
                         v
                JSON API Response


                   POST /appeal
                         |
                         v
                 Update Status
                "Under Review"
                         |
                         v
                Structured Audit Log
                         |
                         v
                   JSON Response
```

---

## Setup

1. Create / activate a virtual environment and install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Provide a Groq API key in a `.env` file in the project root:

   ```text
   GROQ_API_KEY=your_key_here
   ```

3. Run the app:

   ```bash
   python app.py
   ```

   The server starts on `http://localhost:5000`.

---

## Detection Signals

Each signal produces a normalized score between **0.0** and **1.0**:

- **0.0 = Strongly Human**
- **1.0 = Strongly AI**

### Signal 1 — Groq LLM

The Groq API analyzes overall writing style, sentence coherence, vocabulary and word choice, consistency of tone, and common AI writing patterns. It returns a single confidence score between 0.0 and 1.0.

**Limitations:** can misclassify polished human writing, and can be fooled by heavily edited AI-generated text.

### Signal 2 — Stylometric Analysis

The backend computes three measurable writing statistics, normalizes each to [0.0, 1.0] where higher = more AI-like, and averages them:

- **Sentence length variance** — uniform sentence lengths read as AI-like; varied lengths read as human.
- **Type-Token Ratio (vocabulary diversity)** — repetitive vocabulary reads as AI-like; diverse vocabulary reads as human.
- **Punctuation frequency** — steady, structural punctuation reads as polished/AI-like.

```text
Stylometric Score = (variance_score + ttr_score + punctuation_score) / 3
```

**Limitations:** poems and song lyrics may produce misleading statistics; very short text does not contain enough information for reliable analysis; technical writing may appear overly consistent despite being human-written. In practice this signal is the weaker of the two on short inputs (Type-Token Ratio is naturally high at short lengths and barely discriminates), so it tends to nudge the Groq verdict rather than drive it.

---

## Confidence Scoring

Both signals contribute equally:

```text
Final Confidence = (Groq Score + Stylometric Score) / 2
```

The resulting confidence score ranges from **0.0** to **1.0** and maps to an attribution and a transparency label:

| Confidence Score | Attribution     | Transparency Label    |
| ---------------: | --------------- | --------------------- |
|      0.00 – 0.25 | `human`         | Likely Human-Written  |
|      0.26 – 0.45 | `likely_human`  | Likely Human-Written  |
|      0.46 – 0.54 | `uncertain`     | Uncertain Result      |
|      0.55 – 0.75 | `likely_ai`     | Likely AI-Generated   |
|      0.76 – 1.00 | `ai`            | Likely AI-Generated   |

Because false positives are more harmful than false negatives, the system prefers returning **Uncertain** rather than making an incorrect high-confidence prediction.

---

## API Endpoints

### `POST /submit`

Rate limited to 10 requests/minute and 100/day.

**Request**

```json
{
  "creator_id": "test-user-1",
  "text": "Sample writing..."
}
```

**Response**

```json
{
  "content_id": "72387cb2-17ac-4193-b91d-05819e359be2",
  "attribution": "likely_ai",
  "confidence": 0.6095,
  "label": "Likely AI-Generated",
  "llm_score": 0.8,
  "stylometric_score": 0.4189
}
```

Returns HTTP 400 if `text` or `creator_id` is missing or invalid.

### `POST /appeal`

**Request**

```json
{
  "content_id": "72387cb2-17ac-4193-b91d-05819e359be2",
  "creator_reasoning": "I wrote this myself."
}
```

**Response**

```json
{
  "content_id": "72387cb2-17ac-4193-b91d-05819e359be2",
  "status": "under_review",
  "message": "Your appeal was received and is under review."
}
```

### `GET /log`

Returns the most recent structured audit log entries as JSON.

```json
{ "entries": [ /* ... */ ] }
```

---

## Audit Log

Every submission and appeal writes a structured JSON entry (one JSON object per line) to `audit_log.jsonl`. A submission entry looks like:

```json
{
  "content_id": "72387cb2-17ac-4193-b91d-05819e359be2",
  "creator_id": "u1",
  "attribution": "likely_ai",
  "confidence": 0.6095,
  "llm_score": 0.8,
  "stylometric_score": 0.4189,
  "status": "classified",
  "timestamp": "2026-06-27T03:22:38.133375+00:00"
}
```

---

## Example Results

Tested across the confidence range with both signal scores recorded:

| Input                 | Groq | Stylometric | Confidence | Label                |
| --------------------- | ---: | ----------: | ---------: | -------------------- |
| Clearly AI-generated  | 0.80 |        0.42 |     0.6095 | Likely AI-Generated  |
| Clearly human-written | 0.20 |        0.08 |     0.1412 | Likely Human-Written |
| Formal human writing  | 0.80 |        0.26 |     0.5302 | Uncertain Result     |
| Lightly edited AI     | 0.40 |        0.34 |     0.3676 | Likely Human-Written |

The formal-human case landing in **Uncertain** is expected: formal, consistently structured prose triggers AI-leaning signals, and the system deliberately declines to make a high-confidence call rather than risk a false positive.

### Example request

```bash
curl -s -X POST http://localhost:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"text": "The sun dipped below the horizon, painting the sky in hues of amber and rose. I sat on the porch, coffee in hand, watching the neighborhood slowly go quiet.", "creator_id": "test-user-1"}' | python -m json.tool
```
